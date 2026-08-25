# Lessons Learned

This document records reusable engineering and operational lessons from the Binance rebalancer. It is evidence-based guidance, not a substitute for current exchange rules or a strategy decision.

## Do

- Inspect audit logs before changing strategy parameters. Automatic reviews overlap their 12-run windows, so compare dates and run IDs instead of summing report totals.
- Validate the executable delta per symbol. A global drift threshold is not enough because `NOTIONAL`, `LOT_SIZE`, price, and available balance differ by symbol.
- Keep uplift bounded. Use it only for deltas close to the exchange floor; do not inflate a small target correction into a fee-inefficient order.
- Classify below-floor deltas as non-actionable and record them in `trade_floor`. Reserve `pendings` for conditions that require execution retry or investigation.
- Treat external market sources as unreliable dependencies. Preserve the last valid snapshot with an explicit stale flag and age, while retaining the original timeout or `429` error in the audit.
- Persist fallback state when the scheduler starts a new process. In-memory caches do not survive Windows Task Scheduler runs.
- Validate every promoted OpenRouter model with the exact structured JSON contract used by the portfolio flow. Do not promote untested catalog entries merely because they are listed as free.
- Quarantine models after `404`, repeated `429`, or invalid output, and keep the existing configured chain as a safe fallback if curation cannot produce a valid registry.
- Use `FULL` Binance order responses and record fill commissions by asset. Fees must come from exchange execution data, not estimates inferred from configuration.
- Use unit tests, log replay, and dry-run for changes. Add targeted tests when a normal dry-run takes the `maintain` path and therefore does not exercise trade planning.
- Complete each kanban card independently: move its file between state directories, record RED/GREEN/full verification evidence, commit, and only then start the next card.

## Do Not

- Do not treat `skipped` as proof that the strategy is profitable. It proves only that no trade was executed under the current guards.
- Do not treat repeated `NOTIONAL` messages as evidence that the bot should buy more. First determine whether the delta is economically executable after fees and lot rounding.
- Do not rely on a single macro provider or let a provider timeout silently change allocation behavior.
- Do not put untested, stale, or semantically incompatible free models at the top of an automatic fallback list.
- Do not call an in-process cache a scheduler-safe solution.
- Do not validate code by sending live trades, redeeming Simple Earn positions, or subscribing products.
- Do not rewrite historical logs to make an audit look clean; fix classification and preserve the original evidence.
- Do not infer return or gain from order count. Evaluate net return, fees, turnover, residual drift, and time in stable assets over a defined observation window.

## Operational Checklists

### Before a strategy change

1. Confirm the observed symptom in recent audit runs.
2. Calculate the per-symbol executable floor and expected fee impact.
3. Define the smallest parameter or code change that addresses the symptom.
4. Add a regression test and observe the RED failure.
5. Validate with full tests, dry-run, and audit replay.
6. Observe at least seven days before judging practical effect.

### Before trusting an AI fallback change

1. Check model availability and zero pricing in the current catalog.
2. Probe the exact JSON/action/target contract.
3. Verify fallback after simulated `404`, `429`, timeout, and invalid output.
4. Confirm the selected model and failure reason are present in the audit.
5. Keep deterministic portfolio guardrails independent of AI advice.

### Before closing an incident

1. Separate source failure from strategy decision.
2. Record whether the data was fresh or stale.
3. Confirm no live mutation occurred during validation.
4. Add a durable rule or test if the failure can recur.
5. State residual risk and the next observation window.

## Current Follow-Up

- Continue observing the 3% drift and per-symbol floor filter for seven days.
- Monitor whether the persistent CoinGecko cache is reused and marked stale during outages.
- Monitor whether OpenRouter promoted models continue to return valid structured output without repeated fallback.
- Measure net return, commission, turnover, executed order count, non-actionable floor events, and residual drift before changing allocation targets.
