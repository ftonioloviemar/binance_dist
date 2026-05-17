from __future__ import annotations

from pathlib import Path

from logging_audit import load_recent_runs, load_run_detail


def _write_log_with_invalid_utf8(logs_dir: Path) -> str:
    run_id = "run_with_bad_encoding"
    content = (
        b"2026-05-13T09:00:08-03:00 | run_start | "
        b"run_id=run_with_bad_encoding | status=started | profile=moderate | dry_run=false\n"
        b"2026-05-13T09:00:09-03:00 | step | "
        b"run_id=run_with_bad_encoding | status=info | name=legacy | detail=bad byte: \xc1\n"
        b"2026-05-13T09:00:10-03:00 | run_end | "
        b"run_id=run_with_bad_encoding | status=completed\n"
    )
    (logs_dir / "20260513.log").write_bytes(content)
    return run_id


def test_load_recent_runs_tolerates_invalid_utf8_bytes(tmp_path: Path) -> None:
    run_id = _write_log_with_invalid_utf8(tmp_path)

    runs = load_recent_runs(limit=1, logs_dir=tmp_path)

    assert runs == [
        {
            "run_id": run_id,
            "completed_at": "2026-05-13T09:00:10-03:00",
            "status": "completed",
            "started_at": "2026-05-13T09:00:08-03:00",
            "profile": "moderate",
            "dry_run": False,
        }
    ]


def test_load_run_detail_tolerates_invalid_utf8_bytes(tmp_path: Path) -> None:
    run_id = _write_log_with_invalid_utf8(tmp_path)

    detail = load_run_detail(run_id, logs_dir=tmp_path)

    assert detail is not None
    assert detail["run"]["status"] == "completed"
    assert detail["steps"] == [
        {
            "timestamp": "2026-05-13T09:00:09-03:00",
            "name": "legacy",
            "status": "info",
            "detail": "bad byte: �",
        }
    ]
