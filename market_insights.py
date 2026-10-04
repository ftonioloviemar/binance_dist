from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping

from market_candles import (
    DEFAULT_DB_PATH as CANDLE_DB_PATH,
    SUPPORTED_ASSETS,
    CandleCollection,
    CandleSource,
    MarketCandle,
)


METRICS_VERSION = "market_metrics_v1"
SCHEMA_VERSION = 1
DEFAULT_DB_PATH = CANDLE_DB_PATH
DECIMAL_PRECISION = 48
DAY = timedelta(days=1)
MILLISECOND = timedelta(milliseconds=1)
USABLE_SOURCE_STATUSES = frozenset({"fresh", "cached", "incomplete"})
METRIC_WINDOWS = {
    "return_1d": 2,
    "return_7d": 8,
    "return_30d": 31,
    "vol30": 31,
    "distance_sma30": 30,
    "relative_quote_volume": 31,
}


@dataclass(frozen=True, slots=True)
class MetricObservation:
    value: Decimal | None
    status: str
    sample_count: int
    window_start: datetime | None = None
    window_end: datetime | None = None


@dataclass(frozen=True, slots=True)
class AssetIndicators:
    asset: str
    source_status: str
    latest_open_time: datetime | None
    latest_close_time: datetime | None
    metrics: Mapping[str, MetricObservation]


@dataclass(frozen=True, slots=True)
class MarketIndicatorSnapshot:
    collected_at: datetime
    metrics_version: str
    input_fingerprint: str
    assets: Mapping[str, AssetIndicators]
    breadth: MetricObservation
    unsupported_assets: tuple[str, ...]
    deadline_exceeded: bool


def calculate_market_indicators(
    collection: CandleCollection,
) -> MarketIndicatorSnapshot:
    """Calculate descriptive indicators from closed candles without side effects."""
    collected_at = _as_utc(collection.collected_at, "collected_at")
    assets: dict[str, AssetIndicators] = {}
    canonical_inputs: dict[str, object] = {}

    for asset in SUPPORTED_ASSETS:
        source = collection.by_asset.get(asset)
        source_status = source.status if source is not None else "missing"
        if source_status in USABLE_SOURCE_STATUSES:
            timeline, invalid_input = _prepare_timeline(
                asset, source, collected_at
            )
            metrics = _calculate_asset_metrics(timeline, invalid_input)
        else:
            timeline = {}
            invalid_input = False
            quality_status = (
                "source_invalid"
                if source_status == "invalid"
                else "source_unavailable"
            )
            metrics = _unavailable_metrics(quality_status)

        latest_open = max(timeline) if timeline else None
        latest = timeline.get(latest_open) if latest_open is not None else None
        latest_close_time = latest.close_time if isinstance(latest, MarketCandle) else None
        assets[asset] = AssetIndicators(
            asset=asset,
            source_status=source_status,
            latest_open_time=latest_open,
            latest_close_time=latest_close_time,
            metrics=metrics,
        )
        canonical_inputs[asset] = _canonical_asset_input(
            source_status, timeline, invalid_input
        )

    unsupported_assets = tuple(sorted(set(collection.unsupported_assets)))
    fingerprint = _fingerprint(
        canonical_inputs,
        unsupported_assets,
        collection.deadline_exceeded,
    )
    breadth = _calculate_breadth(assets)
    return MarketIndicatorSnapshot(
        collected_at=collected_at,
        metrics_version=METRICS_VERSION,
        input_fingerprint=fingerprint,
        assets=assets,
        breadth=breadth,
        unsupported_assets=unsupported_assets,
        deadline_exceeded=collection.deadline_exceeded,
    )


def persist_market_indicators(
    snapshot: MarketIndicatorSnapshot,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> str:
    """Persist one deterministic, versioned observation; return its fingerprint."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _snapshot_payload(snapshot)
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    with sqlite3.connect(path) as connection:
        _ensure_indicator_schema(connection)
        connection.execute(
            """
            INSERT OR IGNORE INTO market_indicator_snapshots
                (metrics_version, input_fingerprint, observed_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                snapshot.metrics_version,
                snapshot.input_fingerprint,
                snapshot.collected_at.isoformat(),
                payload_json,
            ),
        )
    return snapshot.input_fingerprint


