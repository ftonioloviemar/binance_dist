# TASK-019 - Calibrate drift threshold against executable notional

## Objective

Reduce avoidable rebalance cycles whose per-symbol delta is below Binance's executable `NOTIONAL` floor.

## Context

Recent audits show `DEFAULT_DRIFT=0.01` permits small candidate deltas between roughly 0.1 and 3.7 USDT while exchange floors are about 5 USDT. The existing 10% uplift intentionally rejects these deltas instead of forcing oversized orders.

## Decision

Use a 3% default drift threshold in the local runtime configuration. Keep `DEFAULT_MIN_NOTIONAL_UPLIFT_TOLERANCE=0.10`; do not increase it to compensate for deltas far below the exchange floor.

## Scope

- Update the local `.env` runtime setting and the example configuration/documentation if needed.
- Add a regression test documenting the selected default contract without exposing secrets.
- Preserve all notional, lot-size, available-balance, max-notional, and anti-churn guards.

## TDD Contract

- RED: configuration contract test fails until the selected default drift threshold is represented.
- GREEN: configuration and example settings expose the 3% threshold.
- Verification: `uv run pytest tests/test_config.py -q`, then `uv run pytest`.

## Acceptance

- The scheduled runtime uses `DEFAULT_DRIFT=0.03`.
- Near-floor uplift remains bounded at 10%.
- No live command is executed as validation.
- Audit/log replay and the full test suite remain clean.

## Risk

A higher threshold may delay rebalancing of genuinely meaningful but smaller allocations. Reassess after seven days using executed orders, fees, turnover, and residual drift.

## Evidence

- Backup: `.env` copied to `C:\python\binance_dist-backups\.env.backup-20260813-sizing` before the runtime change.
- RED: `uv run pytest tests/test_config.py -q` -> 1 failed, 5 passed; failure was the expected old fallback `0.10` versus `0.03`.
- GREEN: `uv run pytest tests/test_config.py -q` -> 6 passed.
- Full verification: `uv run pytest` -> 48 passed.
- Dry-run: `uv run app.py rebalance --dry-run true --drift 0.03 --min-notional 0 --min-notional-uplift-tolerance 0.10` -> completed in DRY mode; 5 trades planned, 4 simulated, 1 blocked by anti-churn, and 1 remaining `NOTIONAL` pending (`BNBUSDT` 2.0655 below 5.4778).
- Audit: run `006fbbef3cad47f29197b2b789273c0a` recorded `drift=0.03` and `min_notional_uplift_tolerance=0.1`.
