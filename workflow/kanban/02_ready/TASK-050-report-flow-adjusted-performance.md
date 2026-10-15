# TASK-050: Report net P&L and Modified Dietz return

## Objective

Use complete snapshots and one certified external-flow ledger to report
quote-currency net P&L and a timestamp-weighted Modified Dietz return.

## Dependencies

- TASK-049 must provide certified coverage and flow rows by quote asset.
- TASK-048 selected P&L plus Modified Dietz, without a separate money-weighted
  IRR.

## TDD contract

- For each existing report horizon, use the selected first `before` and last
  `after` snapshots. Require both snapshots to be complete, use the same quote
  asset, and require one certified ledger interval for that quote asset that
  covers the entire inclusive snapshot interval.
- Include external flows with `start_timestamp < flow_timestamp <=
  end_timestamp`. Treat `in` as positive and `out` as negative. Spot/Earn
  transfers are not external flows.
- Let `B` be starting total value, `E` ending total value, `CF_i` signed
  external flows, and `w_i=(end-flow_time)/(end-start)` using elapsed UTC
  seconds. Compute net P&L as `E - B - sum(CF_i)` and Modified Dietz return as
  `(E - B - sum(CF_i)) / (B + sum(CF_i*w_i))`; report the rate as a percentage
  without annualizing it.
- Report explicit fields for `net_pnl_quote`, `external_net_flow_quote`,
  `modified_dietz_return_pct`, `return_method`, and `flow_coverage_status`.
  Mark Modified Dietz as approximate. Keep P&L/return null unless coverage and
  snapshots are complete; a zero/nonpositive denominator makes the rate null
  with an explicit reason.
- Preserve existing `observed_change` as raw change in portfolio value and
  preserve existing hold benchmark. Do not label raw change as profit.
- Fees already reflected in snapshot values must not be deducted again. Keep
  commission totals separate. Do not claim slippage or separate Earn yield
  attribution without their own evidence contracts.
- Update `CONTEXT.md` with stable definitions for certified external flow,
  quote-currency net P&L, and Modified Dietz return.
- No live API calls, strategy changes, or trade/Earn operations.

## Verification

- RED/GREEN: `uv run pytest -q tests/test_performance.py tests/test_performance_report.py tests/test_external_flows.py`
- Regression: `uv run pytest -q`
- Read-only smoke: `uv run python app.py performance --days 30 --json`; verify the real SQLite hash is unchanged.

## Acceptance

- Tests cover no-flow certified ledger, inflow/outflow, mid-period and end-time
  flow weights, full and partial horizons, missing/ambiguous certification,
  quote mismatch, incomplete snapshots, empty certified ledger, and zero
  denominator.
- Incomplete or uncovered horizons do not expose P&L or return; they retain
  only the existing appropriately labeled observed-change behavior.
- Fee subtotals remain independent and are not subtracted a second time.
- Independent TDD result auditor reports no unresolved P1/P2 findings.

## Risks and forbidden shortcuts

- The CSV certification is user-supplied evidence; report its source and
  covered dates and never imply automatic completeness verification.
- Never infer that no CSV rows means no flows unless the interval was
  explicitly certified.
- Never combine overlapping/partial ledger versions for one report.
- Do not present Modified Dietz as realized strategy alpha or an investment
  recommendation.

## Completion evidence

- Pending.
