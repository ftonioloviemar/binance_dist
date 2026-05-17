# TASK-004 - Selecionar cenario de estrategia para buscar melhor ganho

## Status

`05_done`

## Objective

Choose the next portfolio strategy experiment before implementing any allocation behavior that can materially change live trading.

## Context

The current system mostly operates as AI directive plus drift gate plus Simple Earn. Improving returns should be handled as explicit scenario selection followed by backtest, not by directly changing live allocation logic.

See `docs/strategy-improvement-options.md`.

## Options

- Scenario A: execution-quality baseline only.
- Scenario B: threshold rebalancing with volatility and transaction-cost guard.
- Scenario C: regime-based defensive/offensive allocation.
- Scenario D: momentum overlay with volatility scaling.
- Scenario E: risk-parity or HRP-style allocation.
- Scenario F: yield-first stable allocation using Earn/BFUSD-style carry where appropriate.

## Recommendation

Start with Scenario B as the next implementable experiment after TASK-001 through TASK-003. It offers the best balance between likely practical improvement, explainability, and implementation risk.

## Human decision

2026-05-17: User selected Scenario B: threshold plus volatility/cost-aware guard.

## Resume criteria

Completed. Create/execute follow-up work for Scenario B after TASK-001 through TASK-003 establish reliable audit, order filtering, and adaptive observability.

## Dependency impact

Blocks implementation of new profit-seeking strategy logic. Does not block TASK-001, TASK-002, or TASK-003.
