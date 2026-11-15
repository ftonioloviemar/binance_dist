from __future__ import annotations

import argparse
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import app
from binance_client import Balance, SimpleEarnPosition
from config import EnvSettings
from portfolio import RebalanceDecision
from performance_store import load_portfolio_snapshots, record_portfolio_snapshot


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("Network access is forbidden in this test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr(app, "build_performance_report", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app, "render_performance_report", lambda *_args, **_kwargs: "")


def test_after_snapshot_failed_price_refresh_reports_unpriced_raw_ld_alias(monkeypatch):
    spot = [Balance(asset="USDQ", free=10, locked=0), Balance(asset="LDTEST", free=2, locked=0)]
    earn = [SimpleEarnPosition(
        product_id="synthetic", asset="TEST", total_amount=2,
        redeemable_amount=2, can_fast_redeem=True,
    )]
    steps = []

    class Auditor:
        def log_step(self, **kwargs):
            steps.append(kwargs)

    class Client:
        def get_account_balances(self):
            return spot

        def get_simple_earn_flexible_positions(self):
            return earn

    def failed_refresh(*_args, **_kwargs):
        raise RuntimeError("synthetic price refresh failure")

    monkeypatch.setattr(app, "_fetch_asset_prices", failed_refresh)
    result = app._build_post_trade_performance_snapshot_payload(
        client=Client(), auditor=Auditor(), run_id="synthetic", quote="USDQ",
        spot_balances=[], earn_positions=[], prices={"TEST": 3}, targets={},
        timestamp="2026-01-01T00:00:00Z", products_by_asset={},
        simple_earn_enabled=True, dry_run=False, spot_balances_fresh=True,
        pendings=[],
    )

    assert result["data_quality"] == "incomplete"
    assert "LDTEST" in result["missing_prices"]
    assert result["spot_value"] == "10.00"
    assert result["earn_value"] == "6.00"
    assert result["total_value"] == "16.00"
    assert "spot:LDTEST" not in result["asset_values"]
    assert any(
        step.get("name") == "prices_snapshot_after"
        and step.get("status") == "warning"
        and "completed operations remain in effect" in step.get("detail", "")
        for step in steps
    )


@pytest.mark.parametrize(
    "alias_price", [None, 0.0, -1.0, float("nan"), float("inf"), -float("inf")],
    ids=["missing", "zero", "negative", "nan", "inf", "negative-inf"]
)
def test_after_snapshot_unpriced_ld_alias_is_incomplete_without_double_counting(
    monkeypatch, alias_price
):
    spot = [Balance(asset="USDQ", free=10, locked=0), Balance(asset="LDTEST", free=2, locked=0)]
    earn = [
        SimpleEarnPosition(
            product_id="synthetic",
            asset="TEST",
            total_amount=2,
            redeemable_amount=2,
            can_fast_redeem=True,
        )
    ]
    steps = [{"name": "earn_redeem", "status": "completed", "detail": "synthetic"}]
    seen_balances = []

    class Auditor:
        def log_step(self, **kwargs):
            steps.append(kwargs)

    class Client:
        def get_account_balances(self):
            return spot

        def get_simple_earn_flexible_positions(self):
            return earn

    def fetch_prices(client, balances, targets, quote):
        seen_balances.extend((balance.asset, balance.total) for balance in balances)
        prices = {"TEST": 3}
        if alias_price is not None:
            prices["LDTEST"] = alias_price
        return prices

    monkeypatch.setattr(app, "_fetch_asset_prices", fetch_prices)
    result = app._build_post_trade_performance_snapshot_payload(
        client=Client(),
        auditor=Auditor(),
        run_id="synthetic",
        quote="USDQ",
        spot_balances=spot,
        earn_positions=earn,
        prices={"TEST": 3},
        targets={},
        timestamp="2026-01-01T00:00:00Z",
        products_by_asset={},
        simple_earn_enabled=True,
        dry_run=False,
        spot_balances_fresh=True,
        pendings=[],
    )

    assert ("LDTEST", 2) in seen_balances
    assert [(balance.asset, balance.total) for balance in spot] == [
        ("USDQ", 10),
        ("LDTEST", 2),
    ]
    assert result["phase"] == "after"
    assert result["spot_value"] == "10.00"
    assert result["earn_value"] == "6.00"
    assert result["total_value"] == "16.00"
    assert "spot:LDTEST" not in result["asset_values"]
    assert steps[0] == {
        "name": "earn_redeem",
        "status": "completed",
        "detail": "synthetic",
    }
    assert not any(
        "revert" in str(step).lower() or "rollback" in str(step).lower()
        for step in steps
    )
    assert result["data_quality"] == "incomplete"
    assert "LDTEST" in result["missing_prices"]


@pytest.mark.parametrize(
    "alias_price", [None, 0.0, -1.0, float("nan"), float("inf"), -float("inf")],
    ids=["missing", "zero", "negative", "nan", "inf", "negative-inf"],
)
@pytest.mark.parametrize("dry_run", [False, True], ids=["live-path", "dry-run"])
def test_run_persists_incomplete_after_snapshot_for_unpriced_ld_alias(
    monkeypatch, tmp_path, alias_price, dry_run
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "isolated-performance.db"
    steps = []
    final_status = []
    actions = []
    alias = Balance(asset="LDTEST", free=2, locked=0)
    initial = [Balance(asset="USDQ", free=10, locked=0)]
    after = [*initial, alias]
    if dry_run:
        initial = after
    price_fetches = 0
    earn = [
        SimpleEarnPosition(
            product_id="synthetic",
            asset="TEST",
            total_amount=2,
            redeemable_amount=2,
            can_fast_redeem=True,
        )
    ]

    class Auditor:
        run_id = "synthetic-run"

        def start_run(self, **kwargs):
            pass

        def log_step(self, **kwargs):
            steps.append(kwargs)

        def log_exception(self, **kwargs):
            steps.append({"name": "exception", **kwargs})

        def finalize_run(self, status):
            final_status.append(status)

        def close(self):
            pass

        def __getattr__(self, name):
            raise AssertionError(f"Unexpected exchange method: {name}")

    class Client:
        def __init__(self, **kwargs):
            self.spot_calls = 0

        def get_account_balances(self):
            self.spot_calls += 1
            return initial if self.spot_calls <= 2 else after

        def get_simple_earn_flexible_positions(self):
            return earn

        def get_simple_earn_flexible_products(self):
            return {}

        def get_exchange_info(self):
            return {}

        def close(self):
            pass

        def __getattr__(self, name):
            raise AssertionError(f"Unexpected exchange method: {name}")

    def prices(_client, balances, _targets, _quote):
        nonlocal price_fetches
        price_fetches += 1
        result = {"TEST": 3}
        if any(balance.asset == "LDTEST" for balance in balances):
            if dry_run and price_fetches < 3:
                result["LDTEST"] = 3
            elif alias_price is not None:
                result["LDTEST"] = alias_price
        return result

    def redeem(**kwargs):
        actions.append("redeem")
        kwargs["auditor"].log_step(
            name="earn_redeem", status="completed", detail="completed"
        )

    def execute(**kwargs):
        actions.append("execute")

    def forbidden(*_args, **_kwargs):
        actions.append("unexpected external operation")
        raise AssertionError("Unexpected external operation")

    monkeypatch.setattr(app, "BinanceClient", Client)
    monkeypatch.setattr(app, "AuditLogger", Auditor)
    monkeypatch.setattr(
        app,
        "load_env_settings",
        lambda recv_window: EnvSettings(
            api_key="fake",
            api_secret="fake",
            testnet=True,
            base_url="https://invalid.example",
            recv_window=recv_window,
            simple_earn_enabled=True,
            ai_provider="off",
        ),
    )
    monkeypatch.setattr(
        app,
        "fetch_macro_snapshot",
        lambda: SimpleNamespace(data={}, errors=[], sources={}),
    )
    monkeypatch.setattr(app, "_fetch_asset_prices", prices)
    monkeypatch.setattr(app, "_ensure_target_prices", lambda _client, values, *_args: values)
    monkeypatch.setattr(app, "get_adaptive_manager", lambda: None)
    monkeypatch.setattr(app, "_resolve_ai_advice", lambda *_args: SimpleNamespace(
        targets={"USDQ": 1.0}, action="rebalance", rationale=None,
        provider="off", model_failures=(), model_used=None,
    ))
    monkeypatch.setattr(app, "_refresh_openrouter_models_after_failure", lambda *_args: None)
    monkeypatch.setattr(app, "evaluate_cost_gate", lambda **_kwargs: SimpleNamespace(
        status="completed", mode="observe", allowed=True, expected_benefit_bps=None,
        estimated_cost_bps=None, net_benefit_bps=None, reason="synthetic",
    ))
    monkeypatch.setattr(
        app,
        "record_portfolio_snapshot",
        lambda _path, payload: record_portfolio_snapshot(db_path, payload),
    )
    monkeypatch.setattr(app, "_build_shadow_run", lambda **kwargs: None)
    monkeypatch.setattr(app, "observe_shadow_run", forbidden)
    monkeypatch.setattr(app, "_subscribe_simple_earn_balances", forbidden)
    monkeypatch.setattr(app, "filter_dust_positions", lambda snapshot, *_args: (snapshot, {}))
    monkeypatch.setattr(
        app,
        "decide_rebalance",
        lambda *_args: RebalanceDecision(True, {"TEST": 0.5}),
    )
    monkeypatch.setattr(app, "rebalance_has_tradable_orders", lambda **kwargs: True)
    monkeypatch.setattr(app, "build_trades", lambda **kwargs: [object()])
    monkeypatch.setattr(
        app,
        "filter_anti_churn_trades",
        lambda **kwargs: kwargs["trades"],
    )
    monkeypatch.setattr(app, "_redeem_simple_earn_positions", redeem)
    monkeypatch.setattr(app, "_init_available_balances", lambda *_args: {})
    monkeypatch.setattr(app, "_fetch_fee_reference_prices", lambda *_args: {})
    monkeypatch.setattr(app, "execute_trades", execute)
    monkeypatch.setattr(app, "_print_summary", lambda *_args: None)
    args = argparse.Namespace(
        command="rebalance",
        dry_run=dry_run,
        profile="moderate",
        drift=0.01,
        max_slippage=0.003,
        min_notional=0.0,
        targets="USDQ=1",
        quote="USDQ",
        recv_window=5000,
        config_path=Path("missing.toml"),
        adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    assert actions == ["redeem", "execute"]
    assert final_status == ["completed"]
    assert any(
        step.get("name") == "execution" and step.get("status") == "completed"
        for step in steps
    )
    assert any(
        step.get("name") == "earn_redeem" and step.get("status") == "completed"
        for step in steps
    )
    assert not any(step.get("name") == "exception" for step in steps)
    [snapshot] = [
        item for item in load_portfolio_snapshots(db_path, run_id="synthetic-run")
        if item["phase"] == "after"
    ]
    assert snapshot["spot_value"] == "10.00"
    assert snapshot["earn_value"] == "6.00"
    assert snapshot["total_value"] == "16.00"
    assert "spot:LDTEST" not in snapshot["asset_values"]
    assert snapshot["data_quality"] == "incomplete"
    assert snapshot["missing_prices"] == ["LDTEST"]
    if dry_run:
        [warning] = [
            step
            for step in steps
            if step.get("name") == "prices_snapshot_after"
            and step.get("status") == "warning"
        ]
        assert sum(
            step.get("name") == "prices_snapshot_after"
            and step.get("status") == "warning"
            for step in steps
        ) == 1
        assert "completed operations remain in effect" not in warning["detail"]
        return
    [warning] = [
        step
        for step in steps
        if step.get("name") == "prices_snapshot_after" and step.get("status") == "warning"
    ]
    assert "incomplete" in warning["detail"]
    assert "completed operations remain in effect" in warning["detail"]
    assert "LDTEST" not in warning["detail"]
    assert "synthetic-run" not in warning["detail"]
    assert any(
        step.get("name") == "portfolio_snapshot"
        and '"phase":"after"' in step.get("detail", "")
        and '"data_quality":"incomplete"' in step.get("detail", "")
        for step in steps
    )


def test_dry_run_final_only_unpriced_ld_alias_marks_after_incomplete(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "performance.db"
    steps = []
    balance_calls = []
    actions = []
    initial = [Balance(asset="USDQ", free=10, locked=0)]
    final = [*initial, Balance(asset="LDTEST", free=2, locked=0)]
    earn = [SimpleEarnPosition(
        product_id="synthetic", asset="TEST", total_amount=2,
        redeemable_amount=2, can_fast_redeem=True,
    )]

    class Auditor:
        run_id = "synthetic-final-only"

        def start_run(self, **kwargs):
            pass

        def log_step(self, **kwargs):
            steps.append(kwargs)

        def log_exception(self, **kwargs):
            steps.append({"name": "exception", **kwargs})

        def finalize_run(self, status):
            pass

        def close(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_account_balances(self):
            balance_calls.append(None)
            return initial if len(balance_calls) == 1 else final

        def get_simple_earn_flexible_positions(self):
            return earn

        def get_simple_earn_flexible_products(self):
            return {}

        def get_exchange_info(self):
            return {}

        def close(self):
            pass

        def __getattr__(self, name):
            raise AssertionError(f"Unexpected exchange method: {name}")

    def fake_action(**kwargs):
        assert kwargs["dry_run"] is True
        actions.append(True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unexpected external operation")

    monkeypatch.setattr(app, "BinanceClient", Client)
    monkeypatch.setattr(app, "AuditLogger", Auditor)
    monkeypatch.setattr(app, "load_env_settings", lambda recv_window: EnvSettings(
        api_key="fake", api_secret="fake", testnet=True,
        base_url="https://invalid.example", recv_window=recv_window,
        simple_earn_enabled=True, ai_provider="off",
    ))
    monkeypatch.setattr(app, "fetch_macro_snapshot", lambda: SimpleNamespace(
        data={}, errors=[], sources={},
    ))
    monkeypatch.setattr(app, "_fetch_asset_prices", lambda *_args: {"TEST": 3})
    monkeypatch.setattr(app, "_ensure_target_prices", lambda _client, values, *_args: values)
    monkeypatch.setattr(app, "get_adaptive_manager", lambda: None)
    monkeypatch.setattr(app, "_resolve_ai_advice", lambda *_args: SimpleNamespace(
        targets={"USDQ": 1.0}, action="rebalance", rationale=None,
        provider="off", model_failures=(), model_used=None,
    ))
    monkeypatch.setattr(app, "_refresh_openrouter_models_after_failure", lambda *_args: None)
    monkeypatch.setattr(app, "evaluate_cost_gate", lambda **_kwargs: SimpleNamespace(
        status="completed", mode="observe", allowed=True, expected_benefit_bps=None,
        estimated_cost_bps=None, net_benefit_bps=None, reason="synthetic",
    ))
    monkeypatch.setattr(app, "record_portfolio_snapshot", lambda _path, payload:
                        record_portfolio_snapshot(db_path, payload))
    monkeypatch.setattr(app, "_build_shadow_run", lambda **kwargs: None)
    monkeypatch.setattr(app, "observe_shadow_run", forbidden)
    monkeypatch.setattr(app, "_subscribe_simple_earn_balances", forbidden)
    monkeypatch.setattr(app, "filter_dust_positions", lambda snapshot, *_args: (snapshot, {}))
    monkeypatch.setattr(app, "decide_rebalance", lambda *_args: RebalanceDecision(True, {"TEST": 0.5}))
    monkeypatch.setattr(app, "rebalance_has_tradable_orders", lambda **kwargs: True)
    monkeypatch.setattr(app, "build_trades", lambda **kwargs: [object()])
    monkeypatch.setattr(app, "filter_anti_churn_trades", lambda **kwargs: kwargs["trades"])
    monkeypatch.setattr(app, "_redeem_simple_earn_positions", fake_action)
    monkeypatch.setattr(app, "_init_available_balances", lambda *_args: {})
    monkeypatch.setattr(app, "_fetch_fee_reference_prices", lambda *_args: {})
    monkeypatch.setattr(app, "execute_trades", fake_action)
    monkeypatch.setattr(app, "_print_summary", lambda *_args: None)
    args = argparse.Namespace(
        command="rebalance", dry_run=True, profile="moderate", drift=0.01,
        max_slippage=0.003, min_notional=0.0, targets="USDQ=1", quote="USDQ",
        recv_window=5000, config_path=Path("missing.toml"), adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    assert len(balance_calls) == 2
    assert len(actions) == 2
    [snapshot] = [item for item in load_portfolio_snapshots(
        db_path, run_id="synthetic-final-only") if item["phase"] == "after"]
    assert snapshot["data_quality"] == "incomplete"
    assert snapshot["missing_prices"] == ["LDTEST"]
    assert snapshot["spot_value"] == "10.00"
    assert snapshot["earn_value"] == "6.00"
    assert snapshot["total_value"] == "16.00"
    assert "spot:LDTEST" not in snapshot["asset_values"]
    [warning] = [step for step in steps if step.get("name") == "prices_snapshot_after"
                 and step.get("status") == "warning"]
    assert "no live operations were performed" in warning["detail"].lower()


@pytest.mark.parametrize("failed_refresh", ["balances", "prices"])
def test_dry_run_final_refresh_failure_persists_incomplete_snapshot(
    monkeypatch, tmp_path, failed_refresh
):
    _assert_dry_run_incomplete_snapshot(monkeypatch, tmp_path, failed_refresh)


def test_dry_run_initial_earn_failure_persists_incomplete_after_snapshot(
    monkeypatch, tmp_path
):
    _assert_dry_run_incomplete_snapshot(monkeypatch, tmp_path, "earn")


def _assert_dry_run_incomplete_snapshot(monkeypatch, tmp_path, failed_refresh):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "synthetic-performance.db"
    steps = []
    balance_calls = []
    final_price_attempts = []
    actions = []
    initial = [Balance(asset="USDQ", free=10, locked=0),
               Balance(asset="TEST", free=2, locked=0)]
    final = [Balance(asset="USDQ", free=10, locked=0),
             Balance(asset="TEST", free=3, locked=0)]

    class Auditor:
        run_id = "synthetic-refresh-failure"

        def start_run(self, **kwargs):
            pass

        def log_step(self, **kwargs):
            steps.append(kwargs)

        def log_exception(self, **kwargs):
            steps.append({"name": "exception", **kwargs})

        def finalize_run(self, status):
            pass

        def close(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_account_balances(self):
            balance_calls.append(None)
            if len(balance_calls) == 1:
                return initial
            assert len(balance_calls) == 2
            if failed_refresh == "balances":
                raise RuntimeError("synthetic final balance failure")
            return final

        def get_simple_earn_flexible_positions(self):
            if failed_refresh == "earn":
                raise RuntimeError("synthetic initial earn failure")
            return []

        def get_simple_earn_flexible_products(self):
            return {}

        def get_exchange_info(self):
            return {}

        def close(self):
            pass

        def __getattr__(self, name):
            raise AssertionError(f"Unexpected exchange method: {name}")

    def prices(_client, balances, _targets, _quote):
        if balances is final:
            final_price_attempts.append(True)
            if failed_refresh == "prices":
                raise RuntimeError("synthetic final price failure")
        return {"TEST": 3}

    def fake_action(**kwargs):
        assert kwargs["dry_run"] is True
        actions.append(True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unexpected external operation")

    monkeypatch.setattr(app, "BinanceClient", Client)
    monkeypatch.setattr(app, "AuditLogger", Auditor)
    monkeypatch.setattr(app, "load_env_settings", lambda recv_window: EnvSettings(
        api_key="fake", api_secret="fake", testnet=True,
        base_url="https://invalid.example", recv_window=recv_window,
        simple_earn_enabled=True, ai_provider="off",
    ))
    monkeypatch.setattr(app, "fetch_macro_snapshot", lambda: SimpleNamespace(
        data={}, errors=[], sources={},
    ))
    monkeypatch.setattr(app, "_fetch_asset_prices", prices)
    monkeypatch.setattr(app, "_ensure_target_prices", lambda _client, values, *_args: values)
    monkeypatch.setattr(app, "get_adaptive_manager", lambda: None)
    monkeypatch.setattr(app, "_resolve_ai_advice", lambda *_args: SimpleNamespace(
        targets={"USDQ": 1.0}, action="rebalance", rationale=None,
        provider="off", model_failures=(), model_used=None,
    ))
    monkeypatch.setattr(app, "_refresh_openrouter_models_after_failure", lambda *_args: None)
    monkeypatch.setattr(app, "evaluate_cost_gate", lambda **_kwargs: SimpleNamespace(
        status="completed", mode="observe", allowed=True, expected_benefit_bps=None,
        estimated_cost_bps=None, net_benefit_bps=None, reason="synthetic",
    ))
    monkeypatch.setattr(app, "record_portfolio_snapshot", lambda _path, payload:
                        record_portfolio_snapshot(db_path, payload))
    monkeypatch.setattr(app, "_build_shadow_run", lambda **kwargs: None)
    monkeypatch.setattr(app, "observe_shadow_run", forbidden)
    monkeypatch.setattr(app, "_subscribe_simple_earn_balances", forbidden)
    monkeypatch.setattr(app, "filter_dust_positions", lambda snapshot, *_args: (snapshot, {}))
    monkeypatch.setattr(app, "decide_rebalance", lambda *_args: RebalanceDecision(True, {"TEST": 0.5}))
    monkeypatch.setattr(app, "rebalance_has_tradable_orders", lambda **kwargs: True)
    monkeypatch.setattr(app, "build_trades", lambda **kwargs: [object()])
    monkeypatch.setattr(app, "filter_anti_churn_trades", lambda **kwargs: kwargs["trades"])
    monkeypatch.setattr(app, "_redeem_simple_earn_positions", fake_action)
    monkeypatch.setattr(app, "_init_available_balances", lambda *_args: {})
    monkeypatch.setattr(app, "_fetch_fee_reference_prices", lambda *_args: {})
    monkeypatch.setattr(app, "execute_trades", fake_action)
    monkeypatch.setattr(app, "_print_summary", lambda *_args: None)
    args = argparse.Namespace(
        command="rebalance", dry_run=True, profile="moderate", drift=0.01,
        max_slippage=0.003, min_notional=0.0, targets="USDQ=1", quote="USDQ",
        recv_window=5000, config_path=Path("missing.toml"), adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    assert len(balance_calls) == 2
    assert len(final_price_attempts) == (0 if failed_refresh == "balances" else 1)
    assert len(actions) == 1
    if failed_refresh == "earn":
        assert any(step.get("name") == "earn_snapshot"
                   and step.get("status") == "failed"
                   and "synthetic initial earn failure" in step.get("detail", "")
                   for step in steps)
    else:
        assert any(step.get("name") == "final_balances" and step.get("status") == "failed"
                   for step in steps)
    [snapshot] = [item for item in load_portfolio_snapshots(
        db_path, run_id="synthetic-refresh-failure") if item["phase"] == "after"]
    assert snapshot["missing_prices"] == []
    assert snapshot["data_quality"] == "incomplete"
    if failed_refresh != "earn":
        assert any(step.get("status") == "warning"
                   and "incomplete" in step.get("detail", "").lower()
                   and "snapshot" in step.get("detail", "").lower()
                   for step in steps)
    assert any(step.get("name") == "portfolio_snapshot"
               and step.get("status") == "warning"
               and '"phase":"after"' in step.get("detail", "")
               and '"data_quality":"incomplete"' in step.get("detail", "")
               for step in steps)
