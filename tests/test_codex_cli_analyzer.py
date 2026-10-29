from __future__ import annotations

import hashlib
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ai_contract import AnalysisRequest


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        portfolio_value=1000,
        current_weights={"BTC": 0.6, "ETH": 0.4},
        proposed_weights={"BTC": 0.55, "ETH": 0.45},
    )


def _windows_error(winerror: int, error_number: int) -> OSError:
    error = OSError(error_number, "secret")
    error.winerror = winerror
    return error


class _CompletedProcess:
    def __init__(
        self,
        command: list[str],
        kwargs: dict[str, object],
        response: bytes | None,
        returncode: int = 0,
    ):
        self.command = command
        self.kwargs = kwargs
        self.response = response
        self.returncode = returncode

    def communicate(self, input: str, timeout: float) -> tuple[str, str]:
        self.kwargs["captured_input"] = input
        self.kwargs["captured_timeout"] = timeout
        if self.response is not None:
            output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            output_path.write_bytes(self.response)
        return '{"type":"agent_message","message":"not the final answer"}\n', ""


def test_runner_requests_fixed_model_and_parses_only_final_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import codex_cli_analyzer

    response = json.dumps(
        {"action": "maintain", "targets": {"BTC": 0.55, "ETH": 0.45}, "rationale": "ok"}
    ).encode("utf-8")
    captured: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> _CompletedProcess:
        captured["command"] = command
        captured.update(kwargs)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        home = Path(environment["CODEX_HOME"])
        captured["home_exists_during_call"] = home.exists()
        captured["home_has_user_config"] = (home / "config.toml").exists()
        captured["home_mcp_entries"] = list(home.glob("mcp*"))
        process = _CompletedProcess(command, kwargs, response)
        captured["process"] = process
        return process

    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "C:/tools/codex.exe")
    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("BINANCE_API_KEY", "sentinel-binance-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "sentinel-binance-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sentinel-openrouter-key")

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[command.index("--model") + 1] == "gpt-6-luna"
    assert "--config" in command
    config_values = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "--config"]
    assert 'model_reasoning_effort="medium"' in config_values
    assert "features.shell_tool=false" in config_values
    assert "features.apps=false" in config_values
    assert "features.hooks=false" in config_values
    assert "features.multi_agent=false" in config_values
    assert "features.remote_plugin=false" in config_values
    assert 'web_search="disabled"' in config_values
    assert 'windows.sandbox="mxc"' in config_values
    assert "--ignore-user-config" in command
    assert "--ephemeral" in command
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--json" in command
    assert "--output-schema" in command
    assert "--output-last-message" in command
    assert command[-1] == "-"
    assert captured["shell"] is False
    assert captured["stdout"] is codex_cli_analyzer.subprocess.DEVNULL
    assert captured["stderr"] is codex_cli_analyzer.subprocess.DEVNULL
    process = captured["process"]
    assert isinstance(process, _CompletedProcess)
    assert process.kwargs["captured_input"] == codex_cli_analyzer.build_analysis_prompt(_request())
    assert 0 < process.kwargs["captured_timeout"] <= 120
    workdir = Path(str(captured["cwd"])).resolve()
    assert workdir != Path.cwd().resolve()
    if os.name == "nt":
        system_temp = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp").resolve()
        user_home = Path.home().resolve()
        assert workdir.is_relative_to(system_temp)
        assert not workdir.is_relative_to(user_home)
    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert not {"BINANCE_API_KEY", "BINANCE_API_SECRET", "OPENROUTER_API_KEY"} & set(child_env)
    assert not {"sentinel-binance-key", "sentinel-binance-secret", "sentinel-openrouter-key"} & set(command)
    isolated_home = Path(child_env["CODEX_HOME"])
    assert captured["home_exists_during_call"]
    assert not captured["home_has_user_config"]
    assert not captured["home_mcp_entries"]
    assert advice.targets == {"BTC": 0.55, "ETH": 0.45}
    assert advice.action == "maintain"
    assert advice.rationale == "ok"
    assert advice.provider == "codex_cli"
    assert advice.reasoning_effort == "medium"
    assert not Path(str(captured["cwd"])).exists()
    assert not isolated_home.exists()


def test_runner_settings_enforce_timeout_bounds() -> None:
    import codex_cli_analyzer

    assert codex_cli_analyzer.CodexCliSettings().timeout_seconds == 120
    assert codex_cli_analyzer.CodexCliSettings(timeout_seconds=300).timeout_seconds == 300
    for timeout in (0, -1, 301, 1.5):
        with pytest.raises(ValueError):
            codex_cli_analyzer.CodexCliSettings(timeout_seconds=timeout)


