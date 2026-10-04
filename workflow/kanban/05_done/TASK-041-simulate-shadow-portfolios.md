# TASK-041: Simulate Shadow Portfolios

## Objective

Build a deterministic virtual portfolio simulator using isolated per-scenario inventory, captured decision inputs, local order constraints, and configurable modeled costs.

## Context

See `docs/market-insights.md`, existing planner/exchange filters, and financial attribution limits in `docs/financial-performance.md`.

## Test Contract

- Tests: new `tests/test_market_insights_simulation.py`.
- RED: existing `strategy_replay.py` counts trade/cost proxies but does not evolve inventory or calculate portfolio return.
- Contract review: independent Luna-medium review confirmed the approved decisions and identified the ambiguity cases below; coordinator incorporated them before implementation. Reuse the existing portfolio decision/planning functions for decision and quantity selection (those functions use floats); convert planned quantities immediately to `Decimal` and use fixed-precision `Decimal` for fills, balances, equity, costs, and metrics. Never round for display before accounting.
- Cover same complete pre-decision seed and prices for isolated hold, baseline, and `volatility_guard_v1` portfolios; sequential runs preserve each policy's inventory and calculate drift from that policy's own portfolio while sharing observed targets/advice.
- Cover exact outputs for net return, cumulative costs, gross and relative turnover, observed drawdown, and post-fill residual drift. Drawdown is `(running_peak_equity - observed_trough_equity) / running_peak_equity` at complete marks (including seed); residual drift is the maximum absolute target/current weight difference over the union of held and target assets, with missing targets treated as zero, using post-fill quantities marked at that run's reference prices.
- Costs per fill: gross notional is filled quantity times captured reference price; fee and slippage are each their configured rate times that gross notional and are debited from quote (buy: gross plus costs; sell: gross less costs). Turnover excludes costs. Cover cumulative costs and no negative asset or quote balances. If a whole buy cannot be funded after sells and costs, skip it without partial fill. Sort assets deterministically within sell and buy groups; sells execute first.
- Reuse the local planner's dust filter, global rebalance trigger (including its stable-asset guardrail), `rebalance_has_tradable_orders`, and `build_trades`; capture effective drift, min-notional, uplift tolerance, max-slippage, and advice action. Once the global decision triggers, test that the planner may include a nonzero per-asset delta that is individually below the drift threshold if it passes trade-floor checks. Cover `SymbolFilters` lot step, min/max quantity, min/max notional, and min-notional uplift. A potential order is a nonzero non-quote delta in the planner decision after dust filtering when the policy's global rebalance decision triggers. If its symbol filter is absent, mark that policy and the shared comparison point `incomplete`, name the affected symbol, and atomically pause all three sessions without advancing inventory, metrics, or last-processed run.
- Missing required prices (including assets remaining only in persisted virtual inventory), missing BTC 30-day volatility needed by the candidate (including at the initial seed), or incomplete initial Spot/Earn snapshot make the shared comparison point `incomplete`; all policies pause atomically and financial deltas are null. An incomplete update preserves state and can be retried for the same run after corrected inputs. For a completed `(session, run, policy version)`, replay with the same input fingerprint is a no-op; a different fingerprint for that already-completed identity fails closed. Persist `policy_version` with each aggregate and return it on replay. Combined fee and slippage rates must be at most 100% per side.
- Cover Spot/Earn alias reconciliation using the existing matched `LD<asset>` contract, idempotent replay, and continuation after incomplete data. Verify persistence boundaries: minimum virtual state only in `shadow_portfolios.db`, aggregate results only in `market_insights.db`, and no writes to `performance.db` or raw snapshots, secrets, or per-asset virtual inventory in `market_insights.db`.
- Commit shadow state and market aggregates in one attached-database SQLite transaction. Fail closed when either file uses WAL because cross-file atomic commit is not guaranteed in that mode. Test that aggregate-table write failure rolls back session state too; completed-run markers in the shadow DB contain only identity and fingerprint, not duplicate aggregate history.
- Command: `uv run pytest tests/test_market_insights_simulation.py`.

## Acceptance And Constraints

- Model hypothetical fills at captured reference prices and label that fill assumption; disclose modeled costs, omitted flows/yield, and Earn liquidity assumption.
- Never write synthetic results to `state/performance.db` or call live trade/Earn methods.
- The comparison does not reconstruct historical live anti-churn cooldown decisions; disclose this as a simulator limitation rather than implying exact live order parity.
- Existing planner quantity/decision calculations are floats, so virtual financial accounting remains Decimal after planner outputs are converted; report that boundary rather than claiming end-to-end Decimal planner parity.

