# TASK-065: Correct Audit Source and Monitor Correlation

## Objective

Make the CLI help, durable documentation, and paused Codex monitor accurately identify the current daily text logs as the audit source and correlate their run IDs with performance snapshots.

## Evidence and scope

- `app audit` uses `load_recent_runs()` over `logs/YYYYMMDD.log`; `logs/audit.db` is legacy and is not the current run source.
- Reconcile the monitor's claims using daily audit records and performance snapshots joined by run ID. A failed invalid-valuation guard with an incomplete before snapshot and skipped shadow observation is expected fail-closed behavior, not proof of an audit/performance persistence outage.
- Update only CLI help, project lessons/docs/state as needed, and the existing Codex heartbeat prompt. Keep the automation PAUSED.
- Do not alter Windows Task Scheduler, strategy, collection behavior, historical logs, SQLite data, or invoke live exchange operations.

## Verification and acceptance

- Confirm `app audit --help` describes the correct source and semantics.
- Review the prompt text and verify its persisted status remains PAUSED; no run is triggered as part of the change.
- Add/update focused doc/CLI tests where appropriate; run their offline tests and `git diff --check`.
- Independent Terra/medium review before closing; commit this card separately from TASK-064.

## Status

- Implemented pending independent review and separate commit.
- CLI help now identifies `logs/YYYYMMDD.log` as the source and `logs/audit.db` as legacy.
- Lessons and the paused heartbeat prompt require run-ID correlation and classify fail-closed valuation guard outcomes as expected unless independent persistence failure evidence exists.
- Verification: `uv run pytest -q tests/test_audit_help_source.py tests/test_logging_audit.py` -> 3 passed; `uv run python app.py audit --help` confirms source text; TOML parsed successfully and retained `PAUSED` and `FREQ=DAILY;INTERVAL=3`; `git diff --check` passed.
- No monitor run was triggered; no scheduler, historical data, or Binance operations changed.
