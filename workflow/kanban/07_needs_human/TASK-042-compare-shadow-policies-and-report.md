# TASK-042: Compare Shadow Policies And Report

## Objective

Compare hold, baseline, and volatility-guard scenarios and add read-only text/JSON reporting.

## Context

See `docs/market-insights.md`, `TASK-040`, and `TASK-041`. The candidate threshold and cost rates are experimental assumptions.

## Test Contract

- Tests: `tests/test_market_insights_report.py`.
- RED: no read-only market-insights report exists.
- Cover net simulated change, cost sensitivity (definition pending below), turnover, drawdown, residual drift, incomplete data/null metrics, policy version, report without network access, and deterministic JSON.
- Pair `hold`, `baseline`, and `volatility_guard_v1` by `(session_id, run_id)`; compare each policy's net-return delta to hold only when all required rows are complete and share the same initial equity. Missing policies, mismatched seeds, or incomplete rows produce an incomplete comparison with null deltas, never zero-filled values.
- Include observations in the UTC lookback window, with an injectable reference time for deterministic tests. Sort output by observation time, session, run, and policy.
- JSON must have a stable schema, decimal-safe serialization, and no generated-at timestamp, input fingerprints, holdings, or balances. Text and JSON must derive from the same report model.
- Open `market_insights.db` read-only; a missing/invalid DB must not create a file, schema, or table. Tests use isolated temporary paths and prove no access to `shadow_portfolios.db`, `performance.db`, network, collectors, or simulator.
- Command: `uv run pytest tests/test_market_insights_report.py`.

## Acceptance And Constraints

- Command interface: `uv run python app.py insights --days 30 [--json]`.
- Report reads only `state/market_insights.db`; no collection or session mutation.
- Do not describe conditional simulation as a full AI counterfactual or realized profit.
- Label every value simulated and conditional on previously observed targets/advice; incomplete data remains explicit.

## Human Decision Required

- Decision needed: define what “cost sensitivity” means in this report.
- Context: current aggregate rows store modeled cost, cost-adjusted net return, and gross turnover, but do not persist the fee/slippage rates or a cost-profile identifier. The documented default/stress rates can support a post-hoc cost overlay on the persisted turnover while holding the executed trade path fixed; that is an estimate, not a re-simulation.
- Options: (1) report only observed modeled cost and its ratios; (2) apply default/stress cost overlays to persisted turnover and label the fixed-trade-path assumption; (3) re-execute policies under separate cost profiles, which requires an expanded simulator/persistence contract.
- Recommendation: option 2 offers useful cost sensitivity while keeping TASK-042 read-only, provided the report explicitly says order quantities, affordability, and decisions are held fixed. Use a separate approved task for option 3.
- Human decision: pending.
- Resume criteria: record the selected meaning, update acceptance tests, then resume in `08_human_reviewed`.
- Dependency impact: TASK-043 may integrate the bounded collector/simulator into run outcomes, but must not add or present cost-sensitivity reporting until this contract is settled. TASK-044's report smoke depends on TASK-042 completion.
