# TASK-064: Fail closed on invalid valuation prices

## Objective

Prevent a zero, negative, missing, or non-finite price for a positive Spot/Earn balance from being treated as a valid portfolio valuation or from producing an order plan.

## Context

The 7-day performance report was `incomplete` with null deltas even though its boundary snapshots were labelled `complete`. Read-only inspection found a zero market price associated with a positive Earn balance: `performance_store.py` accepted zero (`>= 0`), and `portfolio.py` used it as a zero-value position. The report's comparison rejects a zero start price, so its null deltas are the correct protective behavior; the snapshot/weighting validation is inconsistent.

## Approved Safety Contract

- A non-quote price is valid only if finite and greater than zero.
- Treat missing, zero, negative, NaN, and infinite prices as unavailable for positive held Spot/Earn balances.
- Block the run before order, Earn redeem, or Earn subscribe planning when any such held balance is unpriced; apply equally to dry-run.
- Do not block on zero-balance assets or unused symbols. Validate target prices before any corresponding order could be planned.
- Persist affected snapshots as `incomplete`, even if the caller requested `complete`.
- If an after-operation refresh is invalid, preserve records of already completed operations and mark the after snapshot incomplete; do not imply reversal.
- Do not change strategy parameters, targets, schedule, historical logs, or existing SQLite data.

## Scope

- `performance_store.py`: price normalization and snapshot data quality.
- `portfolio.py`: reject invalid prices instead of silently omitting/zero-valuing held positions.
- `app.py`: fail closed and audit safely before planning; preserve incomplete after-snapshot handling.
- Focused regression tests for snapshot, portfolio, report, and app paths.

## TDD Contract

- Test author: clean-context `gpt-6.1-terra`/medium specialist writes tests before production changes.
- Test runner/implementer: `gpt-6-luna`/medium runs RED, implements minimal changes, then GREEN and regression.
- Independent reviewer: `gpt-6.1-terra`/medium with `superpowers:requesting-code-review`; reviewer must not be the test author or implementer.
- RED must prove zero can currently pass as complete/zero-valued and invalid held prices do not yet reliably block order planning.
- Cover both Spot and Earn, finite positive and quote-price success cases, missing/zero/negative/NaN/infinity, before/after snapshot quality, and no order/redeem/subscribe side effects in scheduled and dry-run paths.
- Tests must use fakes/mocks only; no live API calls.

## Verification

- Focused: specialist to select exact test paths before implementation; expected to include `tests/test_performance_store.py`, `tests/test_performance.py`, and app/integration tests.
- Full regression: `uv run pytest`.
- Read-only smoke: `uv run python app.py performance --days 30 --json`.
- `git diff --check`; inspect final diff, repository status, and SQLite/log file hashes for unintended changes.

## Risks

- Fail-closed behavior may skip scheduled runs while any positive holding is unpriceable; this is the approved trade-off to avoid distorted allocation decisions.
- Existing historical snapshots remain unchanged, so the 7-day horizon may remain incomplete until both selected endpoints have valid valuation data or fall outside that horizon.
- Do not infer realized profit/loss from shadow simulations or incomplete flow-adjusted reporting.

## Progress

- [x] Root cause investigated read-only; no project files or account data changed.
- [x] User approved fail-closed behavior, including dry-run.
- [x] Terra test contract/tests and RED evidence.
- [x] Luna implementation and regression results.
- [x] Independent Terra review, at most three cycles.
- [x] Move to `05_done` and commit with evidence.

### Execution evidence (2026-11-05)

