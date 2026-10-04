"""Bounded, public-only collection of closed Binance Spot daily candles."""

from __future__ import annotations

import sqlite3
import queue
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Mapping

import requests


SUPPORTED_ASSETS = ("BTC", "ETH", "SOL", "BNB", "AVAX", "ADA")
KLINES_ENDPOINT = "https://data-api.binance.vision/api/v3/klines"
KLINE_INTERVAL = "1d"
KLINE_LIMIT = 92
DAY_MS = 86_400_000
DEFAULT_DEADLINE_SECONDS = 20.0
MAX_DEADLINE_SECONDS = 20.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_DB_PATH = Path("state/market_insights.db")


@dataclass(frozen=True, slots=True)
class MarketCandle:
    asset: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal


@dataclass(frozen=True, slots=True)
class CandleSource:
    status: str
    candles: tuple[MarketCandle, ...] = ()
    error: str | None = None
    refreshed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CandleCollection:
    by_asset: Mapping[str, CandleSource]
    unsupported_assets: tuple[str, ...]
    collected_at: datetime
    deadline_exceeded: bool = False


def collect_market_candles(
    assets: Iterable[str] | None = None,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    now: datetime | None = None,
    http_get: Callable[..., object] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> CandleCollection:
    """Fetch/cache at most six supported assets without using trading APIs."""
    collected_at = now or datetime.now(timezone.utc)
    if collected_at.tzinfo is None or collected_at.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("now must be timezone-aware UTC")
    collected_at = collected_at.astimezone(timezone.utc)
    if assets is None:
        requested = SUPPORTED_ASSETS
    elif isinstance(assets, str):
        requested = (assets,)
    else:
        requested = tuple(assets)
    unique: list[str] = []
    unsupported: list[str] = []
    for raw_asset in requested:
        asset = raw_asset.strip().upper() if isinstance(raw_asset, str) else ""
        if asset not in SUPPORTED_ASSETS:
            if asset and asset not in unsupported:
                unsupported.append(asset)
            continue
        if asset not in unique:
            unique.append(asset)
    if len(unique) > len(SUPPORTED_ASSETS):
        unsupported.extend(unique[len(SUPPORTED_ASSETS) :])
        unique = unique[: len(SUPPORTED_ASSETS)]

    if deadline_seconds <= 0 or deadline_seconds > MAX_DEADLINE_SECONDS:
        raise ValueError("deadline must be positive and no greater than 20 seconds")
    if request_timeout_seconds <= 0:
        raise ValueError("request timeout must be positive")
    deadline = monotonic() + deadline_seconds
    get = http_get or requests.get
    results: dict[str, CandleSource] = {}

    try:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path, timeout=min(0.25, deadline_seconds)) as connection:
            _ensure_schema(connection)
            connection.commit()
            for asset in unique:
                symbol = f"{asset}USDT"
                cached_rows = _read_candles(connection, symbol)
                refresh = _read_refresh(connection, symbol, collected_at.date())
                if refresh is not None:
                    status, error, refreshed_at = refresh
                    results[asset] = _same_day_source(
                        status, error, refreshed_at, cached_rows
                    )
                    continue

                remaining = deadline - monotonic()
                if remaining <= 0:
                    results[asset] = _expired_source(cached_rows)
                    continue

                _write_refresh(
                    connection,
                    symbol,
                    collected_at,
                    "in_progress",
                    "collection attempt started",
                )
                connection.commit()
                if monotonic() >= deadline:
                    results[asset] = _expired_source(cached_rows)
                    continue

                try:
                    payload = _fetch_payload(
                        get,
                        symbol=symbol,
                        timeout=min(request_timeout_seconds, remaining),
                        deadline=deadline,
                        monotonic=monotonic,
                    )
                except Exception as exc:
                    error = _safe_error(exc)
                    if monotonic() >= deadline:
                        results[asset] = _expired_source(cached_rows, error)
                    else:
                        _write_refresh(
                            connection,
                            symbol,
                            collected_at,
                            "unavailable",
                            error,
                        )
                        connection.commit()
                        results[asset] = _fallback_source(
                            "unavailable", error, collected_at, cached_rows
                        )
                    continue

                if monotonic() >= deadline:
                    results[asset] = _expired_source(cached_rows)
                    continue

                candles, parse_errors = _parse_payload(payload, asset, collected_at)
                if monotonic() >= deadline:
                    results[asset] = _expired_source(cached_rows)
                    continue
                status = "incomplete" if parse_errors else "fresh"
                error = "; ".join(parse_errors[:3]) or None
                if not candles:
                    status = "missing" if not parse_errors else "invalid"
                    error = error or "response contained no closed daily candles"

                connection.execute("BEGIN")
                try:
                    _write_candles(connection, symbol, candles, collected_at)
                    _write_refresh(connection, symbol, collected_at, status, error)
                    _prune_candles(connection, symbol)
                    if monotonic() >= deadline:
                        connection.rollback()
                        results[asset] = _expired_source(cached_rows)
                        continue
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                rows = _read_candles(connection, symbol)
                if monotonic() >= deadline:
                    results[asset] = _expired_source(cached_rows)
                else:
                    results[asset] = _fallback_source(
                        status, error, collected_at, rows
                    ) if status in {"missing", "invalid"} else CandleSource(
                        status=status,
                        candles=rows,
                        error=error,
                        refreshed_at=collected_at,
                    )
    except Exception as exc:
        error = _safe_error(exc)
        for asset in unique:
            results.setdefault(
                asset,
                CandleSource(status="unavailable", error=error),
            )

    deadline_exceeded = monotonic() >= deadline
    if deadline_exceeded:
        for asset in unique:
            if asset not in results:
                results[asset] = CandleSource(status="timeout", error="collection deadline exceeded")
    return CandleCollection(
        by_asset=results,
        unsupported_assets=tuple(unsupported),
        collected_at=collected_at,
        deadline_exceeded=deadline_exceeded,
    )


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS market_candles (
            symbol TEXT NOT NULL,
            open_time_ms INTEGER NOT NULL,
            close_time_ms INTEGER NOT NULL,
            open TEXT NOT NULL,
            high TEXT NOT NULL,
            low TEXT NOT NULL,
            close TEXT NOT NULL,
            base_volume TEXT NOT NULL,
            quote_volume TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            PRIMARY KEY (symbol, open_time_ms)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS market_candle_refreshes (
            symbol TEXT NOT NULL,
            refresh_day_utc TEXT NOT NULL,
            refreshed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            PRIMARY KEY (symbol, refresh_day_utc)
        )
        """
    )


def _parse_payload(
    payload: object, asset: str, now: datetime
) -> tuple[tuple[MarketCandle, ...], list[str]]:
    if not isinstance(payload, list):
        return (), ["response is not a kline list"]
    parsed: dict[int, MarketCandle] = {}
    errors: list[str] = []
    for index, row in enumerate(payload):
        try:
            candle = _parse_row(row, asset)
            if candle.close_time >= now:
                continue
            open_ms = int(candle.open_time.timestamp() * 1000)
            if open_ms in parsed:
                errors.append(f"duplicate kline open time at row {index}")
                continue
            parsed[open_ms] = candle
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            errors.append(f"invalid kline row {index}: {type(exc).__name__}")

    candles = tuple(parsed[key] for key in sorted(parsed))
    for previous, current in zip(candles, candles[1:]):
        delta_ms = int((current.open_time - previous.open_time).total_seconds() * 1000)
        if delta_ms != DAY_MS:
            errors.append("daily kline history contains a gap")
            break
    return candles, errors


def _fetch_payload(
    http_get: Callable[..., object],
    *,
    symbol: str,
    timeout: float,
    deadline: float,
    monotonic: Callable[[], float],
) -> object:
    result_queue: queue.Queue[tuple[bool, object, Exception | None]] = queue.Queue(
        maxsize=1
    )
    cancelled = threading.Event()

    def request() -> None:
        if cancelled.is_set() or monotonic() >= deadline:
            result_queue.put((False, None, TimeoutError("collection deadline exceeded")))
            return
        try:
            response = http_get(
                KLINES_ENDPOINT,
                params={
                    "symbol": symbol,
                    "interval": KLINE_INTERVAL,
                    "limit": KLINE_LIMIT,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            result_queue.put((True, response.json(), None))
        except Exception as exc:
            result_queue.put((False, None, exc))

    worker = threading.Thread(target=request, daemon=True)
    worker.start()
    try:
        remaining = min(timeout, deadline - monotonic())
        if remaining <= 0:
            raise queue.Empty
        succeeded, payload, error = result_queue.get(timeout=remaining)
    except queue.Empty as exc:
        cancelled.set()
        raise TimeoutError("request exceeded remaining collection budget") from exc
    if not succeeded:
        assert error is not None
        raise error
    return payload


def _parse_row(row: object, asset: str) -> MarketCandle:
    if not isinstance(row, (list, tuple)) or len(row) < 8:
        raise ValueError("row is shorter than required kline fields")
    open_ms = _timestamp_ms(row[0])
    close_ms = _timestamp_ms(row[6])
    if open_ms % DAY_MS != 0 or close_ms != open_ms + DAY_MS - 1:
        raise ValueError("kline timestamps do not match a UTC daily candle")
    open_time = datetime.fromtimestamp(open_ms / 1000, timezone.utc)
    close_time = datetime.fromtimestamp(close_ms / 1000, timezone.utc)
    values = tuple(_decimal(row[index]) for index in (1, 2, 3, 4, 5, 7))
    open_price, high, low, close, base_volume, quote_volume = values
    if min(open_price, high, low, close) <= 0 or min(base_volume, quote_volume) < 0:
        raise ValueError("kline prices must be positive and volumes nonnegative")
    if high < max(open_price, close, low) or low > min(open_price, close):
        raise ValueError("kline OHLC values are inconsistent")
    return MarketCandle(
        asset=asset,
        open_time=open_time,
        close_time=close_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        base_volume=base_volume,
        quote_volume=quote_volume,
    )


def _timestamp_ms(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("kline timestamp must be a nonnegative integer in milliseconds")
    return value


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("kline numeric field has an unsupported type")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("kline numeric field is not finite")
    return number


def _write_candles(
    connection: sqlite3.Connection,
    symbol: str,
    candles: tuple[MarketCandle, ...],
    collected_at: datetime,
) -> None:
    rows = [
        (
            symbol,
            int(candle.open_time.timestamp() * 1000),
            int(candle.close_time.timestamp() * 1000),
            str(candle.open),
            str(candle.high),
            str(candle.low),
            str(candle.close),
            str(candle.base_volume),
            str(candle.quote_volume),
            collected_at.isoformat(),
        )
        for candle in candles
    ]
    connection.executemany(
        """
        INSERT INTO market_candles (
            symbol, open_time_ms, close_time_ms, open, high, low, close,
            base_volume, quote_volume, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, open_time_ms) DO UPDATE SET
            close_time_ms=excluded.close_time_ms,
            open=excluded.open, high=excluded.high, low=excluded.low,
            close=excluded.close, base_volume=excluded.base_volume,
            quote_volume=excluded.quote_volume, collected_at=excluded.collected_at
        """,
        rows,
    )


def _write_refresh(
    connection: sqlite3.Connection,
    symbol: str,
    collected_at: datetime,
    status: str,
    error: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO market_candle_refreshes (
            symbol, refresh_day_utc, refreshed_at, status, error
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol, refresh_day_utc) DO UPDATE SET
            refreshed_at=excluded.refreshed_at,
            status=excluded.status, error=excluded.error
        """,
        (
            symbol,
            collected_at.date().isoformat(),
            collected_at.isoformat(),
            status,
            error,
        ),
    )


