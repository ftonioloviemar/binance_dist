# Model Selection

Use enough intelligence to avoid rework, then reduce cost where the task is bounded.

## Plan -> Goal -> Review Defaults

- Every user-requested plan: `gpt-6.1-terra` with `medium` reasoning, including a thorough grill of unresolved decisions and safety constraints.
- Approved implementation Goal: `gpt-6-luna` with `medium` reasoning.
- Independent end-of-Goal reviewer: separate `gpt-6.1-terra` subagent with `medium` reasoning, dispatched using `superpowers:requesting-code-review` and its reviewer template; follow the three-round maximum in `docs/project-continuity.md`.
- The host controls the primary session model and reasoning; creating a Goal does not change either. Verify the selected model/effort for each stage. If a required selection or subagent is unavailable or cannot be verified, explain the blocker and request user selection or authorization of an alternative; never claim a silent switch or substitute.
- A plan-only request remains plan-only, without file edits unless explicitly permitted. Execution requires authorization, and Goal creation additionally requires an explicit user request as defined by platform rules. User-selected strategy and live-trading approval gates remain mandatory.

## TDD Test Defaults

- Test author: a clean-context test-specialist subagent using `gpt-6.1-terra` with `medium` reasoning writes tests and the contract before production code, following `superpowers:test-driven-development`.
- Test execution: `gpt-6-luna` with `medium` reasoning runs RED, GREEN and regression tests, either as the confirmed implementation coordinator or a scoped test-runner subagent. Use TDD and `superpowers:verification-before-completion` for evidence; use a specialized test skill only where applicable and available.
- These assignments apply to TDD tasks regardless of the general cheapest-adequate specialist defaults. Availability, isolation, safety and no-silent-substitution rules are in `docs/project-continuity.md`.

## Other Defaults

- Outside the Plan -> Goal -> Review default, select a coordinator strong enough for ambiguous strategy, trading-sensitive changes, architecture, or multi-file implementation; escalate when evidence shows the selected model is insufficient.
- Bounded review or contract tasks: use a cheaper clean-context subagent only when the task has a clear card, small scope, and objective acceptance criteria.
- Docs-only edits with clear source material: use cheaper reasoning where available, but still verify against canonical repo docs.
- Trading/live-funds safety, API permissions, or unclear exchange behavior: do not downshift just to save tokens.

## Subagent Policy

- Use subagents to reduce context load or provide independent review, not for parallelism alone.
- Prompts must include minimal context: `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, active card, and cited docs.
- If a cheap subagent result would require substantial rework or verification by the coordinator, use a stronger model instead.
- Use `docs/subagent-specialist-matrix.md` to choose reusable specialist type, model class, reasoning level, and recalibration rule.
- Prefer the cheapest model class that can satisfy the task without increasing expected rework. Promote after repeated misses; demote after repeated overkill.

## Context Policy

- Prefer context-mode for history and large files.
- Prefer native Codex compaction plus `docs/STATE.md` for long-running continuity.
- Do not re-read broad docs when a focused indexed query or short state file answers the question.