- Test-author subagent supplied `tests/test_invalid_valuation_guard.py`; the execution environment did not expose the selected model/reasoning metadata, so Terra attribution is not independently verifiable here.
- RED command `uv run pytest tests/test_invalid_valuation_guard.py -q`: 31 failed, 39 passed. Failures exposed zero/non-finite valuation acceptance, missing-price weight omissions, and lack of an early run guard.
- Implemented finite-positive price handling in snapshot construction, portfolio weighting, target-order construction, and rebalance pre-planning. Invalid held-price runs now persist an incomplete `before` snapshot and emit a sanitized `valuation_guard` failure; after-refresh invalid prices keep the `after` snapshot incomplete and explicitly preserve completed-operation semantics.
- Focused regression command `uv run pytest tests/test_invalid_valuation_guard.py tests/test_portfolio.py tests/test_performance_store.py tests/test_performance_integration.py -q`: 100 passed.
- Full `uv run pytest`: 460 passed, 1 failed. The sole failure is `tests/test_app_adaptive.py::test_rebalance_fails_closed_when_required_macro_source_is_untrusted[overflow]`, reproduced independently; it fails while JSON-serializing the fixture's 10,000-digit macro integer, before the valuation guard. It is unrelated to this patch and remains unresolved.
- Read-only `uv run python app.py performance --days 30 --json`: 7d is `incomplete` with null observed/hold deltas; 24h and 30d report `flow_coverage_status=insufficient`, so no flow-adjusted result is available.
- `git diff --check` passed. No live exchange calls, trades, Earn operations, historical log edits, or SQLite writes were performed. The pre-existing untracked `=` file was left untouched.
- The current tool session cannot select or verify `gpt-6-luna`/medium, nor dispatch the independent `gpt-6.1-terra`/medium reviewer. Keep the card in `03_doing`; obtain that review before moving it or committing.

### Independent review follow-up (2026-11-05)

- Terra review identified that the first guard ran before `auditor.start_run`, that a second price fetch could invalidate a holding before snapshot persistence, and that matched LD Spot aliases remain in strategy balances even though the performance snapshot reconciles them with Earn.
- Terra test specialist added `tests/test_invalid_valuation_review.py`. RED: `uv run pytest tests/test_invalid_valuation_review.py -q` produced 3 failures and 1 pass, reproducing audit-ID overwrite and missing incomplete snapshots after later Spot/Earn price invalidation.
- Moved the first valuation guard after adaptive resolution and `start_run`, preserving the effective-profile/config audit. Added a second guard immediately after the later price fetch and before weight/order planning. The guard validates original Spot/Earn balances, including matched LD aliases, without normalizing strategy balances; incomplete snapshots include invalid raw valuation keys while retaining TASK-035's deduplicated asset values.
- GREEN: `uv run pytest tests/test_invalid_valuation_review.py -q` passed 4 tests. Focused regression (`test_invalid_valuation_guard.py`, `test_invalid_valuation_review.py`, `test_portfolio.py`, `test_performance_store.py`, `test_performance_integration.py`) passed 104 tests.
- Full `uv run pytest`: 464 passed, 1 failed, same unrelated `test_rebalance_fails_closed_when_required_macro_source_is_untrusted[overflow]` JSON integer digit-limit failure.
- Read-only performance smoke: 7d remains `incomplete` with null deltas; 24h/30d flow coverage remains insufficient and Modified Dietz is absent. `git diff --check` passed. No live API calls, commits, or Kanban move.

### Continuation and final verification (2026-11-21)

- Reconciled the isolated implementation against the uncommitted TASK-064 work in `C:\python\binance_dist` without copying over either worktree. Retained valuation-only matched `LD<asset>` alias normalization (only when positive Simple Earn base exists), raw Spot balances for execution/redemption, fail-closed guards before planning and after refreshed prices, and incomplete after-snapshot semantics. The original Scheduler checkout and its pre-existing untracked `=` file were left unchanged; no scheduler activation or live operations were performed.
- Fixed one unrelated integration-test fixture: its recent order timestamp was written under hard-coded `20260801.log`, which audit retention deleted before anti-churn could read it. The filename now derives from `prior_time`; production anti-churn logic was not changed.
- Luna runner: anti-churn regression -> 1 passed; focused TASK-064 regression -> 130 passed; full `uv run pytest` with process-only placeholder `BINANCE_API_KEY=test` and `BINANCE_API_SECRET=test` -> 491 passed.
- Read-only `uv run python app.py performance --days 30 --json` -> exit 0; 24h/7d/30d are `no_data`, flow coverage is `no_data`, and Modified Dietz is null. `state/performance.db` SHA-256 and mtime were unchanged.
- `git diff --check` passed. Three independent review rounds were used; findings were corrected and covered by tests. No fourth review was dispatched to honor the three-round cap, so this card records coordinator verification rather than claiming a further reviewer sign-off.
- No live exchange/provider calls, trades, Simple Earn actions, historical log edits, or database writes were performed.
