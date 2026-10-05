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
- TASK-042 has now added the read-only `insights` report; perform the isolated empty/temp-database CLI smoke and final integration checks here. Do not infer live profitability from the current seeded-only production-local data.
- Final focused report tests -> 11 passed; full suite -> 214 passed; compileall and diff check passed.
- Isolated CLI subprocess smoke from a temporary working directory -> exit 0, valid JSON with zero observations, empty insights DB unchanged, and no shadow DB created. The command has no exchange/OpenRouter code path; tests also block network connection attempts.

## Acceptance And Constraints

- Update docs/STATE.md with final command evidence and future 7-/30-day review points.
- Update the existing every-three-days monitor only if its available automation mechanism supports the desired safe, material-only summary; do not create another schedule.
- No live trades, Earn actions, or automatic candidate activation.

## Closure Evidence

- Adaptive source classifications are documented in the monitor prompt and remain consistent with `app.py`: full/degraded are applied quality levels, required-source fallback is warning, technical error is failed, and an absent adaptive step is expected when not enabled.
- Existing heartbeat `monitor-diario-binance-dist` remains at `FREQ=DAILY;INTERVAL=3`; no duplicate schedule was created. Prompt only reports material changes and checks shadow/indicator quality without reading private holdings.
- Local production-path smoke currently returns only a `seeded` observation. This is expected after initialization; wait for complete later runs and the documented 7-/30-day review milestones before judging policy performance.
- No live trade/Earn calls or network calls were made during validation.
