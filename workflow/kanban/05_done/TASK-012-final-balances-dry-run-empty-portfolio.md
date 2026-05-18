---
id: TASK-012
title: Treat empty final balances as expected in dry-run
status: 05_done
kind: tdd
---

# TASK-012 - Treat empty final balances as expected in dry-run

## Objective

Stop the dry-run audit noise where `final_balances` is logged as failed after the run already completed successfully and the final portfolio refresh ends up empty.

## Context

- Current evidence: recent dry-run executions end with `final_balances` logged as failed because `compute_current_weights(...)` raises `PortfolioError("Unable to compute weights for an empty portfolio")`.
- This happens after simulated `earn_redeem` / trade planning, so the run itself is not broken; the audit signal is too strict.
- Relevant code: [`app.py`](../../../app.py) around the final balance refresh block, [`portfolio.py`](../../../portfolio.py), and the adaptive runner tests in [`tests/test_app_adaptive.py`](../../../tests/test_app_adaptive.py).

## Scope

- Add a regression test in `tests/test_app_adaptive.py` for the dry-run path where the final account snapshot is empty.
- Update `app.py` so the end-of-run final balance refresh does not log a failed step for this expected dry-run condition.
- Keep live behavior conservative: do not change trading execution, order planning, or portfolio math outside this specific end-of-run audit path.

## Test Contract

- Expected RED failure: the new regression test should show `final_balances` is currently logged as `failed` when the final portfolio refresh is empty.
- Expected GREEN behavior: after the fix, the run should still complete, but `final_balances` should be treated as an expected dry-run outcome instead of a failure.
- Verification command: `uv run pytest tests/test_app_adaptive.py tests/test_portfolio.py`
- Edge cases:
  - Dry-run with no final positions after simulated redeem/trade flow.
  - Non-dry-run behavior must remain cautious and must not hide real refresh errors.
- Forbidden shortcuts:
  - Do not rewrite logs or suppress the audit globally.
  - Do not change `PortfolioError` semantics in `portfolio.py` just to silence this one call site.
  - Do not touch live trading or Simple Earn execution paths.

## Acceptance

- The regression test passes.
- Existing adaptive strategy tests continue to pass.
- The dry-run log no longer shows `final_balances` as a failure for the empty-portfolio refresh case.

## Verification

- `uv run pytest tests/test_app_adaptive.py tests/test_portfolio.py` -> 13 passed.
- `uv run pytest` -> 31 passed.

## Independent Review

- Subagent audit verdict: good fit.
- Risk noted: the `empty portfolio` string match is a little brittle, but the fix stays local to the dry-run final audit path.

## Risks

- Overbroad suppression could hide genuine refresh failures.
- The fix must stay local to the final audit step in `app.py`.
