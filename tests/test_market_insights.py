from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, localcontext

import pytest

from market_candles import (
    SUPPORTED_ASSETS,
    CandleCollection,
    CandleSource,
    MarketCandle,
)
from market_insights import calculate_market_indicators, persist_market_indicators


AS_OF = datetime(2026, 10, 4, 0, 0, 1, tzinfo=UTC)
ONE_MILLISECOND = timedelta(milliseconds=1)


def _candles(
    count: int,
    *,
    asset: str = "BTC",
    descending: bool = False,
    volumes: list[Decimal] | None = None,
    end_open: datetime | None = None,
) -> tuple[MarketCandle, ...]:
    latest_open = end_open or datetime.combine(
        AS_OF.date() - timedelta(days=1), time.min, tzinfo=UTC
    )
    first_open = latest_open - timedelta(days=count - 1)
    result = []
    for index in range(count):
        close = Decimal(200 - index if descending else 100 + index)
        open_time = first_open + timedelta(days=index)
        result.append(
            MarketCandle(
                asset=asset,
                open_time=open_time,
                close_time=open_time + timedelta(days=1) - ONE_MILLISECOND,
                open=close,
                high=close,
                low=close,
                close=close,
                base_volume=Decimal("1"),
                quote_volume=(volumes[index] if volumes else Decimal(index + 1)),
            )
        )
    return tuple(result)


def _collection(
    *,
    count: int = 31,
    by_asset: dict[str, tuple[MarketCandle, ...]] | None = None,
    statuses: dict[str, str] | None = None,
    unsupported_assets: tuple[str, ...] = (),
    collected_at: datetime = AS_OF,
) -> CandleCollection:
    candle_map = by_asset or {
        asset: _candles(count, asset=asset) for asset in SUPPORTED_ASSETS
    }
    statuses = statuses or {}
    sources = {
        asset: CandleSource(
            status=statuses.get(asset, "fresh"), candles=asset_candles
        )
        for asset, asset_candles in candle_map.items()
    }
    return CandleCollection(
        by_asset=sources,
        unsupported_assets=unsupported_assets,
        collected_at=collected_at,
    )


def _metric(snapshot, name: str, asset: str = "BTC"):
    return snapshot.assets[asset].metrics[name]


def _close_enough(actual: Decimal, expected: Decimal) -> None:
    assert abs(actual - expected) < Decimal("1e-24")


def test_calculates_returns_sma_distance_and_relative_quote_volume() -> None:
    snapshot = calculate_market_indicators(_collection(count=31))

    _close_enough(_metric(snapshot, "return_1d").value, Decimal(130) / 129 - 1)
    _close_enough(_metric(snapshot, "return_7d").value, Decimal(130) / 123 - 1)
    _close_enough(_metric(snapshot, "return_30d").value, Decimal(130) / 100 - 1)
    _close_enough(_metric(snapshot, "distance_sma30").value, Decimal(130) / Decimal("115.5") - 1)
    _close_enough(_metric(snapshot, "relative_quote_volume").value, Decimal(2))
    assert all(
        _metric(snapshot, name).status == "complete"
        for name in (
            "return_1d",
            "return_7d",
            "return_30d",
            "distance_sma30",
            "relative_quote_volume",
        )
    )


@pytest.mark.parametrize(
    ("metric_name", "sample_size", "expected"),
    [
        ("return_1d", 2, Decimal(101) / 100 - 1),
        ("return_7d", 8, Decimal(107) / 100 - 1),
        ("return_30d", 31, Decimal(130) / 100 - 1),
    ],
)
def test_returns_use_the_approved_minimum_contiguous_sample(
    metric_name: str, sample_size: int, expected: Decimal
) -> None:
    metric = _metric(
        calculate_market_indicators(_collection(count=sample_size)), metric_name
    )

    assert metric.status == "complete"
    assert metric.sample_count == sample_size
    _close_enough(metric.value, expected)


def test_sma30_includes_latest_close_and_needs_only_30_candles() -> None:
    snapshot = calculate_market_indicators(_collection(count=30))

    sma_distance = _metric(snapshot, "distance_sma30")
    assert sma_distance.status == "complete"
    assert sma_distance.sample_count == 30
    _close_enough(sma_distance.value, Decimal(129) / Decimal("114.5") - 1)
    assert _metric(snapshot, "return_30d").status == "insufficient"


def test_vol30_is_sample_standard_deviation_of_30_log_returns_not_annualized() -> None:
    closes = [Decimal(100 + index) for index in range(31)]
    with localcontext() as context:
        context.prec = 48
        log_returns = [(right / left).ln() for left, right in zip(closes, closes[1:])]
        mean = sum(log_returns) / Decimal(len(log_returns))
        variance = sum((item - mean) ** 2 for item in log_returns) / Decimal(29)
        expected = variance.sqrt()

    metric = _metric(calculate_market_indicators(_collection(count=31)), "vol30")

    assert metric.status == "complete"
    assert metric.sample_count == 31
    _close_enough(metric.value, expected)


