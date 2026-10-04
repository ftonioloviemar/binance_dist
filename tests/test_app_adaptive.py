from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import app
from binance_client import Balance, SymbolFilters
from config import EnvSettings
from logging_audit import AuditLogger, load_run_detail
from macro_context import MacroSnapshot
from portfolio import AIAdvice


@pytest.fixture(autouse=True)
def _disable_shadow_observation_in_app_tests(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_CANDLE_COLLECTION_ENABLED", "false")
    monkeypatch.setenv("SHADOW_PORTFOLIO_SIMULATION_ENABLED", "false")
    observed_instances: set[int] = set()
    original_log_step = AuditLogger.log_step
    original_finalize_run = AuditLogger.finalize_run

    def track_step(self, *args, **kwargs):
        if kwargs.get("name") == "market_insights_observation":
            observed_instances.add(id(self))
        return original_log_step(self, *args, **kwargs)

    def require_shadow_step(self, status):
        assert id(self) in observed_instances
        observed_instances.discard(id(self))
        return original_finalize_run(self, status)

    monkeypatch.setattr(AuditLogger, "log_step", track_step)
    monkeypatch.setattr(AuditLogger, "finalize_run", require_shadow_step)


def _macro_sources(now: datetime | None = None, *, coingecko_status: str = "fresh"):
    current = now or datetime.now(timezone.utc)

    def iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "fear_greed": {
            "status": "fresh",
            "observed_at": iso(current - timedelta(minutes=5)),
            "collected_at": iso(current),
            "age_seconds": 300.0,
            "cache_used": False,
            "error": None,
        },
        "btc_24h": {
            "status": "fresh",
            "observed_at": None,
            "collected_at": iso(current - timedelta(seconds=30)),
            "age_seconds": 0.0,
            "cache_used": False,
            "error": None,
        },
        "crypto_global": {
            "status": coingecko_status,
            "observed_at": None,
            "collected_at": iso(current) if coingecko_status == "fresh" else None,
            "age_seconds": 0.0 if coingecko_status == "fresh" else None,
            "cache_used": coingecko_status == "cached",
            "error": None if coingecko_status == "fresh" else "request timeout",
        },
    }


def _valid_adaptive_snapshot(now: datetime) -> MacroSnapshot:
    return MacroSnapshot(
        data={
            "fear_greed": {"value": 55, "classification": "Neutral"},
            "btc_24h": {"price": 60000.0, "price_change_percent": -11.0},
            "crypto_global": {"market_cap_change_24h": -1.0},
        },
        errors=[],
        sources=_macro_sources(now),
    )


def test_adaptive_sources_require_complete_fresh_required_feeds() -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    snapshot = _valid_adaptive_snapshot(now)

    assessment = app._assess_adaptive_sources(snapshot, now=now)

    assert assessment.quality == "full"
    assert assessment.market_cap_change_24h == -1.0
    assert assessment.btc_change_24h == -11.0


@pytest.mark.parametrize("coingecko_status", ["cached", "missing", "invalid"])
def test_optional_coingecko_quality_degrades_without_disabling_adaptive(
    coingecko_status: str,
) -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    snapshot = _valid_adaptive_snapshot(now)
    snapshot.sources["crypto_global"]["status"] = coingecko_status
    snapshot.sources["crypto_global"]["cache_used"] = coingecko_status == "cached"

    assessment = app._assess_adaptive_sources(snapshot, now=now)

    assert assessment.quality == "degraded"
    assert assessment.market_cap_change_24h is None
    assert assessment.btc_change_24h == -11.0


def test_legacy_snapshot_without_source_metadata_fails_closed() -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    snapshot = MacroSnapshot(
        data={
            "fear_greed": {"value": 55, "classification": "Neutral"},
            "btc_24h": {"price": 60000.0, "price_change_percent": 1.0},
        },
        errors=[],
    )

    assessment = app._assess_adaptive_sources(snapshot, now=now)

    assert assessment.quality == "unavailable"
    assert "fear_greed" in assessment.reason


def test_non_finite_conversion_of_large_integer_is_rejected() -> None:
    assert app._finite_market_number(10**10000) is None


