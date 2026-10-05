# TASK-044: Validate And Operationalize Market Insights

## Objective

Complete integrated verification, document the operator workflow, and update the existing three-day monitor with material-only market-insight checks.

## Context

See `docs/market-insights.md`, `docs/project-continuity.md`, `docs/STATE.md`, and the existing scheduled-monitor definition. Keep its current cadence.

## Verification

- Run all focused tests and `uv run pytest`.
- Run read-only `insights --days 30 --json` smoke against an isolated empty/temp database and verify no exchange or OpenRouter calls.
- Review adaptive audit classifications and monitor language against full/degraded/fallback semantics.
- Inspect git diff/status and ensure all test DBs/artifacts are isolated.

## Dependency And Progress

- The existing `monitor-diario-binance-dist` heartbeat was updated in place to include `market_insights_observation` audit states, indicator freshness/coverage, and read-only isolation checks for market/shadow databases. It preserves the existing three-day cadence, makes no live calls, and stays quiet without material changes.
- The monitor now distinguishes adaptive `full`, `degraded`, source-quality `warning` fallback, and technical `failed`; absent adaptive steps are not faults when `--adaptive` was not enabled. This matches the audit details emitted by `app.py`.
- `uv run pytest -q` -> 203 passed. No live operations or network calls were used for this verification.
- `docs/STATE.md` records technical review after 7 days and initial comparison after 30 complete shadow days; incomplete observations do not count, and these milestones are not claims of statistical significance.
- The read-only insights report smoke remains blocked on the TASK-042 human decision about cost-sensitivity semantics. Do not implement or approximate that report before the decision is recorded.

## Acceptance And Constraints

- Update docs/STATE.md with final command evidence and future 7-/30-day review points.
- Update the existing every-three-days monitor only if its available automation mechanism supports the desired safe, material-only summary; do not create another schedule.
- No live trades, Earn actions, or automatic candidate activation.