def test_insufficient_data_is_null_and_never_coerced_to_zero() -> None:
    snapshot = calculate_market_indicators(_collection(count=7))

    assert _metric(snapshot, "return_1d").value is not None
    assert _metric(snapshot, "return_7d").value is None
    assert _metric(snapshot, "return_7d").status == "insufficient"
    assert _metric(snapshot, "return_30d").value is None
    assert _metric(snapshot, "vol30").value is None
    assert _metric(snapshot, "distance_sma30").value is None
    assert _metric(snapshot, "relative_quote_volume").value is None


def test_gap_only_invalidates_metric_windows_that_cross_it() -> None:
    all_candles = list(_candles(40))
    missing_open = all_candles[15].open_time
    candles_with_gap = tuple(candle for candle in all_candles if candle.open_time != missing_open)
    snapshot = calculate_market_indicators(
        _collection(by_asset={"BTC": candles_with_gap})
    )

    assert _metric(snapshot, "return_1d").status == "complete"
    assert _metric(snapshot, "return_7d").status == "complete"
    for name in (
        "return_30d",
        "vol30",
        "distance_sma30",
        "relative_quote_volume",
    ):
        assert _metric(snapshot, name).value is None
        assert _metric(snapshot, name).status == "gap"


def test_malformed_candle_outside_metric_windows_does_not_invalidate_them() -> None:
    candles = list(_candles(40))
    candles[0] = replace(candles[0], asset="ETH")

    snapshot = calculate_market_indicators(
        _collection(by_asset={"BTC": tuple(candles)})
    )

    for name in (
        "return_1d",
        "return_7d",
        "return_30d",
        "vol30",
        "distance_sma30",
        "relative_quote_volume",
    ):
        assert _metric(snapshot, name).status == "complete"


def test_malformed_candle_invalidates_only_windows_that_include_its_day() -> None:
    candles = list(_candles(40))
    candles[10] = replace(candles[10], asset="ETH")

    snapshot = calculate_market_indicators(
        _collection(by_asset={"BTC": tuple(candles)})
    )

    for name in ("return_1d", "return_7d"):
        assert _metric(snapshot, name).status == "complete"
    for name in (
        "return_30d",
        "vol30",
        "distance_sma30",
        "relative_quote_volume",
    ):
        assert _metric(snapshot, name).value is None
        assert _metric(snapshot, name).status == "invalid"


def test_incomplete_source_can_still_have_valid_per_metric_coverage() -> None:
    snapshot = calculate_market_indicators(
        _collection(count=8, by_asset={"BTC": _candles(8)}, statuses={"BTC": "incomplete"})
    )

    assert snapshot.assets["BTC"].source_status == "incomplete"
    assert _metric(snapshot, "return_7d").status == "complete"
    assert _metric(snapshot, "return_7d").value is not None
    assert _metric(snapshot, "return_30d").status == "insufficient"


def test_open_candle_is_excluded_at_its_utc_close_boundary() -> None:
    prior = _candles(31)
    open_time = datetime.combine(AS_OF.date(), time.min, tzinfo=UTC)
    open_candle = _candles(1, asset="BTC", end_open=open_time)[0]
    snapshot = calculate_market_indicators(
        _collection(
            count=31,
            by_asset={"BTC": prior + (open_candle,)},
            collected_at=open_candle.close_time,
        )
    )

    latest = snapshot.assets["BTC"].latest_close_time
    assert latest == prior[-1].close_time
    _close_enough(_metric(snapshot, "return_1d").value, Decimal(1) / 129)


def test_breadth_requires_six_valid_smas_on_the_same_utc_session() -> None:
    candle_map = {
        asset: _candles(30, asset=asset, descending=index >= 3)
        for index, asset in enumerate(SUPPORTED_ASSETS)
    }
    snapshot = calculate_market_indicators(_collection(by_asset=candle_map))

    assert snapshot.breadth.status == "complete"
    assert snapshot.breadth.sample_count == 6
    assert snapshot.breadth.value == Decimal("0.5")

    older = dict(candle_map)
    older[SUPPORTED_ASSETS[-1]] = _candles(
        30,
        asset=SUPPORTED_ASSETS[-1],
        descending=True,
        end_open=datetime(2026, 10, 2, 0, 0, tzinfo=UTC),
    )
    stale_snapshot = calculate_market_indicators(_collection(by_asset=older))
    assert stale_snapshot.breadth.value is None
    assert stale_snapshot.breadth.status == "incomplete_coverage"


