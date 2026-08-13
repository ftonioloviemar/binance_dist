# Current State

Last updated: 2026-08-01.

## Purpose

Short continuity file for native Codex compaction and new chats. Keep this file concise; detailed evidence belongs in kanban cards, audit logs, tests, or strategy docs.

## Current Baseline

- Repository workflow source of truth: `workflow/kanban/`.
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
- Latest verification: `uv run pytest` -> 48 passed; dry-run audit `006fbbef3cad47f29197b2b789273c0a` completed with 4 simulated trades and one anti-churn block.
- OpenRouter model fallback and event-driven auto-curation are implemented and documented.
- Current active card: `TASK-019` sizing/drift/notional calibration (review).
- Latest completed card: `TASK-018` Binance order commission logging.
- Next safe verification: `uv run pytest`.

## Known Follow-Up

- No current blocker. The dry-run `final_balances` empty-portfolio warning was addressed in `TASK-012`.
