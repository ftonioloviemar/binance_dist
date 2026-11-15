# TASK-067: Stabilize Anti-Churn Test History Fixture

## Objective

Repair the failing anti-churn integration test so its recent filled-order history survives the audit logger's retention cleanup.

## Scope and safety

- The test currently writes a recent order into a stale-dated filename (`20260801.log`); production retention uses the filename date, so the fixture may be deleted before anti-churn reads it.
- Use a fixed current timestamp and matching daily filename, or another deterministic fixture that honors retention. Keep production retention and anti-churn behavior unchanged.
- Preserve the test that blocks an opposite-side order within cooldown; do not interact with live exchange or credentials.

## TDD and verification

- Terra/medium authors the deterministic test/fixture first.
- Luna/medium runs RED/GREEN and the targeted adaptive suite with network blocked.
- Run the full offline suite and `git diff --check`; compare relevant assertions and ensure no false-pass.
- Independent Terra/medium review, maximum three rounds; commit separately.

## Acceptance

- The test proves recent history exists under the filename convention before filtering and confirms `execute_trades` is not called when the opposite order is blocked.
- The full offline suite has no remaining failures attributable to these test fixtures.
- No production strategy, retention, or scheduler behavior changes.

## Evidence

- Terra updated only the integration-test fixture: fixed UTC clock, matching daily log filename, and assertion that the filled history entry remains present before anti-churn filtering; sentinel remains intact.
- Isolated anti-churn test with network blocked -> 1 passed.
- Adaptive suite with network blocked -> 31 passed.
- Full offline suite with socket/DNS blocked -> 513 passed.
- No production retention/cooldown changes or live exchange calls.

- Independent Terra review approved with no findings; reviewer confirmed no production changes and approved close/commit.