def test_overflowing_optional_cap_signal_degrades_without_blocking_adaptive() -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    snapshot = _valid_adaptive_snapshot(now)
    snapshot.data["crypto_global"]["market_cap_change_24h"] = 10**10000

    assessment = app._assess_adaptive_sources(snapshot, now=now)

    assert assessment.quality == "degraded"
    assert assessment.market_cap_change_24h is None


def test_adaptive_freshness_accepts_limits_and_rejects_older_or_future_sources() -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    snapshot = _valid_adaptive_snapshot(now)
    snapshot.sources["fear_greed"]["observed_at"] = (
        now - timedelta(hours=36)
    ).isoformat().replace("+00:00", "Z")
    snapshot.sources["btc_24h"]["collected_at"] = (
        now - timedelta(minutes=15)
    ).isoformat().replace("+00:00", "Z")
    assert app._assess_adaptive_sources(snapshot, now=now).quality == "full"

    snapshot.sources["fear_greed"]["observed_at"] = (
        now - timedelta(hours=36, seconds=1)
    ).isoformat().replace("+00:00", "Z")
    assert app._assess_adaptive_sources(snapshot, now=now).quality == "unavailable"

    snapshot = _valid_adaptive_snapshot(now)
    snapshot.sources["btc_24h"]["collected_at"] = (
        now + timedelta(seconds=1)
    ).isoformat().replace("+00:00", "Z")
    assert app._assess_adaptive_sources(snapshot, now=now).quality == "unavailable"


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", True),
        ("value", 101),
        ("value", 55.5),
        ("classification", ""),
    ],
)
def test_invalid_required_source_values_fail_closed(field: str, value: object) -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    snapshot = _valid_adaptive_snapshot(now)
    snapshot.data["fear_greed"][field] = value

    assessment = app._assess_adaptive_sources(snapshot, now=now)

    assert assessment.quality == "unavailable"
    assert "fear_greed" in assessment.reason


def test_adaptive_manager_preserves_btc_guard_without_global_cap_signal() -> None:
    manager = app.get_adaptive_manager()
    conservative = manager.calculate_adaptive_config(
        current_sentiment=app.MarketSentiment.GREED,
        btc_change_24h=-11.0,
        market_cap_change_24h=None,
        current_profile="moderate",
    )
    unchanged = manager.calculate_adaptive_config(
        current_sentiment=app.MarketSentiment.GREED,
        btc_change_24h=-2.0,
        market_cap_change_24h=None,
        current_profile="moderate",
    )

    assert conservative.profile.value == "conservative"
    assert unchanged.profile.value == "moderate"


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


class LowNotionalClient(FakeClient):
    def get_account_balances(self) -> list[Balance]:
        return [
            Balance(asset="BTC", free=0.51, locked=0.0),
            Balance(asset="USDT", free=49.0, locked=0.0),
        ]

    def get_symbol_price(self, symbol: str) -> float:
        return {"BTCUSDT": 100.0}.get(symbol, 1.0)

    def get_prices(self, symbols=None):
        prices = {"BTCUSDT": 100.0}
        if symbols:
            return {symbol: prices[symbol] for symbol in symbols if symbol in prices}
        return prices

    def get_exchange_info(self):
        return {
            "BTCUSDT": SymbolFilters(
                symbol="BTCUSDT",
                lot_step=0.0001,
                min_qty=0.0001,
                max_qty=1000.0,
                min_notional=5.0,
                price_tick=0.01,
            )
        }


class LotFloorClient(FakeClient):
    def get_account_balances(self) -> list[Balance]:
        return [
            Balance(asset="BTC", free=0.45, locked=0.0),
            Balance(asset="USDT", free=55.0, locked=0.0),
        ]

    def get_symbol_price(self, symbol: str) -> float:
        return {"BTCUSDT": 100.0}.get(symbol, 1.0)

    def get_prices(self, symbols=None):
        prices = {"BTCUSDT": 100.0}
        if symbols:
            return {symbol: prices[symbol] for symbol in symbols if symbol in prices}
        return prices

    def get_exchange_info(self):
        return {
            "BTCUSDT": SymbolFilters(
                symbol="BTCUSDT",
                lot_step=0.1,
                min_qty=0.1,
                max_qty=1000.0,
                min_notional=5.0,
                price_tick=0.01,
            )
        }


