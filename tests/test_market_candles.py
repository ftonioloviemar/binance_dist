from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import threading
import sqlite3
import time

import pytest

import market_candles
from market_candles import collect_market_candles


UTC = timezone.utc
AS_OF = datetime(2026, 10, 4, 12, tzinfo=UTC)
DAY_MS = 86_400_000


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def _row(day: int, *, close_ms: int | None = None) -> list[object]:
    open_time = int(datetime(2026, 10, day, tzinfo=UTC).timestamp() * 1000)
    return [
        open_time,
        "10.0",
        "12.0",
        "9.0",
        "11.0",
        "2.5",
        close_ms if close_ms is not None else open_time + DAY_MS - 1,
        "27.5",
        10,
        "1.0",
        "11.0",
        "0",
    ]


def test_collects_allowlisted_usdt_daily_klines_with_official_request_shape(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, object], float]] = []

    def http_get(url: str, *, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse([_row(1), _row(2)])

    result = collect_market_candles(
        ["BTC", "ETH", "SOL", "BNB", "AVAX", "ADA", "XRP"],
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=http_get,
    )

    assert len(calls) == 6
    assert all(url == "https://data-api.binance.vision/api/v3/klines" for url, _, _ in calls)
    assert all(params["interval"] == "1d" and params["limit"] == 92 for _, params, _ in calls)
    assert {params["symbol"] for _, params, _ in calls} == {
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "ADAUSDT"
    }
    assert result.unsupported_assets == ("XRP",)
    assert result.by_asset["BTC"].status == "fresh"
    assert result.by_asset["BTC"].candles[0].close == Decimal("11.0")
    assert result.by_asset["BTC"].candles[0].quote_volume == Decimal("27.5")


def test_deduplicates_requested_assets_and_never_queries_unsupported_assets(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def http_get(_url: str, *, params, timeout):
        calls.append(params["symbol"])
        return FakeResponse([_row(1)])

    result = collect_market_candles(
        ["BTC", "BTC", "XRP", "ETH"],
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=http_get,
    )

    assert calls == ["BTCUSDT", "ETHUSDT"]
    assert result.unsupported_assets == ("XRP",)


def test_accepts_one_asset_string_without_iterating_characters(tmp_path: Path) -> None:
    calls: list[str] = []

    result = collect_market_candles(
        "btc",
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=lambda _url, *, params, timeout: (
            calls.append(params["symbol"]) or FakeResponse([_row(1)])
        ),
    )

    assert calls == ["BTCUSDT"]
    assert result.unsupported_assets == ()


def test_excludes_open_candle_and_close_equal_to_now(tmp_path: Path) -> None:
    cutoff = datetime(2026, 10, 2, 23, 59, 59, 999000, tzinfo=UTC)
    included = _row(1)
    equal_cutoff = _row(2, close_ms=int(cutoff.timestamp() * 1000))
    open_candle = _row(3)

    result = collect_market_candles(
        ["BTC"],
        db_path=tmp_path / "market_insights.db",
        now=cutoff,
        http_get=lambda *_args, **_kwargs: FakeResponse(
            [included, equal_cutoff, open_candle]
        ),
    )

    candles = result.by_asset["BTC"].candles
    assert len(candles) == 1
    assert candles[0].open_time == datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "bad_row",
    [
        [1, "1", "2"],
        ["not-a-timestamp", "1", "2", "0.5", "1", "2", 3, "2"],
        [int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000), "NaN", "2", "0.5", "1", "2", int(datetime(2026, 10, 2, tzinfo=UTC).timestamp() * 1000) - 1, "2"],
    ],
)
def test_malformed_rows_are_not_persisted_or_replaced_with_zero(
    tmp_path: Path, bad_row
) -> None:
    result = collect_market_candles(
        ["BTC"],
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=lambda *_args, **_kwargs: FakeResponse([_row(1), bad_row]),
    )

    source = result.by_asset["BTC"]
    assert source.status == "incomplete"
    assert len(source.candles) == 1
    assert source.candles[0].close == Decimal("11.0")
    assert source.error


