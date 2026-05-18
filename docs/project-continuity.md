# Project Continuity

This repository should continue cleanly across chats, IDEs, and agents.

Canonical sources:

- `AGENTS.md`
- `README.md`
- `SKILLS.md`
- `CONTEXT.md`
- `docs/STATE.md`
- `docs/project-continuity.md`
- the active card under `workflow/kanban/`
- docs explicitly referenced by the active card

## Workflow Standard

Use this loop for each task or coherent milestone:

1. Before starting a new task in the same session, run a focused `mcp context-mode` lookup for relevant indexed history. Then reload `AGENTS.md`, this file, `SKILLS.md`, `docs/STATE.md`, `workflow/kanban/README.md`, the active card, and at most 1-2 canonical docs cited by the card.
2. Classify the card: TDD implementation, docs-only, investigation, strategy decision, or trading-sensitive.
3. For TDD implementation, define the test contract before production code. The contract must state expected behavior, files/tests, command, RED failure, acceptance criteria, edge cases, and forbidden shortcuts.
4. Use specialist subagents when they reduce risk, context load, or repeated reasoning. Follow `docs/subagent-specialist-matrix.md`; do not dispatch subagents for blind parallelism.
5. Implement one small slice at a time. Do not combine unrelated fixes.
6. Verify with the command named in the card, normally `uv run pytest`.
7. Update durable docs or the kanban card with evidence and follow-up tasks.
8. Move completed or cancelled cards to the correct kanban directory.
9. Commit each completed card before starting the next one, unless the user explicitly asks to hold commits.
10. If a session already accumulated multiple completed cards before this rule was applied, create a clearly described catch-up commit, then return to one commit per card.
11. At closeout, review whether the task produced a reusable rule, test, helper, agent instruction, skill trigger, glossary term, or follow-up card.

## Context And Compaction Policy

- Use context-mode to query indexed history or large files without loading everything into the live context.
- Prefer `mcp__context_mode__.ctx_execute_file`, `ctx_index`, and focused `ctx_search` on Windows. Avoid broad full-file reads unless the file is small and directly needed.
- Native Codex compaction is allowed and expected when the context grows. Before compaction or chat handoff, write only durable, task-relevant state to `docs/STATE.md` or the active card.
- `docs/STATE.md` must stay short: current objective, active/next card, latest verification, known blockers, and the next safe command. Do not turn it into a full session log.
- A final context-mode checkpoint is optional. Use it only when there is concrete continuity risk before ending the session, switching chats, or starting a broad new task.

## Kanban Policy

- `workflow/kanban/00_pending_approval/`: proposals or decisions needing user approval.
- `workflow/kanban/01_backlog/`: known work not yet ready.
- `workflow/kanban/02_ready/`: approved, specified, executable work.
- `workflow/kanban/03_doing/`: active work.
- `workflow/kanban/04_review/`: implemented, awaiting review/verification.
- `workflow/kanban/05_done/`: completed with evidence.
- `workflow/kanban/06_cancelado/`: cancelled scope.
- `workflow/kanban/07_needs_human/`: blocked by a required human decision.
- `workflow/kanban/08_human_reviewed/`: human decision recorded, ready to resume.

Cards in `00_pending_approval` are not executable until the user approves them. Cards in `07_needs_human` must include the decision needed, options, recommendation, impact, and resume criteria.

## Skill Usage

Use skills only when they reduce ambiguity, risk, or context cost:

- `run-kanban-loop`: execute approved cards sequentially until blocked or empty.
- `superpowers:test-driven-development`: every feature, bugfix, refactor, or behavior change.
- `superpowers:systematic-debugging`: root-cause work for failures such as audit decoding, rejected orders, or strategy not activating.
- `superpowers:subagent-driven-development`: implementation plans with independent cards and review gates.
- `docs/subagent-specialist-matrix.md`: reusable specialist subagent matrix, model/reasoning classes, and recalibration loop.
- `superpowers:writing-plans`: multi-step implementation plans before code.
- `grill-with-docs`: unclear strategy, workflow, or domain terms that must become durable docs. Stable trading/domain terms go to `CONTEXT.md`; workflow/orchestration terms stay here or in `workflow/kanban/README.md`.
- `setup-matt-pocock-skills`: refresh `docs/agents/` if the tracker/domain layout changes.
- `security-best-practices` and `security-threat-model`: changes involving API keys, live trading, permissions, or account safety.
- `zoom-out`: inspect how a module fits the trading flow before changing localized behavior.

## Domain Notes

This is a Binance Spot portfolio rebalancer with optional OpenRouter target refinement and Simple Earn automation.

Keep strategy docs separate from workflow docs and domain glossary:

- Workflow/orchestration terms stay in this file and `workflow/kanban/README.md`.
- Trading strategy choices should be documented under `docs/strategy-*.md`.
- Stable domain vocabulary lives in `CONTEXT.md`.
- Tool-specific wrappers (`CLAUDE.md`, `.github/copilot-instructions.md`) stay thin and point back to canonical docs.

## Safety Defaults

- Default validation is test/log replay, not live trading.
- Live `--dry-run=false`, Simple Earn redeem, and Simple Earn subscribe require explicit user intent for that execution.
- Historical logs are evidence; do not rewrite them to hide failures.
- If a failure depends on Binance behavior, cite official Binance docs or captured API responses.
