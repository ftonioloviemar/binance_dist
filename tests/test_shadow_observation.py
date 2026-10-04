from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

import shadow_observation
from market_candles import CandleCollection
from market_insights import (
    AssetIndicators,
    MarketIndicatorSnapshot,
    MetricObservation,
    persist_market_indicators,
)
from shadow_portfolios import ShadowRun


def _run() -> ShadowRun:
    return ShadowRun(
        session_id="shadow-usdt-v1",
        run_id="run-1",
        observed_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
        quote_asset="USDT",
        spot_balances={"USDT": Decimal("100"), "BTC": Decimal("1")},
        earn_balances={},
        prices={"USDT": Decimal("1"), "BTC": Decimal("100")},
        target_weights={"USDT": Decimal("0.5"), "BTC": Decimal("0.5")},
        drift_threshold=Decimal("0.03"),
        btc_vol30=None,
        symbol_filters={},
    )


def _indicators(vol30: Decimal = Decimal("0.07")) -> MarketIndicatorSnapshot:
    return MarketIndicatorSnapshot(
        collected_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
        metrics_version="market_metrics_v1",
        input_fingerprint="fingerprint",
        assets={
            "BTC": AssetIndicators(
                asset="BTC",
                source_status="fresh",
                latest_open_time=None,
                latest_close_time=None,
                metrics={
                    "vol30": MetricObservation(
                        value=vol30, status="complete", sample_count=31
                    )
                },
            )
        },
        breadth=MetricObservation(value=None, status="insufficient", sample_count=0),
        unsupported_assets=(),
        deadline_exceeded=False,
    )


def test_enabled_observation_persists_indicators_then_simulates(tmp_path, monkeypatch) -> None:
    events: list[str] = []
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        shadow_observation,
        "collect_market_candles",
        lambda assets, **kwargs: (events.append("collect") or CandleCollection({}, (), _run().observed_at)),
    )
    monkeypatch.setattr(
        shadow_observation, "calculate_market_indicators", lambda collection: _indicators()
    )
    monkeypatch.setattr(
        shadow_observation,
        "persist_market_indicators",
        lambda snapshot, **kwargs: events.append("persist"),
    )

    def simulate(run, **kwargs):
        events.append("simulate")
        captured["run"] = run
        return SimpleNamespace(policies={"baseline": SimpleNamespace(status="complete")})

    monkeypatch.setattr(shadow_observation, "simulate_shadow_run", simulate)

    result = shadow_observation.observe_shadow_run(
        _run(),
        assets=("BTC",),
        collect_enabled=True,
        simulate_enabled=True,
        market_db_path=tmp_path / "market.db",
        shadow_db_path=tmp_path / "shadow.db",
    )

    assert events == ["collect", "persist", "simulate"]
    assert result.status == "completed"
    assert captured["run"].btc_vol30 == Decimal("0.07")
    assert not (tmp_path / "performance.db").exists()


def test_observation_persists_virtual_inventory_and_aggregates_separately(
    tmp_path, monkeypatch
) -> None:
    market_db = tmp_path / "market.db"
    shadow_db = tmp_path / "shadow.db"
    monkeypatch.setattr(
        shadow_observation,
        "collect_market_candles",
        lambda *args, **kwargs: CandleCollection({}, (), _run().observed_at),
    )
    monkeypatch.setattr(
        shadow_observation, "calculate_market_indicators", lambda collection: _indicators()
    )

    result = shadow_observation.observe_shadow_run(
        _run(),
        assets=("BTC",),
        collect_enabled=True,
        simulate_enabled=True,
        market_db_path=market_db,
        shadow_db_path=shadow_db,
    )

    assert result.status == "completed"
    assert set(result.simulation.policies) == {
        "hold",
        "baseline",
        "volatility_guard_v1",
    }
    with sqlite3.connect(shadow_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()[0] == 3
        assert connection.execute(
            "SELECT COUNT(*) FROM shadow_completed_runs"
        ).fetchone()[0] == 3
    with sqlite3.connect(market_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM market_indicator_snapshots"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM shadow_policy_observations"
        ).fetchone()[0] == 3
    assert not (tmp_path / "performance.db").exists()


def test_collection_and_simulation_switches_are_independent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        shadow_observation,
        "collect_market_candles",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("collector called")),
    )
    monkeypatch.setattr(
        shadow_observation,
        "load_latest_btc_vol30",
        lambda **kwargs: Decimal("0.04"),
    )
    captured: list[ShadowRun] = []
    monkeypatch.setattr(
        shadow_observation,
        "simulate_shadow_run",
        lambda run, **kwargs: (
            captured.append(run)
            or SimpleNamespace(policies={"baseline": SimpleNamespace(status="complete")})
        ),
    )

    result = shadow_observation.observe_shadow_run(
        _run(),
        assets=("BTC",),
        collect_enabled=False,
        simulate_enabled=True,
        market_db_path=tmp_path / "market.db",
        shadow_db_path=tmp_path / "shadow.db",
    )

    assert result.status == "completed"
    assert captured[0].btc_vol30 == Decimal("0.04")


