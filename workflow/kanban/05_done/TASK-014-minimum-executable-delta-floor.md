# TASK-014 - Add minimum executable delta floor for tradability-aware sizing

status: 05_done
type: tdd
priority: medium

## Objective

Reduce avoidable `noop` runs by estimating the minimum executable delta per asset from exchange filters and using that floor in the rebalance decision path.

## Context

TASK-013 already skips runs when no order is tradable at all. The next refinement is to make the sizing logic more explicit so we can reason about the floor per asset, keep drift thresholds conservative, and avoid generating rebalance intent that is below the smallest executable move.

## Scope

- Add a helper that estimates the minimum executable delta for an asset using `min_notional`, `min_qty`, and `lot_step`.
- Use the estimated floor to decide whether a rebalance is actually actionable.
- Keep live allocation targets unchanged.
- Preserve existing dry-run and final-balance behavior.

## Test Contract

- Add a failing test for a snapshot where drift exists but every asset delta stays below the estimated executable floor, so the run is skipped.
- Add a unit test for the floor helper itself.
- Keep the existing tradable-drift regression tests passing.

## Acceptance Criteria

- Small drifts below the executable floor are treated as non-actionable.
- Tradable drift still reaches the trade planner.
- No regression in dry-run final balances or current trade filter tests.
- Tests pass and the result is captured in kanban and state.

## Outcome

- Added `estimate_executable_trade_floor(...)` to centralize the minimum executable move per asset.
- Added floor-aware skip logging so non-actionable drifts explain their floor instead of looking like a generic noop.
- Verified with `uv run pytest` -> 36 passed.

## Risks

- Overestimating the floor could suppress valid rebalances.
- The helper must remain conservative and local to execution viability, not a strategy rewrite.
