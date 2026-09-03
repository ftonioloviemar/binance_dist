# Current State

Last updated: 2026-09-03.

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
- Latest verification: `uv run pytest -q` -> 53 passed; `TASK-023` focused test -> 16 passed after RED reproduced the historical `NoneType` failure.
- OpenRouter model fallback and event-driven auto-curation are implemented and documented.
- Current active card: none.
- Latest completed cards: `TASK-020`, `TASK-021`, `TASK-022`, and `TASK-023` operational resilience adjustments.
- Next safe verification: `uv run pytest`.

## Known Follow-Up

- No current blocker. The integrated dry-run did not exercise trade-floor logging because the portfolio was within drift; unit tests cover that path. The dry-run `final_balances` empty-portfolio warning was addressed in `TASK-012`.
