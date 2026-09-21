# Current State

Last updated: 2026-09-21.

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
- Current active card: none.
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
- Next safe verification: `uv run pytest`.

## Known Follow-Up

- No current blocker. The integrated dry-run did not exercise trade-floor logging because the portfolio was within drift; unit tests cover that path. The dry-run `final_balances` empty-portfolio warning was addressed in `TASK-012`.
