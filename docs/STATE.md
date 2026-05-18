# Current State

Last updated: 2026-05-18.

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

- Last catch-up commit: `6f18b9f chore: catch up completed binance_dist tasks`.
- Latest workflow commit: `f687d19 docs: add context economy workflow`.
- Latest skill-alignment commit: `8d82cd8 docs: align grill workflow practices`.
- Latest full test evidence before this docs update: `uv run pytest` -> 31 passed.
- OpenRouter model fallback and event-driven auto-curation are implemented and documented.
- Current active card: none.
- Latest completed card: `TASK-012` to treat empty final balances as expected in dry-run.
- Next safe verification: `uv run pytest`.

## Known Follow-Up

- No current blocker. The dry-run `final_balances` empty-portfolio warning was addressed in `TASK-012`.
