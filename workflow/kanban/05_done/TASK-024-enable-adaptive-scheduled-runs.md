# TASK-024: Enable adaptive strategy in scheduled runs

## Objective

Run the user-approved adaptive allocation layer during scheduled production
rebalances so each run applies and audits current market-regime parameters.

## Context and decision

- Recent scheduled runs use profile `moderate` but do not record an
  `adaptive_strategy` step because `run_prod.bat` omits `--adaptive`.
- The user explicitly approved enabling adaptive strategy on 2026-09-18.
- This can change live target allocations and is therefore strategy-sensitive.

## Scope

- Add `--adaptive` to the production launcher used by the Windows task.
- Keep caller arguments last so a later `--dry-run true` can safely override
  the launcher's default `--dry-run=false` for validation.
- Document the activation and test the exact launcher in dry-run mode.
- Do not execute a live run as validation.

## TDD and verification

- RED: `uv run pytest tests/test_run_prod_launcher.py -q` fails because the
  launcher does not include `--adaptive`.
- GREEN: focused test passes; execute `run_prod.bat --dry-run true` and verify
  the audit has `adaptive_strategy` and `dry_run=true`; run `uv run pytest -q`.
- Acceptance: scheduled invocation of the existing task action records
  `adaptive_strategy`; dry-run override remains functional; no real orders.

## Risks and rollback

- Adaptive targets can change future live allocation. User approved this
  specific change; other thresholds and task times remain unchanged.
- Rollback: restore the pre-change `run_prod.bat` backup or revert this card's
  commit.
- Never validate with live trading, Earn redemption, or subscription.

## Evidence and closure

- Backup of original launcher: `%TEMP%\run_prod-pre-adaptive-20260918-161835.bat`.
- RED: `uv run pytest tests/test_run_prod_launcher.py -q` -> 1 failed because
  the production launcher lacked `--adaptive`.
- GREEN: `uv run pytest tests/test_run_prod_launcher.py -q` -> 1 passed.
- Safe launcher run: `run_prod.bat --dry-run true` -> run
  `4462f11c56904297bb6ce00f950c49f0`, completed `DRY`; audit recorded
  `adaptive_strategy` with Neutral sentiment, moderate profile, 1.00% drift,
  and 0.30% max slippage. One simulated SOLUSDT BUY; zero live orders and no
  exceptions. `final_balances` was skipped as expected in dry-run.
- Full verification: `uv run pytest -q` -> 54 passed.
- Scheduler read-back: task `binance_dist` is `Ready` and still points to
  `C:\python\binance_dist\run_prod.bat`.
