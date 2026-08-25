# TASK-022 - Filter below-floor per-symbol deltas

## Objective

Stop treating per-symbol deltas below Binance's executable notional floor as actionable trades.

## Context

The 3% global drift threshold reduced churn but a completed run still reported four per-symbol `NOTIONAL` pendings. The existing executable floor and 10% uplift rules should be applied before a trade is treated as planned.

## TDD Contract

- RED: tests fail until below-floor deltas are classified as non-actionable while near-floor uplift remains executable.
- Verification: `uv run pytest tests/test_portfolio.py -q` and `uv run pytest`.

## Acceptance

- Below-floor deltas do not become trade instructions.
- Near-floor deltas within configured uplift remain executable.
- Sell availability, lot size, min/max notional, and anti-churn guards remain unchanged.
- No live trade or Earn operation is used for validation.

## Risks

Small allocations may remain below target longer; this is intentional to avoid forced fee-inefficient orders.

## Evidence

- RED: `uv run pytest tests/test_portfolio.py::test_build_trades_skips_below_effective_exchange_notional -q` -> failed with unexpected `non_actionable_rejections` argument.
- GREEN: focused test -> 1 passed; `uv run pytest tests/test_portfolio.py -q` -> 15 passed.
- Full verification: `uv run pytest` -> 52 passed.
