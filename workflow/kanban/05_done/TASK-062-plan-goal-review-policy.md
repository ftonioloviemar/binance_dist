# TASK-062: Plan, Goal, and Independent Review Defaults

Status: done.

## Objective

Apply the user-requested project default: `gpt-6.1-terra`/medium plans with a thorough grill, approved implementation Goals using `gpt-6-luna`/medium, and independent `gpt-6.1-terra`/medium review, bounded to three review rounds.

Each review must use `superpowers:requesting-code-review` and provide its reviewer template to the independent reviewer, as clarified by the user.

For TDD work, a `gpt-6.1-terra`/medium test-specialist subagent must author tests and their contract. `gpt-6-luna`/medium must execute RED, GREEN and regression tests; use suitable test skills when available.

## Scope and Safety

- Change project workflow/model/skill instructions only; do not change trading code, scheduler, credentials, or strategy.
- Preserve plan-only and explicit approval gates, including trading/live-operation approvals.
- Explain host limitations: creating a Goal does not select the primary model, and unavailable or unverifiable model/effort/subagent must be reported rather than silently substituted.
- Work in an isolated worktree based on `652f655`; use that commit as rollback point. Do not touch the separate Simple Earn worktree.

## Verification

- Check cross-document consistency for model IDs, `medium` effort, interview scope, explicit execution authorization, independent review and the three-round stop condition.
- Confirm the specified review-skill requirement and unavailable-skill stop condition are consistent across workflow, model selection and skill catalog.
- Confirm the TDD author/runner roles, applicable skills, isolation and unavailable-model behavior are consistent across the same canonical docs.
- Check for contradictions with the prior cheaper-specialist policy and trading safety gates.
- Review `git diff --check`, staged diff and worktree status. No production or exchange execution is needed for this docs-only card.

## Review Round 1

- An independent `gpt-6.1-terra`/medium review identified two ambiguity risks: a plan-only request could be read as permitting file writes, and implementation approval could be mistaken for an explicit Goal request. The policy now states both gates separately and honors the user's standing Goal request only when it meets platform requirements.
- An independent second review found no further actionable issues. After that review, the user specified `superpowers:requesting-code-review`; the policy requires that skill and its reviewer template, not a different fallback.
- The third review found one minor consistency issue: general skill/subagent guidance did not explicitly exempt the mandatory review policy. The exception was added. During that review the user added the TDD author and runner requirements; the existing `superpowers:test-driven-development` and `superpowers:verification-before-completion` skills fit those roles, with specialized test skills only when applicable.
- The third reviewer confirmed the exception fix and the added TDD roles without further material findings. The reviewer inspected documentation only; actual future model selection and dispatch remain subject to host availability and verification.

## Closure Evidence

- Canonical workflow, model selection, specialist matrix, skills catalog and `AGENTS.md` now agree on the requested routing, approval boundaries, independent review and three-round maximum.
- Independent reviews used `gpt-6.1-terra`/medium. The last review used `superpowers:requesting-code-review` and its reviewer template.
- The available TDD and verification skills were inspected; no generic test-execution-only skill is assumed. No application tests or exchange operations were required for this docs-only change.
