# TASK-020 - Harden OpenRouter free-model curation

## Objective

Prevent invalid, non-free, or unvalidated models from becoming the primary OpenRouter fallback.

## Context

Recent audits found one 404, one 429, and invalid structured-output responses. The generated registry also contained models that were not validated in the promotion window.

## TDD Contract

- RED: candidate ranking/promotion tests fail until unvalidated candidates are excluded from the promoted prefix and non-free candidates are excluded.
- Verification: `uv run pytest tests/test_openrouter_model_curator.py -q` and `uv run pytest`.

## Acceptance

- Only zero-priced text input/output candidates are considered.
- Only candidates that pass the structured JSON probe can enter the validated active prefix.
- Existing fallback and quarantine behavior remains intact.
- No live trade or Earn operation is used for validation.

## Risks

Over-filtering can leave too few models; retain the existing configured chain as a safe fallback when the catalog/probe is unavailable.

## Evidence

- RED: `uv run pytest tests/test_openrouter_model_curator.py -q` -> 1 failed, 3 passed; the failure showed an untested model remained active after a valid probe.
- GREEN: `uv run pytest tests/test_openrouter_model_curator.py -q` -> 4 passed.
- Full verification: `uv run pytest` -> 50 passed.
