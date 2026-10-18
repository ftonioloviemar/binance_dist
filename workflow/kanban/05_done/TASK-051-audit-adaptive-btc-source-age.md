# TASK-051: Audit Adaptive BTC Source Age

## Objective

Record enough safe timing evidence in `adaptive_strategy` audit details to diagnose required `btc_24h` freshness fallbacks.

## Context

Audits on 2026-10-17 21:00 and 2026-10-18 09:00 reported `btc_24h collection is outside 0..15m`. The current audit records the reason but not the collection timestamp, decision timestamp, or computed age. Investigation found that the collector timestamps the successful BTC ticker response with `time.time()` and the adaptive assessor compares it with `datetime.now(UTC)`; the normal code path has no intentional delay between those operations. Historical cause is not proven by existing logs.

See `docs/superpowers/plans/2026-10-18-adaptive-btc-freshness-audit.md`, `workflow/kanban/05_done/TASK-037-model-macro-source-quality.md`, and `workflow/kanban/05_done/TASK-038-enable-adaptive-with-valid-required-sources.md`.

## Scope

- Include UTC BTC `collected_at`, UTC assessment/decision time, and signed computed age in adaptive audit details for applied, fallback-warning, and calculation-failure outcomes.
- Represent missing/unparseable collection time explicitly; do not echo untrusted raw timestamp text.
- Preserve the 0..15 minute eligibility gate and existing fallback/configuration semantics.
- Do not change scheduled tasks, strategy parameters, source collection, or external integrations.

## Test Contract

- Tests: `tests/test_app_adaptive.py`.
- RED: a stale-BTC audit currently contains the fallback reason but lacks the two timestamps and computed age.
- Assert a deterministic 16-minute-stale input records `btc_age_seconds=960.000` and both UTC timestamps.
- Assert stale/future data remains unavailable and the configured base profile/settings remain intact.
- Assert successful adaptive audit records the same timing fields.
- Command: `uv run pytest tests/test_app_adaptive.py tests/test_adaptive_strategy.py -q`.

## Acceptance And Constraints

- No change to strategy output, 15-minute boundary, or fallback behavior.
- No account/portfolio details or provider payloads in timing diagnostics.
- No live Binance, Simple Earn, or OpenRouter calls.
- Full verification: `uv run pytest`, compileall for touched Python files, and `git diff --check`.

## Status

- Complete.
- Baseline: clean `master` at `0c9323a`; rollback point is the committed baseline.
- Disk check: approximately 62.7 GB free on C:.
- RED: new assessment and audit assertions failed because timing diagnostics were absent.
- Focused verification: `uv run pytest tests/test_app_adaptive.py tests/test_adaptive_strategy.py -q` -> 33 passed.
- Full verification: `uv run pytest` -> 280 passed; `uv run python -m compileall -q app.py` and `git diff --check` passed.
- The 15-minute boundary, config fallback, and targets are unchanged; no live operations or external calls were made.
