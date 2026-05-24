# TASK-013 - Add tradability-aware drift guard to reduce noop from NOTIONAL and lot size

status: 05_done
type: tdd
priority: medium

## Objective

Reduce `noop` runs caused by drift signals that cannot become executable orders because the resulting notionals are below Binance `NOTIONAL`/`LOT_SIZE` floors.

## Context

Recent daily audits show the adaptive strategy still proposes redistribution, but many live runs end with `No trades required after filters` or `noop` because the trade sizes are too small to pass local/exchange filters. Scenario B in `docs/strategy-improvement-options.md` already recommends a threshold plus cost-aware guard.

## Scope

- Add a tradability-aware guard before rebalance execution.
- Make rebalance decisions consider whether any asset delta can clear the minimum tradable floor after notional and lot-step constraints.
- Keep live allocation targets unchanged for now.
- Preserve dry-run and live safety behavior.

## Test Contract

- Add a failing test first for a snapshot where drift exists but every candidate delta is below the tradable floor, so the run should be skipped instead of producing `noop`.
- Add a second test ensuring a clearly tradable delta still triggers rebalance.
- Verification command: `uv run pytest tests/test_portfolio.py tests/test_app_adaptive.py`

## Acceptance Criteria

- Small, untradable drifts no longer produce avoidable `noop` runs.
- Tradable drift still results in a rebalance decision and planned trades.
- Existing final-balance dry-run behavior remains intact.
- Tests pass and evidence is recorded.

## Outcome

- Implemented a tradability-aware pre-check in `app.py` backed by `portfolio.rebalance_has_tradable_orders`.
- Untradable drift now finalizes as `skipped` instead of `noop`.
- Verified with `uv run pytest` -> 34 passed.

## Risks

- Overly aggressive floors could suppress real rebalances.
- The guard must remain conservative and local to execution viability, not change strategic targets.
