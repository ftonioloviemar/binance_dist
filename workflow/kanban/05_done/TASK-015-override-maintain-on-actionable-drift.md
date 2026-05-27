# TASK-015 - Override AI maintain when drift is still actionable

status: 05_done
type: tdd
priority: medium

## Objective

Stop the AI `maintain` directive from suppressing a rebalance when the portfolio drift is already actionable according to the local drift decision and executable floor checks.

## Context

Recent runs show the bot increasingly skipping because the AI layer says `maintain`, even though the local portfolio decision path is capable of detecting actionable drift. The AI should remain a hint, not a veto, when the drift is clearly tradable.

## Scope

- Keep `maintain` as a valid stop signal only when the local decision path also says there is no actionable drift.
- Allow the run to continue when the local decision says rebalance is needed.
- Preserve the current tradability floor guard and dry-run safety.

## Test Contract

- Add a failing test proving that `maintain` still skips when drift is not actionable.
- Add a failing test proving that `maintain` does not suppress a tradable rebalance.
- Keep the current adaptive and tradability regression tests passing.

## Acceptance Criteria

- `maintain` no longer hides real rebalance opportunities.
- Non-actionable drift still stops cleanly.
- Tests pass and the behavior is recorded in the kanban and state.

## Outcome

- `maintain` now acts as a veto only when local drift decision also says no rebalance is needed.
- Actionable drift proceeds to tradability checks and trade planning.
- Verified with `uv run pytest` -> 38 passed.

## Risks

- Overriding `maintain` too often could increase turnover.
- The override must remain local to actionable drift, not a blind bypass of the AI layer.
