# TASK-037: Model Macro Source Quality

## Objective

Represent validity, freshness, timestamps, cache state, and sanitized errors for each existing macro source while preserving current `MacroSnapshot` callers.

## Context

See `docs/market-insights.md` and current `macro_context.py` contracts. This is a TDD behavior card.

## Test Contract

- Tests: `tests/test_macro_context.py`.
- RED: source freshness/validation metadata and required missing/invalid conditions are not currently represented.
- Cover valid, missing, malformed, stale, cached, and provider-error payloads; validate finite numeric values and Fear & Greed bounds.
- Preserve constructor compatibility for `MacroSnapshot(data, errors)` and existing data keys.
- Command: `uv run pytest tests/test_macro_context.py`.

## Acceptance And Constraints

- Implement the source metadata and validation contract from `docs/market-insights.md`.
- No secrets or portfolio data in persisted market context; no live trading behavior in this card.