@pytest.mark.parametrize(
    ("response", "returncode", "expected_error"),
    [
        (None, 0, "output_missing"),
        (b"not-json", 0, "output_invalid"),
        (b"\xff", 0, "output_encoding"),
        (b"x" * (64 * 1024 + 1), 0, "output_too_large"),
        (None, 1, "process_failed"),
    ],
    ids=["missing", "malformed", "invalid-utf8", "oversized", "nonzero-exit"],
)
def test_failures_return_sanitized_deterministic_advice(
    monkeypatch: pytest.MonkeyPatch,
    response: bytes | None,
    returncode: int,
    expected_error: str,
) -> None:
    import codex_cli_analyzer
    working_directories: list[Path] = []

    def fake_popen(command: list[str], **kwargs: object) -> _CompletedProcess:
        working_directories.append(Path(str(kwargs["cwd"])))
        return _CompletedProcess(command, kwargs, response, returncode)

    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("BINANCE_API_KEY", "sentinel-binance-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sentinel-openrouter-key")

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )

    assert advice.targets == _request().proposed_weights
    assert advice.action == "redistribute"
    assert advice.model_failures[0].error_type == expected_error
    assert "sentinel" not in repr(advice)
    assert "not-json" not in repr(advice)
    assert advice.provider == "codex_cli"
    assert len(working_directories) == 1
    assert not working_directories[0].exists()


def test_missing_executable_and_process_spawn_error_are_typed_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import codex_cli_analyzer

    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: None)
    missing = codex_cli_analyzer.analyze_with_codex(_request(), codex_cli_analyzer.CodexCliSettings())
    assert missing.model_failures[0].error_type == "executable_not_found"

    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")

    def fail_to_spawn(*args: object, **kwargs: object) -> None:
        raise OSError("secret-bearing exception should not escape")

    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", fail_to_spawn)
    spawn_failure = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )
    assert spawn_failure.model_failures[0].error_type == "process_spawn_error"
    assert "secret-bearing" not in repr(spawn_failure)


def test_process_communication_error_is_sanitized_and_terminates_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import codex_cli_analyzer

    class CommunicationFailure:
        pid = 12345
        returncode = None

        def communicate(self, **kwargs: object) -> None:
            raise OSError("secret-bearing communication detail")

    process = CommunicationFailure()
    terminated: list[object] = []
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        codex_cli_analyzer,
        "_terminate_process_tree",
        lambda child, deadline: terminated.append(child),
    )

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )

    assert advice.model_failures[0].error_type == "process_communication_error"
    assert "secret-bearing" not in repr(advice)
    assert terminated == [process]


