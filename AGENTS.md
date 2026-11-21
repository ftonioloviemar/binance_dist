# Project Instructions

These rules apply to agents and tools working in this repository.

## General Rules

- Always read the project documentation and skill guidance before deciding.
- Before changing files, check available disk space and create a backup or rollback point when reversal would be costly.
- If you do not know, say "nao sei" clearly.
- Do not invent commands, parameters, URLs, exchange rules, or API behavior.
- Consider the real environment before running commands. This repo is operated mostly from Windows/PowerShell with `uv`.
- Do not revert user or parallel-chat changes without an explicit request.

## Canonical Workflow

- Work is tracked in the internal kanban under `workflow/kanban/`, not GitHub Issues.
- Use `docs/project-continuity.md` as the canonical workflow/orchestration guide.
- Use `docs/STATE.md` as the short current-state and handoff file for native Codex compaction or new chats.
- Use `CONTEXT.md` for stable trading/domain terminology. Do not put workflow terms there.
- Use `SKILLS.md` as the local skill catalog and trigger map.
- For every user-requested plan, follow the Plan -> Goal -> independent review policy in `docs/project-continuity.md` and its model assignments in `docs/model-selection.md`. Preserve explicit plan-only requests and safety/approval gates.
- For behavior changes, follow TDD: a clean-context `gpt-6.1-terra`/medium test-specialist subagent authors the tests; `gpt-6-luna`/medium runs RED, GREEN and regression tests; then refactor. Follow the availability, isolation and safety rules in `docs/project-continuity.md`.
- For non-trivial TDD cards, use an independent specialist to audit results before closing; do not let the test author or implementer serve as the independent end-of-Goal reviewer.
- For other repeated task types, use reusable specialist subagents only when `docs/subagent-specialist-matrix.md` predicts precision/context/cost gain, except for the independent end-of-Goal review required by the Plan -> Goal policy. Do not downshift when it would create rework or trading risk.
- Keep work in small cards that can be verified and committed independently.
- When a card is done, move the file to the matching kanban state directory; editing status text is not enough.
- Commit every completed card before starting the next one, unless the user explicitly asks to hold commits. If prior work was accumulated before this rule, make a clearly described catch-up commit and then resume one-commit-per-card.
- At task close, check whether a reusable rule, test, helper, agent instruction, skill trigger, or follow-up card should be captured before moving on.

## Context Economy

- Before starting each new task in the same session, use `mcp context-mode` to retrieve relevant indexed context cheaply, then reload `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, the active card, and at most 1-2 canonical docs directly cited by the card.
- Use native Codex compaction when context grows, but persist any important state first in `docs/STATE.md` or the active kanban card. Do not rely on chat memory alone for task continuity.
- Use the current Context Mode Engine MCP tools: `ctx_execute`, `ctx_batch`, `ctx_index`, `ctx_search`, `ctx_resume`, `ctx_stats`, `ctx_doctor`, `ctx_upgrade`, and `ctx_purge`.
- In Windows/PowerShell, use `ctx_execute` with its optional `file` field for focused large-file processing; use `ctx_index` plus `ctx_search` when the same docs or output will be queried repeatedly. Use `ctx_batch` for multiple concise commands plus questions about their combined output. Do not call obsolete names such as `ctx_execute_file` or `ctx_batch_execute`.
- After native compaction or resuming a long chat, call `ctx_resume` before repeating work. Use `ctx_doctor` to check installation/health and `ctx_stats` when context savings are requested. Never use `ctx_purge` or `ctx_upgrade` as routine maintenance; those change local data or the installation and require an explicit user request.
- Do not repeat long results already captured in `docs/STATE.md`, kanban cards, or docs; reference the file and continue.
- Context-mode is not mandatory inside subagents. Instead, prompts to subagents must include or point to the minimal rules and active-card context they need.
- The coordinator must evaluate subagent output before applying it, and recalibrate future model/reasoning choices when a subagent is too weak, too expensive, or assigned to the wrong role.

## Domain And Docs

- Use `grill-with-docs` when strategy, workflow, or domain language is fuzzy, overloaded, or likely to become a durable rule.
- When `grill-with-docs` resolves a stable domain term, update `CONTEXT.md` immediately. Use ADRs sparingly and only for hard-to-reverse decisions with real trade-offs.
- Keep tool-specific wrappers such as `CLAUDE.md` and `.github/copilot-instructions.md` thin; they should point back to canonical repo docs.
- Use `docs/model-selection.md` when choosing coordinator/subagent model strength.

## Trading Safety

- Do not run live trading, live redemption, or live subscription commands just to validate a code change unless the user explicitly approves that execution.
- Prefer dry-run, unit tests, and log replay for validation.
- Treat API keys, account balances, order history, and strategy parameters as sensitive.
- Any strategy change that can materially alter live allocation must be documented and selected by the user before implementation.

## Verification

- Default test command: `uv run pytest`.
- For audit/log behavior, prefer tests over editing historical logs.
- For exchange behavior, verify against official Binance documentation and the local parser/client code.
- Before a commit, review `git status`, the diff, and the verification evidence.