## Verification

- RED: focused test initially failed collection with `ModuleNotFoundError: shadow_portfolios`, confirming the missing simulator behavior.
- Initial focused command: `uv run pytest tests/test_market_insights_simulation.py -q` -> 18 passed before independent final audit.
- Related market-insights tests: `uv run pytest tests/test_market_insights_simulation.py tests/test_market_insights.py -q` -> 37 passed before the final configurable-cost test.
- Four independent audits found and drove regressions for nine issues: missing prices for virtual-only persisted assets could raise `KeyError` or be omitted from early-return diagnostics; a nonpositive quote price could produce false completed metrics; an initial seed could complete without required BTC volatility and block retry; aggregates/replays omitted `policy_version`; combined costs above 100% could produce negative sell proceeds; SQLite connections were not explicitly closed in the simulator and public persistence wrappers; residual drift coverage was only a broad range; and planner preflight/final passes could duplicate skipped-order diagnostics. All findings were reproduced and fixed.
- Focused command after all fixes: `uv run pytest tests/test_market_insights_simulation.py tests/test_market_insights.py -q` -> 47 passed.
- Full suite after all fixes: `uv run pytest -q` -> 195 passed.
- `uv run python -m compileall -q shadow_portfolios.py market_insights.py tests/test_market_insights_simulation.py tests/test_market_insights.py` and `git diff --check` passed. `ruff` is unavailable in this environment.
- Tests use temporary SQLite paths only. No exchange/network calls, live orders, Earn operations, or writes to the real `performance.db`.
- Independent final audit: no P1/P2 findings. Confirmed deterministic single skip for below-floor BTC plus executable ETH, null metrics and atomic retry behavior, connection close in success/error paths, cost limits, replay, database rollback, and planner boundaries. Focused tests -> 47 passed; `git diff --check` passed. Auditor performed no edits or external operations.

## Human Decision Required

- Resolved 2026-10-04: the user approved option 1. Use local-only `state/shadow_portfolios.db` for minimum per-policy virtual inventory/session state. Keep public candles, indicators, and aggregate scenario results in `state/market_insights.db`; do not store raw Spot/Earn snapshots, credentials, or per-asset virtual balances in that market-insights store. The virtual quantities remain sensitive derived data.
- Resolved 2026-10-04: turnover is gross notional across all simulated buys and sells, with relative turnover normalized by initial session equity. Drawdown is observed peak-to-trough equity decline across complete marked snapshots, including the session seed; it is not intraday drawdown. Residual drift is the maximum absolute target-versus-virtual-post-fill weight difference.
- Resolved 2026-10-04: if a potentially actionable order has no captured symbol filters, mark that policy update `incomplete`, identify the symbol, and pause progression of that session. Do not silently count the order as skipped and continue.
- Resume criteria were met on 2026-10-04; implementation and final-audit corrections were completed and independently reviewed on 2026-10-04.

## Specialist Review Calibration

- The Luna-medium contract review gave useful simulation/test coverage and correctly identified unresolved metric/filter conventions, but missed the explicit storage/privacy conflict in the canonical docs. The coordinator detected it before implementation. In later reviews of persisted financial derivatives, independently cross-check data destinations and privacy rules rather than treating the specialist review as sufficient.
- The follow-up Luna-medium contract review surfaced actionable gaps in replay identity, incomplete retry semantics, cost arithmetic, exact metric formulas, full captured-filter limits, and DB-boundary tests; the coordinator resolved these in the contract before writing tests. This review was appropriately scoped and required no rework.
- The first independent completion audit found three substantive omissions despite passing tests. The coordinator added targeted regressions and fixed them; future simulation reviews should explicitly inspect persisted-only inventory valuation, replay payload completeness, and cost-bound invariants, then verify the regressions are present rather than relying on broad suite success.
- The second final audit added important edge cases (invalid quote marks, missing persisted symbols on early exits, explicit SQLite close) beyond the original review. The coordinator added a second test/fix pass and raised test specificity; on future audits, include combined-invalid-input scenarios and resource-lifecycle checks, not only isolated-path probes.
- The third audit found seed-path volatility gating and connection lifecycle gaps in public market-insights persistence wrappers. The coordinator added fail-closed seed/retry regressions and success/error connection-close checks; treat initial seeding and every standalone DB wrapper as independently auditable paths.
- The fourth audit found duplicate order-floor diagnostics when preflight and final order construction both inspected a non-actionable delta. Clearing both preflight logs before final construction fixed the duplicate without losing entries; a forced deterministic BTC-before-ETH regression asserts exactly one skip.
