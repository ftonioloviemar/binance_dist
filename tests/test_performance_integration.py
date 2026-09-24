from __future__ import annotations

import json
from decimal import Decimal

import app
from binance_client import Balance, SimpleEarnPosition


def test_build_performance_snapshot_payload_separates_spot_and_earn() -> None:
    payload = app._build_performance_snapshot_payload(
        run_id="run-1",
        phase="before",
        quote="USDT",
        spot_balances=[Balance(asset="USDT", free=100.0, locked=0.0)],
        earn_positions=[
            SimpleEarnPosition(
                product_id="p1",
                asset="BTC",
                total_amount=0.01,
                redeemable_amount=0.01,
                can_fast_redeem=True,
            )
        ],
        prices={"BTC": 20000.0},
        timestamp="2026-09-21T12:00:00+00:00",
    )

    assert payload["spot_value"] == "100.00"
    assert payload["earn_value"] == "200.00"
    assert json.loads(json.dumps(payload))["data_quality"] == "complete"


def test_build_performance_snapshot_payload_marks_simulation() -> None:
    payload = app._build_performance_snapshot_payload(
        run_id="run-1",
        phase="after",
        quote="USDT",
        spot_balances=[],
        earn_positions=[],
        prices={},
        timestamp="2026-09-21T12:00:00+00:00",
        data_quality="simulation",
    )

    assert payload["data_quality"] == "simulation"
    assert payload["total_value"] == "0.00"


class PostActionClient:
    def __init__(self, balances, earn_positions):
        self.balances = balances
        self.earn_positions = earn_positions
        self.calls = []

    def get_account_balances(self):
        self.calls.append("spot")
        if isinstance(self.balances, Exception):
            raise self.balances
        return self.balances

    def get_simple_earn_flexible_positions(self):
        self.calls.append("earn")
        if isinstance(self.earn_positions, Exception):
            raise self.earn_positions
        return self.earn_positions

    def get_prices(self):
        self.calls.append("prices")
        return {"BTCUSDT": 1.0}


class SnapshotAuditor:
    def __init__(self):
        self.steps = []

    def log_step(self, **step):
        self.steps.append(step)


def _earn_position(asset: str, amount: float) -> SimpleEarnPosition:
    return SimpleEarnPosition(
        product_id="product",
        asset=asset,
        total_amount=amount,
        redeemable_amount=amount,
        can_fast_redeem=True,
    )


def _capture_post_trade_snapshot(
    client,
    *,
    dry_run=False,
    products=None,
    spot=None,
    earn=None,
    prices=None,
    spot_balances_fresh=True,
):
    auditor = SnapshotAuditor()
    pendings = []
    payload = app._build_post_trade_performance_snapshot_payload(
        client=client,
        auditor=auditor,
        run_id="run-final",
        quote="USDT",
        spot_balances=spot or [],
        earn_positions=earn or [],
        prices=prices or {},
        targets={},
        timestamp="2026-09-24T12:00:00+00:00",
        products_by_asset=products or {},
        simple_earn_enabled=bool(products),
        dry_run=dry_run,
        spot_balances_fresh=spot_balances_fresh,
        pendings=pendings,
    )
    return payload, auditor, pendings


def test_final_snapshot_uses_post_redeem_spot_and_earn_positions() -> None:
    client = PostActionClient(
        balances=[Balance(asset="USDT", free=100.0, locked=0.0)],
        earn_positions=[],
    )

    payload, _, _ = _capture_post_trade_snapshot(
        client,
        spot=[Balance(asset="USDT", free=100.0, locked=0.0)],
        earn=[_earn_position("BTC", 100.0)],
    )

    assert payload["spot_value"] == "100.00"
    assert payload["earn_value"] == "0.00"
    assert payload["total_value"] == "100.00"
    assert payload["data_quality"] == "complete"
    assert client.calls == ["spot", "earn", "prices"]


