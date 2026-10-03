# TASK-037: Model Macro Source Quality

## Objective

Represent validity, freshness, timestamps, cache state, and sanitized errors for each existing macro source while preserving current `MacroSnapshot` callers.

## Context

See `docs/market-insights.md` and current `macro_context.py` contracts. This is a TDD behavior card.

## Test Contract

- Tests: `tests/test_macro_context.py`.
- RED: source freshness/validation metadata and required missing/invalid conditions are not currently represented.
- Metadata contract: additive `MacroSnapshot.sources` map keyed by `fear_greed`, `btc_24h`, and `crypto_global`; each value has `status`, `observed_at`, `collected_at`, `age_seconds`, `cache_used`, and sanitized `error`. UTC timestamps are ISO-8601; missing values and unknown age are null.
- Statuses: successful valid response is `fresh`; valid in-TTL CoinGecko fallback is `cached`; unavailable source without usable cache is `missing`; malformed, out-of-range, non-finite, or future-dated payload is `invalid`.
- Fear & Greed requires nonempty rows, integer value 0..100, nonempty classification, and valid Unix provider timestamp no older than 36 hours.
- BTC ticker requires positive finite price and finite 24h change; `collected_at` is local UTC collection time. Decision-time 15-minute expiry is enforced in TASK-038, not this loader.
- CoinGecko `market_cap_usd` must be positive finite, `market_cap_change_24h` finite, and `btc_dominance` finite in 0..100 for a fresh/cached market-cap observation. In-TTL cache is `cached`, never `fresh`; expired/future-dated or malformed cache is unusable.
- Cover valid, missing, malformed, stale, cached, and provider-error payloads; check that diagnostics never echo a URL query or credential-like value from exception text.
- Preserve constructor compatibility for `MacroSnapshot(data, errors)` and existing data keys.
- Keep adaptive eligibility/fallback out of this card; `errors` compatibility remains while source quality metadata is added.
- Command: `uv run pytest tests/test_macro_context.py`.

## Acceptance And Constraints

- Implement the source metadata and validation contract from `docs/market-insights.md`.
- No secrets or portfolio data in persisted market context; no live trading behavior in this card.
- A clean-context test-contract review was completed with Luna medium before implementation.

## Verification Evidence

- RED before implementation: focused suite reported 14 failures because source metadata/validation did not exist; 2 pre-existing cache tests passed.
- Independent audit found and reproduced a Bearer-token redaction gap; added a regression test, fixed header sanitization, and separately classify malformed Fear & Greed schema.
- GREEN: focused `uv run pytest tests/test_macro_context.py -q` -> 26 passed; isolated full suite `uv run --project C:\python\binance_dist python -m pytest C:\python\binance_dist\tests -q --basetemp <temporary-directory>` -> 108 passed.
- Test fixtures mock every external request.
- No exchange-account, trading, or Earn operations were executed. Full suite ran with a temporary working directory so relative state/log writes remained isolated.
- Independent result audit: approved after fixing Bearer credential leakage and validating malformed UTF-8 cache handling; schema-invalid F&G and empty F&G observations remain distinct.
