# Project Continuity

This repository should continue cleanly across chats, IDEs, and agents.

Canonical sources:

- `AGENTS.md`
- `README.md`
- `SKILLS.md`
- `docs/project-continuity.md`
- the active card under `workflow/kanban/`
- docs explicitly referenced by the active card

## Workflow Standard

Use this loop for each task or coherent milestone:

1. Reload `AGENTS.md`, this file, `SKILLS.md`, `workflow/kanban/README.md`, and the active card.
2. Classify the card: TDD implementation, docs-only, investigation, strategy decision, or trading-sensitive.
3. For TDD implementation, define the test contract before production code. The contract must state expected behavior, files/tests, command, RED failure, acceptance criteria, edge cases, and forbidden shortcuts.
4. Use specialist subagents when they reduce risk or context load. For non-trivial behavior changes, use one specialist for the test contract and a separate one for result audit.
5. Implement one small slice at a time. Do not combine unrelated fixes.
6. Verify with the command named in the card, normally `uv run pytest`.
7. Update durable docs or the kanban card with evidence and follow-up tasks.
8. Move completed or cancelled cards to the correct kanban directory.
9. Commit each completed card before starting the next one, unless the user explicitly asks to hold commits.
10. If a session already accumulated multiple completed cards before this rule was applied, create a clearly described catch-up commit, then return to one commit per card.

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
- `superpowers:writing-plans`: multi-step implementation plans before code.
- `grill-with-docs`: unclear workflow/domain terms or strategy decisions that must become durable docs.
- `setup-matt-pocock-skills`: refresh `docs/agents/` if the tracker/domain layout changes.
- `security-best-practices` and `security-threat-model`: changes involving API keys, live trading, permissions, or account safety.

## Domain Notes

This is a Binance Spot portfolio rebalancer with optional OpenRouter target refinement and Simple Earn automation.

Keep strategy docs separate from workflow docs:

- Workflow/orchestration terms stay in this file and `workflow/kanban/README.md`.
- Trading strategy choices should be documented under `docs/strategy-*.md`.
- Create `CONTEXT.md` only when stable domain vocabulary needs a glossary.

## Safety Defaults

- Default validation is test/log replay, not live trading.
- Live `--dry-run=false`, Simple Earn redeem, and Simple Earn subscribe require explicit user intent for that execution.
- Historical logs are evidence; do not rewrite them to hide failures.
- If a failure depends on Binance behavior, cite official Binance docs or captured API responses.
