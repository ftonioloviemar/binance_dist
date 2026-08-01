# TASK-017 - Add anti-churn cooldown for opposite trades

## Objective

Prevent avoidable buy/sell reversals on the same symbol in short windows when drift is not large enough to justify paying spread, slippage, and Spot trading fees again.

## Context

Recent live logs showed BTC/SOL trades reversing direction in less than 12 hours. The trades were technically successful, but this pattern can reduce net results through exchange fees, spread, and slippage.

## Scope

- Add a configurable anti-churn cooldown for same-symbol opposite-side trades.
- Default policy: block opposite-side trades within 12 hours unless current absolute drift is greater than 2x the active drift threshold.
- Use only local audit logs for the cooldown decision.
- Log blocked trades as `anti_churn`/pending evidence.
- Do not call Binance, Simple Earn, or OpenRouter for validation.

## TDD Contract

- RED: add a unit test proving an opposite-side trade inside cooldown is blocked.
- RED: add a unit test proving a same-side trade is not blocked.
- RED: add a unit test proving large drift bypasses the cooldown.
- RED: add an app-level test proving blocked trades do not trigger execution.
- Command: `uv run pytest tests/test_anti_churn.py tests/test_app_adaptive.py -q`

## Acceptance

- Same-symbol opposite-side churn is blocked inside the configured window.
- Legit same-side trades and large-drift corrective trades still execute.
- Audit evidence shows why a trade was blocked.
- Full suite passes.

## Evidence

- 2026-08-01: `uv run pytest tests/test_anti_churn.py tests/test_app_adaptive.py -q` -> 12 passed.

## Risks

- A cooldown that is too strict can delay useful rebalancing after a real market move.
- Historical log parsing must fail closed only for the specific symbol/window, not disable all trading.
