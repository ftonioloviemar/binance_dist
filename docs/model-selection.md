# Model Selection

Use enough intelligence to avoid rework, then reduce cost where the task is bounded.

## Defaults

- Coordinator for ambiguous strategy, trading-sensitive changes, architecture, or multi-file implementation: keep the strongest available model/reasoning.
- Bounded review or contract tasks: use a cheaper clean-context subagent only when the task has a clear card, small scope, and objective acceptance criteria.
- Docs-only edits with clear source material: use cheaper reasoning where available, but still verify against canonical repo docs.
- Trading/live-funds safety, API permissions, or unclear exchange behavior: do not downshift just to save tokens.

## Subagent Policy

- Use subagents to reduce context load or provide independent review, not for parallelism alone.
- Prompts must include minimal context: `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, active card, and cited docs.
- If a cheap subagent result would require substantial rework or verification by the coordinator, use a stronger model instead.

## Context Policy

- Prefer context-mode for history and large files.
- Prefer native Codex compaction plus `docs/STATE.md` for long-running continuity.
- Do not re-read broad docs when a focused indexed query or short state file answers the question.
