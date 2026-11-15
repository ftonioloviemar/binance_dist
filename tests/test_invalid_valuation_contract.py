from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

import pytest
import requests

import app
from binance_client import Balance, SimpleEarnPosition
from config import EnvSettings
from performance_store import build_portfolio_snapshot, load_portfolio_snapshots, record_portfolio_snapshot
from portfolio import PortfolioError, compute_current_weights


INVALID_PRICES = [None, 0.0, -1.0, float("nan"), float("inf"), -float("inf")]
INVALID_IDS = ["missing", "zero", "negative", "nan", "inf", "negative-inf"]


@pytest.mark.parametrize("price", INVALID_PRICES, ids=INVALID_IDS)
def test_weights_reject_invalid_price_for_positive_holding(price):
    prices = {} if price is None else {"TEST": price}
    with pytest.raises(PortfolioError):
        compute_current_weights(
            [Balance(asset="USDQ", free=10, locked=0), Balance(asset="TEST", free=1, locked=0)],
            prices,
            "USDQ",
        )


def test_weights_accept_quote_and_positive_price():
    snapshot = compute_current_weights(
        [Balance(asset="USDQ", free=10, locked=0), Balance(asset="TEST", free=2, locked=0)],
        {"TEST": 3}, "USDQ",
    )
    assert snapshot.total_value == 16
    assert snapshot.positions["USDQ"].price == 1
    assert snapshot.positions["TEST"].price == 3


@pytest.mark.parametrize("source", ["spot", "earn"])
@pytest.mark.parametrize("price", INVALID_PRICES, ids=INVALID_IDS)
def test_invalid_held_prices_mark_snapshot_incomplete(source, price):
    position = {"asset": "TEST", "quantity": Decimal("2")}
    payload = build_portfolio_snapshot(
        run_id="isolated", phase="before", quote_asset="USDQ",
        spot_balances=[position] if source == "spot" else [],
        earn_positions=[position] if source == "earn" else [],
        prices={} if price is None else {"TEST": price},
        timestamp="2026-01-01T00:00:00Z", data_quality="complete",
    )
    assert payload["data_quality"] == "incomplete"
    assert payload["missing_prices"] == ["TEST"]
    assert f"{source}:TEST" not in payload["asset_values"]


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "live-path-faked"])
@pytest.mark.parametrize("source", ["spot", "earn", "ld-alias"])
@pytest.mark.parametrize("price", INVALID_PRICES, ids=INVALID_IDS)
def test_run_blocks_before_planning_and_persists_incomplete_snapshot(
    monkeypatch, tmp_path, dry_run, source, price
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "isolated-performance.db"
    actions = []
    asset = "LDTEST" if source == "ld-alias" else "TEST"
    balances = [Balance(asset="USDQ", free=10, locked=0)]
    if source != "earn":
        balances.append(Balance(asset=asset, free=1, locked=0))
    earn = []
    if source in ("earn", "ld-alias"):
        earn.append(SimpleEarnPosition(
            product_id="fake", asset="TEST", total_amount=1,
            redeemable_amount=1, can_fast_redeem=True,
        ))

    class Auditor:
        run_id = "isolated"
        def start_run(self, **kwargs): pass
        def log_step(self, **kwargs): pass
        def log_exception(self, **kwargs): pass
        def finalize_run(self, status): pass
        def close(self): pass

    class Client:
        def __init__(self, **kwargs): pass
        def get_account_balances(self): return balances
        def get_simple_earn_flexible_positions(self): return earn
        def get_simple_earn_flexible_products(self): return {}
        def get_exchange_info(self): return {}
        def close(self): pass

    def forbidden(name):
        def call(*args, **kwargs):
            actions.append(name)
            raise AssertionError(f"{name} must not be reached")
        return call

    prices = {"TEST": 3} if source == "ld-alias" else {}
    if price is not None:
        prices[asset] = price
    monkeypatch.setattr(app, "BinanceClient", Client)
    monkeypatch.setattr(app, "AuditLogger", Auditor)
    monkeypatch.setattr(app, "load_env_settings", lambda recv_window: EnvSettings(
        api_key="fake", api_secret="fake", testnet=True,
        base_url="https://invalid.example", recv_window=recv_window,
        simple_earn_enabled=True, ai_provider="off",
    ))
    monkeypatch.setattr(app, "_fetch_asset_prices", lambda *args: prices)
    monkeypatch.setattr(app, "_ensure_target_prices", lambda _client, values, *_args: values)
    monkeypatch.setattr(app, "fetch_macro_snapshot", lambda: app.MacroSnapshot(data={}, errors=[]))
    monkeypatch.setattr(app, "_build_shadow_run", lambda **_kwargs: None)
    monkeypatch.setattr(app, "observe_shadow_run", forbidden("shadow observation"))
    monkeypatch.setattr(
        app, "_resolve_ai_advice",
        lambda _settings, request, _auditor: app.AIAdvice(
            targets=dict(request.proposed_weights), action="redistribute", provider="off"
        ),
    )
    monkeypatch.setattr(app, "_refresh_openrouter_models_after_failure", lambda *_args: None)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden("network request"))
    monkeypatch.setattr(app, "record_portfolio_snapshot", lambda _path, payload: record_portfolio_snapshot(db_path, payload))
    for name in ("build_trades", "_redeem_simple_earn_positions", "_subscribe_simple_earn_balances", "execute_trades"):
        monkeypatch.setattr(app, name, forbidden(name))
    args = argparse.Namespace(
        command="rebalance", dry_run=dry_run, profile="moderate", drift=0.01,
        max_slippage=0.003, min_notional=0.0, targets="USDQ=1", quote="USDQ",
        recv_window=5000, config_path=Path("missing.toml"), adaptive=False,
    )

    assert app.run_rebalance(args) != 0
    assert actions == []
    snapshots = load_portfolio_snapshots(db_path, run_id="isolated")
    [before] = [item for item in snapshots if item["phase"] == "before"]
    assert before["data_quality"] == "incomplete"
    assert asset in before["missing_prices"]
    assert not any(item["phase"] == "after" for item in snapshots)
