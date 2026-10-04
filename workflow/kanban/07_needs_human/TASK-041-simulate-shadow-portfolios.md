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

## Human Decision Required

- Resolved 2026-10-04: the user approved option 1. Use local-only `state/shadow_portfolios.db` for minimum per-policy virtual inventory/session state. Keep public candles, indicators, and aggregate scenario results in `state/market_insights.db`; do not store raw Spot/Earn snapshots, credentials, or per-asset virtual balances in that market-insights store. The virtual quantities remain sensitive derived data.
- Still awaiting user decisions on (1) turnover/drawdown/residual-drift conventions and (2) whether a potentially actionable order with a missing captured symbol filter makes the run incomplete or is recorded as skipped.
- Resume criteria: record those choices, move this card to `08_human_reviewed`, and begin test-first implementation. Until then, no simulator code or database schema is written.

## Specialist Review Calibration

- The Luna-medium contract review gave useful simulation/test coverage and correctly identified unresolved metric/filter conventions, but missed the explicit storage/privacy conflict in the canonical docs. The coordinator detected it before implementation. In later reviews of persisted financial derivatives, independently cross-check data destinations and privacy rules rather than treating the specialist review as sufficient.
