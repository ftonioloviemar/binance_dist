# TASK-063: Null deltas for incomplete performance horizons

## Objective

Prevent the performance report from exposing `observed_change` or
`hold_change` when a horizon is incomplete because snapshots are incomplete or
an asset price required for attribution is missing.

## Scope

- Keep complete snapshot comparisons unchanged.
- For incomplete snapshot quality or missing asset pricing, return null for
  both `observed_change` and `hold_change` and retain the incomplete status.
- Do not change the separate behavior for complete snapshots with insufficient
  external-flow coverage in this task.
- No strategy, schedule, exchange, or credential changes.

## TDD Contract

- Test specialist: clean-context `gpt-6.1-terra`/medium writes regression tests
  only before production changes.
- Test runner: `gpt-6-luna`/medium runs RED, GREEN, and regression commands.
- RED must fail because an incomplete comparison currently exposes a non-null
  `observed_change`.
- Cover missing asset pricing and incomplete snapshot quality; preserve
  existing complete-comparison values.
- Test author: clean-context `gpt-6.1-terra`/medium; only
  `tests/test_performance.py` changed in the test-author phase.

## Verification

- Focused: `uv run pytest -q tests/test_performance.py tests/test_performance_report.py`
- Regression: `uv run pytest -q`
- Read-only report smoke: `uv run python app.py performance --days 30 --json`
- Confirm incomplete horizons expose null deltas and complete horizons retain
  existing metrics.

## Safety

- Read local code, tests, audits, and SQLite data only.
- Never run live trading, Simple Earn redeem/subscribe, or exchange API calls.
- Do not expose balances, holdings, flow IDs, or sensitive account data.

## Progress

- Root cause confirmed in `performance.py`: `observed_change` currently depends
  on snapshot quality only, while missing assets independently mark attribution
  incomplete.
- RED: focused tests produced the expected two failures for missing prices
  (`observed_change` was `"10.00"` instead of null); 17 other focused tests
  passed.
- GREEN: focused command passed, 19 tests.
- Full regression: 390 passed; one unrelated failure in
  `tests/test_app_adaptive.py::test_rebalance_fails_closed_when_required_macro_source_is_untrusted[overflow]`.
  It errors during JSON encoding of a 10,000-digit integer (Python's 4,300-digit
  conversion limit), before reaching that test's assertion. No files in that
  test's scope were changed.
- Read-only JSON smoke: 24h remains incomplete with both changes null; complete
  snapshot horizons retain their prior behavior. SHA-256 hashes for all three
  local SQLite databases remained unchanged.
- `git diff --check` passed.
- Independent `gpt-6.1-terra`/medium review using
  `superpowers:requesting-code-review`: no findings. Residual coverage note:
  invalid/missing `asset_values` are not separately parameterized, although
  they share the guarded `missing_assets` path.

## Outcome

Implemented and verified for the reported incomplete horizon. The full suite
has one unrelated failure documented above; focused tests and the read-only
report smoke pass. No strategy, schedule, live exchange, or SQLite data changed.