def test_disabled_simulation_can_collect_without_opening_shadow_db(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        shadow_observation,
        "collect_market_candles",
        lambda *args, **kwargs: (calls.append("collect") or CandleCollection({}, (), _run().observed_at)),
    )
    monkeypatch.setattr(
        shadow_observation, "calculate_market_indicators", lambda collection: _indicators()
    )
    monkeypatch.setattr(
        shadow_observation,
        "persist_market_indicators",
        lambda snapshot, **kwargs: calls.append("persist"),
    )
    monkeypatch.setattr(
        shadow_observation,
        "simulate_shadow_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("simulator called")),
    )

    result = shadow_observation.observe_shadow_run(
        _run(),
        assets=("BTC",),
        collect_enabled=True,
        simulate_enabled=False,
        market_db_path=tmp_path / "market.db",
        shadow_db_path=tmp_path / "shadow.db",
    )

    assert calls == ["collect", "persist"]
    assert result.status == "collection_only"
    assert not (tmp_path / "shadow.db").exists()


def test_optional_collection_failure_does_not_escape_or_run_simulator(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        shadow_observation,
        "collect_market_candles",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr(
        shadow_observation,
        "simulate_shadow_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("simulator called")),
    )

    result = shadow_observation.observe_shadow_run(
        _run(),
        assets=("BTC",),
        collect_enabled=True,
        simulate_enabled=True,
        market_db_path=tmp_path / "market.db",
        shadow_db_path=tmp_path / "shadow.db",
    )

    assert result.status == "failed"
    assert result.error == "offline"


def test_deadline_exceeded_marks_observation_incomplete(tmp_path, monkeypatch) -> None:
    collection = CandleCollection(
        {}, (), _run().observed_at, deadline_exceeded=True
    )
    monkeypatch.setattr(
        shadow_observation,
        "collect_market_candles",
        lambda *args, **kwargs: collection,
    )
    monkeypatch.setattr(
        shadow_observation, "calculate_market_indicators", lambda value: _indicators()
    )
    monkeypatch.setattr(
        shadow_observation, "persist_market_indicators", lambda *args, **kwargs: "fp"
    )
    result = shadow_observation.observe_shadow_run(
        _run(),
        assets=("BTC",),
        collect_enabled=True,
        simulate_enabled=True,
        market_db_path=tmp_path / "market.db",
        shadow_db_path=tmp_path / "shadow.db",
    )

    assert result.status == "incomplete"
    assert result.deadline_exceeded is True
    with sqlite3.connect(tmp_path / "shadow.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM shadow_completed_runs"
        ).fetchone()[0] == 0


def test_cached_vol30_reader_is_read_only_and_does_not_create_missing_db(tmp_path) -> None:
    missing = tmp_path / "missing.db"
    assert shadow_observation.load_latest_btc_vol30(db_path=missing) is None
    assert not missing.exists()

    existing = tmp_path / "market.db"
    persist_market_indicators(_indicators(), db_path=existing)
    assert shadow_observation.load_latest_btc_vol30(db_path=existing) == Decimal("0.07")


def test_environment_switches_default_on_and_parse_independently(monkeypatch) -> None:
    monkeypatch.delenv("MARKET_CANDLE_COLLECTION_ENABLED", raising=False)
    monkeypatch.delenv("SHADOW_PORTFOLIO_SIMULATION_ENABLED", raising=False)
    assert shadow_observation.load_shadow_observation_settings() == (True, True)

    monkeypatch.setenv("MARKET_CANDLE_COLLECTION_ENABLED", "false")
    monkeypatch.setenv("SHADOW_PORTFOLIO_SIMULATION_ENABLED", "true")
    assert shadow_observation.load_shadow_observation_settings() == (False, True)

    monkeypatch.setenv("MARKET_CANDLE_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("SHADOW_PORTFOLIO_SIMULATION_ENABLED", "false")
    assert shadow_observation.load_shadow_observation_settings() == (True, False)