class MaintainSkipClient(FakeClient):
    def get_account_balances(self) -> list[Balance]:
        return [
            Balance(asset="BTC", free=0.51, locked=0.0),
            Balance(asset="USDT", free=49.0, locked=0.0),
        ]

    def get_symbol_price(self, symbol: str) -> float:
        return {"BTCUSDT": 100.0}.get(symbol, 1.0)

    def get_prices(self, symbols=None):
        prices = {"BTCUSDT": 100.0}
        if symbols:
            return {symbol: prices[symbol] for symbol in symbols if symbol in prices}
        return prices

    def get_exchange_info(self):
        return {
            "BTCUSDT": SymbolFilters(
                symbol="BTCUSDT",
                lot_step=0.1,
                min_qty=0.1,
                max_qty=1000.0,
                min_notional=5.0,
                price_tick=0.01,
            )
        }


class MaintainOverrideClient(FakeClient):
    def get_account_balances(self) -> list[Balance]:
        return [
            Balance(asset="BTC", free=0.6, locked=0.0),
            Balance(asset="USDT", free=40.0, locked=0.0),
        ]

    def get_symbol_price(self, symbol: str) -> float:
        return {"BTCUSDT": 100.0}.get(symbol, 1.0)

    def get_prices(self, symbols=None):
        prices = {"BTCUSDT": 100.0}
        if symbols:
            return {symbol: prices[symbol] for symbol in symbols if symbol in prices}
        return prices

    def get_exchange_info(self):
        return {
            "BTCUSDT": SymbolFilters(
                symbol="BTCUSDT",
                lot_step=0.1,
                min_qty=0.1,
                max_qty=1000.0,
                min_notional=5.0,
                price_tick=0.01,
            )
        }


class SmallOppositeTradeClient(MaintainOverrideClient):
    def get_account_balances(self) -> list[Balance]:
        return [
            Balance(asset="BTC", free=5.15, locked=0.0),
            Balance(asset="USDT", free=485.0, locked=0.0),
        ]


@pytest.mark.parametrize(
    "coingecko_status,errors,source_quality,explicit_targets",
    [
        ("fresh", [], "full", None),
        ("cached", ["coingecko: request timeout"], "degraded", None),
        (
            "missing",
            ["coingecko: request timeout"],
            "degraded",
            "btc=0.4,eth=0.2,sol=0.15,usdt=0.15,bnb=0.033,avax=0.033,ada=0.034",
        ),
    ],
)
def test_rebalance_audits_adaptive_strategy_after_run_start(
    tmp_path: Path,
    monkeypatch,
    coingecko_status: str,
    errors: list[str],
    source_quality: str,
    explicit_targets: str | None,
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
                "btc_24h": {"price": 60000.0, "price_change_percent": -2.0},
                "crypto_global": {"market_cap_change_24h": -1.0},
            },
            errors=errors,
            sources=_macro_sources(coingecko_status=coingecko_status),
        ),
    )
    ai_calls = []
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: (
            ai_calls.append(kwargs)
            or AIAdvice(
                targets=dict(kwargs["proposed_weights"]),
                action="maintain",
                rationale="test maintain",
            )
        ),
    )
    monkeypatch.setenv("MARKET_CANDLE_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("SHADOW_PORTFOLIO_SIMULATION_ENABLED", "true")
    captured_shadow_runs = []
    monkeypatch.setattr(
        app,
        "observe_shadow_run",
        lambda run, **kwargs: (
            captured_shadow_runs.append((run, kwargs))
            or SimpleNamespace(
                status="completed", deadline_exceeded=False, error=None
            )
        ),
    )

    args = argparse.Namespace(
        command="rebalance",
        dry_run=True,
        profile="moderate",
        drift=0.01,
        max_slippage=0.003,
        min_notional=0.0,
        targets=explicit_targets,
        quote="USDT",
        recv_window=5000,
        config_path=Path("missing.toml"),
        adaptive=True,
    )

    assert app.run_rebalance(args) == 0
    assert len(ai_calls) == 1
    [run] = app.load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")

    assert detail is not None
    assert len(captured_shadow_runs) == 1
    shadow_run, shadow_kwargs = captured_shadow_runs[0]
    assert shadow_run.session_id == "shadow-usdt-v1"
    assert shadow_run.run_id == run["run_id"]
    assert shadow_run.quote_asset == "USDT"
    assert shadow_run.spot_balances
    assert shadow_kwargs["collect_enabled"] is True
    assert shadow_kwargs["simulate_enabled"] is True
    snapshot = detail["run"]["config_snapshot"]
    assert run["profile"] == "conservative"
    assert snapshot["profile"] == "conservative"
    assert snapshot["drift"] == 0.02
    if explicit_targets is None:
        assert snapshot["targets"]["USDT"] > 0.15
    else:
        assert snapshot["targets"] == pytest.approx(
            {"BTC": 0.4, "ETH": 0.2, "SOL": 0.15, "USDT": 0.15,
             "BNB": 0.033, "AVAX": 0.033, "ADA": 0.034}
        )
    adaptive_step = next(
        step for step in detail["steps"] if step["name"] == "adaptive_strategy"
    )
    shadow_step = next(
        step for step in detail["steps"] if step["name"] == "market_insights_observation"
    )
    assert shadow_step["status"] in {"completed", "incomplete", "warning", "skipped"}
    assert "slippage=0.45%" in adaptive_step["detail"]
    assert f"source_quality={source_quality}" in adaptive_step["detail"]
    if explicit_targets is not None:
        assert "targets_changed=false" in adaptive_step["detail"]
    else:
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
                "btc_24h": {"price": 60000.0, "price_change_percent": -2.0},
                "crypto_global": {"market_cap_change_24h": -1.0},
            },
            errors=[],
            sources=_macro_sources(),
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


