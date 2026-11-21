# TASK-068: Align project guidance with current Context Mode MCP

## Objective

Replace obsolete Context Mode tool names and document safe routing for the current MCP tools.

## Context

Project guidance referred to `ctx_execute_file` and `ctx_batch_execute`. The installed Context Mode Engine exposes `ctx_execute` with an optional `file` field and `ctx_batch`.

## Scope

- Update `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, `SKILLS.md`, and `workflow/kanban/README.md`.
- Preserve the distinction between read-only retrieval and mutating `ctx_upgrade`/`ctx_purge` operations.
- Do not upgrade the local installation or delete context data.

## Verification

- Compare names and roles with the active MCP tool definitions and [official tool reference](https://contextmode.ai/docs/engine/tools).
- Search canonical project docs for obsolete MCP method names.
- Run `git diff --check` and inspect the exact documentation diff.

## Evidence

- `ctx_doctor` reported Context Mode Engine `2.2.1`, latest; MCP, project, SQLite, index, and current hook round-trip checks passed. It also reported legacy data/temp artifacts and a prior hook error; no cleanup or upgrade was authorized or performed.
- Updated canonical guidance to use `ctx_execute`/`file`, `ctx_batch`, `ctx_index`, `ctx_search`, `ctx_resume`, `ctx_stats`, `ctx_doctor`, `ctx_upgrade`, and `ctx_purge`.
- Verified against the active MCP definitions and the official tool reference; obsolete names remain only in explicit warnings against using them.
- `git diff --check` passed. No Context Mode upgrade, data purge, or hook/config edit was performed.