def _read_refresh(
    connection: sqlite3.Connection, symbol: str, refresh_day: date
) -> tuple[str, str | None, datetime] | None:
    row = connection.execute(
        """
        SELECT status, error, refreshed_at FROM market_candle_refreshes
        WHERE symbol = ? AND refresh_day_utc = ?
        """,
        (symbol, refresh_day.isoformat()),
    ).fetchone()
    if row is None:
        return None
    return row[0], row[1], _parse_datetime(row[2])


def _read_candles(
    connection: sqlite3.Connection, symbol: str
) -> tuple[MarketCandle, ...]:
    rows = connection.execute(
        """
        SELECT open_time_ms, close_time_ms, open, high, low, close,
               base_volume, quote_volume
        FROM market_candles WHERE symbol = ? ORDER BY open_time_ms
        """,
        (symbol,),
    ).fetchall()
    return tuple(
        MarketCandle(
            asset=symbol.removesuffix("USDT"),
            open_time=datetime.fromtimestamp(row[0] / 1000, timezone.utc),
            close_time=datetime.fromtimestamp(row[1] / 1000, timezone.utc),
            open=Decimal(row[2]),
            high=Decimal(row[3]),
            low=Decimal(row[4]),
            close=Decimal(row[5]),
            base_volume=Decimal(row[6]),
            quote_volume=Decimal(row[7]),
        )
        for row in rows
    )


