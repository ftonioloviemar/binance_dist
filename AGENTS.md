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
- Use `SKILLS.md` as the local skill catalog and trigger map.
- For behavior changes, follow TDD: failing test first, minimal implementation, verification, then refactor.
- For non-trivial TDD cards, use a clean-context specialist subagent to define or validate the test contract before implementation and a separate specialist to audit results before closing.
- Keep work in small cards that can be verified and committed independently.
- When a card is done, move the file to the matching kanban state directory; editing status text is not enough.
- Commit every completed card before starting the next one, unless the user explicitly asks to hold commits. If prior work was accumulated before this rule, make a clearly described catch-up commit and then resume one-commit-per-card.

## Context Economy

- Before starting each new task in the same session, use `mcp context-mode` to retrieve relevant indexed context cheaply, then reload `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, the active card, and at most 1-2 canonical docs directly cited by the card.
- Use native Codex compaction when context grows, but persist any important state first in `docs/STATE.md` or the active kanban card. Do not rely on chat memory alone for task continuity.
- In Windows/PowerShell, prefer `mcp__context_mode__.ctx_execute_file`, `ctx_index`, or focused `ctx_search` over dumping whole files into context. Use `ctx_batch_execute` mainly for concise command batches and indexed searches.
- Do not repeat long results already captured in `docs/STATE.md`, kanban cards, or docs; reference the file and continue.
- Context-mode is not mandatory inside subagents. Instead, prompts to subagents must include or point to the minimal rules and active-card context they need.

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
