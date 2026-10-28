# Subagent Specialist Matrix

This policy defines when reusable specialist subagents are worth using in `binance_dist`.

## Judgment

The strategy is useful when it reduces repeated reasoning, isolates review context, or lets a specialist validate a narrow contract cheaper than the coordinator can. It is harmful when it becomes a blanket rule to dispatch work that is too small, too ambiguous, trading-sensitive without enough context, or likely to require rework.

Use the rule as **maximum useful delegation**, not maximum possible delegation. Prefer standard specialists by broad card class, not overfitted subtypes for every small kanban variation.

## Core Rule

Except for the mandatory TDD test-author subagent and independent review of an authorized Plan -> Goal effort in `docs/project-continuity.md`, dispatch a subagent only when all are true:

- The task has a clear card, question, or review target.
- The expected output can be judged objectively.
- The prompt can fit in a small context package.
- The subagent has a disjoint responsibility or independent review angle.
- The coordinator can cheaply verify the output.

For other subagent uses, do not dispatch a subagent when any are true:

- The work is a tiny docs edit or one-line mechanical change.
- The main blocker is a human decision.
- The task is too ambiguous to specify without the coordinator resolving it first.
- The subagent would need broad repo history that is cheaper to inspect locally with context-mode.
- The result affects live trading/funds and cannot be independently verified before use.

## Model Classes

For TDD test authoring, TDD test execution and Plan -> Goal independent review, use the explicit model/effort assignments in `docs/model-selection.md`. For other roles, use classes first and map them to actual available models in the current environment.

- **Cheap bounded**: cheapest available model that follows instructions reliably. Use for read-only summaries, checklist review, simple card drafting, and focused diff review.
- **Standard specialist**: low-cost model with enough reasoning for test contracts, bug triage, and audit review. Current default suggestion: `gpt-5.4-mini` with `medium` reasoning for bounded tasks.
- **Strong specialist**: stronger model/reasoning for trading-sensitive design, architecture, unclear bugs, or cases where a cheap miss would cost more than it saves.
- **Coordinator**: strongest/current session model for final decisions, integration, live-trading safety, and ambiguous strategy trade-offs.

If a cheap subagent creates rework twice for the same task type, promote that specialist one class for future runs.

## Specialist Matrix

| Task type | Specialist | Default model class | Reasoning | Use when | Avoid when |
|---|---|---:|---:|---|---|
| TDD test author | Test-specialist subagent | `gpt-6.1-terra` | medium | Every TDD task: define contract and write tests before production code | Never silently skip; report if unavailable |
| TDD test execution | Confirmed coordinator or test-runner subagent | `gpt-6-luna` | medium | Run RED, GREEN and regressions with appropriate test/verification skills | Never silently substitute; report if unavailable |
| TDD completion | Result auditor | Standard specialist | medium | Diff/tests need independent check before `05_done` | Docs-only card |
| Plan -> Goal completion | Independent review subagent | `gpt-6.1-terra` | medium | Every authorized Plan -> Goal execution; up to three review rounds | Never silently skip; report if unavailable |
| Bug/regression | Diagnose investigator | Standard specialist, promote if hard | medium/high | Need reproduce/minimize/hypothesize loop | Existing failing test already localizes cause |
| Strategy/trading decision | Grill/domain challenger | Strong specialist or coordinator-only | high | Terms, risks, or allocation behavior are fuzzy | Decision is already selected and documented |
| Architecture/refactor | Architecture reviewer | Strong specialist | high | User asks to improve architecture/testability | Small localized bugfix |
| Security/API/funds | Security reviewer | Strong specialist | high | API key, permissions, live trading, Earn automation | Pure docs/readme update |
| Docs/workflow policy | Docs consistency reviewer | Cheap bounded | low/medium | Source docs are clear and consistency is objective | Single typo or wording-only change |
| Smoke/audit result | Evidence reviewer | Cheap bounded | low/medium | Need independent pass/fail scan of command output | Output is short and unambiguous |
| Kanban grooming | Card shaper | Cheap bounded | low | Split approved work into executable cards | Requires user decision first |

## Base Prompt Package

Every subagent prompt should include only:

- Role and exact output expected.
- Active card path and objective.
- Relevant canonical docs: `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, `SKILLS.md`, plus 1-2 directly cited docs.
- Constraints: no live trade, no broad refactor, no reverting unrelated changes.
- Verification target or evidence to inspect.

Do not send full logs, full repo dumps, or all prior chat. Use context-mode or a short summary first.

## Recalibration Loop

After each subagent result, the coordinator records a lightweight judgment in the card when it matters:

- **Good fit**: result was correct, concise, and reduced coordinator work.
- **Too weak**: missed requirement, hallucinated, weakened tests, or required rework.
- **Too expensive**: output was correct but the prompt/review cost exceeded local execution.
- **Wrong specialist**: task type did not match assigned role.

Recalibrate:

- Promote model class/reasoning after repeated `too weak`.
- Demote model class/reasoning after repeated `too expensive`.
- Retire or narrow a specialist if it often creates rework.
- Add a reusable prompt template only after the same specialist pattern succeeds at least twice.
- For Plan -> Goal, follow the explicit maximum of three independent review rounds, including the first, in `docs/project-continuity.md`. Stop and report remaining valid findings after round three. For other work, if one or two correction cycles do not converge, reduce scope or move the task back to the coordinator/strong specialist.

## Parallelism Rule

Parallelism is allowed only for independent tasks with disjoint write sets or read-only review targets. Do not parallelize two agents into the same files or the same unresolved design decision.

Precision and economy are the goal; parallelism is a secondary benefit.
