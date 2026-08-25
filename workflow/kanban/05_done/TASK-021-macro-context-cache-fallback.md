# TASK-021 - Add stale-cache fallback for CoinGecko macro data

## Objective

Keep macro context usable when CoinGecko times out or returns `429`, while explicitly exposing stale data.

## Context

CoinGecko failures recur across automatic reviews. Binance ticker and Fear & Greed are independent sources and must continue to load normally.

## TDD Contract

- RED: tests fail until a recent valid CoinGecko snapshot is reused after an upstream failure and stale metadata is exposed.
- Verification: `uv run pytest tests/test_macro_context.py -q` and `uv run pytest`.

## Acceptance

- Cache is bounded by a configurable freshness window with a conservative default.
- Failed refresh remains visible in `MacroSnapshot.errors`.
- Stale context includes age/flag and never masquerades as fresh data.
- No live trade or Earn operation is used for validation.

## Risks

Stale macro data can influence adaptive decisions; explicit stale metadata and audit logging must make that condition visible.

## Evidence

- RED: `uv run pytest tests/test_macro_context.py -q` -> 2 failed; cache behavior and the time source did not exist.
- GREEN: `uv run pytest tests/test_macro_context.py -q` -> 2 passed.
- Full verification: `uv run pytest` -> 52 passed.
