# TASK-042: Compare Shadow Policies And Report

## Objective

Compare hold, baseline, and volatility-guard scenarios and add read-only text/JSON reporting.

## Context

See `docs/market-insights.md`, `TASK-040`, and `TASK-041`. The candidate threshold and cost rates are experimental assumptions.

## Test Contract

- Tests: `tests/test_market_insights_report.py`.
- RED: no read-only market-insights report exists.
- Cover net simulated change, cost sensitivity, turnover, drawdown, residual drift, incomplete data/null metrics, policy version, report without network access, and deterministic JSON.
- Command: `uv run pytest tests/test_market_insights_report.py`.

## Acceptance And Constraints

- Command interface: `uv run python app.py insights --days 30 [--json]`.
- Report reads only `state/market_insights.db`; no collection or session mutation.
- Do not describe conditional simulation as a full AI counterfactual or realized profit.
