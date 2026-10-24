# Current State

Last updated: 2026-10-24.

## Purpose

Short continuity file for native Codex compaction and new chats. Keep this file concise; detailed evidence belongs in kanban cards, audit logs, tests, or strategy docs.

## Current Baseline

- Repository workflow source of truth: `workflow/kanban/`.
- Durable operational lessons: `docs/lessons-learned.md`.
- Agent entrypoints: `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, `SKILLS.md`, `CONTEXT.md`, active card.
- Thin cross-tool wrappers: `CLAUDE.md`, `.github/copilot-instructions.md`.
- Default verification: `uv run pytest`.
- Trading validation default: unit tests, audit/log replay, and dry-run only.
- Commit rule: commit each completed card before starting the next one unless the user explicitly asks to hold commits.
- Use `grill-with-docs` for fuzzy strategy/domain/workflow language; update `CONTEXT.md` for stable trading terms.
- Catalogoantigo-adjacent skills installed in Codex home: `caveman`, `handoff`, `diagnose`, `improve-codebase-architecture`. Restart Codex for active skill list refresh.

## Current Work

- Planning request: replace OpenRouter analysis with local Codex CLI, exactly `gpt-6-luna` / `medium`. TASK-052 documents the design and implementation wave in `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md` and `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.
- User approved implementing the saved wave. TASK-053 completed in `b00f295`; TASK-054 completed offline in `5b64027`; TASK-055 completed and independently audited in `299cd4e`.
- User authorized unlimited synthetic TASK-056 inferences for fixed synthetic context/Luna-medium/sanitized diagnostics; that authorization alone excluded scheduler/live Binance/Earn/TASK-057. A separate TASK-057 cutover and next scheduled live-cycle approval was received on 2026-10-24 and is recorded below. Root cause confirmed: Git for Windows descendants of `codex exec` retained temp files after the CLI exited (Restart Manager found Git in all 5 observed cleanup failures). Reaper now pins and revalidates descendant process handles, then terminates only those descendants before cleanup. Three consecutive synthetic inferences were accepted; 12 descendants terminated, zero busy cleanup errors. Focused replay/adapter/launcher -> 46 passed; full suite -> 367 passed and 7 known baseline failures. `fe37b5d` was the pre-cutover production baseline; TASK-057 advanced production as recorded below. This authorization supersedes older notes below that say no further inference was authorized.
- The stdin-based sanitized wrapper passed stub-only success and exception tests; it reports acceptance/failure code or exception class, never rationale or exception text. Continuous synthetic-call authorization is recorded in `docs/codex-cli-analysis.md` and TASK-056; old “no further inference” notes are superseded. TASK-057 cutover is now separately authorized and executing.
- TASK-054 RED was confirmed (missing module); focused verification -> 62 passed. Full suite -> 315 passed, 7 unrelated baseline failures. Workdir is pinned outside the user profile at `%SystemRoot%\Temp`; matching `debug prompt-input` preflight found no global AGENTS marker. No real model call.
- Still unproven: effective managed model identity/policy, complete real Codex API-vs-tool/network boundary, and Task Scheduler PATH/auth access. The CLI accepted structured output for the requested `gpt-6-luna` / medium, but did not expose an independent effective-model identity. These limitations remain documented during the authorized TASK-057 rollout.
- TASK-057 production cutover selected code at `9e6b81b`; the reviewed test/documentation follow-up beginning at `05e4236` was fast-forwarded to production. `.env` and `run_prod.bat` SHA-256 values matched their pre-sync values, confirming neither changed. `.env` selects `codex_cli`, contains no OpenRouter key, and loads with no OpenRouter models. Sanitized rollback template is outside Git with protected ACL; see active card for hashes/path. User disabled the exposed OpenRouter key; UI now offers `Enable` for that key. No replacement key unless rollback requires OpenRouter. Task `binance_dist` is `Ready`, last run 09:00 result 0, next 21:00 on 2026-10-24. One-time same-thread follow-up is scheduled for 21:10 local to inspect Scheduler and sanitized logs only; no manual task/exchange call. Interactive Codex CLI/auth are present, but scheduled PATH/auth remain unproven until its run.
- A prior MCP inventory command surfaced credential values in tool output. Do not repeat or store them; rotate potentially exposed affected credentials outside this implementation flow. No credentials were persisted and no rotation was performed.
- Goal: make adaptive `btc_24h` freshness fallbacks diagnosable without changing strategy behavior.
- `TASK-051-audit-adaptive-btc-source-age` completed: audit details now record UTC collection/decision times and signed BTC source age for adaptive applied, fallback, and calculation-failure outcomes.
- Verification: adaptive tests -> 33 passed; full `uv run pytest` -> 280 passed; compileall and `git diff --check` passed. No live exchange/provider calls or schedule/config changes.
- Historical cause of the 2026-10-17/18 stale-source fallbacks remains unproven; the next scheduled audit will include the missing timing evidence.

