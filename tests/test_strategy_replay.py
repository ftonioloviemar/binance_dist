from __future__ import annotations

import pytest

from strategy_replay import ReplayCase, ScenarioBPolicy, replay_scenario_b


def test_scenario_b_raises_threshold_during_high_volatility() -> None:
    summary = replay_scenario_b(
        [
            ReplayCase(
                run_id="high-vol",
                max_abs_drift=0.04,
                planned_trade_notionals=[25.0],
                realized_volatility=0.08,
            )
        ],
        ScenarioBPolicy(
            base_drift_threshold=0.03,
            high_volatility_threshold=0.06,
            high_volatility_multiplier=2.0,
            min_trade_notional=10.0,
            fee_rate=0.001,
            slippage_rate=0.002,
        ),
    )

    assert summary.drift_breach_count == 0
    assert summary.order_count == 0
    assert summary.skipped_small_trade_count == 0
    assert summary.turnover_proxy == 0.0
    assert summary.decisions[0].effective_threshold == 0.06
    assert summary.decisions[0].action == "skip_drift"


def test_scenario_b_counts_tradable_orders_and_small_trade_skips() -> None:
    summary = replay_scenario_b(
        [
            ReplayCase(
                run_id="cost-aware",
                max_abs_drift=0.08,
                planned_trade_notionals=[4.0, 12.0, 20.0],
                realized_volatility=0.02,
            )
        ],
        ScenarioBPolicy(
            base_drift_threshold=0.03,
            high_volatility_threshold=0.06,
            high_volatility_multiplier=2.0,
            min_trade_notional=10.0,
            fee_rate=0.001,
            slippage_rate=0.002,
        ),
    )

    assert summary.drift_breach_count == 1
    assert summary.order_count == 2
    assert summary.skipped_small_trade_count == 1
    assert summary.turnover_proxy == 32.0
    assert summary.estimated_cost_proxy == pytest.approx(0.096)
    assert summary.decisions[0].action == "rebalance"


def test_scenario_b_skips_when_drift_breaches_but_no_trade_passes_cost_guard() -> None:
    summary = replay_scenario_b(
        [
            ReplayCase(
                run_id="small-only",
                max_abs_drift=0.08,
                planned_trade_notionals=[4.0, 9.99],
                realized_volatility=0.02,
            )
        ],
        ScenarioBPolicy(
            base_drift_threshold=0.03,
            high_volatility_threshold=0.06,
            high_volatility_multiplier=2.0,
            min_trade_notional=10.0,
            fee_rate=0.001,
            slippage_rate=0.002,
        ),
    )

    assert summary.drift_breach_count == 1
    assert summary.order_count == 0
    assert summary.skipped_small_trade_count == 2
    assert summary.turnover_proxy == 0.0
    assert summary.estimated_cost_proxy == 0.0
    assert summary.decisions[0].action == "skip_cost"


def test_scenario_b_aggregates_multiple_replay_cases() -> None:
    summary = replay_scenario_b(
        [
            ReplayCase(
                run_id="skip",
                max_abs_drift=0.02,
                planned_trade_notionals=[50.0],
                realized_volatility=0.01,
            ),
            ReplayCase(
                run_id="trade",
                max_abs_drift=0.08,
                planned_trade_notionals=[5.0, 15.0],
                realized_volatility=0.01,
            ),
            ReplayCase(
                run_id="cost",
                max_abs_drift=0.09,
                planned_trade_notionals=[4.0],
                realized_volatility=0.01,
            ),
        ],
        ScenarioBPolicy(
            base_drift_threshold=0.03,
            high_volatility_threshold=0.06,
            high_volatility_multiplier=2.0,
            min_trade_notional=10.0,
            fee_rate=0.001,
            slippage_rate=0.002,
        ),
    )

    assert [decision.action for decision in summary.decisions] == [
        "skip_drift",
        "rebalance",
        "skip_cost",
    ]
    assert summary.drift_breach_count == 2
    assert summary.order_count == 1
    assert summary.skipped_small_trade_count == 2
    assert summary.turnover_proxy == 15.0
    assert summary.estimated_cost_proxy == pytest.approx(0.045)
