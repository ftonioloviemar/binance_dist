# TASK-002 - Corrigir planejamento de ordens abaixo de NOTIONAL

## Status

`05_done`

## Objective

Prevent repeated Binance `Filter failure: NOTIONAL` rejections by ensuring trade planning respects both `MIN_NOTIONAL` and `NOTIONAL` exchange filters before sending live orders.

## Context

Recent live logs show multiple rejected orders with Binance code `-1013` and message `Filter failure: NOTIONAL`. Official Binance Spot docs state that `MIN_NOTIONAL` and `NOTIONAL` validate `price * quantity`, and these filters may apply to `MARKET` orders.

Reference: https://developers.binance.com/docs/binance-spot-api-docs/filters

## Scope

- Characterize current `exchangeInfo` parsing for `MIN_NOTIONAL`, `NOTIONAL`, `LOT_SIZE`, and `MARKET_LOT_SIZE`.
- Add tests proving orders below the effective notional minimum are rejected locally before execution.
- Update planning/filter parsing so rejected orders become pendings with clear detail instead of exchange errors.
- Keep the implementation conservative: do not inflate a trade just to pass min notional unless the card explicitly allows that.

Out of scope:

- New allocation strategy.
- Live order execution for validation.

## TDD / Verification

- RED: add tests showing current code plans/sends an order below effective `NOTIONAL`.
- GREEN: planner skips such order with a pending reason.
- Command: `uv run pytest tests/test_binance_client.py tests/test_portfolio.py -q` and then `uv run pytest`.

## Acceptance

- Rebalance planning does not produce a live order below the effective Binance notional minimum.
- Pending detail names the symbol and threshold reason.
- Existing lot-step rounding behavior remains covered.

## Evidence

- RED: `uv run pytest tests/test_binance_client.py tests/test_portfolio.py -q` failed because `SymbolFilters` ignored `NOTIONAL.minNotional`.
- Additional RED: parser/planner had no `max_notional` support for `NOTIONAL.maxNotional`.
- GREEN: `uv run pytest tests/test_binance_client.py tests/test_portfolio.py -q` passed with 10 tests.
- Result audit by separate subagent found low-risk test gaps for precedence and exact boundaries.
- Added coverage for `MIN_NOTIONAL` precedence when more restrictive, absent `NOTIONAL.minNotional`, and exact `min`/`max` boundaries.
- Final focused suite: `uv run pytest tests/test_binance_client.py tests/test_portfolio.py -q` passed with 12 tests.
- Final full suite: `uv run pytest` passed with 14 tests.

## Risks

- Skipping too many small trades may leave drift unresolved. Mitigate by logging the blocked amount so a later strategy card can aggregate or adjust thresholds deliberately.