def test_breadth_is_incomplete_for_missing_or_unsupported_universe_assets() -> None:
    candle_map = {
        asset: _candles(30, asset=asset) for asset in SUPPORTED_ASSETS[:-1]
    }
    snapshot = calculate_market_indicators(
        _collection(by_asset=candle_map, unsupported_assets=("DOGE",))
    )

    assert snapshot.breadth.value is None
    assert snapshot.breadth.status == "incomplete_coverage"


def test_source_failure_does_not_emit_zero_or_valid_indicators() -> None:
    snapshot = calculate_market_indicators(
        _collection(by_asset={"BTC": ()}, statuses={"BTC": "unavailable"})
    )

    assert snapshot.assets["BTC"].source_status == "unavailable"
    for metric in snapshot.assets["BTC"].metrics.values():
        assert metric.value is None
        assert metric.status == "source_unavailable"


def test_invalid_collector_source_is_not_mislabeled_as_unavailable() -> None:
    snapshot = calculate_market_indicators(
        _collection(by_asset={"BTC": ()}, statuses={"BTC": "invalid"})
    )

    assert snapshot.assets["BTC"].source_status == "invalid"
    for metric in snapshot.assets["BTC"].metrics.values():
        assert metric.value is None
        assert metric.status == "source_invalid"


def test_undefined_volume_ratio_and_nonpositive_close_are_explicitly_invalid() -> None:
    zero_volumes = _candles(31, volumes=[Decimal("0")] * 31)
    volume_snapshot = calculate_market_indicators(
        _collection(by_asset={"BTC": zero_volumes})
    )
    assert _metric(volume_snapshot, "relative_quote_volume").value is None
    assert _metric(volume_snapshot, "relative_quote_volume").status == "invalid"

    invalid_close = list(_candles(2))
    invalid_close[-1] = replace(invalid_close[-1], close=Decimal("0"))
    price_snapshot = calculate_market_indicators(
        _collection(by_asset={"BTC": tuple(invalid_close)})
    )
    assert _metric(price_snapshot, "return_1d").value is None
    assert _metric(price_snapshot, "return_1d").status == "invalid"


def test_persisted_observation_is_versioned_precise_and_idempotent(tmp_path) -> None:
    collection = _collection(count=31, by_asset={"BTC": _candles(31)})
    snapshot = calculate_market_indicators(collection)
    db_path = tmp_path / "market_insights.db"

    first_id = persist_market_indicators(snapshot, db_path=db_path)
    second_id = persist_market_indicators(snapshot, db_path=db_path)

    assert first_id == second_id == snapshot.input_fingerprint
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT metrics_version, input_fingerprint, payload_json "
            "FROM market_indicator_snapshots"
        ).fetchall()
    assert len(rows) == 1
    metrics_version, fingerprint, payload_json = rows[0]
    payload = json.loads(payload_json)
    assert metrics_version == snapshot.metrics_version
    assert fingerprint == snapshot.input_fingerprint
    saved = payload["assets"]["BTC"]["metrics"]["return_1d"]["value"]
    assert isinstance(saved, str)
    assert Decimal(saved) == _metric(snapshot, "return_1d").value


def test_fingerprint_ignores_collection_time_but_includes_source_quality(tmp_path) -> None:
    candles = {"BTC": _candles(31)}
    fresh = calculate_market_indicators(_collection(by_asset=candles))
    later = calculate_market_indicators(
        _collection(
            by_asset=candles,
            collected_at=AS_OF + timedelta(hours=1),
        )
    )
    cached = calculate_market_indicators(
        _collection(by_asset=candles, statuses={"BTC": "cached"})
    )
    assert fresh.input_fingerprint == later.input_fingerprint
    assert fresh.input_fingerprint != cached.input_fingerprint

    db_path = tmp_path / "market_insights.db"
    persist_market_indicators(fresh, db_path=db_path)
    persist_market_indicators(later, db_path=db_path)
    persist_market_indicators(cached, db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM market_indicator_snapshots"
        ).fetchone()[0]
    assert count == 2


def test_unknown_database_schema_version_fails_closed(tmp_path) -> None:
    db_path = tmp_path / "market_insights.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE market_indicator_metadata "
            "(component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO market_indicator_metadata VALUES ('market_indicators', 999)"
        )

    snapshot = calculate_market_indicators(_collection(count=31))
    with pytest.raises(ValueError, match="schema"):
        persist_market_indicators(snapshot, db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute(
            "SELECT schema_version FROM market_indicator_metadata "
            "WHERE component = 'market_indicators'"
        ).fetchone()[0]
    assert version == 999
