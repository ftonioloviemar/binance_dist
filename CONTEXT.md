# Domain Context

This glossary captures domain language for the Binance portfolio rebalancer. Workflow terms belong in `docs/project-continuity.md` and `workflow/kanban/README.md`.

## Terms

- **Portfolio snapshot**: Consolidated view of Spot balances, optional Simple Earn positions, prices, total value, and asset weights at a point in time.
- **Target weights**: Desired portfolio allocation after expanding profile buckets such as `STABLE` or `ALT` into concrete assets.
- **Drift**: Absolute difference between current asset weight and target weight. Drift above the configured threshold can trigger rebalance planning.
- **Rebalance plan**: Set of simulated or executable trade instructions required to move from current weights toward target weights.
- **Dry-run**: Execution mode that plans and logs trades without placing live orders or moving funds.
- **Notional guard**: Local validation against exchange minimum/maximum notional filters before an order reaches Binance.
- **Adaptive strategy**: Runtime adjustment of profile, target weights, drift, and slippage based on macro/sentiment inputs such as Fear & Greed and BTC 24h move.
- **AI target refinement**: Optional OpenRouter advice layer that can recommend `maintain` or `redistribute` within deterministic portfolio guardrails.
- **OpenRouter model registry**: Runtime-generated active model list at `state/openrouter_models.json`, created only after the first active model fails and a refresh succeeds.
- **Simple Earn flow**: Optional consolidation step that can simulate or execute redeem/trade/subscribe operations for flexible Earn positions.
- **Audit run**: Persistent JSON-lines record of run config, steps, orders, warnings, and final status, inspectable through `uv run app.py audit`.

## Boundary Rules

- AI advice does not bypass deterministic guardrails for drift, target deltas, slippage, notional, or dry-run/live mode.
- Strategy decisions belong in `docs/strategy-*.md`; glossary terms belong here only when they are stable and meaningful outside implementation details.
- Live trades, live redeem, and live subscribe require explicit user intent for that execution.