@pytest.mark.parametrize("remove_before_error", [True, False])
@pytest.mark.parametrize("verification_error", [None, PermissionError("secret /private/path")])
@pytest.mark.parametrize(
    ("returncode", "expected_error", "expected_action"),
    [(0, None, "maintain"), (1, "process_failed", "redistribute")],
)
def test_cleanup_error_preserves_result_only_when_workspace_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    remove_before_error: bool,
    verification_error: OSError | None,
    returncode: int,
    expected_error: str | None,
    expected_action: str,
) -> None:
    import codex_cli_analyzer

    original_temporary_directory = codex_cli_analyzer.tempfile.TemporaryDirectory
    temporary_paths: list[Path] = []
    temporary_directories: list[object] = []
    cleanup_attempts: list[int] = []

    class CleanupRaisesAfterRemoval:
        def __init__(self, **kwargs: object) -> None:
            self._temporary_directory = original_temporary_directory(**kwargs)
            self.name = self._temporary_directory.name
            temporary_paths.append(Path(self.name))
            temporary_directories.append(self._temporary_directory)

        def __enter__(self) -> str:
            return self._temporary_directory.__enter__()

        def __exit__(self, *args: object) -> None:
            cleanup_attempts.append(1)
            if remove_before_error:
                self._temporary_directory.cleanup()
            raise OSError("secret-bearing cleanup detail")

    response = json.dumps(
        {"action": "maintain", "targets": {"BTC": 0.55, "ETH": 0.45}, "rationale": "ok"}
    ).encode("utf-8")
    monkeypatch.setattr(
        codex_cli_analyzer.tempfile,
        "TemporaryDirectory",
        CleanupRaisesAfterRemoval,
    )
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(
        codex_cli_analyzer.subprocess,
        "Popen",
        lambda command, **kwargs: _CompletedProcess(command, kwargs, response, returncode),
    )
    if verification_error is not None:
        original_stat = Path.stat
        workspace_path: Path | None = None

        def fail_workspace_stat(path: Path, *args: object, **kwargs: object):
            if workspace_path is not None and path == workspace_path:
                raise verification_error
            return original_stat(path, *args, **kwargs)

        original_temporary_directory_init = CleanupRaisesAfterRemoval.__init__

        def record_workspace(self, **kwargs: object) -> None:
            nonlocal workspace_path
            original_temporary_directory_init(self, **kwargs)
            workspace_path = Path(self.name)

        monkeypatch.setattr(CleanupRaisesAfterRemoval, "__init__", record_workspace)
        monkeypatch.setattr(Path, "stat", fail_workspace_stat)

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )
    if verification_error is not None:
        monkeypatch.undo()

    if verification_error is not None:
        expected_error = "cleanup_state_unknown"
        expected_action = "redistribute"
    elif not remove_before_error:
        expected_error = "cleanup_workspace_retained"
        expected_action = "redistribute"
    assert advice.action == expected_action
    assert advice.targets == _request().proposed_weights
    if expected_error is None:
        assert advice.model_failures == ()
    else:
        assert advice.model_failures[0].error_type == expected_error
    assert len(temporary_paths) == 1
    assert cleanup_attempts == [1]
    assert temporary_paths[0].exists() is not remove_before_error
    if not remove_before_error:
        temporary_directories[0].cleanup()
        assert not temporary_paths[0].exists()
    assert "secret-bearing" not in repr(advice)
    assert "secret /private/path" not in repr(advice)


@pytest.mark.parametrize(
    ("winerror", "error_number"),
    [(32, errno.EACCES), (33, errno.EACCES), (None, errno.EBUSY)],
)
def test_transient_busy_cleanup_retries_once_and_preserves_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    winerror: int | None,
    error_number: int,
) -> None:
    import codex_cli_analyzer

    original_temporary_directory = codex_cli_analyzer.tempfile.TemporaryDirectory
    cleanup_attempts: list[int] = []
    temporary_paths: list[Path] = []
    sleeps: list[float] = []

    class BusyThenSuccess:
        def __init__(self, **kwargs: object) -> None:
            self._temporary_directory = original_temporary_directory(**kwargs)
            self.name = self._temporary_directory.name
            temporary_paths.append(Path(self.name))

        def __enter__(self) -> str:
            return self._temporary_directory.__enter__()

        def __exit__(self, *args: object) -> None:
            cleanup_attempts.append(1)
            if len(cleanup_attempts) <= 3:
                error = OSError(error_number, "secret cleanup detail")
                if winerror is not None:
                    error.winerror = winerror
                raise error
            self._temporary_directory.__exit__(*args)

    response = json.dumps(
        {"action": "maintain", "targets": {"BTC": 0.55, "ETH": 0.45}, "rationale": "ok"}
    ).encode("utf-8")
    monkeypatch.setattr(codex_cli_analyzer, "_temporary_root", lambda: tmp_path)
    monkeypatch.setattr(codex_cli_analyzer, "_copy_authentication_file", lambda _: None)
    monkeypatch.setattr(codex_cli_analyzer.tempfile, "TemporaryDirectory", BusyThenSuccess)
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(
        codex_cli_analyzer.subprocess,
        "Popen",
        lambda command, **kwargs: _CompletedProcess(command, kwargs, response),
    )
    monkeypatch.setattr(codex_cli_analyzer.time, "sleep", sleeps.append)

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )

    assert advice.action == "maintain"
    assert advice.model_failures == ()
    assert cleanup_attempts == [1, 1, 1, 1]
    assert sleeps == [0.05, 0.1, 0.2]
    assert len(temporary_paths) == 1
    assert not temporary_paths[0].exists()
    assert "secret cleanup detail" not in repr(advice)


