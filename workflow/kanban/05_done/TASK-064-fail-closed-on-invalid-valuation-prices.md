# TASK-064: Fail Closed on Invalid Valuation Prices

## Objective

Reject missing, non-positive, or non-finite prices for positive held Spot/Earn balances before any order or Earn planning, and never persist affected snapshots as complete.

## Approved scope and safety

- Apply to live and dry-run planning paths; validate target prices before an order can be planned.
- Validate again after target-price refresh and after operations. Preserve completed-operation records if the after refresh is invalid; mark the after snapshot incomplete.
- Include raw Spot/Earn aliases in validation even when snapshot reconciliation deduplicates them.
- No strategy parameter, target, schedule, historical audit/log, or operational DB changes. No live exchange, trade, redeem, or subscribe.

## TDD and verification

- Terra/medium test specialist authors isolated tests before production changes.
- Luna/medium runs RED, implements, and runs GREEN/regressions.
- Use `tests/test_invalid_valuation_contract.py` and `tests/test_invalid_valuation_after_ld.py`; mocks must block HTTP and route SQLite to `tmp_path`.
- Run focused valuation/portfolio/performance tests, adaptive tests whose credentials are available, and `git diff --check`. Full suite may be run only if it cannot call live services and must report environment-dependent failures precisely.
- Independently review with Terra/medium via `superpowers:requesting-code-review`; maximum three fix/review cycles.

## Acceptance and progress

- [x] Fail-closed implementation and initial isolated regression tests are present.
- [x] Add regression for held price invalidated by the post-target-fetch refresh and canonical audit guard classification.
- [x] Classify selected regression failures; do not mask unrelated fixture/environment failures.
- [x] Resolve final dry-run after-snapshot finding in the separately authorized effort.
- [x] Mark the dry-run after snapshot incomplete when its final balance/price refresh or required initial Earn refresh fails; expose incomplete persistence as an audit warning.
- [x] Independent Terra review for the fresh effort passes with no unresolved material findings.
- [x] Record evidence, move card to `05_done`, and commit independently.

## Evidence so far

- `tests/test_app_adaptive.py`: the exact current run was 25 passed / 6 failed. Five cases stop before client creation because this checkout has no Binance API environment variables; no credentials were injected. The remaining anti-churn test reaches its patched `execute_trades` sentinel and fails; its cause has not been established and is not attributed to this change.
- One early unisolated RED invocation could have attempted an external macro fetch; no request/result is known. Later isolated test invocation blocked HTTP and used temporary SQLite, with no network/operational DB access observed.

### Authorized worktree execution (2026-11-14)

