from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Iterator, Mapping

from ai_contract import (
    AnalysisRequest,
    build_analysis_prompt,
    build_analysis_schema,
    parse_analysis_response,
)
from portfolio import AIAdvice, AIModelFailure


MODEL = "gpt-6-luna"
REASONING_EFFORT = "medium"
MAX_OUTPUT_BYTES = 64 * 1024
CLEANUP_RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4)


@dataclass(frozen=True, slots=True)
class CodexCliSettings:
    executable: str | None = None
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 300
        ):
            raise ValueError("timeout_seconds must be an integer from 1 to 300")


def analyze_with_codex(request: AnalysisRequest, settings: CodexCliSettings) -> AIAdvice:
    started = time.monotonic()
    deadline = started + settings.timeout_seconds
    stage = "temp_setup"
    run_directory: Path | None = None
    pending_result: AIAdvice | None = None
    cleanup_reserve = min(2.0, settings.timeout_seconds * 0.1)
    executable = _resolve_executable(settings)
    if not executable:
        return _failure(request, "executable_not_found", started)

    try:
        with _temporary_directory_with_cleanup_retry(
            cleanup_deadline=deadline,
            prefix="codex-analysis-",
            dir=str(_temporary_root()),
        ) as temporary_directory:
            run_directory = Path(temporary_directory)
            codex_home = run_directory / "codex-home"
            codex_home.mkdir()
            stage = "auth_copy"
            _copy_authentication_file(codex_home)
            schema_path = run_directory / "response-schema.json"
            output_path = run_directory / "final-response.json"
            stage = "schema_write"
            schema_path.write_text(
                json.dumps(build_analysis_schema(request), separators=(",", ":")),
                encoding="utf-8",
            )
            command = _build_command(executable, schema_path, output_path)
            stage = "process_spawn"
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                cwd=str(run_directory),
                env=_child_environment(codex_home),
                text=True,
                encoding="utf-8",
                errors="strict",
            )
            stage = "process_communication"
            try:
                communicate_timeout = max(
                    0.01,
                    deadline - time.monotonic() - cleanup_reserve,
                )
                process.communicate(
                    input=build_analysis_prompt(request),
                    timeout=communicate_timeout,
                )
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process, deadline)
                _terminate_orphaned_descendants(process, deadline)
                failure = _failure(request, "timeout", started)
                pending_result = failure
                stage = "cleanup"
                return failure
            except (OSError, subprocess.SubprocessError):
                _terminate_process_tree(process, deadline)
                _terminate_orphaned_descendants(process, deadline)
                failure = _failure(request, "process_communication_error", started)
                pending_result = failure
                stage = "cleanup"
                return failure

            _terminate_orphaned_descendants(process, deadline)
            if process.returncode != 0:
                failure = _failure(request, "process_failed", started)
                pending_result = failure
                stage = "cleanup"
                return failure
            stage = "output_read"
            try:
                response = _read_bounded_output(output_path)
                targets, action, rationale = parse_analysis_response(response, request)
            except FileNotFoundError:
                failure = _failure(request, "output_missing", started)
                pending_result = failure
                stage = "cleanup"
                return failure
            except UnicodeDecodeError:
                failure = _failure(request, "output_encoding", started)
                pending_result = failure
                stage = "cleanup"
                return failure
            except _OutputTooLarge:
                failure = _failure(request, "output_too_large", started)
                pending_result = failure
                stage = "cleanup"
                return failure
            except ValueError:
                failure = _failure(request, "output_invalid", started)
                pending_result = failure
                stage = "cleanup"
                return failure

            stage = "cleanup"
            pending_result = AIAdvice(
                targets=targets,
                action=action,
                rationale=rationale,
                model_used=MODEL,
                provider="codex_cli",
                reasoning_effort=REASONING_EFFORT,
                duration_seconds=max(0.0, time.monotonic() - started),
            )
            return pending_result
    except (OSError, subprocess.SubprocessError) as error:
        cleanup_error = "cleanup_error"
        if stage == "cleanup" and pending_result is not None and run_directory is not None:
            workspace_state = "unknown"
            try:
                run_directory.stat()
            except FileNotFoundError:
                return pending_result
            except OSError:
                pass
            else:
                workspace_state = "retained"
            cleanup_error = _cleanup_failure_type(error, workspace_state)
        stage_errors = {
            "temp_setup": "temp_setup_error",
            "auth_copy": "auth_copy_error",
            "schema_write": "schema_write_error",
            "process_spawn": "process_spawn_error",
            "process_communication": "process_communication_error",
            "output_read": "output_read_error",
            "cleanup": cleanup_error,
        }
        return _failure(request, stage_errors[stage], started)