def test_transient_busy_cleanup_exhaustion_returns_sanitized_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import codex_cli_analyzer

    original_temporary_directory = codex_cli_analyzer.tempfile.TemporaryDirectory
    cleanup_attempts: list[int] = []
    temporary_directories: list[object] = []
    sleeps: list[float] = []

    class AlwaysBusy:
        def __init__(self, **kwargs: object) -> None:
            self._temporary_directory = original_temporary_directory(**kwargs)
            self.name = self._temporary_directory.name
            temporary_directories.append(self._temporary_directory)

        def __enter__(self) -> str:
            return self._temporary_directory.__enter__()

        def __exit__(self, *args: object) -> None:
            cleanup_attempts.append(1)
            raise _windows_error(32, errno.EACCES)

    response = json.dumps(
        {"action": "maintain", "targets": {"BTC": 0.55, "ETH": 0.45}, "rationale": "secret rationale"}
    ).encode("utf-8")
    monkeypatch.setattr(codex_cli_analyzer, "_temporary_root", lambda: tmp_path)
    monkeypatch.setattr(codex_cli_analyzer, "_copy_authentication_file", lambda _: None)
    monkeypatch.setattr(codex_cli_analyzer.tempfile, "TemporaryDirectory", AlwaysBusy)
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(
        codex_cli_analyzer.subprocess,
        "Popen",
        lambda command, **kwargs: _CompletedProcess(command, kwargs, response),
    )
    monkeypatch.setattr(codex_cli_analyzer.time, "sleep", sleeps.append)

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )

    assert advice.model_failures[0].error_type == "cleanup_sharing_violation"
    assert advice.rationale is None
    assert cleanup_attempts == [1, 1, 1, 1, 1]
    assert sleeps == [0.05, 0.1, 0.2, 0.4]
    assert "secret rationale" not in repr(advice)
    temporary_directories[0].cleanup()


def test_cleanup_permission_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import codex_cli_analyzer

    original_temporary_directory = codex_cli_analyzer.tempfile.TemporaryDirectory
    cleanup_attempts: list[int] = []
    temporary_directories: list[object] = []

    class PermissionDenied:
        def __init__(self, **kwargs: object) -> None:
            self._temporary_directory = original_temporary_directory(**kwargs)
            self.name = self._temporary_directory.name
            temporary_directories.append(self._temporary_directory)

        def __enter__(self) -> str:
            return self._temporary_directory.__enter__()

        def __exit__(self, *args: object) -> None:
            cleanup_attempts.append(1)
            raise _windows_error(5, errno.EBUSY)

    response = json.dumps(
        {"action": "maintain", "targets": {"BTC": 0.55, "ETH": 0.45}, "rationale": "ok"}
    ).encode("utf-8")
    monkeypatch.setattr(codex_cli_analyzer, "_temporary_root", lambda: tmp_path)
    monkeypatch.setattr(codex_cli_analyzer, "_copy_authentication_file", lambda _: None)
    monkeypatch.setattr(codex_cli_analyzer.tempfile, "TemporaryDirectory", PermissionDenied)
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(
        codex_cli_analyzer.subprocess,
        "Popen",
        lambda command, **kwargs: _CompletedProcess(command, kwargs, response),
    )

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )

    assert advice.model_failures[0].error_type == "cleanup_permission_error"
    assert cleanup_attempts == [1]
    temporary_directories[0].cleanup()


