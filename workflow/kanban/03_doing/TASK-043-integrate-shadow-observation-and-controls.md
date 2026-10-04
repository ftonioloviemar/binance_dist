# TASK-043: Integrate Shadow Observation And Controls

## Objective

Integrate bounded market observations and shadow evaluation into all relevant run outcomes, and provide an independent observability off switch.

## Context

See `docs/market-insights.md` and the run branches in `app.py`. Shadow data cannot enter live OpenRouter inputs, targets, sizing, or order decisions.

## Test Contract

- Tests: focused `tests/test_app_adaptive.py` plus a new integration test module if needed.
- RED: no run-wide persistence point covers maintain/skip/error branches for this feature.
- Cover maintain, skipped, dry-run, adaptive fallback, optional collector failure, hard deadline, off switch, no additional OpenRouter calls, and no writes to financial DB.
- Command: `uv run pytest tests/test_app_adaptive.py` plus the new focused integration test.

## Acceptance And Constraints

- Shadow work uses only already-observed targets/advice and captured inputs.
- Errors are best-effort and cannot suppress or delay live strategy beyond the bounded deadline.
- No live validation.
