---
id: TASK-009
title: Grill-with-docs and catalogoantigo practice alignment
status: 05_done
kind: docs-only
---

# TASK-009 - Grill-with-docs and catalogoantigo practice alignment

## Objective

Adapt useful `catalogoantigo` workflow practices and the `grill-with-docs` skill to this repository.

## Source Practices Reused

- Use `grill-with-docs` to challenge fuzzy strategy/domain language and update glossary/docs as decisions settle.
- Keep tool-specific entrypoints thin and point them to canonical repo docs.
- Keep domain glossary separate from workflow/orchestration docs.
- At task close, check whether a reusable rule, test, helper, agent instruction, or skill trigger should be captured before moving on.
- Document model-selection policy so cheaper agents are used only where they reduce cost without raising rework risk.

## Completed Scope

- Added `CONTEXT.md` with trading/domain glossary.
- Added `docs/model-selection.md`.
- Updated `AGENTS.md`, `SKILLS.md`, `docs/project-continuity.md`, and `docs/STATE.md`.
- Added thin wrappers `CLAUDE.md` and `.github/copilot-instructions.md`.

## Verification

- Source rules were inspected through context-mode and the local `grill-with-docs` skill file.
- Docs-only verification: `git diff --check`.