def _calculate_asset_metrics(
    timeline: Mapping[datetime, MarketCandle | None],
    invalid_input: bool,
) -> dict[str, MetricObservation]:
    metrics: dict[str, MetricObservation] = {}
    windows: dict[str, tuple[MarketCandle, ...] | None] = {}

    for name, sample_size in METRIC_WINDOWS.items():
        status, window, sample_count, start, end = _metric_window(
            timeline, sample_size
        )
        if invalid_input and status != "insufficient":
            status, window = "invalid", None
        windows[name] = window
        value: Decimal | None = None
        if status == "complete" and window is not None:
            value, status = _metric_value(name, window)
        metrics[name] = MetricObservation(
            value=value,
            status=status,
            sample_count=sample_count,
            window_start=start,
            window_end=end,
        )
    return metrics


def _metric_window(
    timeline: Mapping[datetime, MarketCandle | None], sample_size: int
) -> tuple[str, tuple[MarketCandle, ...] | None, int, datetime | None, datetime | None]:
    if not timeline:
        return "insufficient", None, 0, None, None

    latest_open = max(timeline)
    start = latest_open - DAY * (sample_size - 1)
    earliest_open = min(timeline)
    if start < earliest_open:
        trailing_count = _trailing_contiguous_count(timeline)
        return "insufficient", None, min(trailing_count, sample_size), start, latest_open

    expected_opens = tuple(start + DAY * offset for offset in range(sample_size))
    if any(open_time not in timeline for open_time in expected_opens):
        return "gap", None, sample_size, start, latest_open

    values = tuple(timeline[open_time] for open_time in expected_opens)
    if any(candle is None for candle in values):
        return "invalid", None, sample_size, start, latest_open

    candles = tuple(candle for candle in values if candle is not None)
    return "complete", candles, sample_size, start, candles[-1].close_time


def _trailing_contiguous_count(
    timeline: Mapping[datetime, MarketCandle | None],
) -> int:
    if not timeline:
        return 0
    current = max(timeline)
    count = 0
    while current in timeline and timeline[current] is not None:
        count += 1
        current -= DAY
    return count


def _metric_value(
    name: str, candles: tuple[MarketCandle, ...]
) -> tuple[Decimal | None, str]:
    if any(not candle.close.is_finite() or candle.close <= 0 for candle in candles):
        return None, "invalid"

    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        if name.startswith("return_"):
            return candles[-1].close / candles[0].close - 1, "complete"
        if name == "distance_sma30":
            sma = sum((candle.close for candle in candles), Decimal(0)) / Decimal(30)
            return candles[-1].close / sma - 1, "complete"
        if name == "relative_quote_volume":
            volumes = tuple(candle.quote_volume for candle in candles)
            if any(not volume.is_finite() or volume < 0 for volume in volumes):
                return None, "invalid"
            baseline = sum(volumes[:-1], Decimal(0)) / Decimal(30)
            if baseline <= 0:
                return None, "invalid"
            return volumes[-1] / baseline, "complete"
        if name == "vol30":
            returns = tuple(
                (right.close / left.close).ln()
                for left, right in zip(candles, candles[1:])
            )
            mean = sum(returns, Decimal(0)) / Decimal(len(returns))
            variance = sum(
                ((item - mean) ** 2 for item in returns), Decimal(0)
            ) / Decimal(len(returns) - 1)
            return variance.sqrt(), "complete"
    raise ValueError(f"Unknown market metric: {name}")


def _prepare_timeline(
    asset: str,
    source: CandleSource,
    collected_at: datetime,
) -> tuple[dict[datetime, MarketCandle | None], bool]:
    timeline: dict[datetime, MarketCandle | None] = {}
    invalid_input = False
    for candle in source.candles:
        try:
            open_time = _as_utc(candle.open_time, "candle.open_time")
            close_time = _as_utc(candle.close_time, "candle.close_time")
        except (AttributeError, TypeError, ValueError):
            invalid_input = True
            continue
        if close_time >= collected_at:
            continue
        expected_open_time = open_time.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if (
            candle.asset != asset
            or open_time != expected_open_time
            or close_time != open_time + DAY - MILLISECOND
        ):
            timeline[expected_open_time] = None
            continue
        if open_time in timeline:
            timeline[open_time] = None
        else:
            timeline[open_time] = candle
    return timeline, invalid_input