def test_final_snapshot_subscribes_before_refreshing_positions(monkeypatch) -> None:
    client = PostActionClient(
        balances=[Balance(asset="USDT", free=60.0, locked=0.0)],
        earn_positions=[_earn_position("BTC", 40.0)],
    )
    call_order = []

    def subscribe(**_kwargs):
        call_order.append("subscribe")

    monkeypatch.setattr(app, "_subscribe_simple_earn_balances", subscribe)
    payload, _, _ = _capture_post_trade_snapshot(
        client,
        products={"BTC": object()},
        spot=[Balance(asset="USDT", free=100.0, locked=0.0)],
        earn=[_earn_position("BTC", 100.0)],
    )

    assert payload["spot_value"] == "60.00"
    assert payload["earn_value"] == "40.00"
    assert payload["total_value"] == "100.00"
    assert call_order == ["subscribe"]
    assert client.calls == ["spot", "earn", "prices"]


def test_failed_earn_refresh_does_not_reuse_stale_positions() -> None:
    client = PostActionClient(
        balances=[Balance(asset="USDT", free=60.0, locked=0.0)],
        earn_positions=RuntimeError("earn refresh unavailable"),
    )

    payload, auditor, pendings = _capture_post_trade_snapshot(
        client,
        spot=[Balance(asset="USDT", free=60.0, locked=0.0)],
        earn=[_earn_position("BTC", 40.0)],
    )

    assert payload["earn_value"] == "0.00"
    assert payload["data_quality"] == "incomplete"
    assert any(
        step["name"] == "earn_snapshot_after" and step["status"] == "failed"
        for step in auditor.steps
    )
    assert any("Earn" in pending for pending in pendings)


def test_failed_spot_refresh_marks_snapshot_incomplete() -> None:
    client = PostActionClient(
        balances=RuntimeError("spot refresh unavailable"),
        earn_positions=[],
    )

    payload, auditor, pendings = _capture_post_trade_snapshot(
        client,
        spot=[Balance(asset="USDT", free=60.0, locked=0.0)],
    )

    assert payload["data_quality"] == "incomplete"
    assert any(
        step["name"] == "spot_snapshot_after" and step["status"] == "failed"
        for step in auditor.steps
    )
    assert any("Spot" in pending for pending in pendings)


def test_subscription_is_skipped_when_pre_subscription_spot_is_stale(monkeypatch) -> None:
    client = PostActionClient(
        balances=[Balance(asset="USDT", free=60.0, locked=0.0)],
        earn_positions=[_earn_position("BTC", 40.0)],
    )
    subscriptions = []

    def subscribe(**_kwargs):
        subscriptions.append(True)

    monkeypatch.setattr(app, "_subscribe_simple_earn_balances", subscribe)
    payload, auditor, pendings = _capture_post_trade_snapshot(
        client,
        products={"BTC": object()},
        spot=[Balance(asset="USDT", free=100.0, locked=0.0)],
        earn=[_earn_position("BTC", 100.0)],
        spot_balances_fresh=False,
    )

    assert subscriptions == []
    assert payload["data_quality"] == "complete"
    assert payload["total_value"] == "100.00"
    assert any(
        step["name"] == "earn_subscribe" and step["status"] == "skipped"
        for step in auditor.steps
    )
    assert any(
        "Spot balances could not be confirmed" in pending for pending in pendings
    )


def test_dry_run_does_not_refresh_or_move_funds_after_snapshot(monkeypatch) -> None:
    client = PostActionClient(balances=[], earn_positions=[])
    subscriptions = []

    def simulated_subscribe(**kwargs):
        subscriptions.append(kwargs["dry_run"])

    monkeypatch.setattr(app, "_subscribe_simple_earn_balances", simulated_subscribe)
    payload, _, _ = _capture_post_trade_snapshot(
        client,
        dry_run=True,
        products={"BTC": object()},
        spot=[Balance(asset="USDT", free=100.0, locked=0.0)],
        earn=[_earn_position("BTC", 1.0)],
        prices={"BTC": 1.0},
    )

    assert payload["data_quality"] == "simulation"
    assert payload["total_value"] == "101.00"
    assert subscriptions == [True]
    assert client.calls == []
