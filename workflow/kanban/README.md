# Kanban

This directory is the source of truth for repository work items.

## States

- `00_pending_approval`: proposed card or strategy decision waiting for user approval.
- `01_backlog`: known work not yet ready for execution.
- `02_ready`: approved and specified work ready to execute.
- `03_doing`: active work.
- `04_review`: implemented work awaiting verification/review.
- `05_done`: completed work with evidence.
- `06_cancelado`: cancelled work.
- `07_needs_human`: blocked by human decision, approval, or missing definition.
- `08_human_reviewed`: human decision recorded and ready to resume.

## Card Rules

- A card should state objective, context, scope, TDD/verification, acceptance, and risks.
- TDD implementation cards must name the expected RED failure and verification command.
- Before starting a new card in the same session, use `mcp context-mode` for focused context recovery, then reload `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, this README, the active card, and at most 1-2 directly cited docs.
- Use native Codex compaction when useful, but persist task-critical state in `docs/STATE.md` or the card before relying on compaction.
- Use `grill-with-docs` when a card depends on fuzzy strategy/domain/workflow terms. Capture stable trading vocabulary in `CONTEXT.md` and workflow terms in `docs/project-continuity.md`.
- Move card files between directories when state changes.
- Commit each completed card before starting the next card unless the user explicitly asks to hold commits.
- Do not execute cards in `00_pending_approval` without user approval.
- Do not close cards without verification evidence.
- Live trading, live redemption, and live subscription require explicit user intent for that execution.

## Human Decision Block

Cards moved to `07_needs_human` must include:

- Decision needed
- Context
- Options
- Recommendation
- Human decision
- Resume criteria
- Dependency impact