## Context Economy

- Before starting each new task in the same session, use focused `mcp context-mode` lookup, then reload the canonical docs and active card.
- Prefer `ctx_execute_file`, `ctx_index`, and focused `ctx_search` for large files or history.
- Use native Codex compaction when the context grows, but persist important handoff state here or in the active card first.

## Latest Verified State

- Latest implementation: `TASK-013` added a tradability-aware drift guard so untradable drift now skips instead of producing avoidable `noop`.
- Latest implementation: `TASK-014` added minimum executable delta floor estimation and floor-aware skip logging.
- Latest implementation: `TASK-016` adds configurable min-notional uplift tolerance for near-floor trade sizing.
- Latest implementation: `TASK-018` requests full Binance order responses and logs returned fill commissions in live order audit details.
- Latest implementation: `TASK-019` raises the local/default drift threshold to 3% to avoid planning deltas that commonly fall below Binance's executable notional floor; uplift remains capped at 10%.
- Latest implementation: `TASK-020` promotes only OpenRouter free models that pass the structured JSON probe; untested catalog entries are no longer promoted.
- Latest implementation: `TASK-021` persists a 24-hour CoinGecko cache and marks reused macro data stale with age after upstream failure.
- Latest implementation: `TASK-022` classifies below-floor per-symbol deltas as non-actionable `trade_floor` events instead of pending execution failures.
- Latest implementation: `TASK-023` treats null/non-text OpenRouter message content as an invalid model output, preserving fallback and preventing run-level `NoneType` failures.
- Latest strategy activation: `TASK-024` enables `--adaptive` in `run_prod.bat`, used by the scheduled production task; this was explicitly approved by the user. Validate audit evidence in subsequent scheduled runs.
- Latest verification: `uv run pytest -q` -> 53 passed; `TASK-023` focused test -> 16 passed after RED reproduced the historical `NoneType` failure.
- OpenRouter model fallback and event-driven auto-curation are implemented and documented.
- Current active card: TASK-057 in `workflow/kanban/03_doing/`; earlier TASK-051 is complete.
- Latest completed cards: `TASK-020`, `TASK-021`, `TASK-022`, `TASK-023`, and `TASK-024` operational resilience/strategy activation.
- `TASK-024` verified that `run_prod.bat` applies adaptive strategy in a dry-run; the Windows task remains `Ready` and points to that launcher. Observe upcoming scheduled run audits for `adaptive_strategy` before evaluating practical results.
- Latest verification: `uv run pytest -q` -> 54 passed; adaptive launcher dry-run `4462f11c56904297bb6ce00f950c49f0` completed without live orders.
- Current financial-observability work: `TASK-025` persists decimal portfolio snapshots for Spot and Simple Earn in SQLite under `state/`, with data-quality and missing-price markers; no cost gate is active yet.
- Latest verification: `TASK-025` focused tests -> 3 passed; full `uv run pytest -q` -> 57 passed.
- `TASK-026` adds fill-level effective-cost summarization and compatible audit detail fields; app integration will pass live quote/reference prices in the next card.
- Latest verification: `TASK-026` focused tests -> 5 passed; full `uv run pytest -q` -> 61 passed.
- `TASK-027` integrates before/after Spot+Earn snapshots and fee-reference lookup into the rebalance flow; persistence remains best-effort and no cost gate is active.
- Latest verification: `TASK-027` focused tests -> 11 passed; full `uv run pytest -q` -> 63 passed.
- `TASK-028` adds hold benchmarking, explicit missing-price handling, and external-flow records; values are not labeled profit unless future reconciliation marks flows complete.
- Latest verification: `TASK-028` focused tests -> 3 passed; full `uv run pytest -q` -> 66 passed.
- `TASK-029` adds `performance --days 30` with text/JSON output for 24h, 7d, and 30d; empty history reports `no_data`.
- Latest verification: `TASK-029` focused tests -> 3 passed; full `uv run pytest -q` -> 69 passed; CLI JSON smoke passed.
- `TASK-030` adds configurable `off/observe/enforce` cost policy and audit event before execution; default `observe`, and uncalibrated data never blocks.
- Latest verification: `TASK-030` focused tests -> 19 passed; full `uv run pytest -q` -> 73 passed.
- `TASK-031` persists real execution costs and aggregates gross notional, commission, bps, and unknown conversions in performance horizons; dry-run costs are not persisted.
- Latest verification: `TASK-031` focused tests -> 1 passed; full `uv run pytest -q` -> 74 passed.
- `TASK-032` documents performance interpretation, cost-gate configuration, attribution limits, and lessons learned; SQLite schema is version 2.
- Latest verification: `TASK-032` full `uv run pytest -q` -> 74 passed; `git diff --check` and performance JSON smoke passed.
- Integrated dry-run `7c6e041dc5f04b1a8bb706085dd33ff7` completed with five simulated trades; audit recorded `cost_gate=uncalibrated`/allowed and before/after snapshots. Simple Earn `LD*` assets remain an explicit incomplete-price data gap.
- `TASK-034` refreshes Spot and Earn after trades/subscriptions, suppresses performance deltas for incomplete snapshots, and invalidates two confirmed duplicate `after` snapshots while preserving their values and SQLite backup.
- Latest verification: `TASK-034` full suite -> 82 passed with test-only settings; report against the corrected SQLite shows incomplete/unknown deltas in 24h, 7d, and 30d. No live exchange calls.
- `TASK-035` removes a Spot `LD<asset>` alias from financial snapshot input only when the matching underlying asset is present in Simple Earn positions; unmatched aliases remain incomplete. Trade/execution balances are unchanged.
- Latest verification: `TASK-035` RED reproduced incomplete quality; focused integration tests -> 10 passed; full `uv run pytest` -> 84 passed. Current historical report remains incomplete because past SQLite snapshots cannot safely be reconstructed from persisted data; no live exchange calls.
- Next safe verification: inspect the next newly persisted before/after snapshots and confirm `missing_prices` no longer includes matched `LD*` aliases.

