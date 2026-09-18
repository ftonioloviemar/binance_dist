from pathlib import Path


def test_production_launcher_enables_adaptive_without_removing_dry_run_override() -> None:
    launcher = Path(__file__).parents[1] / "run_prod.bat"
    command = launcher.read_text(encoding="utf-8").lower()

    assert "--dry-run=false --adaptive %*" in command
