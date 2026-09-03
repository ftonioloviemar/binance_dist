# TASK-023: Tolerate OpenRouter null message content

## Objective

Prevent a malformed OpenRouter response with `message.content = null` from
failing the complete rebalance run. Treat it as an invalid model output so the
existing model fallback and audit path can continue.

## Context

The scheduled runs `81a67780` (2026-07-15) and `3b8872aa` (2026-08-29) ended
with `expected string or bytes-like object, got 'NoneType'` immediately after
the AI consultation step. The parser currently passes the response content
directly to `re.search()`.

## Scope

- Add a regression test for null/non-string OpenRouter content.
- Make the parser return an empty plan for null/non-string content.
- Preserve existing invalid-output classification and model fallback behavior.
- Do not change trading thresholds, live execution, or historical logs.

## TDD and verification

- RED: `uv run pytest tests/test_portfolio.py -q` with the new regression test
  failing at `re.search()`.
- GREEN: same focused test, then `uv run pytest`.
- Acceptance: null content produces `invalid_model_output` at the model-result
  boundary; the run does not raise `TypeError`; all existing tests pass.

## Risks and forbidden shortcuts

- Do not silently treat malformed content as a valid maintain/redistribute
  decision.
- Do not broaden the change into model curation or macro-source behavior.
- Do not run live trades, Earn mutations, or redeems for validation.

## Evidence and closure

- RED: `uv run pytest tests/test_portfolio.py -q` -> 1 failed, 15 passed;
  reproduced `TypeError` in `re.search()` with `content=None`.
- GREEN: `uv run pytest tests/test_portfolio.py -q` -> 16 passed.
- Full verification: `uv run pytest -q` -> 53 passed.
- The parser now rejects non-string content before regex parsing. The public
  fallback contract remains unchanged: if every model fails, proposed targets
  are retained and each failure is auditable.