def _calculate_breadth(assets: Mapping[str, AssetIndicators]) -> MetricObservation:
    sma_metrics = [assets[asset].metrics["distance_sma30"] for asset in SUPPORTED_ASSETS]
    session_times = [assets[asset].latest_open_time for asset in SUPPORTED_ASSETS]
    if (
        any(metric.status != "complete" or metric.value is None for metric in sma_metrics)
        or any(session is None for session in session_times)
        or len(set(session_times)) != 1
    ):
        return MetricObservation(
            value=None,
            status="incomplete_coverage",
            sample_count=sum(metric.status == "complete" for metric in sma_metrics),
            window_end=None,
        )
    above = sum(metric.value > 0 for metric in sma_metrics if metric.value is not None)
    return MetricObservation(
        value=Decimal(above) / Decimal(len(SUPPORTED_ASSETS)),
        status="complete",
        sample_count=len(SUPPORTED_ASSETS),
        window_end=assets[SUPPORTED_ASSETS[0]].latest_close_time,
    )


def _unavailable_metrics(status: str) -> dict[str, MetricObservation]:
    return {
        name: MetricObservation(None, status, 0) for name in METRIC_WINDOWS
    }


def _canonical_asset_input(
    source_status: str,
    timeline: Mapping[datetime, MarketCandle | None],
    invalid_input: bool,
) -> dict[str, object]:
    if not timeline:
        candles: list[MarketCandle | None] = []
    else:
        latest_open = max(timeline)
        first_open = latest_open - DAY * 30
        candles = [
            timeline[open_time]
            for open_time in sorted(timeline)
            if first_open <= open_time <= latest_open
        ]
    return {
        "source_status": source_status,
        "invalid_input": invalid_input,
        "candles": [
            None
            if candle is None
            else [
                _iso(candle.open_time),
                _iso(candle.close_time),
                _decimal_string(candle.close),
                _decimal_string(candle.quote_volume),
            ]
            for candle in candles
        ],
    }


def _fingerprint(
    canonical_inputs: Mapping[str, object],
    unsupported_assets: tuple[str, ...],
    deadline_exceeded: bool,
) -> str:
    payload = {
        "metrics_version": METRICS_VERSION,
        "assets": canonical_inputs,
        "unsupported_assets": unsupported_assets,
        "deadline_exceeded": deadline_exceeded,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_payload(snapshot: MarketIndicatorSnapshot) -> dict[str, object]:
    return {
        "observed_at": _iso(snapshot.collected_at),
        "unsupported_assets": list(snapshot.unsupported_assets),
        "deadline_exceeded": snapshot.deadline_exceeded,
        "breadth": _metric_payload(snapshot.breadth),
        "assets": {
            asset: {
                "source_status": indicators.source_status,
                "latest_open_time": _iso(indicators.latest_open_time),
                "latest_close_time": _iso(indicators.latest_close_time),
                "metrics": {
                    name: _metric_payload(metric)
                    for name, metric in indicators.metrics.items()
                },
            }
            for asset, indicators in snapshot.assets.items()
        },
    }


def _metric_payload(metric: MetricObservation) -> dict[str, object]:
    return {
        "value": _decimal_string(metric.value) if metric.value is not None else None,
        "status": metric.status,
        "sample_count": metric.sample_count,
        "window_start": _iso(metric.window_start),
        "window_end": _iso(metric.window_end),
    }


def _ensure_indicator_schema(connection: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    metadata_exists = "market_indicator_metadata" in tables
    snapshots_exist = "market_indicator_snapshots" in tables

    if not metadata_exists and snapshots_exist:
        raise ValueError("Market indicator database has no schema version")

    if metadata_exists:
        version_row = connection.execute(
            "SELECT schema_version FROM market_indicator_metadata "
            "WHERE component = 'market_indicators'"
        ).fetchone()
        if version_row is None or version_row[0] != SCHEMA_VERSION:
            version = "missing" if version_row is None else version_row[0]
            raise ValueError(f"Unsupported market indicator schema version: {version}")
        if not snapshots_exist:
            raise ValueError("Market indicator schema is missing its snapshots table")
        return

    connection.execute(
        """
        CREATE TABLE market_indicator_metadata (
            component TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE market_indicator_snapshots (
            metrics_version TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (metrics_version, input_fingerprint)
        )
        """
    )
    connection.execute(
        "INSERT INTO market_indicator_metadata (component, schema_version) "
        "VALUES ('market_indicators', ?)",
        (SCHEMA_VERSION,),
    )


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _decimal_string(value: Decimal) -> str:
    return format(value, "f")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
