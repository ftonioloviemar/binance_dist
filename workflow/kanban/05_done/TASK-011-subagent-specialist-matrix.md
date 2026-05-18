---
id: TASK-011
title: Subagent specialist matrix and calibration policy
status: 05_done
kind: docs-only
---

# TASK-011 - Subagent specialist matrix and calibration policy

## Objective

Define when and how to use reusable specialist subagents by task type without turning subagent usage into blind parallelism.

## Scope

- Evaluate whether the strategy gives real token/accuracy gain.
- Add a reusable subagent specialist matrix.
- Define base prompt contracts and model/reasoning selection rules.
- Define recalibration criteria after subagent results.
- Wire the policy into canonical workflow docs.

## Decision

Adopt the strategy as **maximum useful delegation**, not maximum possible delegation.

Use reusable specialists by broad card class, not by every fine subtype. The goal is precision with economy. Parallelism is secondary and allowed only when tasks are independent.

## Independent Review

Explorer review confirmed the policy should be by broad card class, not fine subtype. Cheap subagents are recommended only for small, stable, objectively verifiable tasks; ambiguous strategy, architecture, trading-sensitive, or multi-file behavior remains coordinator/strong-specialist work.

## Completed Scope

- Added `docs/subagent-specialist-matrix.md`.
- Updated `AGENTS.md`.
- Updated `docs/project-continuity.md`.
- Updated `docs/model-selection.md`.
- Updated `SKILLS.md`.

## Verification

- Independent explorer review completed.
- Docs-only verification: `git diff --check`.
