from __future__ import annotations

import argparse
from pathlib import Path

import app
from binance_client import Balance, SymbolFilters
from config import EnvSettings
from logging_audit import load_run_detail
from macro_context import MacroSnapshot
from portfolio import AIAdvice


class FakeClient:
    def __init__(self, **_: object) -> None:
        self.closed = False

    def get_account_balances(self) -> list[Balance]:
        return [
            Balance(asset="BTC", free=0.01, locked=0.0),
            Balance(asset="USDT", free=1000.0, locked=0.0),
        ]

    def get_symbol_price(self, symbol: str) -> float:
        return {"BTCUSDT": 50000.0}.get(symbol, 1.0)

    def get_prices(self, symbols=None):
        prices = {
            "BTCUSDT": 50000.0,
            "ETHUSDT": 3000.0,
            "SOLUSDT": 100.0,
            "BNBUSDT": 600.0,
            "AVAXUSDT": 30.0,
            "ADAUSDT": 1.0,
        }
        if symbols:
            return {symbol: prices[symbol] for symbol in symbols if symbol in prices}
        return prices

    def get_exchange_info(self):
        return {
            "BTCUSDT": SymbolFilters(
                symbol="BTCUSDT",
                lot_step=0.00001,
                min_qty=0.00001,
                max_qty=1000.0,
                min_notional=5.0,
                price_tick=0.01,
            )
        }

    def close(self) -> None:
        self.closed = True


def test_rebalance_audits_adaptive_strategy_after_run_start(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", FakeClient)
    monkeypatch.setattr(
        app,
        "load_env_settings",
        lambda recv_window: EnvSettings(
            api_key="key",
            api_secret="secret",
            testnet=False,
            base_url="https://api.binance.com",
            recv_window=recv_window,
            openrouter_api_key="openrouter-key",
            openrouter_models=("broken/primary:free", "working/fallback:free"),
        ),
    )
    monkeypatch.setattr(
        app,
        "fetch_macro_snapshot",
        lambda: MacroSnapshot(
            data={
                "fear_greed": {"value": 25, "classification": "Fear"},
                "btc_24h": {"price_change_percent": -2.0},
                "crypto_global": {"market_cap_change_24h": -1.0},
            },
            errors=[],
        ),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: AIAdvice(
            targets=dict(kwargs["proposed_weights"]),
            action="maintain",
            rationale="test maintain",
        ),
    )

    args = argparse.Namespace(
        command="rebalance",
        dry_run=True,
        profile="moderate",
        drift=0.01,
        max_slippage=0.003,
        min_notional=0.0,
        targets=None,
        quote="USDT",
        recv_window=5000,
        config_path=Path("missing.toml"),
        adaptive=True,
    )

    assert app.run_rebalance(args) == 0
    [run] = app.load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")

    assert detail is not None
    snapshot = detail["run"]["config_snapshot"]
    assert run["profile"] == "conservative"
    assert snapshot["profile"] == "conservative"
    assert snapshot["drift"] == 0.02
    assert snapshot["targets"]["USDT"] > 0.15
    adaptive_step = next(
        step for step in detail["steps"] if step["name"] == "adaptive_strategy"
    )
    assert "slippage=0.45%" in adaptive_step["detail"]
    assert "targets_changed=true" in adaptive_step["detail"]


def test_rebalance_persists_adaptive_strategy_failure(tmp_path: Path, monkeypatch) -> None:
    class BrokenAdaptiveManager:
        def get_market_sentiment(self, *_args, **_kwargs):
            return app.MarketSentiment.FEAR

        def calculate_adaptive_config(self, *_args, **_kwargs):
            raise RuntimeError("adaptive boom")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", FakeClient)
    monkeypatch.setattr(app, "get_adaptive_manager", lambda: BrokenAdaptiveManager())
    monkeypatch.setattr(
        app,
        "fetch_macro_snapshot",
        lambda: MacroSnapshot(
            data={
                "fear_greed": {"value": 25, "classification": "Fear"},
                "btc_24h": {"price_change_percent": -2.0},
                "crypto_global": {"market_cap_change_24h": -1.0},
            },
            errors=[],
        ),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: AIAdvice(
            targets=dict(kwargs["proposed_weights"]),
            action="maintain",
            rationale=None,
        ),
    )

    args = argparse.Namespace(
        command="rebalance",
        dry_run=True,
        profile="moderate",
        drift=0.01,
        max_slippage=0.003,
        min_notional=0.0,
        targets=None,
        quote="USDT",
        recv_window=5000,
        config_path=Path("missing.toml"),
        adaptive=True,
    )

    assert app.run_rebalance(args) == 0
    [run] = app.load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")

    assert detail is not None
    assert detail["run"]["config_snapshot"]["profile"] == "moderate"
    adaptive_step = next(
        step for step in detail["steps"] if step["name"] == "adaptive_strategy"
    )
    assert adaptive_step["status"] == "failed"
    assert adaptive_step["detail"] == "Failed to apply adaptive strategy: adaptive boom"


def test_rebalance_triggers_openrouter_refresh_when_primary_model_fails(
    tmp_path: Path, monkeypatch
) -> None:
    refresh_calls: list[dict[str, object]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", FakeClient)
    monkeypatch.setattr(
        app,
        "load_env_settings",
        lambda recv_window: EnvSettings(
            api_key="key",
            api_secret="secret",
            testnet=False,
            base_url="https://api.binance.com",
            recv_window=recv_window,
            openrouter_api_key="openrouter-key",
            openrouter_models=("broken/primary:free", "working/fallback:free"),
        ),
    )
    monkeypatch.setattr(
        app,
        "fetch_macro_snapshot",
        lambda: MacroSnapshot(
            data={
                "fear_greed": {"value": 50, "classification": "Neutral"},
                "btc_24h": {"price_change_percent": 0.0},
                "crypto_global": {"market_cap_change_24h": 0.0},
            },
            errors=[],
        ),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: AIAdvice(
            targets=dict(kwargs["proposed_weights"]),
            action="maintain",
            rationale="fallback ok",
            model_used="working/fallback:free",
            model_failures=(
                app.AIModelFailure(
                    model="broken/primary:free",
                    error_type="http_404",
                    detail="404",
                    status_code=404,
                ),
            ),
            first_model_failed=True,
        ),
    )
    monkeypatch.setattr(
        app,
        "refresh_openrouter_models",
        lambda **kwargs: refresh_calls.append(kwargs),
    )

    args = argparse.Namespace(
        command="rebalance",
        dry_run=True,
        profile="moderate",
        drift=0.01,
        max_slippage=0.003,
        min_notional=0.0,
        targets=None,
        quote="USDT",
        recv_window=5000,
        config_path=Path("missing.toml"),
        adaptive=False,
    )

    assert app.run_rebalance(args) == 0

    assert refresh_calls
    assert refresh_calls[0]["failed_primary_model"] == "broken/primary:free"
    assert refresh_calls[0]["current_models"][0] == "broken/primary:free"