def test_preserves_gaps_and_deduplicates_duplicate_open_times(tmp_path: Path) -> None:
    result = collect_market_candles(
        ["BTC"],
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=lambda *_args, **_kwargs: FakeResponse(
            [_row(1), _row(3), _row(3)]
        ),
    )

    candles = result.by_asset["BTC"].candles
    assert [candle.open_time.day for candle in candles] == [1, 3]
    assert result.by_asset["BTC"].status == "incomplete"


def test_same_utc_day_uses_cache_and_next_day_refreshes(tmp_path: Path) -> None:
    db_path = tmp_path / "market_insights.db"
    calls = 0

    def http_get(_url: str, *, params, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse([_row(1), _row(2)])

    first = collect_market_candles(
        ["BTC"], db_path=db_path, now=AS_OF, http_get=http_get
    )
    same_day = collect_market_candles(
        ["BTC"], db_path=db_path, now=AS_OF + timedelta(hours=2), http_get=http_get
    )
    next_day = collect_market_candles(
        ["BTC"], db_path=db_path, now=AS_OF + timedelta(days=1), http_get=http_get
    )

    assert calls == 2
    assert first.by_asset["BTC"].status == "fresh"
    assert same_day.by_asset["BTC"].status == "cached"
    assert next_day.by_asset["BTC"].status == "fresh"
    assert same_day.by_asset["BTC"].candles == first.by_asset["BTC"].candles


def test_failed_refresh_preserves_previous_candles_as_cached(tmp_path: Path) -> None:
    db_path = tmp_path / "market_insights.db"
    calls = 0

    def successful_get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse([_row(1)])

    collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF,
        http_get=successful_get,
    )

    def fail_get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError("offline")

    failed = collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF + timedelta(days=1),
        http_get=fail_get,
    )
    same_day = collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF + timedelta(days=1, hours=2),
        http_get=fail_get,
    )

    source = failed.by_asset["BTC"]
    assert source.status == "cached"
    assert len(source.candles) == 1
    assert "offline" in source.error
    assert same_day.by_asset["BTC"].status == "cached"
    assert calls == 2


def test_empty_response_is_missing_and_does_not_create_zero_candles(
    tmp_path: Path,
) -> None:
    result = collect_market_candles(
        ["BTC"],
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=lambda *_args, **_kwargs: FakeResponse([]),
    )

    assert result.by_asset["BTC"].status == "missing"
    assert result.by_asset["BTC"].candles == ()


@pytest.mark.parametrize("failure", ["http", "json"])
def test_request_and_json_errors_return_quality_evidence(
    tmp_path: Path, failure: str
) -> None:
    def http_get(*_args, **_kwargs):
        if failure == "http":
            raise OSError("upstream unavailable")
        raise ValueError("bad json")

    result = collect_market_candles(
        ["BTC"],
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=http_get,
    )

    assert result.by_asset["BTC"].status == "unavailable"
    assert result.by_asset["BTC"].candles == ()
    assert result.by_asset["BTC"].error


def test_global_deadline_caps_request_timeout_and_starts_no_late_request(
    tmp_path: Path,
) -> None:
    clock = [0.0]
    calls: list[tuple[str, float]] = []

    def http_get(_url: str, *, params, timeout):
        calls.append((params["symbol"], timeout))
        clock[0] += 11.0
        return FakeResponse([_row(1)])

    result = collect_market_candles(
        ["BTC", "ETH", "SOL"],
        db_path=tmp_path / "market_insights.db",
        now=AS_OF,
        http_get=http_get,
        monotonic=lambda: clock[0],
        deadline_seconds=20.0,
    )

    assert [symbol for symbol, _ in calls] == ["BTCUSDT", "ETHUSDT"]
    assert calls[0][1] <= 20.0
    assert calls[1][1] <= 9.0
    assert result.by_asset["SOL"].status == "timeout"
    assert result.deadline_exceeded is True