## Known Follow-Up

- No current blocker. The integrated dry-run did not exercise trade-floor logging because the portfolio was within drift; unit tests cover that path. The dry-run `final_balances` empty-portfolio warning was addressed in `TASK-012`.

## Current Goal

- Latest user objective: implement the Codex CLI analysis version. TASK-053 through TASK-056 are complete; TASK-057 is actively executing under explicit production and next-cycle authorization. The exposed OpenRouter key is disabled; do not create a replacement unless rollback requires OpenRouter.
- Active card: TASK-057 in `workflow/kanban/03_doing/`; TASK-056 is complete in `workflow/kanban/05_done/`. Production cutover is authorized and complete; observation of the next scheduled live cycle is pending. Manual live runs and scheduled-task changes remain out of scope.
- Current verification in the production checkout with its `.env` loaded: focused Codex/provider/launcher tests -> 74 passed; full suite -> 373 passed, 1 known baseline adaptive overflow failure (`test_rebalance_fails_closed_when_required_macro_source_is_untrusted[overflow]`). The candidate full suite without production `.env` produced 368 passed and 6 adaptive failures, so use the production result for the live configuration. Independent review approved the TASK-057 docs/test follow-up; test-isolation fixes are integrated in production history since `05e4236`.
- Next step: observe the scheduled 2026-10-24 21:00 -03:00 cycle via the one-shot read-only check scheduled for 21:10. Do not manually start the task.
- Decision: keep the 0..15 minute BTC freshness gate and base-profile fallback unchanged; do not change schedule or live allocation automatically.
- Earlier card `TASK-051-audit-adaptive-btc-source-age` is complete; see its kanban card for test and commit evidence.
- Completed: `TASK-036` documented market-data reliability rules, shadow-session semantics, cost assumptions, and attribution boundaries; see `docs/market-insights.md` and `docs/strategy-scenario-b.md`.
- Existing market-insights work remains documented below; its completed cards are historical context, not active tasks.
- Strategy comparison is hypothetical and conditional on the advice/targets observed in each real run; use a separate SQLite store, full-precision quantities, explicit cost assumptions, and `incomplete` when data coverage is insufficient.
- No live trades, Earn operations, production schedule change, automatic strategy activation, or new model calls for shadow evaluation.
- Verification baseline before this wave: working tree clean at `77ff825`; 21.5 GB free on C:.
- TASK-037 completed and independently audited: additive source metadata, UTC timestamps, validation, stale/cache classification, and sanitized diagnostics. Final isolated full suite -> 108 passed; no live exchange calls. See its kanban card for evidence.
- TASK-038 implementation verification: focused adaptive tests -> 29 passed; isolated full suite -> 127 passed; compileall and diff check passed. Independent audit found numeric overflow, fixed with regression coverage; final reviewer confirmation is pending. No live exchange calls.
- TASK-038 completed and independently reviewed with no remaining findings; adaptive source gating is tested and the market-insights contract doc now reflects implementation.
- TASK-039 completed and independently audited: public closed-candle collector with bounded UTC cache and 20-second budget; focused tests -> 21 passed, isolated full suite -> 148 passed. Follow-up audit found no remaining deadline/persistence findings; late worker test confirms no post-timeout candle writes. No live calls.
- TASK-040 completed and independently audited: Decimal multi-horizon market indicators, per-metric invalid/gap coverage, deterministic input fingerprints, and versioned idempotent SQLite persistence; focused tests -> 20 passed, isolated full suite -> 168 passed. Runtime invocation is deferred to TASK-043. No live calls.
- TASK-041: user approved isolated shadow storage, metric formulas, and fail-closed handling for missing symbol filters. Four independent audits surfaced nine material gaps, now fixed: missing prices for virtual-only holdings pause atomically with complete symbol diagnostics, null deltas, and retry; nonpositive quote marks and missing BTC volatility (including seed) fail closed; `policy_version` is persisted/replayed; combined fee/slippage above 100% is rejected; all owned SQLite connections close on success/error; residual-drift assertion is exact; and planner skips are counted once independent of delta iteration order. Focused tests -> 47 passed; full suite -> 195 passed; compileall and diff check passed. Final independent audit found no P1/P2 issues. Committed as `937335a` before TASK-042.
- TASK-042: user approved option 2: fixed-trade-path default/stress cost overlay, estimated from persisted gross turnover, with no re-simulation. Read-only `insights` CLI/report implemented; focused tests -> 11 passed, full suite -> 214 passed, compileall and diff check passed. Independent specialist audit found no P1/P2 issues. Local DB has only a valid `seeded` observation; no policy performance comparison is available yet.
- TASK-043 completed: user-approved shadow persistence is integrated with independent documented switches and stable per-quote sessions. Real simulator tests verify virtual inventory/completion state only in `shadow_portfolios.db`, indicators/aggregates only in `market_insights.db`, and no session advance on collection deadline. Full suite -> 203 passed; compileall and diff check passed; independent audit found no P1/P2. No live operations.
- TASK-044 complete: existing `monitor-diario-binance-dist` heartbeat remains on its three-day cadence and includes read-only shadow/indicator checks with material-only notifications. Isolated CLI smoke returned valid empty JSON, left its temporary DB unchanged, and created no shadow DB. TASK-042 focused report tests -> 11 passed; full suite -> 214 passed; compileall and diff check passed. No live operations or network calls.
- TASK-044 verification so far: adaptive audit semantics are distinguished as full/degraded/fallback/technical failure in the monitor prompt; full suite -> 203 passed at that stage. No live exchange operations.
- Review milestones: inspect technical integrity after 7 days from the first complete shadow observation; evaluate initial comparisons after 30 complete days. These are review points, not statistical-significance claims; incomplete observations do not count toward the comparison window.
