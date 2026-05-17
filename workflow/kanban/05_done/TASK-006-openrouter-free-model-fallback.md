---
id: TASK-006
title: OpenRouter free model fallback list
status: 05_done
kind: TDD implementation
---

# TASK-006 - OpenRouter free model fallback list

## Objective

Replace the fixed three-model OpenRouter chain with an unlimited configurable free-model fallback list ordered from best to worst for this portfolio-refinement task.

## Context

The previous configured OpenRouter model IDs returned 404 during a dry-run on 2026-05-17:

- `mistralai/mistral-small-3.2-24b-instruct:free`
- `deepseek/deepseek-chat-v3.1:free`
- `openrouter/polaris-alpha`

## Completed Scope

- Added `OPENROUTER_MODELS` as the preferred comma/semicolon/newline-separated fallback list.
- Kept `MODEL_NAME`, `MODEL_FALLBACK`, and `MODEL_SECOND_FALLBACK` as backwards-compatible inputs when `OPENROUTER_MODELS` is absent.
- Added ordered default free model list in `config.py`.
- Updated local `.env`, `.env.example`, `README.md`, and `docs/openrouter-free-models.md`.
- Created daily heartbeat automation `monitor-diario-binance-dist`.

## Evidence

- RED: `uv run pytest tests/test_config.py` failed because `openrouter_models` did not exist.
- GREEN: `uv run pytest tests/test_config.py` passed with 4 tests.
- Full suite: `uv run pytest` passed with 25 tests.
- Diff hygiene: `git diff --check` passed; only Windows CRLF warnings were emitted.
- Dry-run: `uv run python adaptive_bot_windows.py --test` completed successfully without OpenRouter 404 warnings.
- Audit proof: latest dry-run `3e2ece846567476abe3bbf3cc183153b` completed as DRY profile `conservative`.
- Audit proof: `ai_consult` logged `Consulting 24 AI model(s) on consolidated holdings`.

## Follow-Up Observation

The dry-run still logs `final_balances | failed | Unable to compute weights for an empty portfolio`. This is not part of the OpenRouter fix, but the daily monitor should flag it if it repeats.
