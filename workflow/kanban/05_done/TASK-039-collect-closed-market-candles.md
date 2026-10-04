# TASK-039: Collect Closed Market Candles

## Objective

Collect public Binance daily klines for a bounded configured universe with daily caching, closed-candle filtering, and strict time/request limits.

## Context

See `docs/market-insights.md` and official REST documentation linked there. Keep this collector independent from exchange trading clients and execution methods.

## Test Contract

- Tests: new `tests/test_market_candles.py`; injectable HTTP getter, UTC clock, monotonic clock, and SQLite path.
- RED: no bounded historical candle collector or cache contract exists.
- Module/API: `market_candles.py` exposes immutable candle/source result types and a public `collect_market_candles(...)`; it must not import or call `BinanceClient` or portfolio/order methods.
- Source universe: allowlist base assets BTC, ETH, SOL, BNB, AVAX, ADA, mapped only to `*USDT`; deduplicate; never make more than six HTTP requests. Unsupported assets are returned as explicit unsupported/incomplete evidence and are not queried.
- Binance request: public `GET https://data-api.binance.vision/api/v3/klines`, with `interval=1d`, UTC default timezone, and `limit=92`. The official response identifies open time at index 0, close time at 6, close at 4, base volume at 5, quote volume at 7; parse only needed fields with strict finite/positive/shape checks. Do not parse a partial row into zero.
- UTC cutoff: inject `now`; retain a candle only when its millisecond `close_time` converts to UTC and is strictly less than `now`. Exclude the still-open daily candle, including equality at the cutoff. Require a UTC-midnight open and expected daily close boundary; sort by open time and do not fill gaps.
- Mixed valid/malformed response: keep validated rows, mark that symbol `incomplete`, include a sanitized reason, and never claim full coverage. Empty, all-invalid, missing, HTTP/JSON/timeout failures are distinguishable as `missing`, `invalid`, or `unavailable`/`timeout` evidence.
- Cache: default `state/market_insights.db`; injectable temporary DB for tests. Cache freshness/refresh day is UTC. At most one refresh attempt per symbol per UTC day (including failures, to avoid repeated upstream retries); same-day reads avoid HTTP. Next UTC date refreshes. Upsert by `(symbol, open_time_ms)`; duplicates do not multiply rows. A failed/partial refresh never deletes prior valid candles; if prior candles are returned, mark them `cached`/stale with the current refresh error, not fresh. Do not reset a corrupted or unknown-version DB.
- Persist only valid closed candles and bounded history sufficient for the 92-candle fetch; keep response quality/refresh metadata sufficient for TASK-040 to distinguish fresh, cached, incomplete, and unavailable data. DB failures are source-quality evidence and do not escape the collector.
- Deadline: one monotonic 20-second budget for all symbol requests and cache work; each HTTP timeout is capped by remaining budget, no new request starts after expiry, and uncollected symbols are marked timeout/incomplete. Inject clock/transport to test global budget without sleeping.
- Cover request parameters, parser/row validation, close boundary (before/equal/after), cache hit and UTC-day refresh, failed refresh retaining cache, malformed/empty/duplicate/gapped rows, unsupported assets and six-symbol bound, request/JSON/DB errors, and global deadline. Every network test uses a mock; no live exchange/account access.
- Command: `uv run pytest tests/test_market_candles.py`.

## Acceptance And Constraints

- At most six symbols, daily refresh, closed candles only, 20-second overall deadline.
- Collector failure returns source-quality evidence and never prevents rebalance.
- Unit tests mock the network; no live exchange account calls.
- Clean-context Luna-medium TDD contract review completed. It identified cache freshness, result metadata, malformed/partial rows, gap, and global-deadline semantics; the test contract above resolves these for TASK-040 integration.

## Implementation And Verification

- Added `market_candles.py`, isolated from trading clients. It requests the public Binance market-data endpoint, parses daily OHLCV into `Decimal`, enforces UTC daily boundaries and strict close-time cutoff, preserves gaps, and records per-asset quality.
- Added idempotent `market_candles` and `market_candle_refreshes` tables in the dedicated market-insights SQLite database; history is bounded to 92 candles per symbol. UTC-day refresh attempts are cached, and failed/partial refreshes retain prior valid candles with explicit cached/incomplete quality.
- Network requests run in a daemon worker bounded by the remaining global monotonic deadline; timed-out workers cannot write to the database. Database/network/parser errors return source evidence rather than raising to callers.
- RED: `uv run pytest tests/test_market_candles.py -q` initially failed collection because `market_candles` did not exist. Independent audit then found deadline cap, timeout-attempt persistence, and post-parse persistence gaps; focused regression tests reproduced each before fixes.
- Focused verification: `uv run pytest tests/test_market_candles.py -q` -> 21 passed.
- Full isolated suite: `uv run --project C:\python\binance_dist python -m pytest C:\python\binance_dist\tests -q --basetemp <temp>` -> 148 passed.
- `uv run python -m compileall -q market_candles.py` and `git diff --check` passed. All HTTP tests mock the transport; no live exchange/account access and no financial database writes.
- First independent audit's P1/P2 findings were addressed: maximum deadline is 20s, each UTC-day attempt is reserved before network access (including timeout), and a deadline observed after parse rolls back candle writes. Added tests for parse overrun, no same-day retry, corrupted DB preservation, and partial refresh preservation.
- Final independent audit found no deadline or persistence violation. It requested an explicit assertion that a late worker cannot write after return; the test now waits for worker completion and verifies candle count remains zero.
- Final focused verification after audit feedback: 21 passed; full isolated suite: 148 passed. No live exchange calls or operational database writes.