def test_blocked_transport_cannot_hold_caller_past_deadline(tmp_path: Path) -> None:
    release = threading.Event()
    worker_finished = threading.Event()

    def blocked_get(*_args, **_kwargs):
        release.wait()
        worker_finished.set()
        return FakeResponse([_row(1)])

    db_path = tmp_path / "market_insights.db"
    started = time.monotonic()
    try:
        result = collect_market_candles(
            ["BTC"],
            db_path=db_path,
            now=AS_OF,
            http_get=blocked_get,
            deadline_seconds=0.2,
            request_timeout_seconds=5.0,
        )
    finally:
        release.set()

    assert time.monotonic() - started < 1.0
    assert result.by_asset["BTC"].status == "timeout"
    assert result.deadline_exceeded is True
    assert worker_finished.wait(1.0)
    with sqlite3.connect(db_path) as connection:
        candle_count = connection.execute(
            "SELECT COUNT(*) FROM market_candles"
        ).fetchone()[0]
    assert candle_count == 0


def test_sqlite_failure_returns_quality_evidence_without_raising(tmp_path: Path) -> None:
    db_path_is_directory = tmp_path / "not-a-database"
    db_path_is_directory.mkdir()

    result = collect_market_candles(
        ["BTC"], db_path=db_path_is_directory, now=AS_OF
    )

    assert result.by_asset["BTC"].status == "unavailable"
    assert result.by_asset["BTC"].error


def test_corrupted_database_is_reported_without_resetting_its_contents(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "market_insights.db"
    original = b"not a sqlite database"
    db_path.write_bytes(original)

    result = collect_market_candles(["BTC"], db_path=db_path, now=AS_OF)

    assert result.by_asset["BTC"].status == "unavailable"
    assert db_path.read_bytes() == original


def test_partial_refresh_preserves_older_valid_candles(tmp_path: Path) -> None:
    db_path = tmp_path / "market_insights.db"
    collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF,
        http_get=lambda *_args, **_kwargs: FakeResponse([_row(1), _row(2)]),
    )

    result = collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF + timedelta(days=1),
        http_get=lambda *_args, **_kwargs: FakeResponse([_row(3), [1, "short"]]),
    )

    source = result.by_asset["BTC"]
    assert source.status == "incomplete"
    assert len(source.candles) == 3
    assert source.candles[0].open_time.day == 1
    assert source.candles[-1].open_time.day == 3


def test_deadline_cannot_be_configured_above_twenty_seconds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="20"):
        collect_market_candles(
            ["BTC"],
            db_path=tmp_path / "market_insights.db",
            now=AS_OF,
            deadline_seconds=20.1,
        )


def test_parse_overrun_discards_payload_without_persisting_candles(
    tmp_path: Path, monkeypatch
) -> None:
    clock = [0.0]
    original_parse = market_candles._parse_payload

    def overrun_parse(payload, asset, now):
        result = original_parse(payload, asset, now)
        clock[0] = 20.1
        return result

    monkeypatch.setattr(market_candles, "_parse_payload", overrun_parse)
    db_path = tmp_path / "market_insights.db"
    result = collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF,
        http_get=lambda *_args, **_kwargs: FakeResponse([_row(1)]),
        monotonic=lambda: clock[0],
    )

    with sqlite3.connect(db_path) as connection:
        candle_count = connection.execute(
            "SELECT COUNT(*) FROM market_candles"
        ).fetchone()[0]
    assert result.by_asset["BTC"].status == "timeout"
    assert result.deadline_exceeded is True
    assert candle_count == 0


def test_timeout_consumes_the_utc_day_attempt_and_does_not_retry(
    tmp_path: Path,
) -> None:
    clock = [0.0]
    calls = 0

    def overrun_get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        clock[0] = 20.1
        return FakeResponse([_row(1)])

    db_path = tmp_path / "market_insights.db"
    first = collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF,
        http_get=overrun_get,
        monotonic=lambda: clock[0],
    )
    retry = collect_market_candles(
        ["BTC"],
        db_path=db_path,
        now=AS_OF + timedelta(hours=1),
        http_get=overrun_get,
        monotonic=lambda: clock[0],
    )

    assert first.by_asset["BTC"].status == "timeout"
    assert retry.by_asset["BTC"].status == "timeout"
    assert calls == 1
