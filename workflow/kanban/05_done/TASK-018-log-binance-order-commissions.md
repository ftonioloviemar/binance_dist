# TASK-018 - Log Binance order commissions

## Objective

Make live order audit logs show the real Binance Spot commission returned by the exchange, so trade reviews can distinguish gross action from net cost.

## Context

Binance Spot order responses can include `fills` when `newOrderRespType=FULL`. Each fill may include `commission` and `commissionAsset`, which are the actual fee amount and asset charged for that fill.

## Scope

- Request `newOrderRespType=FULL` for live Spot orders.
- Summarize returned fill commissions by asset in the order audit detail.
- Keep dry-run logs unchanged.
- Keep logs bounded and avoid dumping full raw exchange responses into text logs.
- Document that commission visibility depends on Binance returning `fills`.

## TDD Contract

- RED: add a client test proving live `place_order` sends `newOrderRespType=FULL` by default.
- RED: add an execution test proving filled order `fills` commissions are aggregated in audit order detail.
- Command: `uv run pytest tests/test_binance_client.py tests/test_execution.py -q`

## Acceptance

- Live order placement asks Binance for a full order response.
- Audit order detail includes `commission=<amount> <asset>` when fills contain commission data.
- Multiple fills with the same commission asset are summed.
- Full suite passes.

## Evidence

- 2026-08-01: RED `uv run pytest tests/test_binance_client.py tests/test_execution.py -q` failed because `newOrderRespType` was missing and order detail only logged `clientOrderId`.
- 2026-08-01: GREEN `uv run pytest tests/test_binance_client.py tests/test_execution.py -q` -> 6 passed.
- 2026-08-01: `uv run pytest` -> 47 passed.

## Risks

- Some order states or Binance response types may not include `fills`; in that case logs must remain valid and not invent a fee.
- Commission can be charged in assets like BNB, base, or quote; aggregation must preserve the asset.
