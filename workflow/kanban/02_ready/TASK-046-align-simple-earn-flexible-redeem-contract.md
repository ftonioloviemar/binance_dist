# TASK-046: Align Simple Earn Flexible Redeem Contract

## Objective

Construct Flexible Redeem requests according to the current official Binance
API contract and expose that the legacy FAST/STANDARD selector is not part of
the currently documented endpoint.

## Context

Current `binance_client.py` sends `type=FAST|STANDARD`. The current official
endpoint documentation lists `productId`, `redeemAll`, `amount`, `destAccount`,
`timestamp`, and `recvWindow`; `destAccount` defaults to `SPOT`. Historical
successful requests show the legacy payload may have been tolerated, so this
mismatch is not claimed as the proven cause of prior HTTP 400 errors.

## Scope

- Make the redeem request explicitly target `SPOT` and omit undocumented
  `type`.
- Resolve the old `fast` method argument and
  `SIMPLE_EARN_FAST_REDEEM` setting without silently reporting unsupported
  FAST/STANDARD semantics as effective.
- Preserve existing flow and response/audit sequencing except for clearly
  reporting the unsupported legacy option.
- Add request-construction/config-diagnostic tests using mocked sessions.
- No live redemption/subscription/trade; no schedule or account config edits.

## Test contract

- RED: request contains `productId`, formatted `amount`, `destAccount=SPOT`,
  timestamp, `recvWindow`, signature; it excludes `type`.
- RED: if the legacy fast setting is configured, run/audit diagnostics clearly
  state that the current API contract does not offer the selector; no false
  claim that FAST or STANDARD was selected.
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

Ready; do not start until TASK-045 is committed.
