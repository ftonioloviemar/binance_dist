# TASK-045: Preserve Binance API Error Details

## Objective

Keep safe, structured Binance error information when signed API calls fail so
Simple Earn audits distinguish exchange-side causes instead of recording only
an empty HTTP 400 message.

## Context

Recent audits show intermittent HTTP 400 responses from Simple Earn redeem and
subscribe, followed by successful runs. The current `_request` parses JSON only
for timestamp error detection, then `raise_for_status()` discards the exchange
diagnosis. The original response body was not persisted, so the historic cause
cannot be proven.

## Scope

- Modify `binance_client.py` to raise a typed Binance API exception retaining
  HTTP status and safe `code`/`msg` fields.
- Ensure `str(exception)` is suitable for app audit details and never includes
  request URL/query, signature, API key, request parameters, or raw response.
- Preserve current timestamp-sync and HTTP 418/429 retry behavior.
- Add focused tests in `tests/test_binance_client.py`; add audit-propagation
  coverage only if existing test seams allow it without broad refactoring.
- Do not change retry policy, trading behavior, or Simple Earn request fields
  in this card.

## Test contract

- RED: fake HTTP 400 with `{"code":-6009,"msg":"Request frequency too high"}`
  raises a typed error whose rendered detail includes HTTP 400, `-6009`, and
  the message.
- RED: the same detail excludes the full URL, `signature`, fake signature
  value, API key, request values, and an extra canary field in the raw body.
- RED: normalize control characters, redact URL/credential-like text, and
  cap the surfaced message at 160 characters.
- RED: malformed/non-JSON HTTP errors still produce a useful status-only
  exception, not a JSON parsing error.
- Cover all non-2xx responses with a status-only 503 case; the last 429 after
  existing retries must produce the typed error.
- Add regression tests proving -1021 still triggers timestamp sync/retry and
  418/429 retain their current retry behavior (patch sleep; no network).
- Verify audit/pending propagation for `earn_redeem` if the existing test seam
  permits it without production refactoring; `earn_subscribe` uses the same
  `str(exc)` path and should be covered if the seam is similarly small.

## Verification

- Focused: `uv run pytest tests/test_binance_client.py -q`
- Full: `uv run pytest -q`
- Mocked sessions only; no network/exchange calls.

## Acceptance and closeout

- Coordinator reviews the patch and verification output.
- Independent result auditor confirms no sensitive data leakage and checks
  retry behavior for regressions.
- Move this card to `workflow/kanban/05_done/` and commit the completed card
  before beginning TASK-046.

## Risks

- Exchange error messages are untrusted text; bound and sanitize message length
  before including them in persistent audit logs.
- Do not infer a fixed retry delay for `-6009`; the local evidence does not
  record the code and the project has no verified endpoint-specific retry rule.

## Status

Done; independently audited and ready to commit.

## Verification Evidence

- RED: `uv run pytest tests/test_binance_client.py -q` -> 4 failed, 9 passed;
  failures asserted that the generic error lacked `BinanceAPIError` diagnostics.
- Focused GREEN: `uv run pytest tests/test_binance_client.py tests/test_app_adaptive.py -q`
  -> 41 passed.
- Full GREEN: `uv run pytest -q` -> 223 passed.
- Error details are limited to HTTP status, valid integer Binance code, and a
  160-character normalized message with URL and credential-like fields
  redacted; response body and request URL are not attached.
- Timestamp `-1021` and 418/429 retry behavior is explicitly tested with fake
  sessions and patched sleep. No live exchange calls were made.
- Independent clean-context test-contract specialist reviewed the scenarios
  and recommended explicit retry/status/message-bound assertions; these were
  incorporated before implementation.
- Independent result audit found and drove closure of two sanitizer gaps:
  echoed scalar credentials/request values and `doseq`-encoded sequence
  elements. A second audit of the updated implementation found no further
  findings. Tuple/set/nested-mapping paths are implemented but not separately
  exercised; the production request path uses a list canary.
