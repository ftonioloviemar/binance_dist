from __future__ import annotations

import pytest
import requests

from binance_client import Balance, SymbolFilters
from portfolio import (
    AssetPosition,
    PortfolioError,
    PortfolioSnapshot,
    RebalanceDecision,
    build_trades,
    compute_current_weights,
    decide_rebalance,
    rebalance_has_tradable_orders,
    validate_target_map,
    ai_refine_targets,
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


def test_rebalance_has_tradable_orders_blocks_untradable_drift() -> None:
    snapshot = PortfolioSnapshot(
        quote_asset="USDT",
        total_value=100.0,
        positions={
            "BTC": AssetPosition(asset="BTC", quantity=0.51, price=100.0, value=51.0, weight=0.51),
            "USDT": AssetPosition(asset="USDT", quantity=49.0, price=1.0, value=49.0, weight=0.49),
        },
    )
    decision = RebalanceDecision(rebalance_needed=True, deltas={"BTC": 0.04, "USDT": -0.04})
    filters = {
        "BTCUSDT": SymbolFilters(
            symbol="BTCUSDT",
            lot_step=0.0001,
            min_qty=0.0001,
            max_qty=1000.0,
            min_notional=5.0,
            price_tick=0.01,
        )
    }
    tradable = rebalance_has_tradable_orders(
        snapshot=snapshot,
        decision=decision,
        prices={"BTC": 100.0},
        filters=filters,
        min_notional=0.0,
    )

    assert tradable is False


def test_rebalance_has_tradable_orders_allows_tradable_delta() -> None:
    snapshot = PortfolioSnapshot(
        quote_asset="USDT",
        total_value=100.0,
        positions={
            "BTC": AssetPosition(asset="BTC", quantity=0.7, price=100.0, value=70.0, weight=0.7),
            "USDT": AssetPosition(asset="USDT", quantity=30.0, price=1.0, value=30.0, weight=0.3),
        },
    )
    decision = RebalanceDecision(rebalance_needed=True, deltas={"BTC": 0.1, "USDT": -0.1})
    filters = {
        "BTCUSDT": SymbolFilters(
            symbol="BTCUSDT",
            lot_step=0.0001,
            min_qty=0.0001,
            max_qty=1000.0,
            min_notional=5.0,
            price_tick=0.01,
        )
    }
    tradable = rebalance_has_tradable_orders(
        snapshot=snapshot,
        decision=decision,
        prices={"BTC": 100.0},
        filters=filters,
        min_notional=0.0,
    )

    assert tradable is True


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


def test_build_trades_skips_below_effective_exchange_notional() -> None:
    snapshot = PortfolioSnapshot(
        quote_asset="USDT",
        total_value=1000.0,
        positions={
            "ADA": AssetPosition(asset="ADA", quantity=100.0, price=1.0, value=100.0, weight=0.1),
            "USDT": AssetPosition(asset="USDT", quantity=900.0, price=1.0, value=900.0, weight=0.9),
        },
    )
    decision = RebalanceDecision(rebalance_needed=True, deltas={"ADA": 0.004})
    filters = {
        "ADAUSDT": SymbolFilters(
            symbol="ADAUSDT",
            lot_step=0.1,
            min_qty=0.1,
            max_qty=100000.0,
            min_notional=5.0,
            price_tick=0.0001,
        )
    }
    rejections: list[str] = []

    trades = build_trades(
        snapshot=snapshot,
        decision=decision,
        prices={"ADA": 1.0},
        filters=filters,
        min_notional=0.0,
        max_slippage=0.003,
        rejections=rejections,
    )

    assert trades == []
    assert rejections == ["ADAUSDT: notional 4.0000 < min 5.0"]


def test_build_trades_skips_above_exchange_max_notional() -> None:
    snapshot = PortfolioSnapshot(
        quote_asset="USDT",
        total_value=1000.0,
        positions={
            "ADA": AssetPosition(asset="ADA", quantity=100.0, price=1.0, value=100.0, weight=0.1),
            "USDT": AssetPosition(asset="USDT", quantity=900.0, price=1.0, value=900.0, weight=0.9),
        },
    )
    decision = RebalanceDecision(rebalance_needed=True, deltas={"ADA": 0.02})
    filters = {
        "ADAUSDT": SymbolFilters(
            symbol="ADAUSDT",
            lot_step=0.1,
            min_qty=0.1,
            max_qty=100000.0,
            min_notional=5.0,
            max_notional=10.0,
            price_tick=0.0001,
        )
    }
    rejections: list[str] = []

    trades = build_trades(
        snapshot=snapshot,
        decision=decision,
        prices={"ADA": 1.0},
        filters=filters,
        min_notional=0.0,
        max_slippage=0.003,
        rejections=rejections,
    )

    assert trades == []
    assert rejections == ["ADAUSDT: notional 20.0000 > max 10.0"]


def test_build_trades_allows_exact_notional_boundaries() -> None:
    snapshot = PortfolioSnapshot(
        quote_asset="USDT",
        total_value=1000.0,
        positions={
            "ADA": AssetPosition(asset="ADA", quantity=100.0, price=1.0, value=100.0, weight=0.1),
            "USDT": AssetPosition(asset="USDT", quantity=900.0, price=1.0, value=900.0, weight=0.9),
        },
    )
    filters = {
        "ADAUSDT": SymbolFilters(
            symbol="ADAUSDT",
            lot_step=0.1,
            min_qty=0.1,
            max_qty=100000.0,
            min_notional=5.0,
            max_notional=10.0,
            price_tick=0.0001,
        )
    }

    min_trades = build_trades(
        snapshot=snapshot,
        decision=RebalanceDecision(rebalance_needed=True, deltas={"ADA": 0.005}),
        prices={"ADA": 1.0},
        filters=filters,
        min_notional=0.0,
        max_slippage=0.003,
        rejections=[],
    )
    max_trades = build_trades(
        snapshot=snapshot,
        decision=RebalanceDecision(rebalance_needed=True, deltas={"ADA": 0.01}),
        prices={"ADA": 1.0},
        filters=filters,
        min_notional=0.0,
        max_slippage=0.003,
        rejections=[],
    )

    assert [trade.notional for trade in min_trades] == [5.0]
    assert [trade.notional for trade in max_trades] == [10.0]


def test_validate_target_map_rejects_negative_weights() -> None:
    with pytest.raises(PortfolioError):
        validate_target_map({"BTC": -0.1, "ETH": 1.1})


def test_validate_target_map_normalizes_sum_to_one() -> None:
    normalized = validate_target_map({"BTC": 40, "ETH": 60})
    assert pytest.approx(sum(normalized.values()), rel=1e-6) == 1.0


def test_ai_refine_targets_records_first_model_failure_and_fallback_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object] | None = None):
            self.status_code = status_code
            self._payload = payload or {}
            self.headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(
                    f"{self.status_code} error", response=self
                )

        def json(self) -> dict[str, object]:
            return self._payload

    calls: list[str] = []

    def fake_post(_url: str, json: dict[str, object], **_kwargs: object) -> FakeResponse:
        model = str(json["model"])
        calls.append(model)
        if model == "broken/primary:free":
            return FakeResponse(404)
        return FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"action":"redistribute","targets":{"BTC":0.4,"USDT":0.6},"rationale":"fallback ok"}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("portfolio.requests.post", fake_post)

    advice = ai_refine_targets(
        api_key="key",
        models=("broken/primary:free", "working/fallback:free"),
        portfolio_value=1000.0,
        current_weights={"BTC": 0.5, "USDT": 0.5},
        proposed_weights={"BTC": 0.4, "USDT": 0.6},
    )

    assert calls == ["broken/primary:free", "working/fallback:free"]
    assert advice.model_used == "working/fallback:free"
    assert advice.first_model_failed is True
    assert advice.model_failures[0].model == "broken/primary:free"
    assert advice.model_failures[0].status_code == 404
    assert advice.rationale == "fallback ok"
