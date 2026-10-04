# Market Insights And Shadow Evaluation

## Purpose

This feature improves the reliability of existing macro inputs used by the adaptive strategy and evaluates additional public-market indicators without changing live targets. The volatility guard and all newly collected candle indicators are research-only until a separate strategy decision is documented and approved.

## Live Adaptive Data Contract

- Implemented by TASK-038: adaptive requires fresh, valid Fear & Greed and BTC source metadata; errors from optional CoinGecko do not by themselves suppress adaptive.
- Fear & Greed is required, must be an integer from 0 through 100, and must include a valid provider timestamp no more than 36 hours old. Missing provider time is invalid; collection time must not disguise an old observation.
- BTC 24-hour ticker is required, must have a positive price and finite change, and must have been collected no more than 15 minutes ago. Evaluate this freshness from local UTC collection time.
- CoinGecko global market-cap data is optional. A fresh response can participate in the existing severe-market-drop condition. A cached or absent value is identified with age/quality and is not substituted with zero.
- If either required source is absent, stale, or invalid, retain the selected base profile and CLI settings, and record an explicit fallback reason. If the required sources are valid but CoinGecko is not, adaptive remains eligible and is marked degraded.
- Preserve explicit-target precedence and the current live adaptive mapping. Healthy inputs must preserve the existing decision.

Every source observation is exposed in additive `MacroSnapshot.sources`, keyed by `fear_greed`, `btc_24h`, and `crypto_global`. Each value has `status` (`fresh`, `cached`, `missing`, or `invalid`), `observed_at` (provider time as ISO-8601 UTC or null), `collected_at` (local ISO-8601 UTC or null), `age_seconds` (nonnegative number or null), `cache_used` (boolean), and `error` (sanitized text or null). Existing `data` keys and `errors` remain available; the new metadata does not get injected into AI holdings context. CoinGecko age derives from its cache's collection timestamp when using cache. Do not persist secrets or account data in the market-data store.

## Shadow Market Data

Use public Binance daily klines for at most the six built-in risky assets BTC, ETH, SOL, BNB, AVAX, and ADA. If explicit targets include an unsupported asset, mark coverage incomplete for that run; never silently claim full-universe breadth. Cache observations in a separate market-insights SQLite database and collect only closed UTC daily candles. Request up to 92 candles per symbol so the metrics have history and gap-detection buffer. Collection is bounded by a 20-second overall deadline and must not hold up or fail the rebalance. Missing symbols or gaps invalidate only metrics requiring those observations and are reflected in coverage.

Calculate each metric from its own minimum contiguous UTC-daily window; a gap invalidates only windows that cross it:

- `return_1d`: latest close / prior close - 1; 2 consecutive closed candles.
- `return_7d`: latest close / close exactly 7 days earlier - 1; 8 consecutive closed candles.
- `return_30d`: latest close / close exactly 30 days earlier - 1; 31 consecutive closed candles.
- `vol30`: sample standard deviation (`ddof=1`) of the 30 latest daily log returns, `ln(close[i] / close[i-1])`; 31 consecutive closed candles. It is not annualized.
- `distance_sma30`: latest close / mean of the latest 30 closes - 1; the latest candle is included; 30 consecutive closed candles.
- `relative_quote_volume`: latest closed candle quote volume / mean quote volume of the preceding 30 closed candles; 31 consecutive closed candles and a positive denominator.

Candles are anchored by UTC daily open time and must be exactly 24 hours apart. Insufficient samples, gaps in the metric's required window, invalid source/input, and undefined denominators produce a null value with explicit metric coverage; they never become zero. Keep source status separate from per-metric coverage so an `incomplete` source can still provide a valid shorter window. Breadth is the fraction of the six-asset universe whose latest close is above its 30-close average; it is available only when all six SMA30 values are valid for the same latest UTC candle session. These are descriptive indicators, not calibrated probabilities of profit, and remain excluded from live targets and the live AI prompt.

Fear & Greed is a Bitcoin-focused contextual indicator. It is not an independent confirmation of broad altcoin sentiment. Attribute the source when rendering its classification.

## Shadow Scenarios And Limits

Start a shadow session at the first run with a complete pre-decision Spot/Earn snapshot and complete prices. Use exact captured quantities and the same closing/reference prices to seed separate hold, baseline, and `volatility_guard_v1` virtual portfolios. On each later complete run, value each virtual portfolio at that run's captured reference prices and feed all three policies the same targets and AI advice already observed in that live run. Compute drift independently against each policy's own virtual holdings; baseline uses that run's effective live drift threshold, and the candidate doubles it when BTC's 30-day daily-return volatility is at least 6%. A hold portfolio never trades or incurs modeled trading costs. Incomplete data pauses that session update and leaves affected return horizons `incomplete`; it does not restart or interpolate the session. These candidate values are experimental and configurable in shadow evaluation only.

Reuse targets and AI advice already produced by the live run. The result is conditional on that observed advice, not a complete counterfactual AI strategy. Do not add an OpenRouter call for this feature.

Each virtual policy maintains its own inventory across the session. Use the existing pure portfolio decision/planning rules and captured symbol filters where available. Model hypothetical orders as fully filled at the captured reference price, apply the modeled costs to each fill, sell before buys, and prevent negative inventory or quote balance. Reconcile Spot and Earn into one economic quantity per underlying asset, including matched LD aliases, without counting it twice. Assuming Earn inventory is immediately available is a simulation simplification and must be disclosed. Future yield and external flows are excluded; the result remains conditional on the sequence of live-run targets/advice and captured market inputs.

Default modeled costs are 0.10% fee plus 0.10% slippage per side; stress is 0.20% plus 0.20%. These are assumptions, not actual Binance costs. Present recorded execution commissions separately. Results must be labeled simulated and report net return, costs, turnover, drawdown, residual drift, executable/skipped trades, policy version, and data coverage. Incomplete required observations produce `incomplete` and null financial deltas; do not interpolate.

Persist versioned, idempotent observations and scenario results in `state/market_insights.db`. Reporting is read-only and reads this store; it must not fetch market data or mutate a shadow session. The collector and simulator have an independent off switch. The existing monitor remains every three days, reports only material changes, and does not activate a strategy.

## Evaluation And Activation

Review technical integrity after seven days and evaluate initial comparative evidence after 30 complete days. These are review intervals, not claims of statistical significance. A human strategy decision is required before enabling any new indicator or volatility guard for allocation decisions. Performance snapshots with incomplete quality remain excluded, and unknown realized costs/flows remain unattributed.

## References

- Binance Spot REST API, `GET /api/v3/klines`: https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md
- Alternative.me Fear & Greed Index: https://alternative.me/crypto/fear-and-greed-index/
