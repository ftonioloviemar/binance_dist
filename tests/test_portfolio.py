from __future__ import annotations

import pytest

from binance_client import Balance, SymbolFilters
from portfolio import (
    AssetPosition,
    PortfolioError,
    PortfolioSnapshot,
    RebalanceDecision,
    build_trades,
    compute_current_weights,
    decide_rebalance,
    validate_target_map,
)


def test_compute_current_weights_derives_weights() -> None:
    balances = [Balance(asset="BTC", free=0.5, locked=0.0), Balance(asset="USDT", free=10000.0, locked=0.0)]
    prices = {"BTC": 20000.0, "USDT": 1.0}
    snapshot = compute_current_weights(balances, prices, "USDT")
    btc_weight = snapshot.positions["BTC"].weight
    usdt_weight = snapshot.positions["USDT"].weight
    assert pytest.approx(btc_weight, rel=1e-3) == 0.5
    assert pytest.approx(usdt_weight, rel=1e-3) == 0.5


def test_decide_rebalance_triggers_on_drift() -> None:
    snapshot = PortfolioSnapshot(
        quote_asset="USDT",
        total_value=1000.0,
        positions={
            "BTC": AssetPosition(asset="BTC", quantity=0.02, price=30000.0, value=600.0, weight=0.6),
            "ETH": AssetPosition(asset="ETH", quantity=1.0, price=400.0, value=400.0, weight=0.4),
        },
    )
    decision = decide_rebalance(snapshot, {"BTC": 0.4, "ETH": 0.6}, drift_threshold=0.05)
    assert decision.rebalance_needed is True
    assert pytest.approx(decision.deltas["BTC"], rel=1e-3) == -0.2


def test_build_trades_respects_lot_step() -> None:
    snapshot = PortfolioSnapshot(
        quote_asset="USDT",
        total_value=1000.0,
        positions={
            "BTC": AssetPosition(asset="BTC", quantity=0.02, price=50000.0, value=500.0, weight=0.5),
            "ETH": AssetPosition(asset="ETH", quantity=1.0, price=500.0, value=500.0, weight=0.5),
        },
    )
    decision = RebalanceDecision(rebalance_needed=True, deltas={"BTC": 0.1, "ETH": -0.1})
    filters = {
        "BTCUSDT": SymbolFilters(
            symbol="BTCUSDT",
            lot_step=0.0001,
            min_qty=0.0001,
            max_qty=1.0,
            min_notional=10.0,
            price_tick=0.1,
        )
    }
    trades = build_trades(
        snapshot=snapshot,
        decision=decision,
        prices={"BTC": 50000.0},
        filters=filters,
        min_notional=10.0,
        max_slippage=0.003,
    )
    assert trades, "Expected at least one trade"
    btc_trade = trades[0]
    assert btc_trade.symbol == "BTCUSDT"
    step = filters["BTCUSDT"].lot_step
    assert pytest.approx(btc_trade.quantity / step) == round(btc_trade.quantity / step)


def test_validate_target_map_rejects_negative_weights() -> None:
    with pytest.raises(PortfolioError):
        validate_target_map({"BTC": -0.1, "ETH": 1.1})


def test_validate_target_map_normalizes_sum_to_one() -> None:
    normalized = validate_target_map({"BTC": 40, "ETH": 60})
    assert pytest.approx(sum(normalized.values()), rel=1e-6) == 1.0
