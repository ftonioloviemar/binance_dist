# Plan: Valuation Guard and Audit Source Corrections

Planner: `gpt-6.1-sol` / medium. Execution is user-authorized; no material questions remain.

## Decisions and safety boundaries

- Keep the invalid-valuation fail-closed contract, including dry-run; do not relax price freshness/validity checks.
- Do not change strategy parameters, scheduler cadence, historical logs, or operational SQLite data.
- Treat daily `logs/YYYYMMDD.log` records as the current audit source. `logs/audit.db` is legacy and must not be backfilled or presented as current.
- Keep the Codex monitor paused while correcting its source interpretation. Do not enable or modify the Windows trading task.
- Never call live exchange endpoints or perform trades, redemption, or subscription. Tests use fakes, temp SQLite, and blocked HTTP.

## Execution cards

1. **TASK-064, fail closed on invalid valuation prices:** finish tests and review for held Spot/Earn prices missing, non-finite, zero, or negative; validate before planning and after price refresh; preserve operation records and mark after snapshots incomplete. Run isolated RED/GREEN and relevant regressions, then independent Terra review. Commit this card independently.
2. **TASK-065, correct audit provenance and monitor guidance:** align `app audit` help with daily logs; document legacy SQLite distinction; update the paused Codex heartbeat prompt to correlate daily log run IDs with performance snapshots and recognize expected fail-closed incomplete-before/observation-skipped runs. Validate help/docs/prompt and independent review. Preserve PAUSED status. Commit independently.

## Acceptance

- TASK-064: invalid positive holdings cannot reach order/Earn planning, invalid snapshot prices cannot be marked complete, and after snapshots remain `incomplete` when final valuation or required initial dry-run Earn data is unconfirmed. Incomplete persisted snapshots are audit warnings. Regression suite and independent review pass.
- TASK-065: users and future monitor runs identify the canonical audit source correctly, distinguish absent linkage from expected guard failures, and do not report stale `audit.db` as live history. Scheduler/strategy behavior and operational data remain unchanged.

## Model and review routing

- TASK-064: Terra/medium authors tests; Luna/medium runs RED/GREEN and regression; separate Terra/medium reviewer using `superpowers:requesting-code-review` (or disclose tool unavailability and stop the formal review gate).
- TASK-065: Luna/medium implements the bounded documentation/automation correction; separate Terra/medium review. Maximum three review/fix cycles per Goal.

## TASK-064 review-cycle-1 findings to close

- Check the second held-price fetch before `compute_current_weights`; on invalid data, persist the current fetch as an incomplete before snapshot and emit `valuation_guard`.
- Rebuild the incomplete snapshot from the same latest price map; do not overwrite only its `prices` while leaving values/totals from a previous fetch.
- Explicitly block HTTP in the LD caller-level integration tests.
- Correct adaptive test evidence to the exact command result: 25 passed / 6 failed; five cannot initialize without Binance environment variables, and one anti-churn case reaches the test sentinel. Do not assert an unproven root cause for that case.

## Separately authorized TASK-064 effort (2026-11-15)

The user explicitly authorized a new bounded effort after review round 3. Reset the review-round counter for this separately bounded correction; maximum three independent review rounds for this effort.

- Add an integration regression for dry-run post-operation valuation when the final-balance refresh yields an invalid price for a positive holding, including an LD alias reconciled into Earn.
- Required outcome: the after snapshot is `incomplete`, includes the invalid raw alias in `missing_prices`, and does not present `simulation` as sufficient quality when valuation is incomplete. Preserve any completed-operation records and avoid duplicate snapshot values.
- Keep changes limited to the post-operation dry-run path and tests. No live exchange, strategy/scheduler changes, operational DB/log changes, or external HTTP.
- Routing: clean-context Terra/medium test specialist authors RED test; Luna/medium runs RED/GREEN and focused regression; separate Terra/medium reviewer uses requesting-code-review skill/template. New bounded review cap: 3 rounds.

## Separately authorized TASK-064 continuation (2026-11-15)

The user explicitly authorized another bounded effort after the prior independent review reached round 3/3. Reset the review counter to 0/3 for this continuation only.

- Add isolated run-level dry-run regressions for failure of the final Spot balance refresh and failure of the final price refresh.
- In either failure, the persisted after snapshot must be `incomplete`, never `simulation` based on unconfirmed data. The audit must clearly expose the failed refresh and snapshot quality.
- Keep trading/order/Earn behavior unchanged. Do not call exchange endpoints, alter strategy or schedules, or mutate operational databases/logs. Use fake clients, temp SQLite, and blocked HTTP.
- Terra/medium authors the tests first; Luna/medium runs RED, applies the minimal implementation, and runs GREEN plus focused regressions; a separate Terra/medium reviewer uses the `requesting-code-review` skill and template. Stop if the third review still has a valid finding.
- Current evidence: both RED cases failed as expected (`simulation` vs `incomplete`); targeted GREEN 2 passed; focused valuation/portfolio/performance suite 157 passed by Luna and coordinator. Full offline suite 505 passed/6 failed under socket/DNS fence (five credential-dependent adaptive cases, one anti-churn failure of unconfirmed cause). First independent review is pending; no commit.

## Freshly authorized TASK-064 effort: initial Earn quality and audit visibility (2026-11-15)

- User authorized a new bounded effort after review 3/3. Review counter resets for this effort only; maximum three independent review rounds.
- Round 1 found that a failed initial Earn refresh could leave a dry-run after snapshot labeled `simulation`; incomplete portfolio snapshot audit records were also `info`, and helper defaults were not conservative.
- Terra-authored RED verifies initial Earn failure results in an incomplete after snapshot and that final-refresh failures log `portfolio_snapshot` warning. Luna GREEN and coordinator rerun: focused valuation/portfolio/performance suite -> 168 passed; full suite under socket/DNS fence -> 506 passed, 6 environment/baseline failures (five require absent Binance credentials; anti-churn cause remains unconfirmed). No network or live exchange operations.
- Fix propagates initial Earn quality to dry-run after snapshot, defaults helper validation inputs conservatively, and emits audit warning for persisted incomplete snapshots. Terra review round 2/3 found no residual findings. The anti-churn suite failure was rerun against base `3c54103` and fails identically, confirming it is preexisting. Fresh-effort full offline suite remains 506 passed / 6 failed (five require absent Binance credentials; one confirmed baseline anti-churn failure). Card may be committed independently; TASK-065 remains deferred.
