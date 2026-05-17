# Scenario B - Threshold And Cost Guard Replay

Scenario B is selected as the next profit-improvement experiment.

This is a research/backtest layer only. It must not change live trading, scheduled runs, targets, drift defaults, or Simple Earn behavior until a later card explicitly approves production use.

## Current Harness

The first replay harness lives in `strategy_replay.py`.

Inputs:

- `ReplayCase.run_id`: source run identifier.
- `ReplayCase.max_abs_drift`: largest absolute target/current drift observed for the run.
- `ReplayCase.planned_trade_notionals`: candidate order notionals for the run.
- `ReplayCase.realized_volatility`: volatility proxy for the run window.
- `ScenarioBPolicy.base_drift_threshold`: normal drift threshold.
- `ScenarioBPolicy.high_volatility_threshold`: volatility level that raises the effective threshold.
- `ScenarioBPolicy.high_volatility_multiplier`: multiplier applied to the drift threshold in high-volatility regimes.
- `ScenarioBPolicy.min_trade_notional`: minimum cost-aware order size.
- `ScenarioBPolicy.fee_rate` and `ScenarioBPolicy.slippage_rate`: cost proxy rates.

Outputs:

- `order_count`: orders that would pass the Scenario B guard.
- `skipped_small_trade_count`: candidate orders skipped by cost/notional guard.
- `turnover_proxy`: sum of tradable candidate notionals.
- `estimated_cost_proxy`: turnover multiplied by fee plus slippage proxy.
- `drift_breach_count`: runs where drift exceeded the effective threshold.

## Current Limitation

Historical logs do not yet contain enough structured price and pre-plan data for a true return backtest. The current harness is a decision-quality replay: it compares whether Scenario B would trade less, skip low-value orders, and reduce turnover/cost pressure.

The next useful step is to extract `ReplayCase` rows from future audit logs after TASK-001 through TASK-003 are in place and enough new runs have accumulated.
