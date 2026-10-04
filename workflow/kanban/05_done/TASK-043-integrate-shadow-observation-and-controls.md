# TASK-043: Integrate Shadow Observation And Controls

## Objective

Integrate bounded market observations and shadow evaluation into all relevant run outcomes, and provide an independent observability off switch.

## Context

See `docs/market-insights.md` and the run branches in `app.py`. Shadow data cannot enter live OpenRouter inputs, targets, sizing, or order decisions.

## Test Contract

- Tests: `tests/test_shadow_observation.py` and focused `tests/test_app_adaptive.py`.
- RED: no run-wide persistence point covers maintain/skip/error branches for this feature.
- Cover maintain/skipped/noop/blocked/completed/failed run finalization, dry-run, adaptive fallback, optional collector failure, collector deadline, independent switches, stable session/unique run identity, no extra OpenRouter calls, and no shadow writes to the financial DB.
- Command: `uv run pytest tests/test_shadow_observation.py tests/test_app_adaptive.py`.

## Acceptance And Constraints

- Shadow work uses only already-observed targets/advice and captured inputs.
- Errors are best-effort and cannot suppress or delay live strategy beyond the bounded deadline.
- Session identity is stable per quote (`shadow-<quote-lowercase>-v1`); use the audit run ID for each observation.
- `MARKET_CANDLE_COLLECTION_ENABLED` and `SHADOW_PORTFOLIO_SIMULATION_ENABLED` are independent, default-on switches. The collector is capped at 20 seconds; simulation has no separate hard wall-clock deadline and runs only after the live decision/execution path.
- User approved the separate `state/shadow_portfolios.db` and persistence of minimum virtual inventory derived from observed real balances. No raw exchange snapshot or credential persistence.
- No live validation.

## Implementation And Review Evidence

- RED: focused app test failed because the run audit had no `market_insights_observation` step; initial helper tests failed because the orchestration module did not exist.
- GREEN: `uv run pytest -q` -> 203 passed. Tests exercise independent switches, optional collection failure, deadline fail-closed behavior, cached read-only BTC volatility, app finalization, one existing advice call, stable session/audit run identity, and real simulator persistence into separate temporary DBs.
- `uv run python -m compileall -q app.py shadow_observation.py tests/test_shadow_observation.py tests/test_app_adaptive.py` passed.
- `git diff --check` passed (Git emitted only expected LF-to-CRLF working-copy notices for edited text files).
- Independent final audit by a standard specialist (`gpt-6-luna`, medium) found no P1/P2. Residual: no real-network timeout test, by design; some run branches share the tested finalizer rather than having separate end-to-end fixtures.
- No live trades, Simple Earn operations, or network calls were run.