def test_busy_cleanup_retry_wait_respects_cleanup_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import codex_cli_analyzer

    original_temporary_directory = codex_cli_analyzer.tempfile.TemporaryDirectory
    cleanup_attempts: list[int] = []
    temporary_directories: list[object] = []
    sleeps: list[float] = []
    clock = [10.0]

    class AlwaysBusy:
        def __init__(self, **kwargs: object) -> None:
            self._temporary_directory = original_temporary_directory(**kwargs)
            self.name = self._temporary_directory.name
            temporary_directories.append(self._temporary_directory)

        def __enter__(self) -> str:
            return self._temporary_directory.__enter__()

        def __exit__(self, *args: object) -> None:
            cleanup_attempts.append(1)
            raise _windows_error(32, errno.EACCES)

    def advance_clock(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(codex_cli_analyzer.tempfile, "TemporaryDirectory", AlwaysBusy)
    monkeypatch.setattr(codex_cli_analyzer.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(codex_cli_analyzer.time, "sleep", advance_clock)

    with pytest.raises(OSError):
        with codex_cli_analyzer._temporary_directory_with_cleanup_retry(
            cleanup_deadline=10.1,
            prefix="codex-analysis-",
            dir=tmp_path,
        ):
            pass

    assert cleanup_attempts == [1, 1]
    assert sleeps == [0.05]
    temporary_directories[0].cleanup()


@pytest.mark.parametrize(
    ("error", "workspace_state", "expected_error"),
    [
        (PermissionError(errno.EACCES, "secret"), "retained", "cleanup_permission_error"),
        (OSError(errno.EACCES, "secret"), "unknown", "cleanup_permission_error"),
        (_windows_error(5, errno.EACCES), "retained", "cleanup_permission_error"),
        (_windows_error(5, errno.EBUSY), "retained", "cleanup_permission_error"),
        (_windows_error(32, errno.EACCES), "retained", "cleanup_sharing_violation"),
        (_windows_error(33, errno.EACCES), "unknown", "cleanup_lock_violation"),
        (OSError(errno.EBUSY, "secret"), "retained", "cleanup_resource_busy"),
        (OSError("secret"), "retained", "cleanup_workspace_retained"),
        (OSError("secret"), "unknown", "cleanup_state_unknown"),
    ],
)
def test_cleanup_failure_classification_is_sanitized(
    error: OSError,
    workspace_state: str,
    expected_error: str,
) -> None:
    import codex_cli_analyzer

    failure_type = codex_cli_analyzer._cleanup_failure_type(error, workspace_state)

    assert failure_type == expected_error
    assert "secret" not in repr(failure_type)


def test_isolated_home_uses_and_removes_only_an_independent_temporary_auth_copy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import codex_cli_analyzer

    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    source_auth = source_home / "auth.json"
    source_auth.write_bytes(b"synthetic-auth-fixture")
    original_hash = hashlib.sha256(source_auth.read_bytes()).hexdigest()
    response = json.dumps(
        {"action": "maintain", "targets": {"BTC": 0.55, "ETH": 0.45}, "rationale": "ok"}
    ).encode("utf-8")
    observed: dict[str, Path] = {}

    def fake_popen(command: list[str], **kwargs: object) -> _CompletedProcess:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        copied_auth = Path(environment["CODEX_HOME"]) / "auth.json"
        assert copied_auth.exists()
        assert not os.path.samefile(copied_auth, source_auth)
        assert copied_auth.read_bytes() == source_auth.read_bytes()
        observed["copied_auth"] = copied_auth
        copied_auth.write_bytes(b"rotated-synthetic-auth")
        return _CompletedProcess(command, kwargs, response)

    monkeypatch.setenv("CODEX_HOME", str(source_home))
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", fake_popen)

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )

    assert advice.action == "maintain"
    assert not observed["copied_auth"].exists()
    assert hashlib.sha256(source_auth.read_bytes()).hexdigest() == original_hash


def test_timeout_terminates_process_and_returns_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import codex_cli_analyzer

    captured: dict[str, object] = {}

    class TimedOutProcess:
        pid = 12345
        returncode = None

        def communicate(self, **kwargs: object) -> None:
            raise subprocess.TimeoutExpired("codex", timeout=kwargs["timeout"])

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            self.returncode = -9

        def wait(self, timeout: float) -> int:
            self.returncode = -9
            return self.returncode

    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    def fake_popen(command: list[str], **kwargs: object) -> TimedOutProcess:
        captured.update(kwargs)
        process = TimedOutProcess()
        captured["process"] = process
        return process

    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(codex_cli_analyzer.subprocess, "run", lambda *a, **k: None)

    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings(timeout_seconds=1)
    )

    assert advice.model_failures[0].error_type == "timeout"
    assert advice.targets == _request().proposed_weights
    assert not Path(str(captured["cwd"])).exists()
    assert captured["process"].returncode == -9


