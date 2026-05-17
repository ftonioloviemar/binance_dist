---
id: TASK-007
title: OpenRouter event-driven model auto-curation
status: 05_done
kind: TDD implementation
---

# TASK-007 - OpenRouter event-driven model auto-curation

## Objective

Automatically refresh and reorder the free OpenRouter model list only when the first active model fails.

## Context

Daily full refresh is heavier than necessary. The approved design is event-driven: normal runs use the current first model; if that model fails, runtime falls back through the list, completes if possible, and then refreshes the free-model catalog for future runs.

## Completed Scope

- `portfolio.AIAdvice` now records `model_used`, `model_failures`, and `first_model_failed`.
- OpenRouter model failures are logged per model without stopping fallback execution.
- `openrouter_model_curator.py` refreshes the free model catalog, filters poor-fit models, ranks useful free text models, quarantines the failed primary model, and persists `state/openrouter_models.json`.
- `config.py` reads the persisted registry first, unless `OPENROUTER_MODELS_MODE=manual`.
- `app.py` triggers refresh only after the first model fails.
- `README.md`, `.env.example`, `.gitignore`, and `docs/openrouter-free-models.md` document the event-driven behavior.

## Evidence

- RED: focused tests failed for missing `openrouter_model_curator`, model telemetry, and app trigger.
- GREEN focused command passed:
  - `uv run pytest tests/test_portfolio.py::test_ai_refine_targets_records_first_model_failure_and_fallback_success tests/test_openrouter_model_curator.py tests/test_app_adaptive.py::test_rebalance_triggers_openrouter_refresh_when_primary_model_fails`
- Full suite passed:
  - `uv run pytest` -> 30 passed.
- Diff hygiene:
  - `git diff --check` passed with only Windows CRLF warnings.
- Dry-run:
  - `uv run python adaptive_bot_windows.py --test` completed successfully.
  - Latest run `0dc91349bece47d885519ab3153409cf` completed as DRY profile `conservative`.
  - Audit logged `ai_model_used | openrouter/owl-alpha`.
  - No `ai_model_failure` or `openrouter_model_refresh` was logged.
  - `state/openrouter_models.json` was not created, proving no heavy refresh ran when the first model worked.

## Follow-Up Observation

The pre-existing dry-run `final_balances` warning still repeats and should remain visible in the daily monitor.