def _resolve_executable(settings: CodexCliSettings) -> str | None:
    """Resolve Codex from config, PATH, then the observed Windows app install."""
    if settings.executable:
        return settings.executable

    executable = shutil.which("codex")
    if executable:
        return executable

    if os.name != "nt":
        return None

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    install_root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
    candidates: list[Path] = []
    try:
        for version_directory in install_root.iterdir():
            try:
                directory_mode = version_directory.stat().st_mode
            except FileNotFoundError:
                # The installation changed during enumeration; do not guess.
                return None
            if not stat.S_ISDIR(directory_mode):
                continue

            candidate = version_directory / "codex.exe"
            try:
                candidate_mode = candidate.stat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISREG(candidate_mode):
                candidates.append(candidate)
    except OSError:
        # Unlike Path.glob, explicit stat calls preserve access failures.
        return None

    # The app's version directory is opaque; multiple binaries are ambiguous.
    if len(candidates) != 1:
        return None
    return str(candidates[0])


@contextmanager
def _temporary_directory_with_cleanup_retry(
    *, cleanup_deadline: float, **kwargs: object
) -> Iterator[str]:
    temporary_directory = tempfile.TemporaryDirectory(**kwargs)
    temporary_path = temporary_directory.__enter__()
    try:
        yield temporary_path
    finally:
        retry_delays = iter(CLEANUP_RETRY_DELAYS_SECONDS)
        while True:
            try:
                temporary_directory.__exit__(None, None, None)
            except OSError as error:
                if not _is_cleanup_resource_busy(error):
                    raise
                try:
                    retry_delay = next(retry_delays)
                except StopIteration:
                    raise error
                remaining = cleanup_deadline - time.monotonic()
                if remaining < retry_delay:
                    raise error
                time.sleep(retry_delay)
                if time.monotonic() >= cleanup_deadline:
                    raise error
            else:
                break


class _OutputTooLarge(ValueError):
    pass


def _is_cleanup_resource_busy(error: BaseException) -> bool:
    winerror = getattr(error, "winerror", None)
    if winerror is not None:
        return winerror in (32, 33)
    error_number = error.errno if isinstance(error, OSError) else None
    return error_number == errno.EBUSY


def _cleanup_failure_type(error: BaseException, workspace_state: str) -> str:
    winerror = getattr(error, "winerror", None)
    error_number = error.errno if isinstance(error, OSError) else None
    if winerror == 32:
        return "cleanup_sharing_violation"
    if winerror == 33:
        return "cleanup_lock_violation"
    if winerror == 5:
        return "cleanup_permission_error"
    if winerror is None and error_number == errno.EBUSY:
        return "cleanup_resource_busy"
    if winerror is None and error_number in (errno.EACCES, errno.EPERM):
        return "cleanup_permission_error"
    if workspace_state == "retained":
        return "cleanup_workspace_retained"
    if workspace_state == "unknown":
        return "cleanup_state_unknown"
    return "cleanup_error"


def _build_command(executable: str, schema_path: Path, output_path: Path) -> list[str]:
    command = [
        executable,
        "exec",
        "--model",
        MODEL,
        "--config",
        'model_reasoning_effort="medium"',
        "--config",
        "features.shell_tool=false",
        "--config",
        "features.apps=false",
        "--config",
        "features.hooks=false",
        "--config",
        "features.multi_agent=false",
        "--config",
        "features.remote_plugin=false",
        "--config",
        'web_search="disabled"',
        "--config",
        'windows.sandbox="mxc"',
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--json",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "-",
    ]
    return command


def _copy_authentication_file(codex_home: Path) -> None:
    configured_home = os.environ.get("CODEX_HOME")
    source_home = Path(configured_home) if configured_home else Path.home() / ".codex"
    source_auth = source_home / "auth.json"
    if source_auth.is_file():
        shutil.copyfile(source_auth, codex_home / "auth.json")


def _temporary_root() -> Path:
    if os.name != "nt":
        return Path(tempfile.gettempdir())
    root = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp").resolve(strict=True)
    user_home = Path.home().resolve(strict=True)
    try:
        root.relative_to(user_home)
    except ValueError:
        return root
    raise OSError("Windows temporary root must be outside the user profile")


def _child_environment(codex_home: Path) -> dict[str, str]:
    allowed_names = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "TEMP",
        "TMP",
    )
    environment = {
        name: os.environ[name]
        for name in allowed_names
        if name in os.environ
    }
    environment["CODEX_HOME"] = str(codex_home)
    return environment


def _read_bounded_output(output_path: Path) -> str:
    with output_path.open("rb") as response_file:
        content = response_file.read(MAX_OUTPUT_BYTES + 1)
    if len(content) > MAX_OUTPUT_BYTES:
        raise _OutputTooLarge
    return content.decode("utf-8")


def _terminate_process_tree(process: subprocess.Popen[str], deadline: float) -> None:
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        taskkill = Path(system_root) / "System32" / "taskkill.exe"
        remaining = deadline - time.monotonic()
        if remaining > 0:
            try:
                subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=remaining,
                    check=False,
                    shell=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
    except subprocess.SubprocessError:
        pass