@pytest.mark.parametrize("source_case", ["stale", "legacy", "overflow"])
def test_rebalance_fails_closed_when_required_macro_source_is_untrusted(
    tmp_path: Path, monkeypatch, source_case: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", FakeClient)
    sources = _macro_sources()
    if source_case == "stale":
        sources["fear_greed"]["status"] = "cached"
    btc_price = 10**10000 if source_case == "overflow" else 100.0
    monkeypatch.setattr(
        app,
        "fetch_macro_snapshot",
        lambda: MacroSnapshot(
            data={
                "fear_greed": {"value": 25, "classification": "Fear"},
                "btc_24h": {"price": btc_price, "price_change_percent": -2.0},
            },
            errors=[],
            sources=sources if source_case != "legacy" else {},
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
        drift=0.037,
        max_slippage=0.006,
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
    assert run["profile"] == "moderate"
    assert snapshot["profile"] == "moderate"
    assert snapshot["drift"] == pytest.approx(0.037)
    assert snapshot["max_slippage"] == pytest.approx(0.006)
    expected_targets = app.validate_target_map(
        app.expand_buckets(
            app.select_profile_targets("moderate"),
            app.load_bucket_config(Path("missing.toml")),
        )
    )
    assert snapshot["targets"] == expected_targets
    adaptive_step = next(
        step for step in detail["steps"] if step["name"] == "adaptive_strategy"
    )
    assert adaptive_step["status"] == "warning"
    if source_case == "stale":
        assert "required source is not fresh" in adaptive_step["detail"]
    elif source_case == "legacy":
        assert "status=unknown" in adaptive_step["detail"]
    else:
        assert "price or change is missing/invalid" in adaptive_step["detail"]


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


def test_rebalance_skips_failed_final_balances_refresh_in_dry_run(
    tmp_path: Path, monkeypatch
) -> None:
    class EmptyFinalBalancesClient(FakeClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self._balance_calls = 0

        def get_account_balances(self) -> list[Balance]:
            self._balance_calls += 1
            if self._balance_calls == 1:
                return super().get_account_balances()
            return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", EmptyFinalBalancesClient)
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
            openrouter_models=("working/model:free",),
        ),
    )
    monkeypatch.setattr(
        app,
        "fetch_macro_snapshot",
        lambda: MacroSnapshot(
            data={
                "fear_greed": {"value": 25, "classification": "Fear"},
                "btc_24h": {"price": 60000.0, "price_change_percent": -2.0},
                "crypto_global": {"market_cap_change_24h": -1.0},
            },
            errors=[],
            sources=_macro_sources(),
        ),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: AIAdvice(
            targets={"BTC": 0.1, "USDT": 0.9},
            action="redistribute",
            rationale="test redistribute",
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
    final_step = next(
        step for step in detail["steps"] if step["name"] == "final_balances"
    )
    assert final_step["status"] == "skipped"
    assert "empty portfolio" in final_step["detail"].lower()
    assert run["status"] == "completed"


def test_rebalance_skips_when_drift_is_not_tradable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", LowNotionalClient)
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
            openrouter_models=("working/model:free",),
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
            targets={"BTC": 0.55, "USDT": 0.45},
            action="redistribute",
            rationale="test redistribute",
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
        adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    [run] = app.load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")

    assert detail is not None
    assert detail["run"]["status"] == "skipped"
    trade_floor_step = next(
        step for step in detail["steps"] if step["name"] == "trade_floor"
    )
    assert "tradable" in trade_floor_step["detail"].lower()


def test_rebalance_logs_trade_floor_when_drift_is_below_executable_floor(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", LotFloorClient)
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
            openrouter_models=("working/model:free",),
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
            targets={"BTC": 0.51, "USDT": 0.49},
            action="redistribute",
            rationale="test redistribute",
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
        adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    [run] = app.load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")

    assert detail is not None
    assert detail["run"]["status"] == "skipped"
    floor_step = next(step for step in detail["steps"] if step["name"] == "trade_floor")
    assert "floors:" in floor_step["detail"]
    assert "BTC>=10.0000" in floor_step["detail"]


def test_rebalance_maintain_can_skip_when_drift_is_not_actionable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", MaintainSkipClient)
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
            openrouter_models=("working/model:free",),
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
            targets={"BTC": 0.52, "USDT": 0.48},
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
        adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    [run] = app.load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")

    assert detail is not None
    assert detail["run"]["status"] == "skipped"


def test_rebalance_maintain_does_not_suppress_actionable_drift(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "BinanceClient", MaintainOverrideClient)
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
            openrouter_models=("working/model:free",),
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
            targets={"BTC": 0.4, "USDT": 0.6},
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
        adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    [run] = app.load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")

    assert detail is not None
    assert detail["run"]["status"] == "completed"
    assert any(step["name"] == "rebalance_check" for step in detail["steps"])


def test_rebalance_blocks_opposite_side_trade_inside_anti_churn_cooldown(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    prior_time = datetime.now().astimezone() - timedelta(hours=1)
    (logs_dir / "20260801.log").write_text(
        "\n".join(
            [
                f"{prior_time.isoformat()} | run_start | run_id=prior | status=started | profile=moderate | dry_run=false",
                f"{prior_time.isoformat()} | order | run_id=prior | status=FILLED | symbol=BTCUSDT | side=BUY | quantity=0.1 | price=100.0 | detail=prior",
                f"{prior_time.isoformat()} | run_end | run_id=prior | status=completed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "BinanceClient", SmallOppositeTradeClient)
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
            openrouter_models=("working/model:free",),
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
            targets={"BTC": 0.5, "USDT": 0.5},
            action="redistribute",
            rationale="test redistribute",
        ),
    )

    def fail_execute_trades(**_: object) -> None:
        raise AssertionError("execute_trades should not run when anti-churn blocks all trades")

    monkeypatch.setattr(app, "execute_trades", fail_execute_trades)

    args = argparse.Namespace(
        command="rebalance",
        dry_run=True,
        profile="moderate",
        drift=0.01,
        max_slippage=0.003,
        min_notional=0.0,
        min_notional_uplift_tolerance=0.0,
        anti_churn_cooldown_hours=12.0,
        anti_churn_override_multiplier=2.0,
        targets=None,
        quote="USDT",
        recv_window=5000,
        config_path=Path("missing.toml"),
        adaptive=False,
    )

    assert app.run_rebalance(args) == 0
    [run] = app.load_recent_runs(limit=1, logs_dir=logs_dir)
    detail = load_run_detail(run["run_id"], logs_dir=logs_dir)

    assert detail is not None
    assert detail["run"]["status"] == "skipped"
    anti_churn_step = next(step for step in detail["steps"] if step["name"] == "anti_churn")
    assert anti_churn_step["detail"] == "Blocked 1 opposite-side trade(s)"
