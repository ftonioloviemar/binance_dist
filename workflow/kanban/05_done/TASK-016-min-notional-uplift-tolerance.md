# TASK-016 - Add controlled min-notional uplift tolerance

## Objective

Reduce avoidable `noop`/`skipped` outcomes caused by candidate trades that are slightly below Binance effective `NOTIONAL` or lot-size floors.

## Context

Recent reviews show the bot is operationally stable, but many actionable-looking drifts remain unexecuted because the candidate notional is just below the exchange minimum. Previous tasks added conservative guards to prevent bad orders; this task allows a bounded, configurable uplift when the delta is close enough to the executable floor.

## Scope

- Add a configurable uplift tolerance for candidate trades near the executable floor.
- Keep the default bounded and explicit through CLI/env config.
- Preserve existing hard guards for missing prices, missing filters, max notional, lot bounds, and non-near-floor deltas.
- Log pending/rejection details clearly when a delta is too far below the floor.

## TDD Contract

- RED: add a test proving a trade at 4.50 USDT can be uplifted to a 5.00 USDT executable floor when tolerance is 10%.
- RED: add a test proving a trade below that tolerance is still rejected.
- RED: add a test proving the tradability pre-check recognizes the same uplift rule.
- Command: `uv run pytest tests/test_portfolio.py -q`

## Acceptance

- Near-floor candidates can become executable orders only when within the configured tolerance.
- Candidates too far below the floor remain skipped.
- Existing tests still pass.
- Full verification passes with `uv run pytest`.

## Evidence

- RED: `uv run pytest tests/test_portfolio.py -q` failed with unexpected keyword argument for `min_notional_uplift_tolerance`.
- GREEN: `uv run pytest tests/test_portfolio.py -q` -> 15 passed.
- Focused app regression: `uv run pytest tests/test_portfolio.py tests/test_app_adaptive.py -q` -> 23 passed.
- Full verification: `uv run pytest` -> 41 passed.
- CLI check: `uv run app.py rebalance --help` lists `--min-notional-uplift-tolerance`.

## Risks

- Too high a tolerance can overtrade relative to target deltas.
- The default must stay conservative and easy to tune from environment/CLI.