def _terminate_orphaned_descendants(
    process: subprocess.Popen[str], deadline: float
) -> None:
    if os.name != "nt":
        return
    poll = getattr(process, "poll", None)
    root_pid = getattr(process, "pid", None)
    if poll is None or root_pid is None or poll() is None:
        return
    for _ in range(2):
        if time.monotonic() >= deadline:
            return
        process_parents = _windows_process_parents()
        if root_pid in process_parents:
            return
        descendant_depths = _windows_process_descendant_depths(root_pid, process_parents)
        if not descendant_depths:
            return
        handles: dict[int, int] = {}
        try:
            for descendant_pid in descendant_depths:
                if time.monotonic() >= deadline:
                    return
                handle = _open_process_termination_handle(descendant_pid)
                if handle is not None:
                    handles[descendant_pid] = handle
            if not handles or time.monotonic() >= deadline:
                return

            # Recheck ancestry while holding each process handle. The handle pins
            # the verified process object so PID reuse cannot redirect termination.
            current_parents = _windows_process_parents()
            if root_pid in current_parents:
                return
            current_depths = _windows_process_descendant_depths(root_pid, current_parents)
            if not current_depths:
                return
            for descendant_pid in sorted(
                handles,
                key=lambda pid: current_depths.get(pid, 0),
                reverse=True,
            ):
                if descendant_pid not in current_depths:
                    continue
                if time.monotonic() >= deadline:
                    return
                _terminate_process_handle(handles[descendant_pid], deadline)
        finally:
            for handle in handles.values():
                _close_process_handle(handle)


def _windows_process_descendant_depths(
    root_pid: int, process_parents: Mapping[int, int]
) -> dict[int, int]:
    descendants: dict[int, int] = {}
    frontier = [(root_pid, 0)]
    while frontier:
        parent_pid, parent_depth = frontier.pop()
        for pid, candidate_parent in process_parents.items():
            if candidate_parent == parent_pid and pid not in descendants:
                descendants[pid] = parent_depth + 1
                frontier.append((pid, parent_depth + 1))
    return descendants


def _open_process_termination_handle(process_id: int) -> int | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x00100001, False, process_id)
    if not handle:
        return None
    return int(handle)


def _terminate_process_handle(handle: int, deadline: float) -> bool:
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    if kernel32.WaitForSingleObject(handle, 0) == 0:
        return True
    if not kernel32.TerminateProcess(handle, 1):
        return False
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    timeout_ms = min(0xFFFFFFFE, max(0, int(remaining * 1000)))
    return kernel32.WaitForSingleObject(handle, timeout_ms) == 0


def _close_process_handle(handle: int) -> None:
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def _windows_process_parents() -> dict[int, int]:
    if os.name != "nt":
        return {}
    import ctypes
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        return {}
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return {}
        while True:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        return parents
    finally:
        kernel32.CloseHandle(snapshot)


def _failure(
    request: AnalysisRequest,
    error_type: str,
    started: float,
) -> AIAdvice:
    safe_details: Mapping[str, str] = {
        "executable_not_found": "Codex CLI executable is unavailable.",
        "process_start_error": "Codex CLI process could not be started.",
        "temp_setup_error": "Codex CLI temporary workspace could not be prepared.",
        "auth_copy_error": "Codex CLI authentication copy could not be prepared.",
        "schema_write_error": "Codex CLI response schema could not be written.",
        "process_spawn_error": "Codex CLI process could not be started.",
        "process_communication_error": "Codex CLI process communication failed.",
        "output_read_error": "Codex CLI final response could not be read.",
        "cleanup_error": "Codex CLI temporary workspace cleanup failed.",
        "timeout": "Codex CLI analysis exceeded its time limit.",
        "process_failed": "Codex CLI analysis process failed.",
        "output_missing": "Codex CLI final response was not produced.",
        "output_encoding": "Codex CLI final response was not valid UTF-8.",
        "output_too_large": "Codex CLI final response exceeded the size limit.",
        "output_invalid": "Codex CLI final response did not match the analysis contract.",
        "cleanup_workspace_retained": "Codex CLI temporary workspace remains after cleanup.",
        "cleanup_state_unknown": "Codex CLI temporary workspace state could not be verified.",
        "cleanup_permission_error": "Codex CLI temporary workspace cleanup was denied.",
        "cleanup_resource_busy": "Codex CLI temporary workspace was busy during cleanup.",
        "cleanup_sharing_violation": "Another process still held a temporary workspace file open.",
        "cleanup_lock_violation": "A temporary workspace file remained locked during cleanup.",
    }
    failure = AIModelFailure(
        model=MODEL,
        error_type=error_type,
        detail=safe_details[error_type],
    )
    return AIAdvice(
        targets=dict(request.proposed_weights),
        action="redistribute",
        model_used=MODEL,
        model_failures=(failure,),
        first_model_failed=True,
        provider="codex_cli",
        reasoning_effort=REASONING_EFFORT,
        duration_seconds=max(0.0, time.monotonic() - started),
    )
