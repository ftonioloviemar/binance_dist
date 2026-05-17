# TASK-005 - Planejar backtest do cenario B

## Status

`05_done`

## Objective

Build the first testable design for Scenario B: threshold rebalancing with volatility and transaction-cost guard.

## Context

The user selected Scenario B on 2026-05-17. This strategy should not change live allocation behavior until it has a backtest or log-replay harness and explicit approval for live use.

## Scope

- Define the minimal data needed to replay or approximate recent portfolio decisions.
- Add a small strategy/backtest plan or harness that compares current fixed drift against cost-aware threshold variants.
- Keep this as research/backtest first; no live trading behavior change in this card unless a later approval explicitly says so.

Out of scope:

- Live trading.
- Changing default production targets.
- Enabling Scenario B in scheduled runs.

## TDD / Verification

- RED: create tests for the threshold/cost guard behavior before implementation.
- GREEN: implement the smallest pure function or harness needed to pass.
- Command: `uv run pytest`.

## Acceptance

- The repo has a repeatable way to compare current drift behavior with Scenario B candidates.
- The output includes at least order count, skipped-small-trade count, turnover proxy, and drift breach count.
- No live execution path changes without a separate approval.

## Evidence

- RED: `uv run pytest tests/test_strategy_replay.py -q` initially failed because `strategy_replay` did not exist.
- GREEN: added a pure replay harness in `strategy_replay.py` and documented the non-live limitation in `docs/strategy-scenario-b.md`.
- Focused suite: `uv run pytest tests/test_strategy_replay.py -q` passed with 4 tests.
- Full suite: `uv run pytest` passed with 21 tests.
- Result audit by separate subagent: no findings; residual multi-case aggregation risk was covered with an additional test.

## Risks

- Available logs may not contain enough historical price series for a true return backtest. If so, document the limitation and implement a decision-quality replay first.
