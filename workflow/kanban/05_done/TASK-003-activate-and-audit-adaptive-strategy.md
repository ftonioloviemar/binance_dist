# TASK-003 - Garantir efeito real da adaptive_strategy

## Status

`05_done`

## Objective

Prove and fix why recent live runs did not show practical `adaptive_strategy` effect, then make the applied adaptive configuration visible in audit logs.

## Context

The last 30 analyzed runs had `ai_directive=Action=redistribute`, but no `adaptive_strategy` audit step and the config snapshot stayed on the base moderate targets/drift. The code contains adaptive logic, but the observed run evidence does not show it being applied.

## Scope

- Trace the scheduled entrypoint, wrappers, CLI args, and audit timing.
- Add tests for adaptive config application when `--adaptive` is passed and macro context is available.
- Ensure audit logs record applied adaptive profile, drift, slippage, sentiment, and target changes after a run exists.
- Ensure the recommended Windows scheduled entrypoint actually passes the intended adaptive flag.

Out of scope:

- Changing the investment model beyond making the current adaptive strategy execute and log.
- Live execution to validate the fix.

## TDD / Verification

- RED: add a test that demonstrates missing/adaptive audit behavior or missing adaptive application.
- GREEN: make adaptive config observable and applied in the tested path.
- Command: `uv run pytest tests/test_adaptive_strategy.py tests/test_app_adaptive.py -q` if new files are added, then `uv run pytest`.

## Acceptance

- A dry-run or test fixture with `--adaptive` records an `adaptive_strategy` audit step.
- The config snapshot reflects adaptive drift/targets when adaptive conditions are met.
- Documentation or scripts point to the entrypoint that actually enables adaptive mode.

## Evidence

- RED: `uv run pytest tests/test_app_adaptive.py -q` failed because the adaptive config snapshot changed but no `adaptive_strategy` step was persisted.
- Additional RED: `uv run pytest tests/test_adaptive_strategy.py tests/test_app_adaptive.py -q` exposed rounded adaptive targets summing to `0.9998` and missing slippage/target-change details in audit.
- GREEN: `uv run pytest tests/test_adaptive_strategy.py tests/test_app_adaptive.py -q` passed.
- Full suite: `uv run pytest` passed with 16 tests.
- Wrapper inspection: `run_adaptive_bot.bat` uses `adaptive_bot_windows.py`, `run_adaptive_bot_advanced.bat` uses `adaptive_bot.py`, and both Python wrappers pass `--adaptive`.
- Result audit by separate subagent found two medium issues: effective adaptive profile was not persisted in the run snapshot, and adaptive failures were still logged before `run_start`.
- Added RED coverage for persisted effective profile and persisted adaptive failure audit step.
- Final focused suite: `uv run pytest tests/test_adaptive_strategy.py tests/test_app_adaptive.py -q` passed with 3 tests.
- Final full suite: `uv run pytest` passed with 17 tests.

## Risks

- Adaptive allocation may increase turnover if thresholds are too tight. Mitigate by keeping this card limited to activation/observability; strategy tuning remains a separate user decision.
