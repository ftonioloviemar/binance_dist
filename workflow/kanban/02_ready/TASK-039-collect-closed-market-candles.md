# TASK-039: Collect Closed Market Candles

## Objective

Collect public Binance daily klines for a bounded configured universe with daily caching, closed-candle filtering, and strict time/request limits.

## Context

See `docs/market-insights.md` and official REST documentation linked there. Keep this collector independent from exchange trading clients and execution methods.

## Test Contract

- Tests: new `tests/test_market_candles.py`.
- RED: no bounded historical candle collector exists.
- Cover response parsing, UTC close-time cutoff, cache hit/refresh, malformed rows, gaps, request errors, six-symbol cap, and timeout/deadline.
- Command: `uv run pytest tests/test_market_candles.py`.

## Acceptance And Constraints

- At most six symbols, daily refresh, closed candles only, 20-second overall deadline.
- Collector failure returns source-quality evidence and never prevents rebalance.
- Unit tests mock the network; no live exchange account calls.
