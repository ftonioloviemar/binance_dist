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
- Latest implementation: `TASK-017` adds a configurable anti-churn cooldown for same-symbol opposite-side trades inside 12h unless drift exceeds 2x threshold.
- Latest verification: `uv run pytest tests/test_anti_churn.py tests/test_app_adaptive.py -q` -> 12 passed.
- OpenRouter model fallback and event-driven auto-curation are implemented and documented.
- Current active card: none.
- Latest completed card: `TASK-017` anti-churn cooldown.
- Next safe verification: `uv run pytest`.

## Known Follow-Up

- No current blocker. The dry-run `final_balances` empty-portfolio warning was addressed in `TASK-012`.
