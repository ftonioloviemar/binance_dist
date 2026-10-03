# TASK-036: Document Market Insights Contract

## Objective

Record the approved boundaries, data assumptions, shadow scenarios, and evaluation limits for the market-insights improvement wave.

## Context And Scope

Follow `AGENTS.md`, `docs/project-continuity.md`, `docs/STATE.md`, `SKILLS.md`, `workflow/kanban/README.md`, `docs/market-insights.md`, and `docs/strategy-scenario-b.md`.

Document the approved live adaptive source-quality behavior separately from shadow-only indicators. Clarify that simulation outputs are conditional, estimated, and not realized profit. Do not modify production behavior or model routing in this card.

## Verification

- Review source references and local contracts in `macro_context.py`, `app.py`, `adaptive_strategy.py`, `strategy_replay.py`, and `docs/strategy-scenario-b.md`.
- Confirm all thresholds, expiration rules, cost assumptions, exclusions, and the human activation gate are documented consistently.
- Run `git diff --check`.

## Acceptance

- Canonical strategy documents capture approved decisions and known simulation limitations without presenting the existing proxy replay as returns.
- `docs/STATE.md` points to this goal and active card.
- No production code or live defaults change.

## Risk

Do not represent estimated fee/slippage or a simulated counterfactual as a realized outcome.

## Completion Evidence

- `git diff --check` passed.
- Independent documentation review identified four ambiguities; the contract now distinguishes target behavior from current behavior, defines provider versus collection timestamps, and specifies sequential shadow-session seed/hold/cost semantics.
- Updated `docs/strategy-scenario-b.md` so the existing proxy replay is not confused with portfolio-return evidence.
- Documentation-only card; no test suite or exchange calls were needed.
