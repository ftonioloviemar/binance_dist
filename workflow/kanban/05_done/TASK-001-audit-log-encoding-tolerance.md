# TASK-001 - Tornar audit tolerante a encoding de logs

## Status

`05_done`

## Objective

Fix the built-in audit command so `uv run app.py audit --limit N` and `uv run app.py audit --run-id <id>` do not crash on older log files with non-UTF-8 bytes.

## Context

The current audit reader opens all `logs/*.log` with strict UTF-8. A historical log produced `UnicodeDecodeError`, blocking normal inspection even though the relevant pipe-delimited log records are otherwise readable.

## Scope

- Add tests for recent-run and run-detail loading with a log file containing invalid UTF-8 bytes.
- Update `logging_audit.py` to read logs tolerantly while preserving existing parsing behavior.
- Keep historical logs unchanged.

Out of scope:

- Rewriting or deleting log files.
- Changing the public audit CLI format beyond making it work.

## TDD / Verification

- RED: add a test that currently fails with `UnicodeDecodeError`.
- GREEN: make the reader tolerate bad bytes and still parse valid records.
- Command: `uv run pytest tests/test_logging_audit.py -q` and then `uv run pytest`.

## Acceptance

- `uv run app.py audit --limit 30` succeeds.
- `uv run app.py audit --run-id 58b09983ff7e42a8b0a95a3eeda4602c` returns details instead of crashing.
- Tests cover both newest-first and oldest-first readers.

## Evidence

- RED: `uv run pytest tests/test_logging_audit.py -q` failed with `UnicodeDecodeError` in both audit reader paths.
- GREEN: `uv run pytest tests/test_logging_audit.py -q` passed.
- Full suite: `uv run pytest` passed with 9 tests.
- Real audit checks succeeded:
  - `uv run app.py audit --limit 30`
  - `uv run app.py audit --run-id 58b09983ff7e42a8b0a95a3eeda4602c`
- Result audit by separate subagent: no findings.

## Risks

- Overly broad decoding could hide malformed records. Mitigate by skipping only unparsable lines and preserving valid records.
