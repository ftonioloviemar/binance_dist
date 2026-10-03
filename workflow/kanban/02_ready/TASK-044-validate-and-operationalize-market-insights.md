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

## Acceptance And Constraints

- Update docs/STATE.md with final command evidence and future 7-/30-day review points.
- Update the existing every-three-days monitor only if its available automation mechanism supports the desired safe, material-only summary; do not create another schedule.
- No live trades, Earn actions, or automatic candidate activation.
