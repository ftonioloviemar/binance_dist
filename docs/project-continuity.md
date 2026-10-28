# Project Continuity

This repository should continue cleanly across chats, IDEs, and agents.

Canonical sources:

- `AGENTS.md`
- `README.md`
- `SKILLS.md`
- `CONTEXT.md`
- `docs/STATE.md`
- `docs/lessons-learned.md`
- `docs/project-continuity.md`
- the active card under `workflow/kanban/`
- docs explicitly referenced by the active card

## Workflow Standard

Use this loop for each task or coherent milestone:

1. Before starting a new task in the same session, run a focused `mcp context-mode` lookup for relevant indexed history. Then reload `AGENTS.md`, this file, `SKILLS.md`, `docs/STATE.md`, `workflow/kanban/README.md`, the active card, and at most 1-2 canonical docs cited by the card.
2. Classify the card: TDD implementation, docs-only, investigation, strategy decision, or trading-sensitive.
3. For TDD implementation, have the required test-author specialist define the test contract and write tests before production code. The contract must state expected behavior, files/tests, command, RED failure, acceptance criteria, edge cases, and forbidden shortcuts. Follow the TDD test roles below.
4. Use specialist subagents when they reduce risk, context load, or repeated reasoning. Follow `docs/subagent-specialist-matrix.md`; do not dispatch subagents for blind parallelism.
5. Implement one small slice at a time. Do not combine unrelated fixes.
6. Verify with the command named in the card, normally `uv run pytest`.
7. Update durable docs or the kanban card with evidence and follow-up tasks.
8. Move completed or cancelled cards to the correct kanban directory.
9. Commit each completed card before starting the next one, unless the user explicitly asks to hold commits.
10. If a session already accumulated multiple completed cards before this rule was applied, create a clearly described catch-up commit, then return to one commit per card.
11. At closeout, review whether the task produced a reusable rule, test, helper, agent instruction, skill trigger, glossary term, or follow-up card.

## User-Requested Plan -> Goal -> Review

When the user requests a plan, apply this policy by default, including for review findings that require replanning. A later explicit user instruction and higher-priority platform instructions take precedence.

1. **Plan:** use `gpt-6.1-terra` with `medium` reasoning. Read the relevant project docs and apply a thorough `grill-with-docs`/grilling interview: ask the user all material unresolved questions, including choices, constraints, acceptance criteria, risk and safety gates; do not repeat answers already supplied or invent approval. Capture decisions and open questions in the plan; write plan or kanban files only when the user or platform permits file changes. If the grill skill is unavailable, conduct the equivalent interview and disclose the fallback.
2. **Execution Goal:** once the user has authorized implementation, required decisions are resolved, and Goal creation is explicitly requested as required by the platform, start or continue a Goal for the approved scope using `gpt-6-luna` with `medium` reasoning. Apply the user's standing request for a Goal when it satisfies that explicit-request requirement; if it is unclear whether it does, ask instead of inferring a Goal from implementation approval alone. Execute small independently verifiable cards, TDD where applicable, and commit each completed card. A request for a plan alone does not authorize file edits, code changes or live operations; present the plan and wait for execution authorization when required. Explicit approval for the plan and its execution may be given together.
3. **Independent review:** before considering execution complete, use `superpowers:requesting-code-review` and dispatch a separate clean-context review subagent using `gpt-6.1-terra` with `medium` reasoning. Provide the reviewer with the skill's reviewer template and the actual requirements and change; adapt it to documentation or other non-code artifacts as needed. If the skill or the required subagent is unavailable, report the limitation and stop this stage rather than silently substituting or claiming the review ran. Review safety, tests and acceptance criteria, and report actionable findings with evidence. The coordinator independently verifies findings and rejects false positives with reasons.
4. **Bounded review loop:** count the initial independent review as round 1. If valid findings remain, plan corrections, obtain any required decisions/approvals, execute and test them, then dispatch a fresh independent review. Run no more than three review rounds total. If the third review still has valid unresolved findings, stop, record and report them and the verification gap; do not claim a clean review or Goal completion. An explicit later user instruction may authorize a new, separately bounded effort.
5. **Routing and availability:** `medium` is the reasoning effort, not a claim about price or capability. A Goal is not itself a model switch; never claim the primary session model or reasoning was changed unless the host confirms it. If the required model, effort, Goal, or independent subagent cannot be selected or verified, state the limitation and ask the user to select the needed model or authorize an alternative before proceeding with that stage. Never silently substitute a model, mark an unreviewed Goal complete, or use a subagent's model as proof of the coordinator's model.

These defaults do not override the trading safety rules below, strategy-selection approval, user-requested pauses, or platform limits. Parallelism is optional and must not compromise quality or mix worktrees. When the task is explicitly plan-only, finish with a plan and the execution handoff rather than implementing it.

## TDD Test Roles

- For every TDD task, a clean-context test-specialist subagent using `gpt-6.1-terra` with `medium` reasoning is responsible for writing the tests and defining their contract before production code. Use `superpowers:test-driven-development`. Give the specialist the relevant card, requirements and minimal code context; assign a test-only write scope and isolate concurrent work so existing changes are preserved. The coordinator integrates and validates the result.
- `gpt-6-luna` with `medium` reasoning executes the tests, including the initial RED run, the GREEN run and applicable regressions. The Luna implementation coordinator may run them when its model/effort is confirmed; otherwise dispatch a suitably scoped Luna test-runner subagent if available. Use `superpowers:test-driven-development` for the RED/GREEN cycle and `superpowers:verification-before-completion` for final evidence; use a more specialized test skill only when it exists and fits the task. Do not invent a universal test-runner skill.
- The RED run must fail for the intended reason before production code is changed; the GREEN and regression results must include the actual command and outcome. The independent reviewer may inspect test code and evidence, but any test execution in this workflow belongs to the Luna/medium runner. Never use live trading, redemption, subscription, or real credentials merely to run tests.
- If the required model, medium effort, author subagent, runner, or relevant skill is unavailable or cannot be verified, disclose the blocker and ask the user to select the required setup or authorize an alternative. Never silently downshift or claim a test ran under a model that was not confirmed.

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

Use the mandatory Plan -> Goal review and TDD skills described above; use other skills when they reduce ambiguity, risk, or context cost:

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
