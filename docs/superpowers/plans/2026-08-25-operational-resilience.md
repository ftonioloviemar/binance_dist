# Operational Resilience Implementation Plan

> **For agentic workers:** Execute inline with review checkpoints; no live trading or Earn mutations.

**Goal:** Improve OpenRouter model reliability, make CoinGecko failures non-disruptive, and suppress per-symbol trade deltas that cannot satisfy Binance executable notional floors.

**Architecture:** Keep the existing deterministic portfolio guards. Strengthen the event-driven OpenRouter registry so failed or unvalidated models cannot become primary; add bounded stale-cache fallback for macro data; apply the existing executable-floor calculation before a trade is treated as actionable.

**Tech Stack:** Python 3.11, requests, pytest, uv, SQLite audit logs.

**Spec:** Approved recommendations from the 2026-08-25 operational review.

## Global Constraints

- Validation is unit tests, dry-run, and audit replay only.
- No live trades, Simple Earn redeem, or subscribe.
- Preserve API secrets and historical logs.
- Commit each completed kanban card independently.

### Task 1: Harden OpenRouter curation

**Files:**
- Modify: `openrouter_model_curator.py`
- Modify: `portfolio.py` only if failure classification needs a narrow integration change
- Test: `tests/test_openrouter_model_curator.py`
- Card: `workflow/kanban/02_ready/TASK-020-openrouter-curation-hardening.md`

- [x] Write failing tests for excluding non-free/unsafe candidates from the active list and retaining only models that pass structured JSON validation in the tested promotion window.
- [x] Run focused tests and confirm the expected RED failures.
- [x] Implement the smallest filtering/validation change without changing fallback order semantics.
- [x] Run focused tests and then `uv run pytest`.
- [x] Record evidence, move the card to `05_done`, and commit.

### Task 2: Add CoinGecko stale-cache fallback

**Files:**
- Modify: `macro_context.py`
- Test: `tests/test_macro_context.py`
- Card: `workflow/kanban/02_ready/TASK-021-macro-context-cache-fallback.md`

- [x] Write failing tests for reusing a recent valid CoinGecko snapshot after timeout/429 and reporting stale age without hiding the error.
- [x] Run focused tests and confirm the expected RED failures.
- [x] Implement a bounded persistent cache with explicit stale metadata; preserve Binance and Fear & Greed behavior.
- [x] Run focused tests and then `uv run pytest`.
- [x] Record evidence, move the card to `05_done`, and commit.

### Task 3: Filter below-floor per-symbol deltas

**Files:**
- Modify: `portfolio.py`
- Test: `tests/test_portfolio.py`
- Card: `workflow/kanban/02_ready/TASK-022-executable-delta-filter.md`

- [x] Write failing tests proving deltas below the executable floor are classified as non-actionable and not returned as trade instructions, while near-floor uplift remains allowed.
- [x] Run focused tests and confirm the expected RED failures.
- [x] Implement the narrow per-symbol floor check using existing exchange filters and tolerance.
- [x] Run focused tests and then `uv run pytest`.
- [x] Record evidence, move the card to `05_done`, and commit.

### Task 4: Integrated dry-run and closeout

- [x] Run `uv run pytest` fresh.
- [x] Run one `--dry-run true` rebalance and inspect its audit record.
- [x] Confirm no live mutation occurred, update `docs/STATE.md`, and review `git status`.
- [x] Push only if explicitly requested later.
