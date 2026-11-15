from __future__ import annotations

import argparse
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import app
from binance_client import Balance
from config import EnvSettings
from performance_store import load_portfolio_snapshots, record_portfolio_snapshot


@pytest.fixture(params=[None, 0.0, -1.0, float("nan"), float("inf"), -float("inf")],
                ids=["missing", "zero", "negative", "nan", "inf", "negative-inf"])
def invalid_price(request):
    return request.param


@pytest.fixture(params=[True, False], ids=["dry-run", "live-path"])
def rebalance_result(monkeypatch, tmp_path, request, invalid_price, invalidation_stage):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "performance.db"
    steps, statuses, calls = [], [], []

    def blocked(*_args, **_kwargs):
        raise AssertionError("Network access is forbidden in this test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr(app, "build_performance_report", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app, "render_performance_report", lambda *_args, **_kwargs: "")

    class Auditor:
        run_id = "refresh-regression"

        def start_run(self, **kwargs):
            pass

        def log_step(self, **kwargs):
            steps.append(kwargs)

        def log_exception(self, **kwargs):
            steps.append({"name": "exception", **kwargs})

        def finalize_run(self, status):
            statuses.append(status)

        def close(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_account_balances(self):
            return [Balance(asset="USDQ", free=10, locked=0),
                    Balance(asset="TEST", free=2, locked=0),
                    Balance(asset="OTHER", free=2, locked=0)]

        def get_simple_earn_flexible_positions(self):
            return []

        def get_simple_earn_flexible_products(self):
            return {}

        def close(self):
            pass

        def __getattr__(self, name):
            calls.append("client." + name)
            return Mock(side_effect=AssertionError("Unexpected exchange operation: " + name))

    def fetch_prices(*_args):
        calls.append("fetch")
        if invalidation_stage == "second_fetch" and calls.count("fetch") == 2:
            result = {"OTHER": 7.0}
            if invalid_price is not None:
                result["TEST"] = invalid_price
            return result
        return {"TEST": 3.0, "OTHER": 4.0}

    def refresh(_client, prices, *_args):
        calls.append("refresh")
        if invalidation_stage == "second_fetch":
            return prices
        assert prices["TEST"] == 3.0
        result = dict(prices)
        if invalid_price is None:
            result.pop("TEST")
        else:
            result["TEST"] = invalid_price
        return result

    def forbidden(name):
        def operation(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError("Unexpected planning or execution: " + name)
        return operation

    monkeypatch.setattr(app, "BinanceClient", Client)
    monkeypatch.setattr(app, "AuditLogger", Auditor)
    monkeypatch.setattr(app, "load_env_settings", lambda recv_window: EnvSettings(
        api_key="fake", api_secret="fake", testnet=True,
        base_url="https://invalid.example", recv_window=recv_window,
        simple_earn_enabled=True, ai_provider="off"))
    monkeypatch.setattr(app, "fetch_macro_snapshot", lambda: SimpleNamespace(
        data={}, errors=[], sources={}))
    monkeypatch.setattr(app, "_fetch_asset_prices", fetch_prices)
    monkeypatch.setattr(app, "_ensure_target_prices", refresh)
    monkeypatch.setattr(app, "record_portfolio_snapshot",
                        lambda _path, payload: record_portfolio_snapshot(db_path, payload))
    for name in ("_build_shadow_run", "observe_shadow_run", "decide_rebalance",
                 "rebalance_has_tradable_orders", "build_trades",
                 "_redeem_simple_earn_positions", "execute_trades",
                 "_subscribe_simple_earn_balances"):
        monkeypatch.setattr(app, name, forbidden(name))

    args = argparse.Namespace(command="rebalance", dry_run=request.param,
        profile="moderate", drift=0.01, max_slippage=0.003, min_notional=0.0,
        targets="USDQ=1", quote="USDQ", recv_window=5000,
        config_path=Path("missing.toml"), adaptive=False)
    result = app.run_rebalance(args)
    snapshots = load_portfolio_snapshots(db_path, run_id=Auditor.run_id) if db_path.exists() else []
    return result, statuses, calls, steps, snapshots


@pytest.fixture
def invalidation_stage(request):
    return getattr(request, "param", "target_refresh")


def test_refresh_invalid_held_price_stops_before_planning_and_persists_incomplete(rebalance_result):
    result, statuses, calls, _steps, snapshots = rebalance_result
    assert result == 1
    assert statuses == ["failed"]
    assert calls == ["fetch", "fetch", "refresh"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["phase"] == "before"
    assert snapshot["data_quality"] == "incomplete"
    assert "TEST" in snapshot["missing_prices"]


def test_refresh_invalid_held_price_audits_canonical_valuation_guard(rebalance_result):
    _result, _statuses, _calls, steps, _snapshots = rebalance_result
    assert any(step.get("name") == "valuation_guard" and step.get("status") == "failed"
               for step in steps)


@pytest.mark.parametrize("invalidation_stage", ["second_fetch"], indirect=True)
def test_second_fetch_invalid_price_stops_before_planning(rebalance_result):
    result, statuses, calls, _steps, _snapshots = rebalance_result
    assert result == 1
    assert statuses == ["failed"]
    assert calls == ["fetch", "fetch"]


@pytest.mark.parametrize("invalidation_stage", ["second_fetch"], indirect=True)
def test_second_fetch_invalid_price_records_guard_and_incomplete_snapshot(rebalance_result):
    _result, _statuses, _calls, steps, snapshots = rebalance_result
    assert any(step.get("name") == "valuation_guard" and step.get("status") == "failed"
               for step in steps)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["phase"] == "before"
    assert snapshot["data_quality"] == "incomplete"
    assert "TEST" in snapshot["missing_prices"]


@pytest.mark.parametrize("invalidation_stage", ["second_fetch"], indirect=True)
def test_second_fetch_snapshot_uses_latest_valid_price_and_value(rebalance_result):
    _result, _statuses, _calls, _steps, snapshots = rebalance_result
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["prices"]["OTHER"] == "7.00"
    assert snapshot["asset_values"]["spot:OTHER"] == "14.00"
    assert snapshot["spot_value"] == "24.00"
    assert snapshot["total_value"] == "24.00"
