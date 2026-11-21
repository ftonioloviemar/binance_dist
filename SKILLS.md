# Local Skill Catalog

Use this catalog to decide which available Codex/project skills apply in this repository.

## Always Relevant

- `superpowers:systematic-debugging`: use before fixing unexpected behavior, failed audits, rejected orders, timeouts, or strategy drift.
- `superpowers:test-driven-development`: use before changing production behavior in Python code; a `gpt-6.1-terra`/medium test-specialist subagent writes the tests and contract, and `gpt-6-luna`/medium runs RED and GREEN as specified in `docs/project-continuity.md`.
- `superpowers:verification-before-completion`: use before claiming a card is complete.
- `run-kanban-loop`: use when executing approved kanban cards continuously.

## Planning And Orchestration

- `superpowers:writing-plans`: use for multi-step changes that need a saved plan.
- `superpowers:subagent-driven-development`: use when an implementation plan has independent tasks and review gates.
- `superpowers:requesting-code-review`: use for each independent Plan -> Goal review, dispatching the required reviewer with the skill's template and adapting it for non-code changes. If unavailable, report the limitation and stop the review stage rather than silently substituting.
- `grill-with-docs` / `grilling`: use for every user-requested plan to resolve all material open decisions and constraints with the user; do not ask again about decisions already made. Also use when strategy, workflow, or trading-domain language is ambiguous. Resolved stable domain terms go to `CONTEXT.md`; workflow terms stay in `docs/project-continuity.md`. If unavailable, use an equivalent interview and disclose it.
- `setup-matt-pocock-skills`: use if `docs/agents/` needs to be regenerated because the tracker or domain-doc layout changed.
- `zoom-out`: use when a module's role in the trading flow is unclear before making localized changes.
- `handoff`: use when preparing a fresh chat/agent continuation; keep it compact and reference repo artifacts instead of duplicating them.
- `caveman`: use only when the user asks for very terse/token-saving communication.
- `improve-codebase-architecture`: use when the user asks to find refactoring opportunities, deepen modules, improve testability, or make the codebase easier for agents to navigate.

## Security And Trading Safety

- `security-best-practices`: use for API key handling, account permissions, secret logging, and live-trading safeguards.
- `security-threat-model`: use before expanding automation that can move funds, trade live, or change API permissions.

## Debugging

- `diagnose`: use for hard bugs and regressions when a disciplined reproduce/minimize/hypothesize/instrument/fix/regression-test loop is more appropriate than a quick local fix.
- `superpowers:systematic-debugging`: use before fixing unexpected behavior, failed audits, rejected orders, timeouts, or strategy drift.

## Optional Utilities

- `pdf`, `spreadsheets`, `playwright`: use only when the task actually involves those artifacts or browser validation.

## Context And Compaction

- Use the current Context Mode Engine MCP tools for context retrieval: `ctx_search` for indexed history, `ctx_execute` (optional `file`) for bounded processing of large files/output, `ctx_index` for repeated lookup, `ctx_batch` for concise multi-command queries, and `ctx_resume` after native compaction or resuming a long chat.
- Use `ctx_doctor` for installation/health checks and `ctx_stats` when asked about context savings. Do not use obsolete `ctx_execute_file`/`ctx_batch_execute` names. `ctx_upgrade` and `ctx_purge` are mutating operations and require explicit user authorization.

## Local Decisions

- The issue tracker for this repo is `workflow/kanban/`, not GitHub Issues.
- TDD cards should name the exact test file and command.
- The TDD test-author subagent and Plan -> Goal independent review are mandatory as specified in `docs/project-continuity.md`, even when ordinary cost-based guidance would not dispatch a subagent. For other roles, use `docs/subagent-specialist-matrix.md`; avoid unnecessary subagents for simple docs-only edits or unresolved coordinator decisions.
- Locally installed catalogoantigo-adjacent skills are `grill-with-docs`, `setup-matt-pocock-skills`, `zoom-out`, `caveman`, `handoff`, `diagnose`, and `improve-codebase-architecture`. Restart Codex after installation so the session skill list refreshes.
