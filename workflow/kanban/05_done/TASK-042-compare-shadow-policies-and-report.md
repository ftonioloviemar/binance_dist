# TASK-042: Compare Shadow Policies And Report

## Objective

Compare hold, baseline, and volatility-guard scenarios and add read-only text/JSON reporting.

## Context

See `docs/market-insights.md`, `TASK-040`, and `TASK-041`. The candidate threshold and cost rates are experimental assumptions.

## Test Contract

- Tests: `tests/test_market_insights_report.py`.
- RED: no read-only market-insights report exists.
- Cover net simulated change, default/stress post-hoc cost overlays on persisted turnover under a fixed-trade-path assumption, turnover, drawdown, residual drift, incomplete data/null metrics, policy version, report without network access, and deterministic JSON.
- Pair `hold`, `baseline`, and `volatility_guard_v1` by `(session_id, run_id)`; compare each policy's net-return delta to hold only when all required rows are complete and share the same initial equity. Missing policies, mismatched seeds, or incomplete rows produce an incomplete comparison with null deltas, never zero-filled values.
- A complete initial seed is reported as `seeded` (not an incomplete data error); it carries no policy delta or cost-sensitivity claim until a complete subsequent observation exists.
- Include observations in the UTC lookback window, with an injectable reference time for deterministic tests. Sort output by observation time, session, run, and policy.
- JSON must have a stable schema, decimal-safe serialization, and no generated-at timestamp, input fingerprints, holdings, or balances. Text and JSON must derive from the same report model.
- Open `market_insights.db` read-only; a missing/invalid DB must not create a file, schema, or table. Tests use isolated temporary paths and prove no access to `shadow_portfolios.db`, `performance.db`, network, collectors, or simulator.
- Command: `uv run pytest tests/test_market_insights_report.py`.

## Acceptance And Constraints

- Command interface: `uv run python app.py insights --days 30 [--json]`.
- Report reads only `state/market_insights.db`; no collection or session mutation.
- Do not describe conditional simulation as a full AI counterfactual or realized profit.
- Label every value simulated and conditional on previously observed targets/advice; incomplete data remains explicit.

## Decision Record

- Context: current aggregate rows store modeled cost, cost-adjusted net return, and gross turnover, but do not persist the fee/slippage rates or a cost-profile identifier. The documented default/stress rates can support a post-hoc cost overlay on the persisted turnover while holding the executed trade path fixed; that is an estimate, not a re-simulation.
- Options: (1) report only observed modeled cost and its ratios; (2) apply default/stress cost overlays to persisted turnover and label the fixed-trade-path assumption; (3) re-execute policies under separate cost profiles, which requires an expanded simulator/persistence contract.
- Recommendation: option 2 offers useful cost sensitivity while keeping TASK-042 read-only, provided the report explicitly says order quantities, affordability, and decisions are held fixed. Use a separate approved task for option 3.
- Human decision: approved by user (“aprovo 042”) on 2026-10-05: option 2, post-hoc default/stress cost overlays over persisted gross turnover, with observed trade path, quantities, affordability, and decisions fixed. Label outputs as estimates, not re-simulations.
- Cost formula contract: calculate gross return as persisted net return plus persisted modeled cost divided by initial equity; subtract scenario rate times persisted gross turnover divided by initial equity, where each scenario rate is fee plus slippage per side as already charged on every buy/sell notional. Report total modeled cost separately. Default total rate is 0.20% per side and stress total is 0.40% per side, per `docs/market-insights.md`.
- Resume criteria: decision recorded and acceptance tests updated; execution resumed in `03_doing`.
- Dependency impact: TASK-043 integration was completed without report cost sensitivity. TASK-044 can now perform its final report smoke and operational validation.

## Verification

- RED observed: focused collection failed because `market_insights_report` did not exist.
- Focused tests: `uv run pytest tests/test_market_insights_report.py -q` -> 11 passed.
- Full suite: `uv run pytest -q` -> 214 passed; `uv run python -m compileall -q app.py market_insights_report.py` passed; `git diff --check` passed.
- CLI: `uv run python app.py insights --help` passed. Read-only smoke against the local insights database returned one `seeded` observation; no performance comparison is yet available.
- Independent specialist review: no P1/P2 findings. It confirmed the fixed-path cost formula, SQLite read-only boundary, incomplete/seeded semantics, and CLI wiring. Its noted low-level test gaps were covered by adding parser/nonpositive-days and malformed-timestamp tests; the local DB still has only the seed observation.
