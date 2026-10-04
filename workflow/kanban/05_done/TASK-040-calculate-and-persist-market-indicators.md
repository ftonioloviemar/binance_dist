# TASK-040: Calculate And Persist Market Indicators

## Objective

Calculate descriptive multi-horizon market indicators from validated closed candles and persist versioned observations with coverage.

## Context

See `docs/market-insights.md` and `TASK-039`. Do not expose these indicators to live adaptive targets or the live AI prompt.
Application-run collection and invocation are intentionally handled by `TASK-043`; this card owns the pure calculator and durable persistence contract.

## Test Contract

- Tests: new `tests/test_market_insights.py` and isolated temporary SQLite tests.
- RED: the candle-derived metric calculator and durable observation contract do not yet exist; prove the test fails for the missing behavior before adding production code.
- `return_1d = latest / prior - 1` needs 2 consecutive closed daily candles; `return_7d = latest / close 7 UTC days earlier - 1` needs 8; `return_30d = latest / close 30 UTC days earlier - 1` needs 31.
- `vol30` is the sample standard deviation (`ddof=1`) of the latest 30 daily log returns and needs 31 consecutive closes; it is not annualized.
- `distance_sma30 = latest close / mean(latest 30 closes) - 1`, including the latest close, and needs 30 consecutive candles.
- `relative_quote_volume = latest quote volume / mean(previous 30 closed-candle quote volumes)` and needs 31 candles with a positive denominator.
- Each metric uses only its own latest contiguous window. Gaps invalidate only metric windows they cross. Missing/short samples, unavailable/invalid source, and undefined calculations yield null values with explicit quality, never fabricated zeros.
- Breadth is above-SMA30 count / 6, and is available only if all six supported assets have valid SMA30 values on the same latest UTC candle session.
- Keep source status separate from per-metric status. Persist versioned observations in the existing market-insights SQLite database without touching `performance.db`; persist decimal values as strings and fail closed on an unknown schema version.
- Use a separate algorithm/metrics version and deterministic input fingerprint (canonical candle values/timestamps plus source quality; exclude collection time) as the idempotency key. Repeated identical inputs must not create duplicate observations; changed values or quality must produce a distinct observation.
- Cover window calculations, exact minimum sample sizes, gaps localized by metric, open-candle/UTC boundaries, precision, breadth coverage, source quality, idempotency, persistence/reopen, and unknown database versions.
- Command: `uv run pytest tests/test_market_insights.py`.

## Acceptance And Constraints

- Insufficient data is explicit and cannot become zero or a valid signal.
- Preserve numeric precision; use only public market observations and mocked fixtures in tests.
- Indicators are descriptive/shadow-only; do not add them to live adaptive targets or the live AI prompt.
- Human decision recorded: use minimum contiguous sample sizes per metric (2/8/31 candle closes for 1d/7d/30d returns; 31 for vol30; 30 for SMA30; 31 candles for relative quote volume). Gaps invalidate only affected metric windows.
- Implementation choice: schema version is independent from metrics version; unsupported schema versions fail safely rather than being reset or destructively recreated.

## Verification Evidence

- RED before implementation: `uv run pytest tests/test_market_insights.py -q` failed during collection because `market_insights` did not exist.
- RED regression: after adding structural-invalid-input cases, focused tests failed because one malformed candle invalidated unrelated windows; a separate RED case caught invalid source quality mislabeled as unavailable.
- GREEN focused: `uv run pytest tests/test_market_insights.py -q` -> 20 passed.
- GREEN isolated full suite: `uv run --project C:\python\binance_dist pytest C:\python\binance_dist\tests -q --basetemp <temporary-directory>` from a disposable working directory -> 168 passed.
- `uv run python -m compileall -q market_insights.py market_candles.py` and `git diff --check` passed.
- No live exchange/network requests; temporary SQLite persistence tests only. Runtime invocation remains an explicit acceptance item for `TASK-043`.
- Independent Luna-medium result audit: no remaining findings; confirmed the TASK-040/TASK-043 responsibility split and verified focused/full-suite results.
