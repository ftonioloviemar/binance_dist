# TASK-047: Preserve commission conversion provenance

## Objective

Make execution-cost reporting explain which commission assets were charged and
why a quote-currency conversion is unavailable, without estimating historical
prices or mislabeling unknown fees as zero.

## TDD contract

- Preserve each fill commission as exact decimal amount plus commission asset.
- Persist a deterministic per-asset breakdown and per-asset conversion outcome
  with the order cost record, including whether quote currency was native,
  which supplied reference rate was used, or why a rate was unavailable.
- If a fill has a missing, invalid, non-finite, or negative commission amount,
  or lacks its commission asset, mark the order conversion `incomplete`, keep
  quote/bps null, and preserve sanitized issue codes in storage and audit logs.
- Keep aggregate quote commission and bps unavailable unless every commission
  is converted by a known reference price; do not expose partial sums as totals.
- Migrate existing SQLite databases additively. Preserve legacy known
  `commission_quote` values/status even when per-asset detail is absent; legacy
  `unknown`/`partial` rows remain unknown and must not be backfilled with
  inferred prices.
- Report both converted and unknown-order counts, and aggregate unknown
  commissions by asset where that detail exists; expose known converted
  subtotal separately from the complete commission total.
- Do not expose API credentials, signed requests, or raw exchange payloads.
- Do not change sizing, strategy, trading, or call live exchange APIs.

## Verification

- RED/GREEN focused: `uv run pytest -q tests/test_execution_costs.py tests/test_execution_cost_store.py tests/test_performance.py tests/test_performance_report.py`
- Regression: `uv run pytest -q`
- Read-only smoke: `uv run python app.py performance --days 30 --json`
- Exercise schema migration with a database created using the pre-change schema.

## Follow-up / known boundary

This card improves fee decomposition going forward. Historical unknown fees may
only be reconciled from retained audit evidence and an exact, timestamped
reference; otherwise they remain unknown. Flow-adjusted portfolio return,
slippage decomposition, and separately attributed Simple Earn yield require a
separate accounting contract and must not be guessed in this card.

## Completion evidence

- RED/GREEN focused verification: `uv run pytest -q tests/test_execution.py tests/test_execution_costs.py tests/test_execution_cost_store.py tests/test_performance.py tests/test_performance_report.py` — 32 passed.
- Full regression: `uv run pytest -q` — 247 passed.
- Read-only report smoke: `uv run python app.py performance --days 30 --json` succeeded; SHA-256 of `state/performance.db` was unchanged before and after.
- SQLite v2-to-v3 additive migration, legacy known/unknown compatibility, and read-only legacy loading are covered by `tests/test_execution_cost_store.py`.
- Error-path tests prove raw HTTP response bodies and exception text are absent from audit/pending logs; invalid commission values are excluded from fee summaries while sanitized issue codes remain.
- Independent final audit: no P1/P2 findings.
- No live exchange, trading, or Earn operations were performed.
