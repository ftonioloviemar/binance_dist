# TASK-046: Align Simple Earn Flexible Redeem Contract

## Objective

Construct Flexible Redeem requests according to the current official Binance
API contract and expose that the legacy FAST/STANDARD selector is not part of
the currently documented endpoint.

## Context

Current `binance_client.py` sent `type=FAST|STANDARD`. The current official
endpoint documentation lists `productId`, `redeemAll`, `amount`, `destAccount`,
`timestamp`, and `recvWindow`; `destAccount` defaults to `SPOT`. Historical
successful requests show the legacy payload may have been tolerated, so this
mismatch is not claimed as the proven cause of prior HTTP 400 errors.

Reference: [Binance Flexible & Locked API](https://developers.binance.com/en/docs/catalog/investment-and-services-simple-earn/api/rest-api/flexible-locked#redeem-flexible-product).

## Scope

- Make the redeem request explicitly target `SPOT` and omit undocumented
  `type`.
- Keep the old `fast` method argument as an optional compatibility input, but
  ignore it and warn if an external caller supplies it; do not send it to the
  endpoint.
- Keep `SIMPLE_EARN_FAST_REDEEM` recognized temporarily, record whether it
  was explicitly set, and make its unsupported/no-effect status visible in
  run config and the Earn audit.
- Preserve existing flow and response/audit sequencing except for clearly
  reporting the unsupported legacy option.
- Add request-construction/config-diagnostic tests using mocked sessions.
- No live redemption/subscription/trade; no schedule or account config edits.

## Test contract

- RED: request contains `productId`, formatted `amount`, `destAccount=SPOT`,
  timestamp, `recvWindow`, signature; it excludes `type`.
- RED: settings distinguish the absent env var (default value retained but
  not explicitly configured) from explicit `true` and `false`.
- RED: run/audit diagnostics clearly state that the current API contract does
  not offer the selector; no false claim that FAST or STANDARD was selected.
- RED: a legacy `fast` keyword remains accepted for external callers, triggers
  a deprecation/ignored warning, and is not transmitted in the payload.
- GREEN: mock request and audit tests pass; existing Earn sequence tests remain
  unchanged and green.

## Verification

- Focused client/config/audit tests identified by the test-contract review.
- Full: `uv run pytest -q`.
- Static search confirms no redeem payload sends `type`; no live calls.

## Acceptance

- Request fields match Binance Flexible Redeem docs.
- Legacy config behavior is visible and backwards-safe; no unknown parameter
  silently changes redemption semantics.
- Independently audited, moved to `05_done`, and committed before any next card.

## Dependencies

- TASK-045 provides structured API errors and should be completed first.

## Status

Done; independently audited. TASK-045 dependency is committed as `7c1e8a9`.

## Verification Evidence

- RED: focused suite -> 6 failed, 46 passed. Failures showed the missing
  documented payload fields, required legacy argument, missing explicit-env
  marker, and absent run/audit diagnostic.
- Focused GREEN: `uv run pytest tests/test_binance_client.py tests/test_config.py tests/test_app_adaptive.py -q`
  -> 52 passed.
- Full GREEN: `uv run pytest -q` -> 228 passed.
- `git diff --check` passed. All request construction tests use fake sessions;
  no network or live exchange operation was performed.
- Independent test-contract review recommended preserving the legacy method
  argument/config while making no-effect behavior explicit; this was included.
- Independent result audit verified the payload, signing, compatibility and
  audit semantics. It found stale README/STATE descriptions; both were updated
  and then confirmed closed. No live exchange calls were made.
