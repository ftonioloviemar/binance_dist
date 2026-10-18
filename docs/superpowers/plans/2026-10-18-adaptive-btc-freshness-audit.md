# Adaptive BTC Freshness Audit Implementation Plan

> **For agentic workers:** Implement this plan task-by-task, preserving the current freshness gate and fallback behavior.

**Goal:** Make adaptive BTC-source freshness failures diagnosable from local audit records.

**Architecture:** Extend the immutable source assessment with sanitized UTC timing diagnostics captured from the exact decision timestamp. Append these diagnostics to adaptive audit details for applied, source-fallback, and calculation-failure outcomes; do not change eligibility or strategy calculations.

**Tech Stack:** Python, pytest, existing `AuditLogger` and `MacroSnapshot` contracts.

**Spec:** `workflow/kanban/05_done/TASK-051-audit-adaptive-btc-source-age.md`

## Global Constraints

- Keep the existing required-source freshness gate at 0..15 minutes inclusive.
- Preserve base profile/targets/drift/slippage when a required source is unavailable.
- Log timestamps and age only; never log market payloads, balances, holdings, or credentials.
- No live exchange, Simple Earn, or model-provider calls during validation.

## Review Focus

- Stale and future BTC collection timestamps must report signed computed age without becoming eligible.
- Missing or malformed timestamps must be represented as unavailable, not serialized from untrusted raw text.
- Applied and failed adaptive outcomes should carry the same timing evidence as source fallback.
- Time formatting must be explicit UTC and stable for tests.
- Existing adaptive decisions and run status must remain unchanged.

---

### Task 1: Add source timing diagnostics to adaptive audits

**Files:**
- Modify: `app.py`
- Test: `tests/test_app_adaptive.py`

**Steps:**
- [x] Add failing unit/integration assertions for collection timestamp, decision timestamp, and computed BTC age on a stale-source fallback.
- [x] Run the focused tests and confirm the failure is due to absent timing diagnostics.
- [x] Add the exact assessment-time diagnostics and append them to applied, warning, and failed adaptive audit details.
- [x] Verify stale/future inputs remain unavailable and the base configuration is retained.
- [x] Run adaptive focused tests, full `uv run pytest`, compile/check, and review the diff.
- [x] Move TASK-051 to `05_done` and commit the completed card.

**Acceptance:** Audit detail contains UTC `btc_collected_at`, UTC `decision_time`, and signed `btc_age_seconds` for assessed adaptive outcomes; unavailable data is explicit; no target or threshold changes.
