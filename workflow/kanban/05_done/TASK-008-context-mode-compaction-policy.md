---
id: TASK-008
title: Context-mode and native compaction policy
status: 05_done
kind: docs-only
---

# TASK-008 - Context-mode and native compaction policy

## Objective

Adapt the `catalogoantigo` context-economy workflow to this repository.

## Source Rules Reused

- Use `mcp context-mode` before starting each new task in the same session.
- Reload canonical docs and the active card after the context-mode lookup.
- Use native Codex compaction when context grows, but persist important state first.
- Prefer focused context-mode file/index/search tools on Windows instead of dumping broad file contents.
- Do not require a final context-mode checkpoint after every card; use it only when continuity risk exists.

## Completed Scope

- Updated `AGENTS.md` with context economy rules.
- Updated `docs/project-continuity.md` with context-mode/native compaction policy.
- Updated `workflow/kanban/README.md` with card-level context rules.
- Added `docs/STATE.md` as the short continuity/handoff file.

## Verification

- Context source inspected with `mcp context-mode` against `C:\java\catalogoantigo`.
- Docs-only verification: `git diff --check`.