def test_concurrent_calls_use_unique_workdirs_and_keep_prompt_out_of_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import codex_cli_analyzer

    response = json.dumps(
        {"action": "maintain", "targets": {"BTC": 0.55, "ETH": 0.45}, "rationale": "ok"}
    ).encode("utf-8")
    captured: list[tuple[list[str], dict[str, object]]] = []
    lock = threading.Lock()

    def fake_popen(command: list[str], **kwargs: object) -> _CompletedProcess:
        with lock:
            captured.append((command, kwargs))
        return _CompletedProcess(command, kwargs, response)

    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", fake_popen)
    request = AnalysisRequest(
        portfolio_value=1000,
        current_weights={"BTC": 0.6, "ETH": 0.4},
        proposed_weights={"BTC": 0.55, "ETH": 0.45},
        portfolio_context={"note": 'quote " & pipe | $() ` ;'},
    )
    answers = []
    threads = [
        threading.Thread(
            target=lambda: answers.append(
                codex_cli_analyzer.analyze_with_codex(request, codex_cli_analyzer.CodexCliSettings())
            )
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(answers) == 2
    assert all(answer.action == "maintain" for answer in answers)
    working_directories = [str(kwargs["cwd"]) for _, kwargs in captured]
    assert len(set(working_directories)) == 2
    for command, kwargs in captured:
        assert request.portfolio_context["note"] not in command
        assert json.dumps(request.portfolio_context) in codex_cli_analyzer.build_analysis_prompt(request)
        assert kwargs["captured_input"] == codex_cli_analyzer.build_analysis_prompt(request)


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree termination contract")
def test_windows_timeout_kills_descendant_before_late_write(tmp_path: Path) -> None:
    import codex_cli_analyzer

    child_marker = tmp_path / "late-write.txt"
    child_pid_file = tmp_path / "child.pid"
    child_pid_temp_file = tmp_path / "child.pid.tmp"
    child_program = (
        "import pathlib,time; time.sleep(3); "
        f"pathlib.Path({str(child_marker)!r}).write_text('late')"
    )
    parent_program = (
        "import pathlib,subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable,'-c',{child_program!r}]); "
        f"pathlib.Path({str(child_pid_temp_file)!r}).write_text(str(child.pid)); "
        f"pathlib.Path({str(child_pid_temp_file)!r}).replace({str(child_pid_file)!r}); "
        "time.sleep(60)"
    )
    process = subprocess.Popen([sys.executable, "-c", parent_program], shell=False)
    deadline = time.monotonic() + 3
    while not child_pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))

    codex_cli_analyzer._terminate_process_tree(process, time.monotonic() + 5)
    assert process.poll() is not None
    time.sleep(3.2)
    assert not child_marker.exists()
    processes = subprocess.run(
        ["tasklist.exe", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    import csv

    listed_pids = {
        int(row[1])
        for row in csv.reader(processes.stdout.splitlines())
        if len(row) > 1 and row[1].isdigit()
    }
    assert child_pid not in listed_pids


@pytest.mark.skipif(os.name != "nt", reason="Windows orphan cleanup contract")
def test_windows_process_snapshot_reports_current_process() -> None:
    import codex_cli_analyzer

    process_parents = codex_cli_analyzer._windows_process_parents()

    assert os.getpid() in process_parents


@pytest.mark.skipif(os.name != "nt", reason="Windows orphan cleanup contract")
def test_windows_orphan_reaper_skips_pid_reused_before_handle_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import codex_cli_analyzer

    root_pid, child_pid, unrelated_pid = 900_001, 900_002, 900_003
    snapshots = iter(
        [
            {child_pid: root_pid, unrelated_pid: 1},
            {child_pid: unrelated_pid, unrelated_pid: 1},
        ]
    )
    opened: list[int] = []
    closed: list[str] = []
    terminated: list[str] = []

    class ExitedProcess:
        pid = root_pid

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(
        codex_cli_analyzer,
        "_windows_process_parents",
        lambda: next(snapshots),
    )
    monkeypatch.setattr(
        codex_cli_analyzer,
        "_open_process_termination_handle",
        lambda pid: opened.append(pid) or "pinned-handle",
    )
    monkeypatch.setattr(
        codex_cli_analyzer,
        "_close_process_handle",
        closed.append,
    )
    monkeypatch.setattr(
        codex_cli_analyzer,
        "_terminate_process_handle",
        lambda handle, deadline: terminated.append(handle) or True,
    )

    codex_cli_analyzer._terminate_orphaned_descendants(
        ExitedProcess(), time.monotonic() + 2
    )

    assert opened == [child_pid]
    assert closed == ["pinned-handle"]
    assert terminated == []


@pytest.mark.skipif(os.name != "nt", reason="Windows orphan cleanup contract")
def test_windows_completed_cli_reaps_only_its_orphaned_descendants(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import codex_cli_analyzer

    child_pid_file = tmp_path / "child.pid"
    unrelated_pid_file = tmp_path / "unrelated.pid"
    child_program = (
        "import os,pathlib,time; "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(60)"
    )
    unrelated_program = (
        "import os,pathlib,time; "
        f"pathlib.Path({str(unrelated_pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(60)"
    )
    taskkill = str(
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
    )
    child = subprocess.Popen([sys.executable, "-c", child_program], shell=False)
    unrelated = subprocess.Popen([sys.executable, "-c", unrelated_program], shell=False)
    root_pid = 0xFFFFFFFE
    root_exited = [False]
    process_parents = {root_pid - 1: root_pid, root_pid - 2: root_pid - 1, 0: 1}

    def is_running(pid: int) -> bool:
        result = subprocess.run(
            ["tasklist.exe", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            shell=False,
        )
        import csv

        return any(
            len(row) > 1 and row[1].isdigit() and int(row[1]) == pid
            for row in csv.reader(result.stdout.splitlines())
        )

    try:
        deadline = time.monotonic() + 5
        while (
            (not child_pid_file.exists() or not unrelated_pid_file.exists())
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert child_pid_file.exists()
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        unrelated_pid = int(unrelated_pid_file.read_text(encoding="utf-8"))
        process_parents = {root_pid - 1: root_pid, root_pid - 2: root_pid - 1, unrelated_pid: 1}

        class CompletedCodexProcess:
            def __init__(self, pid: int, exited: list[bool]) -> None:
                self.pid = pid
                self._exited = exited

            def poll(self) -> int | None:
                return 0 if self._exited[0] else None

        monkeypatch.setattr(
            codex_cli_analyzer,
            "_windows_process_parents",
            lambda: dict(process_parents),
        )
        process = CompletedCodexProcess(root_pid, root_exited)
        codex_cli_analyzer._terminate_orphaned_descendants(process, deadline)
        assert is_running(child_pid)

        root_exited[0] = True
        process_parents = {child_pid: root_pid, unrelated_pid: 1}
        codex_cli_analyzer._terminate_orphaned_descendants(process, time.monotonic() + 5)
        assert not is_running(child_pid)
        assert is_running(unrelated_pid)
    finally:
        for pid in (
            int(child_pid_file.read_text(encoding="utf-8"))
            if child_pid_file.exists()
            else child.pid,
            int(unrelated_pid_file.read_text(encoding="utf-8"))
            if unrelated_pid_file.exists()
            else unrelated.pid,
        ):
            subprocess.run(
                [taskkill, "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                shell=False,
            )
        child_pid_file.unlink(missing_ok=True)


def _install_candidate(local_appdata: Path, version: str) -> Path:
    candidate = local_appdata / "OpenAI" / "Codex" / "bin" / version / "codex.exe"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.touch()
    return candidate


def _discovery_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str = "nt") -> list[list[str]]:
    import codex_cli_analyzer

    commands: list[list[str]] = []
    monkeypatch.setattr(codex_cli_analyzer, "os", SimpleNamespace(name=platform, environ=os.environ))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", lambda _: None)
    monkeypatch.setattr(codex_cli_analyzer, "_temporary_root", lambda: tmp_path)
    monkeypatch.setattr(codex_cli_analyzer, "_copy_authentication_file", lambda _: None)
    monkeypatch.setattr(codex_cli_analyzer, "_terminate_orphaned_descendants", lambda *args: None)

    def fake_popen(command: list[str], **kwargs: object) -> _CompletedProcess:
        assert kwargs["shell"] is False
        commands.append(command)
        return _CompletedProcess(command, kwargs, None, returncode=1)

    monkeypatch.setattr(codex_cli_analyzer.subprocess, "Popen", fake_popen)
    return commands


def _assert_missing_executable(advice: object, commands: list[list[str]]) -> None:
    assert not commands
    assert advice.targets == _request().proposed_weights
    assert advice.action == "redistribute"
    assert advice.model_failures[0].error_type == "executable_not_found"
    assert advice.model_failures[0].detail == "Codex CLI executable is unavailable."


def test_windows_discovers_single_canonical_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import codex_cli_analyzer

    commands = _discovery_environment(monkeypatch, tmp_path)
    candidate = _install_candidate(tmp_path / "local", "opaque-version")
    codex_cli_analyzer.analyze_with_codex(_request(), codex_cli_analyzer.CodexCliSettings())
    assert len(commands) == 1
    assert Path(commands[0][0]) == candidate


@pytest.mark.parametrize("source", ["explicit", "path"])
def test_executable_precedence_over_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source: str) -> None:
    import codex_cli_analyzer

    commands = _discovery_environment(monkeypatch, tmp_path)
    _install_candidate(tmp_path / "local", "version")
    root = tmp_path / "local" / "OpenAI" / "Codex" / "bin"
    original_glob = Path.glob
    original_iterdir = Path.iterdir
    def forbid_glob(path: Path, *args: object, **kwargs: object):
        assert path != root, "precedence must skip install enumeration"
        return original_glob(path, *args, **kwargs)
    def forbid_iterdir(path: Path):
        assert path != root, "precedence must skip install enumeration"
        return original_iterdir(path)
    monkeypatch.setattr(Path, "glob", forbid_glob)
    monkeypatch.setattr(Path, "iterdir", forbid_iterdir)
    explicit = "explicit-codex.exe" if source == "explicit" else None
    def which(name: str) -> str:
        assert source != "explicit", "explicit executable must skip PATH lookup"
        return "path-codex.exe"
    monkeypatch.setattr(codex_cli_analyzer.shutil, "which", which)
    codex_cli_analyzer.analyze_with_codex(_request(), codex_cli_analyzer.CodexCliSettings(executable=explicit))
    assert len(commands) == 1
    assert commands[0][0] == (explicit or "path-codex.exe")


@pytest.mark.parametrize("case", ["absent", "empty", "missing_root", "no_candidate", "wrong_depth", "directory"])
def test_missing_canonical_install_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str) -> None:
    import codex_cli_analyzer

    commands = _discovery_environment(monkeypatch, tmp_path)
    root = tmp_path / "local" / "OpenAI" / "Codex" / "bin"
    if case == "absent":
        monkeypatch.delenv("LOCALAPPDATA")
    elif case == "empty":
        monkeypatch.setenv("LOCALAPPDATA", "")
    elif case == "no_candidate":
        (root / "version").mkdir(parents=True)
        (root / "version" / "other.exe").touch()
    elif case == "wrong_depth":
        (root / "version" / "nested").mkdir(parents=True)
        (root / "version" / "nested" / "codex.exe").touch()
        (root / "codex.exe").touch()
    elif case == "directory":
        (root / "version" / "codex.exe").mkdir(parents=True)
    advice = codex_cli_analyzer.analyze_with_codex(_request(), codex_cli_analyzer.CodexCliSettings())
    _assert_missing_executable(advice, commands)


@pytest.mark.parametrize("same_mtime", [True, False])
def test_multiple_installs_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, same_mtime: bool) -> None:
    import codex_cli_analyzer

    commands = _discovery_environment(monkeypatch, tmp_path)
    first = _install_candidate(tmp_path / "local", "a")
    second = _install_candidate(tmp_path / "local", "b")
    os.utime(first, (1000000000, 1000000000))
    os.utime(second, (1000000000 if same_mtime else 1000000100,) * 2)
    advice = codex_cli_analyzer.analyze_with_codex(_request(), codex_cli_analyzer.CodexCliSettings())
    _assert_missing_executable(advice, commands)


def test_non_windows_does_not_discover_windows_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import codex_cli_analyzer

    commands = _discovery_environment(monkeypatch, tmp_path, platform="posix")
    _install_candidate(tmp_path / "local", "version")
    advice = codex_cli_analyzer.analyze_with_codex(_request(), codex_cli_analyzer.CodexCliSettings())
    _assert_missing_executable(advice, commands)


def test_install_enumeration_error_falls_back_safely(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import codex_cli_analyzer

    commands = _discovery_environment(monkeypatch, tmp_path)
    root = tmp_path / "local" / "OpenAI" / "Codex" / "bin"
    root.mkdir(parents=True)
    original_glob = Path.glob
    original_iterdir = Path.iterdir
    def fail_glob(path: Path, *args: object, **kwargs: object):
        if path == root:
            raise OSError("secret enumeration failure")
        return original_glob(path, *args, **kwargs)
    def fail_iterdir(path: Path):
        if path == root:
            raise OSError("secret enumeration failure")
        return original_iterdir(path)
    monkeypatch.setattr(Path, "glob", fail_glob)
    monkeypatch.setattr(Path, "iterdir", fail_iterdir)
    advice = codex_cli_analyzer.analyze_with_codex(_request(), codex_cli_analyzer.CodexCliSettings())
    _assert_missing_executable(advice, commands)
    assert "secret" not in repr(advice)
    assert str(root) not in repr(advice)


def test_inaccessible_candidate_fails_closed_with_valid_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import codex_cli_analyzer

    commands = _discovery_environment(monkeypatch, tmp_path)
    _install_candidate(tmp_path / "local", "valid")
    inaccessible = _install_candidate(tmp_path / "local", "inaccessible")
    original_stat = Path.stat

    def denied_stat(path: Path, *args: object, **kwargs: object):
        if path == inaccessible:
            raise PermissionError("secret candidate inspection failure")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", denied_stat)
    advice = codex_cli_analyzer.analyze_with_codex(
        _request(), codex_cli_analyzer.CodexCliSettings()
    )
    _assert_missing_executable(advice, commands)
    assert "secret" not in repr(advice)
    assert str(inaccessible) not in repr(advice)
