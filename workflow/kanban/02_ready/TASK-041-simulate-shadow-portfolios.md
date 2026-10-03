# TASK-041: Simulate Shadow Portfolios

## Objective

Build a deterministic virtual portfolio simulator using isolated per-scenario inventory, captured decision inputs, local order constraints, and configurable modeled costs.

## Context

See `docs/market-insights.md`, existing planner/exchange filters, and financial attribution limits in `docs/financial-performance.md`.

## Test Contract

- Tests: new `tests/test_market_insights_simulation.py`.
- RED: existing `strategy_replay.py` counts trade/cost proxies but does not evolve inventory or calculate portfolio return.
- Cover persistent scenario inventories across sequential runs, hold without trades/costs, same initial complete pre-decision snapshot and reference prices, own-portfolio drift, common observed targets/advice, sell-before-buy, modeled costs, nonnegative balances, exchange min-notional/lot constraints, missing prices, Spot/Earn alias reconciliation, idempotent replay, incomplete status, and session continuation after incomplete input.
- Command: `uv run pytest tests/test_market_insights_simulation.py`.

## Acceptance And Constraints

- Model hypothetical fills at captured reference prices and label that fill assumption; disclose modeled costs, omitted flows/yield, and Earn liquidity assumption.
- Never write synthetic results to `state/performance.db` or call live trade/Earn methods.
