---
id: TASK-010
title: Install catalogoantigo-adjacent skills
status: 05_done
kind: tooling
---

# TASK-010 - Install catalogoantigo-adjacent skills

## Objective

Install the missing skills referenced by the `catalogoantigo` workflow pattern into this Codex environment.

## Installed Skills

- `caveman`
- `handoff`
- `diagnose`
- `improve-codebase-architecture`

## Source

- Repository: `mattpocock/skills`
- Paths:
  - `skills/productivity/caveman`
  - `skills/productivity/handoff`
  - `skills/engineering/diagnose`
  - `skills/engineering/improve-codebase-architecture`

## Evidence

- Installed to `C:\Users\ftoniolo\.codex\skills`.
- Verified each installed directory contains `SKILL.md`.
- Updated local skill catalog to mark them as available after Codex restart.

## Note

Codex must be restarted for newly installed skills to appear in the session's active skill list.
