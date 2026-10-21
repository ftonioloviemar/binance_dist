from pathlib import Path


def test_candidate_launcher_fixes_dry_run_and_provider_without_argument_passthrough() -> None:
    launcher = Path(__file__).parents[1] / "run_codex_candidate.bat"
    command = launcher.read_text(encoding="utf-8").lower()

    assert "setlocal" in command
    assert "ai_provider=codex_cli" in command
    assert "--dry-run=true" in command
    assert "%*" not in command
    assert "run_prod.bat" not in command