def _prune_candles(connection: sqlite3.Connection, symbol: str) -> None:
    connection.execute(
        """
        DELETE FROM market_candles
        WHERE symbol = ? AND open_time_ms NOT IN (
            SELECT open_time_ms FROM market_candles
            WHERE symbol = ? ORDER BY open_time_ms DESC LIMIT ?
        )
        """,
        (symbol, symbol, KLINE_LIMIT),
    )


def _same_day_source(
    status: str,
    error: str | None,
    refreshed_at: datetime,
    cached_rows: tuple[MarketCandle, ...],
) -> CandleSource:
    if status == "in_progress":
        return _fallback_source(
            "timeout", "daily refresh attempt did not complete", refreshed_at, cached_rows
        )
    if status in {"fresh", "incomplete"}:
        return CandleSource("cached" if status == "fresh" else "incomplete", cached_rows, error, refreshed_at)
    return _fallback_source(status, error, refreshed_at, cached_rows)


def _fallback_source(
    status: str,
    error: str | None,
    refreshed_at: datetime,
    cached_rows: tuple[MarketCandle, ...],
) -> CandleSource:
    if cached_rows:
        return CandleSource("cached", cached_rows, error, refreshed_at)
    return CandleSource(status, (), error, refreshed_at)


def _expired_source(
    cached_rows: tuple[MarketCandle, ...], error: str | None = None
) -> CandleSource:
    reason = error or "collection deadline exceeded"
    return CandleSource(
        "cached" if cached_rows else "timeout",
        cached_rows,
        reason,
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("cached refresh timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _safe_error(exc: Exception) -> str:
    detail = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {detail[:180]}" if detail else type(exc).__name__
