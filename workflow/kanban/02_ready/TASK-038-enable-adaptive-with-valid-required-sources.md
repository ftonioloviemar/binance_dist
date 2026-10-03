# TASK-038: Enable Adaptive With Valid Required Sources

## Objective

Allow the existing adaptive strategy when required macro sources are valid even if optional CoinGecko is unavailable; otherwise retain base profile and CLI settings with an auditable reason.

## Context

See `docs/market-insights.md`, `app.py`, and `adaptive_strategy.py`. This changes live adaptive availability, so preserve healthy-run behavior and all target precedence.

## Test Contract

- Tests: `tests/test_app_adaptive.py` and `tests/test_adaptive_strategy.py`.
- RED: optional-source errors currently suppress adaptive; stale/missing required sources must be shown to select fallback.
- Cover full/degraded/fallback cases, CoinGecko stale cache, BTC and Fear & Greed age/invalid bounds, explicit targets, and severe-drop check when cap change is unavailable.
- Command: `uv run pytest tests/test_app_adaptive.py tests/test_adaptive_strategy.py`.

## Acceptance And Constraints

- Healthy valid inputs produce current targets and profile.
- Only a fresh valid CoinGecko value participates in its existing severe-drop guard; BTC guard remains effective without it.
- No new indicator changes allocations. No live run for validation.
