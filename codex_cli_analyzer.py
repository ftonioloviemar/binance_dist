from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Mapping

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
    executable = settings.executable or shutil.which("codex")
    if not executable:
        return _failure(request, "executable_not_found", started)

    try:
        with tempfile.TemporaryDirectory(
            prefix="codex-analysis-",
            dir=str(_temporary_root()),
        ) as temporary_directory:
            run_directory = Path(temporary_directory)
            codex_home = run_directory / "codex-home"
            codex_home.mkdir()
            _link_authentication_file(codex_home)
            schema_path = run_directory / "response-schema.json"
            output_path = run_directory / "final-response.json"
            schema_path.write_text(
                json.dumps(build_analysis_schema(request), separators=(",", ":")),
                encoding="utf-8",
            )
            command = _build_command(executable, schema_path, output_path)
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
            try:
                cleanup_reserve = min(2.0, settings.timeout_seconds * 0.1)
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
                return _failure(request, "timeout", started)

            if process.returncode != 0:
                return _failure(request, "process_failed", started)
            try:
                response = _read_bounded_output(output_path)
                targets, action, rationale = parse_analysis_response(response, request)
            except FileNotFoundError:
                return _failure(request, "output_missing", started)
            except UnicodeDecodeError:
                return _failure(request, "output_encoding", started)
            except _OutputTooLarge:
                return _failure(request, "output_too_large", started)
            except ValueError:
                return _failure(request, "output_invalid", started)

            return AIAdvice(
                targets=targets,
                action=action,
                rationale=rationale,
                model_used=MODEL,
                provider="codex_cli",
                reasoning_effort=REASONING_EFFORT,
                duration_seconds=max(0.0, time.monotonic() - started),
            )
    except (OSError, subprocess.SubprocessError):
        return _failure(request, "process_start_error", started)


class _OutputTooLarge(ValueError):
    pass


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


def _link_authentication_file(codex_home: Path) -> None:
    configured_home = os.environ.get("CODEX_HOME")
    source_home = Path(configured_home) if configured_home else Path.home() / ".codex"
    source_auth = source_home / "auth.json"
    if source_auth.is_file():
        os.link(source_auth, codex_home / "auth.json")


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


def _failure(
    request: AnalysisRequest,
    error_type: str,
    started: float,
) -> AIAdvice:
    safe_details: Mapping[str, str] = {
        "executable_not_found": "Codex CLI executable is unavailable.",
        "process_start_error": "Codex CLI process could not be started.",
        "timeout": "Codex CLI analysis exceeded its time limit.",
        "process_failed": "Codex CLI analysis process failed.",
        "output_missing": "Codex CLI final response was not produced.",
        "output_encoding": "Codex CLI final response was not valid UTF-8.",
        "output_too_large": "Codex CLI final response exceeded the size limit.",
        "output_invalid": "Codex CLI final response did not match the analysis contract.",
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
