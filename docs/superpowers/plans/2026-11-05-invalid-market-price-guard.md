# Invalid Market Price Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Prevent portfolio decisions and performance snapshots from treating a zero, negative, missing, or non-finite market price as a valid valuation.

**Architecture:** Keep validation at the boundary where market prices become portfolio values. A held positive Spot/Earn balance without a finite positive quote price makes the valuation incomplete and stops the run before order or Earn-operation planning, including dry-run. Persist quality honestly; do not modify existing history.

**Tech Stack:** Python, `Decimal`, pytest, SQLite performance snapshots, mocked exchange client.

**Spec:** Approved decision recorded in `workflow/kanban/03_doing/TASK-064-fail-closed-on-invalid-valuation-prices.md`.

## Global Constraints

- Never call live Binance APIs, trade, redeem, or subscribe to Simple Earn.
- Never change strategy targets, thresholds, or schedule as part of this fix.
- Do not edit historical logs or SQLite rows.
- Do not expose account balances, asset names, holdings, quantities, credentials, or flow IDs in diagnostics/tests.
- Keep unaffected valid-price valuation behavior unchanged.
- The quote asset retains its unit price; other held assets require a finite price greater than zero.
- If a positive held Spot/Earn balance has a missing, zero, negative, NaN, or infinite price, block the run before order/redeem/subscribe planning, including dry-run.
- If a post-operation refresh has an invalid price, persist the after snapshot as incomplete and preserve evidence of operations already performed; never imply rollback.

## File Map

- `performance_store.py`: reject non-positive/non-finite prices as usable snapshot prices; ensure explicit `complete` cannot override an invalid held-asset valuation.
- `portfolio.py`: fail closed rather than silently omit or zero-value a positive held balance with an invalid quote price.
- `app.py`: audit the valuation failure and persist an incomplete before snapshot before exiting; keep after-snapshot failures incomplete.
- `tests/test_performance_store.py`: snapshot quality edge cases.
- `tests/test_performance.py`: incomplete horizon behavior and null deltas.
- `tests/test_app_adaptive.py` and/or `tests/test_performance_integration.py`: no planning/execution/Earn side effects when a positive held balance cannot be priced, including dry-run.
- `workflow/kanban/03_doing/TASK-064-fail-closed-on-invalid-valuation-prices.md`: progress and acceptance evidence.

## Tasks

### 1. Define test contract and author regression tests

- [ ] A clean-context `gpt-6.1-terra`/medium test-specialist writes tests only, before production changes.
- [ ] Cover zero, negative, NaN, positive/negative infinity, missing price, valid positive price, and quote-asset unit pricing.
- [ ] Cover both Spot and Earn positive balances, including a snapshot requested as `complete` that must still be `incomplete`.
- [ ] Cover fail-closed before order/redeem/subscribe planning for scheduled and dry-run paths.
- [ ] Cover after-snapshot invalid pricing remains incomplete without representing prior operations as reversed.
- [ ] Run the targeted tests under `gpt-6-luna`/medium and verify RED for the expected validation gaps; no production edits during this step.

### 2. Implement minimal validation

- [ ] `gpt-6-luna`/medium changes only the necessary production code after the RED evidence.
- [ ] Treat invalid prices consistently at snapshot, portfolio-weight, target-order-price, and after-snapshot boundaries.
- [ ] Fail closed before any plan or Earn mutation; keep diagnostics sanitized and actionable.
- [ ] Verify GREEN, then refactor only while tests remain green.

### 3. Verify, review, and close

- [ ] Run focused tests, then `uv run pytest`.
- [ ] Run the local `performance --days 30 --json` report read-only and confirm any horizon that uses a zero/invalid start valuation remains incomplete with null `observed_change` and `hold_change`.
- [ ] Verify no database/log file changed and no live exchange call was made.
- [ ] Review the diff and audit-message privacy.
- [ ] Obtain independent `gpt-6.1-terra`/medium review using `superpowers:requesting-code-review`; resolve valid findings in at most three review cycles.
- [ ] Move the Kanban card to `05_done` with verification evidence and commit the completed card.

## Approval / Grill Decisions

- Approved by the user: block the entire run before order, redeem, or subscribe planning when any positive Spot/Earn balance lacks a finite price greater than zero; apply the same rule to dry-run.
- No unresolved product or safety decision remains. Preserve after-operation evidence even if a refresh is invalid.

## Expected RED and Acceptance

- RED: tests demonstrate that zero-priced Spot/Earn holdings currently become zero-value weights or snapshots incorrectly marked complete, and that the report can only guard the horizon after this inconsistent snapshot was persisted.
- Acceptance: invalid held-asset pricing cannot produce a rebalance plan; affected snapshots are `incomplete`; affected performance deltas remain null; valid-price and quote-asset behavior is unchanged; all tests pass except any previously documented unrelated suite failure, which must be separately identified.

## Progress

- [x] Root cause confirmed from read-only code/log/SQLite inspection: stored zero price in a positive Earn position is accepted as complete by snapshot storage and as a zero-value portfolio position, while performance comparison rejects a zero start price and correctly nulls deltas.
- [x] User approved fail-closed handling, including dry-run.
- [ ] Tests authored and RED verified.
- [ ] Implementation and GREEN/regression evidence.
- [ ] Independent review and card closure.