- Added `tests/test_invalid_valuation_after_refresh.py` via Terra/medium test-specialist assignment. The test agent's RED run was 12 passed / 12 failed solely because the implementation used `market_price_validation` instead of the required `valuation_guard` audit-step name; the new regression also covers a held price changing from valid to invalid after `_ensure_target_prices`.
- Renamed both guard audit steps to `valuation_guard` without changing the guard conditions or trade behavior.
- Valuation + portfolio/performance regression suite: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short tests/test_invalid_valuation_after_refresh.py tests/test_invalid_valuation_after_ld.py tests/test_invalid_valuation_contract.py tests/test_portfolio.py tests/test_performance_store.py tests/test_performance.py tests/test_performance_integration.py` -> 161 passed.
- Selected adaptive audit regression: `tests/test_app_adaptive.py::test_rebalance_audits_adaptive_strategy_after_run_start` -> 3 passed.
- `git diff --check` passed after the audit-step rename. Independent Terra review cycle 2 is pending.

### Review cycle 1

- Independent Terra review found three important gaps: the second held-price fetch was not validated before `compute_current_weights`; the failure snapshot could combine the latest `prices` map with earlier asset values/totals; and the LD integration tests lacked an explicit HTTP block.
- Terra test specialist added RED cases for the second fetch and snapshot consistency and added a network block to both LD tests. RED: `tests/test_invalid_valuation_after_refresh.py tests/test_invalid_valuation_after_ld.py` -> 24 failed, 48 passed, reproducing the missing incomplete snapshot and guard before planning on second-fetch invalidation.
- Luna moved the second-fetch guard before `compute_current_weights` and rebuilds incomplete snapshots from the current price map both there and after `_ensure_target_prices`. The LD integration tests now block HTTP explicitly.
- GREEN after cycle-1 fixes: valuation + portfolio/performance -> 161 passed; selected adaptive audit regression -> 3 passed; `git diff --check` passed. The later dry-run P1 in review round 3 supersedes this interim status.

### Review round 3: stopped at configured limit

- The third independent review found a valid P1: dry-run can replace `latest_prices` during final-balance processing, then `compute_current_weights` can fail while `_build_post_trade_performance_snapshot_payload` skips its held-price validation because `prices_refreshed` is false. The after snapshot can therefore be `simulation` rather than `incomplete`, and a reconciled LD alias may be omitted from `missing_prices`.
- No code change was made after this finding. The project policy caps this effort at three review rounds and requires stopping when round 3 finds a valid unresolved issue.
- Review assignment requested `gpt-6.1-terra` / medium; the tool accepted the assignment, but the reviewer reported the effective runtime model/reasoning metadata is not independently exposed.
- Decision needed: authorize a new, separately bounded effort to add a Terra-authored dry-run/LD regression, implement the guard, run isolated Luna tests, and perform a fresh independent Terra review.
- TASK-065 audit-source/help/paused-monitor correction remains unstarted because the project requires closing/committing each card before starting the next.

### Human decision and resumed effort (2026-11-15)

- User explicitly authorized a new bounded effort after review round 3. This resets the review-round limit for this follow-up only; limit remains three rounds.
- Scope: test and fix dry-run after-snapshot handling when final-balance valuation is invalid, including raw LD alias visibility and `incomplete` quality. Use Terra-authored tests, Luna execution, and independent Terra review. No live exchange or operational data changes.
- Resume criteria met. Card returns to `03_doing`; TASK-065 remains deferred until this card is reviewed and committed.

### New bounded effort: dry-run after-snapshot (2026-11-15)

- Terra/medium test specialist added a run-level regression in `tests/test_invalid_valuation_after_ld.py`, with HTTP blocked and temporary SQLite. The test covers a positive raw `LDTEST` balance reconciled to Earn, whose final dry-run price refresh becomes invalid. It requires an incomplete persisted after snapshot, `LDTEST` in `missing_prices`, deduplicated asset values, and a warning that does not imply live execution.
- Luna/medium reran RED: 6 failed / 6 live-path cases deselected. All six failed as expected because the snapshot was `simulation`, not `incomplete`.
- Luna/medium changed only `app.py`: validate the after-snapshot price map for dry-run as well as successful refresh; mark invalid valuation incomplete and record the raw alias; use dry-run-specific warning text.
- Luna GREEN: targeted LD dry-run regression -> 6 passed / 6 live-path cases deselected; valuation tests -> 133 passed. Coordinator rerun with portfolio/performance regression tests -> 167 passed.
- Full suite under offline network fence and empty API-key variables -> 501 passed, 6 failed. Five adaptive integration tests stop at missing Binance keys by design; the anti-churn test reaches its execution sentinel, cause unconfirmed. No external network access or live exchange operation occurred.
- At the time this section was written, the separately authorized effort was awaiting its first independent review. The subsequent review rounds and final unresolved finding are recorded below; that later status is authoritative. No commit until the review gate passes.

### New effort review follow-up (2026-11-15)

- Review round 1 found that a raw LD alias appearing only in the final balance fetch could be lost if final valuation raised before `latest_balances` was updated. The test-author added a final-only alias dry-run run-level regression. RED: expected `incomplete`, observed `simulation`. Fix: preserve `final_balances` immediately after fetch; validation success remains false until pricing and weight calculation finish. GREEN: new test passed; related valuation/portfolio/performance suite -> 154 passed, independently repeated by coordinator -> 154 passed.
- Review round 2 found a second gap: after-snapshot price refresh exceptions skip raw-alias validation because it was guarded by `dry_run or prices_refreshed`. A synthetic direct-helper regression now requires `LDTEST` in `missing_prices` after failed refresh while retaining incomplete quality, deduplicated values, and the completed-operations warning. RED: failed as intended with `missing_prices=[]`.
- Fix: always validate available after-snapshot balances/earn positions against the latest available price map; removed the now-unused `prices_refreshed` state. This does not retry or perform exchange operations.
- GREEN: exact new test -> 1 passed; related valuation/portfolio/performance suite -> 155 passed. Coordinator independently repeated the 155 tests and `git diff --check`; both passed.
- Review round 2 claimed no reviewer dispatch was available, but the coordinator's tool record confirms a separate Terra reviewer was dispatched and returned a review; this claim is not treated as a code finding. Its valid raw-alias finding was addressed above.
- Final independent review round 3/3 found one valid Important issue: when the final dry-run balance fetch or its price refresh fails, `latest_balances_refresh_succeeded` remains false and the helper does not retry in dry-run; if the earlier price map still values the older balances, the after snapshot can remain `simulation` despite unconfirmed final data. Reviewer reference: `app.py:1274` and `app.py:1551`.
- Recommended correction: propagate final refresh failure into the after-snapshot quality and audit warning; add isolated dry-run regressions for final balance-fetch failure and final price-refresh failure. Do not relax price validation or perform live operations.
- The reviewer did not run tests. Coordinator had independently run the related valuation/portfolio/performance suite immediately before review: 155 passed; `git diff --check` passed. These results do not resolve the review finding.
- Review limit reached: round 3 of 3 for the prior effort. The user subsequently authorized a new separately bounded continuation; see below.

### Separately authorized continuation (2026-11-15)

- User explicitly authorized a new bounded effort after the prior review reached round 3/3. Review counter resets to 0/3 for this continuation only.
- Regression scope: dry-run final `get_account_balances` failure and final `_fetch_asset_prices` failure. In both cases the after snapshot must be persisted as `incomplete`, not `simulation`; the audit must make the failed final refresh and incomplete snapshot evident. Use fake clients, temporary SQLite, and blocked network; no live exchange calls or operations.
- Required workflow: Terra/medium test specialist authors both regressions before production changes; Luna/medium confirms RED, implements the minimal fix, and runs GREEN plus focused regressions; an independent Terra/medium reviewer uses the installed requesting-code-review skill/template.
- Review counter for this separately authorized continuation: 0/3. Do not exceed three rounds; if round 3 has valid unresolved findings, stop and request explicit authorization for another effort.
- Terra authored parametrized run-level regressions for final balance-read and final price-refresh failures. RED: `uv run pytest tests/test_invalid_valuation_after_ld.py -k test_dry_run_final_refresh_failure_persists_incomplete_snapshot` -> 2 failed, 20 deselected, both expected `simulation` vs `incomplete`.
- Luna passes final valuation-refresh success into the after-snapshot helper; dry-run refresh failure now sets the persisted snapshot to `incomplete` and emits a `prices_snapshot_after` warning. Successful dry-runs remain `simulation`; no retry or live operation was added.
- GREEN: targeted tests -> 2 passed, 20 deselected. Focused valuation/portfolio/performance suite -> 157 passed; coordinator independently reran 157 passed. `git diff --check` passed.
- Full suite under an explicit socket/DNS fence with Binance/OpenRouter credentials empty -> 505 passed, 6 failed. Five failures require Binance credentials and stop before client creation; one anti-churn test reaches its `execute_trades` sentinel, cause unconfirmed. No external network request or exchange operation was possible.
- First independent Terra review for this continuation is pending (round 1/3); no commit until review passes.
- The reviewer initially claimed no independent dispatch existed. Coordinator verified this review was dispatched as a separate Terra agent with the required explicit model/effort request; the claim was not treated as a technical finding.

### Fresh bounded effort: initial Earn quality and audit visibility (2026-11-15)

- User authorized a new bounded effort after the previous review cap. Round counter reset for this effort; maximum three rounds.
- Review round 1 found that failure of the initial Simple Earn positions refresh could leave a dry-run after snapshot as `simulation`; it also found that persisted incomplete snapshots were logged at `info`. The reviewer recommended conservative helper defaults.
- Terra/medium authored the integration regression for initial Earn failure and strengthened final-refresh audit assertions. RED: 3 targeted cases failed as expected: Earn case persisted `simulation`; final refresh cases lacked a `portfolio_snapshot` warning.
- The implementation propagates initial Earn quality to the after-snapshot helper, defaults the refresh/quality inputs conservatively, and logs persisted incomplete snapshots as audit `warning`. No order/Earn planning behavior, retries, or live operations were added.
- Luna GREEN and coordinator rerun: focused valuation/portfolio/performance regression suite -> 168 passed; `git diff --check` passed.
- Full suite with socket/DNS fence -> 506 passed / 6 failed. Five adaptive tests require absent Binance credentials and fail before client creation. The anti-churn failure was reproduced identically at the current worktree and base `3c54103`; it is a confirmed preexisting failure. No network or live exchange operation occurred.
- Independent Terra review round 2/3 approved with no critical/important/minor findings. Reviewer did not rerun tests; coordinator verified the stated evidence.
- No Task Scheduler or monitor automation changes. TASK-065 remains deferred until this card is committed.

### Freshly authorized effort: initial Earn quality and audit visibility (2026-11-15)

- User authorized a new bounded effort after the prior review cap. Counter resets for this effort only; maximum three independent review rounds.
- Round 1 found two related gaps: if the initial Simple Earn position refresh fails, dry-run can persist `data_quality=simulation` despite unknown Earn positions; and incomplete persisted portfolio snapshots are logged as `info`, hiding the degraded result. Reviewer also noted helper defaults should fail conservative.
- Terra/medium authored `test_dry_run_initial_earn_failure_persists_incomplete_after_snapshot` and strengthened final-refresh regressions to require an audit warning. RED: the three targeted scenarios failed as expected (Earn snapshot was `simulation`; final refresh cases lacked `portfolio_snapshot` warning).
- Fix passes the initial Earn quality into the after-snapshot helper, makes unconfirmed valuation/Earn-quality defaults conservative, and logs persisted `data_quality=incomplete` as `portfolio_snapshot` warning. Does not block, retry, or change trading/Earn operations.
- Luna GREEN: focused valuation/portfolio/performance suite -> 168 passed; coordinator rerun -> 168 passed. `git diff --check` passed.
- Offline full suite with socket/DNS fence -> 506 passed / 6 failed. Five adaptive integration tests require absent Binance credentials; the anti-churn test reaches its execution sentinel and remains unexplained. No external network or Binance operation was possible.
- Independent Terra review round 2/3 found no critical, important, or minor residual findings. The reviewer requested comparison of the anti-churn full-suite failure against base; coordinator reran that single test under socket/DNS fence and observed the same sentinel failure at both current worktree and base commit `3c54103`. It is therefore a confirmed baseline failure, not caused by TASK-064.
- Verification is complete for this bounded effort; no third review round is needed. The full-suite status remains 506 passed / 6 failed: five credential-dependent tests cannot initialize without Binance keys; one anti-churn test fails identically at base. No network or live exchange operation occurred.
- Review rounds used in this fresh effort: 2/3. Card is ready to close and commit independently.
