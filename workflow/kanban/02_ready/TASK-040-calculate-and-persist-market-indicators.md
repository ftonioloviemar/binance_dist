# TASK-040: Calculate And Persist Market Indicators

## Objective

Calculate descriptive multi-horizon market indicators from validated closed candles and persist versioned observations with coverage.

## Context

See `docs/market-insights.md` and `TASK-039`. Do not expose these indicators to live adaptive targets or the live AI prompt.

## Test Contract

- Tests: new `tests/test_market_insights.py` and isolated temporary SQLite tests.
- RED: current macro data lacks the approved candle-derived metrics and durable observation contract.
- Cover 1/7/30-day returns, 30-day sample volatility, moving-average distance, relative quote volume, breadth coverage, gaps, insufficient samples, UTC boundaries, idempotency, and database versioning.
- Command: `uv run pytest tests/test_market_insights.py`.

## Acceptance And Constraints

- Insufficient data is explicit and cannot become zero or a valid signal.
- Preserve numeric precision; use only public market observations and mocked fixtures in tests.
