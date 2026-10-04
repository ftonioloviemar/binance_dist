"""Best-effort orchestration for public market observations and shadow runs."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from market_candles import (
    DEFAULT_DB_PATH as DEFAULT_MARKET_DB_PATH,
    DEFAULT_DEADLINE_SECONDS,
    collect_market_candles,
)
from market_insights import (
    DEFAULT_DB_PATH as MARKET_INDICATORS_DB_PATH,
    MarketIndicatorSnapshot,
    calculate_market_indicators,
    persist_market_indicators,
)
from shadow_portfolios import (
    DEFAULT_SHADOW_DB_PATH,
    ShadowRun,
    ShadowRunResult,
    simulate_shadow_run,
)


@dataclass(frozen=True, slots=True)
class ShadowObservationResult:
    status: str
    collection_fingerprint: str | None = None
    deadline_exceeded: bool = False
    simulation: ShadowRunResult | None = None
    error: str | None = None


def load_shadow_observation_settings() -> tuple[bool, bool]:
    """Return independent collector/simulator switches, both enabled by default."""
    return (
        _env_bool("MARKET_CANDLE_COLLECTION_ENABLED", default=True),
        _env_bool("SHADOW_PORTFOLIO_SIMULATION_ENABLED", default=True),
    )


def observe_shadow_run(
    run: ShadowRun,
    *,
    assets: Iterable[str],
    collect_enabled: bool,
    simulate_enabled: bool,
    market_db_path: str | Path = MARKET_INDICATORS_DB_PATH,
    candle_db_path: str | Path = DEFAULT_MARKET_DB_PATH,
    shadow_db_path: str | Path = DEFAULT_SHADOW_DB_PATH,
) -> ShadowObservationResult:
    """Collect/persist descriptive data and optionally advance virtual portfolios."""
    if not collect_enabled and not simulate_enabled:
        return ShadowObservationResult(status="disabled")

    indicator_snapshot: MarketIndicatorSnapshot | None = None
    deadline_exceeded = False
    try:
        if collect_enabled:
            collection = collect_market_candles(
                assets,
                db_path=candle_db_path,
                deadline_seconds=DEFAULT_DEADLINE_SECONDS,
            )
            indicator_snapshot = calculate_market_indicators(collection)
            fingerprint = persist_market_indicators(
                indicator_snapshot, db_path=market_db_path
            )
            deadline_exceeded = collection.deadline_exceeded
            vol30 = _btc_vol30(indicator_snapshot)
        else:
            fingerprint = None
            vol30 = load_latest_btc_vol30(db_path=market_db_path)

        if not simulate_enabled:
            return ShadowObservationResult(
                status="collection_only",
                collection_fingerprint=fingerprint,
                deadline_exceeded=deadline_exceeded,
            )

        simulation = simulate_shadow_run(
            replace(
                run,
                btc_vol30=vol30,
                snapshot_complete=run.snapshot_complete and not deadline_exceeded,
            ),
            shadow_db_path=shadow_db_path,
            market_db_path=market_db_path,
        )
        status = (
            "incomplete"
            if deadline_exceeded
            or any(
                policy.status == "incomplete"
                for policy in simulation.policies.values()
            )
            else "completed"
        )
        return ShadowObservationResult(
            status=status,
            collection_fingerprint=fingerprint,
            deadline_exceeded=deadline_exceeded,
            simulation=simulation,
        )
    except Exception as exc:  # Observability must never change the live run result.
        return ShadowObservationResult(
            status="failed",
            collection_fingerprint=(
                indicator_snapshot.input_fingerprint if indicator_snapshot else None
            ),
            deadline_exceeded=deadline_exceeded,
            error=_safe_error(exc),
        )


def load_latest_btc_vol30(
    *, db_path: str | Path = MARKET_INDICATORS_DB_PATH
) -> Decimal | None:
    """Read the latest persisted BTC vol30 without creating a market DB."""
    path = Path(db_path)
    if not path.is_file():
        return None
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=0.25)) as connection:
            row = connection.execute(
                "SELECT payload_json FROM market_indicator_snapshots "
                "WHERE metrics_version = ? ORDER BY observed_at DESC LIMIT 1",
                ("market_metrics_v1",),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        raw = payload["assets"]["BTC"]["metrics"]["vol30"]
        if raw.get("status") != "complete" or raw.get("value") is None:
            return None
        value = Decimal(str(raw["value"]))
        return value if value.is_finite() and value >= 0 else None
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, InvalidOperation):
        return None


def _btc_vol30(snapshot: MarketIndicatorSnapshot) -> Decimal | None:
    indicators = snapshot.assets.get("BTC")
    if indicators is None:
        return None
    metric = indicators.metrics.get("vol30")
    if metric is None or metric.status != "complete" or metric.value is None:
        return None
    return metric.value


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _safe_error(exc: Exception) -> str:
    return " ".join(str(exc).split())[:240] or type(exc).__name__
