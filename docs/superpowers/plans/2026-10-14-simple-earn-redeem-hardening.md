# Simple Earn Redeem Hardening Plan

## Objective

Make Flexible Simple Earn redemption failures actionable in local audits and
align the outgoing request with Binance's current documented contract without
testing against a live account.

## Evidence and boundaries

- Recent local audits include one run with repeated HTTP 400 responses from
  Flexible redeem and subscribe, followed by runs that completed those steps.
  A sanitized local aggregation across seven runs found three runs with partial
  failures (18/18 redeems plus 2 subscribe failures; 14/18 redeems; and 3
  subscribe failures); recent runs then completed. These counts establish
  recurrence, not the specific exchange cause.
- The current client discards the Binance error JSON when `raise_for_status()`
  raises, so historical logs cannot identify the exchange error code/message.
- Current Binance documentation describes Flexible Redeem parameters as
  `productId`, `amount` (unless `redeemAll=true`), and `destAccount` (default
  `SPOT`); it does not document `type=FAST|STANDARD`.
- No live exchange call, redemption, subscription, or trade is permitted for
  implementation or verification.
- Keep timestamps/signatures private. Never log request parameters, URL query,
  API key, signature, raw response body, or account holdings.

## Execution

### TASK-045: preserve structured Binance API errors

1. Add a failing test for an HTTP error response containing a Binance `code`
   and `msg`; expect the raised exception and app audit detail to retain the
   HTTP status and exchange diagnosis, but not URL, signature, request values,
   or raw body.
2. Run the focused test and confirm it fails because the current code only
   raises a generic HTTP exception.
3. Add a small typed exception in `binance_client.py`; parse error payloads
   defensively and expose only status, numeric code when valid, and message
   text normalized for controls, credential/URL-redacted, and capped at 160
   characters. Cover timestamp-sync and 418/429 retry behavior explicitly.
4. Verify focused client/audit tests and the full suite. Do not add guessed
   retry delays for Simple Earn-specific codes.
5. Have an independent specialist audit the diff and test evidence, then move
   this card to `05_done` and commit it.

Status: implementation complete and independently audited; focused tests 41
passed; full suite 223 passed. Commit TASK-045 before starting TASK-046.

### TASK-046: align Flexible Redeem parameters with current API docs

1. Add a failing request-construction test that fixes the expected form fields:
   `productId`, formatted `amount`, explicit `destAccount=SPOT`, timestamp,
   `recvWindow`, and signature; assert that undocumented `type` is absent.
2. Resolve how the legacy `SIMPLE_EARN_FAST_REDEEM` setting and `fast` function
   argument are handled. The current Binance endpoint documentation does not
   expose a FAST/STANDARD selector, so do not silently claim that this setting
   still controls exchange behavior.
3. Implement the smallest backwards-safe interface change and make any
   unsupported legacy setting visible in run diagnostics/documentation.
4. Verify request construction with mocked sessions, focused tests, and the
   full test suite. No live calls.
5. Have an independent specialist audit the diff and test evidence, then move
   this card to `05_done` and commit it.

Status: complete; TASK-045 and TASK-046 independently audited and committed
separately. Final full suite: 228 passed. The legacy argument/env setting are
retained for compatibility but explicitly marked ineffective and omitted from
the API payload. The historical 400 root cause remains unknown pending a
future failure with captured structured diagnostics.

## Acceptance

- A Binance API failure appears in `earn_redeem` audit with enough safe detail
  to distinguish e.g. `-6009` frequency rejection from product/amount errors.
- Diagnostics contain no signed URL, signature, API key, raw response body,
  balances, or holdings.
- Flexible Redeem request fields match the current official documentation;
  FAST/STANDARD behavior is not represented as supported unless the current
  API contract documents it.
- Existing timestamp correction and generic 418/429 retry tests continue to
  pass; no retry is introduced for a code without a documented retry policy.
- All verification is local/mock-only and no live operation is performed.

## Open question for implementation

The historical HTTP 400 response body is not present in local logs, so the
specific cause of the transient failed run is not yet known. Improved logging
will make a future recurrence diagnosable; payload alignment is justified by
the current endpoint contract, not claimed as the proven cause of that run.
