# TASK-049: Import a certified external-flow CSV

## Objective

Allow the user to import a local CSV containing external deposits/withdrawals
and explicitly certify the complete time interval it covers, without live
exchange access.

## Context and approved contract

This implements the source selected in TASK-048. The CSV contains already
converted values in one quote asset; the app must not infer historical prices.
Coverage is a single complete ledger interval per quote asset. A re-import for
that quote asset atomically replaces its prior certified ledger and interval.
The old unverified `external_flows` records remain untouched and are not
eligible for certified performance attribution.

## TDD contract

- Add a `flows import-csv` CLI command requiring CSV path, quote asset, UTC
  coverage start/end, and explicit `--confirm-complete` acknowledgement.
- Required CSV columns: `flow_id,timestamp_utc,asset,quote_value,direction`.
  Additional columns may be ignored. An empty ledger with just the header is
  valid when the user certifies that no external flows occurred in the range.
- Timestamps must be timezone-aware UTC; coverage start/end are inclusive and
  start must be earlier than end. Every row timestamp must lie in the declared
  interval.
- `flow_id` must be nonempty and unique within the file; `asset` is normalized
  uppercase; `quote_value` must be a finite positive decimal in the selected
  quote asset; `direction` is exactly `in` or `out`.
- Parse and validate the whole file before mutation. Any invalid row leaves
  existing certified data unchanged. Importing a valid file atomically
  replaces only that quote asset's prior certified ledger and records the UTC
  coverage interval, certification time, and SHA-256 of the source bytes.
- Persist certified records separately from legacy unverified flow rows using
  additive SQLite schema changes.
- CLI output may report counts/range/status but must not print flow IDs,
  amounts, API credentials, or raw file content.
- Never call Binance, mutate strategy/trading state, or execute trades/Earn.

## Verification

- RED/GREEN: `uv run pytest -q tests/test_external_flows.py`
- Regression: `uv run pytest -q`
- Exercise CLI import only with temporary CSV and temporary SQLite paths.

## Acceptance

- Tests cover valid rows, empty certified ledger, UTC normalization, invalid
  headers/IDs/timestamps/assets/amounts/directions, out-of-range rows,
  missing confirmation, idempotent replacement, per-quote isolation, rollback
  on invalid input, additive migration, and no sensitive values in CLI output.
- Existing legacy `external_flows` records remain unchanged and cannot alone
  mark a report horizon reconciled.
- Independent TDD result auditor reports no unresolved P1/P2 findings.

## Risks and forbidden shortcuts

- Certification is the user's assertion about completeness, not machine proof
  that the source file contains every account movement; expose its interval and
  source hash for audit.
- Do not combine multiple partial certificates or silently assume missing
  flows are zero.
- Do not treat Spot-to-Earn or Earn-to-Spot transfers as external flows.
- Do not persist the input file path or raw CSV content.

## Completion evidence

- Pending.
