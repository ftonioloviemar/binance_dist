from __future__ import annotations

import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
FEAR_GREED = "https://api.alternative.me/fng/?limit=1"
BTC_TICKER = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
DEFAULT_COINGECKO_CACHE_TTL = 24 * 60 * 60
DEFAULT_COINGECKO_CACHE_PATH = Path("state/macro_context_cache.json")
FEAR_GREED_MAX_AGE_SECONDS = 36 * 60 * 60


@dataclass(slots=True)
class MacroSnapshot:
    data: Dict[str, Any]
    errors: list[str]
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)


def fetch_macro_snapshot(
    timeout: int = 10,
    cache_ttl: float = DEFAULT_COINGECKO_CACHE_TTL,
    cache_path: str | Path = DEFAULT_COINGECKO_CACHE_PATH,
) -> MacroSnapshot:
    snapshot: Dict[str, Any] = {}
    errors: list[str] = []
    sources: dict[str, dict[str, Any]] = {}

    _load_coingecko(snapshot, errors, timeout, cache_ttl, cache_path, sources)
    _load_fear_greed(snapshot, errors, timeout, sources)
    _load_btc_ticker(snapshot, errors, timeout, sources)

    return MacroSnapshot(data=snapshot, errors=errors, sources=sources)


def _load_coingecko(
    target: Dict[str, Any],
    errors: list[str],
    timeout: int,
    cache_ttl: float = DEFAULT_COINGECKO_CACHE_TTL,
    cache_path: str | Path = DEFAULT_COINGECKO_CACHE_PATH,
    sources: dict[str, dict[str, Any]] | None = None,
) -> None:
    path = Path(cache_path)
    try:
        response = requests.get(COINGECKO_GLOBAL, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network errors are mocked in tests
        reason = _safe_error(exc)
        logger.warning("Failed to fetch CoinGecko global data: %s", reason)
        errors.append(f"coingecko: {reason}")
        _load_coingecko_cache(target, sources, path, cache_ttl, reason)
        return

    collected_at = time.time()
    try:
        payload = response.json().get("data", {})
        market_cap = _finite_number(payload.get("total_market_cap", {}).get("usd"))
        market_cap_change = _finite_number(
            payload.get("market_cap_change_percentage_24h_usd")
        )
        btc_dominance = _finite_number(
            payload.get("market_cap_percentage", {}).get("btc")
        )
        if (
            market_cap is None
            or market_cap <= 0
            or market_cap_change is None
            or btc_dominance is None
            or not 0 <= btc_dominance <= 100
        ):
            raise ValueError("required CoinGecko fields invalid")
        crypto_global = {
            "market_cap_usd": market_cap,
            "market_cap_change_24h": market_cap_change,
            "btc_dominance": btc_dominance,
        }
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        reason = _safe_error(exc) or "invalid payload"
        logger.warning("Invalid CoinGecko global data: %s", reason)
        errors.append(f"coingecko: {reason}")
        _set_source(
            sources,
            "crypto_global",
            status="invalid",
            collected_at=collected_at,
            error=reason,
        )
        return

    target["crypto_global"] = crypto_global
    _set_source(
        sources,
        "crypto_global",
        status="fresh",
        collected_at=collected_at,
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"cached_at": collected_at, "crypto_global": crypto_global})
            + "\n",
            encoding="utf-8",
        )
    except OSError as cache_exc:  # pragma: no cover - best-effort persistence
        logger.warning("Failed to persist CoinGecko cache: %s", _safe_error(cache_exc))


def _load_coingecko_cache(
    target: Dict[str, Any],
    sources: dict[str, dict[str, Any]] | None,
    path: Path,
    cache_ttl: float,
    fetch_error: str,
) -> None:
    try:
        cached_text = path.read_text(encoding="utf-8")
    except OSError:
        _set_source(
            sources, "crypto_global", status="missing", error=fetch_error
        )
        return
    except UnicodeError:
        _set_source(
            sources,
            "crypto_global",
            status="invalid",
            error="invalid cached text encoding",
        )
        return
    try:
        cached_payload = json.loads(cached_text)
    except (json.JSONDecodeError, UnicodeError):
        _set_source(
            sources,
            "crypto_global",
            status="invalid",
            error="invalid cached JSON",
        )
        return

    try:
        cached_at = _finite_number(cached_payload["cached_at"])
        cached = cached_payload["crypto_global"]
        if cached_at is None or not isinstance(cached, dict):
            raise ValueError("invalid cached payload")
        _utc_iso(cached_at)
        age = time.time() - cached_at
        if age < 0:
            raise ValueError("cache timestamp is in the future")
        if age > cache_ttl:
            _set_source(
                sources, "crypto_global", status="missing", error=fetch_error
            )
            return
        market_cap = _finite_number(cached.get("market_cap_usd"))
        market_cap_change = _finite_number(cached.get("market_cap_change_24h"))
        btc_dominance = _finite_number(cached.get("btc_dominance"))
        if (
            market_cap is None
            or market_cap <= 0
            or market_cap_change is None
            or btc_dominance is None
            or not 0 <= btc_dominance <= 100
        ):
            raise ValueError("invalid cached CoinGecko fields")
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        _set_source(
            sources,
            "crypto_global",
            status="invalid",
            error=_safe_error(exc),
        )
        return

    target["crypto_global"] = {
        "market_cap_usd": market_cap,
        "market_cap_change_24h": market_cap_change,
        "btc_dominance": btc_dominance,
    }
    target["crypto_global_stale"] = True
    target["crypto_global_age_seconds"] = round(age, 3)
    _set_source(
        sources,
        "crypto_global",
        status="cached",
        collected_at=cached_at,
        age_seconds=age,
        cache_used=True,
        error=fetch_error,
    )


def _load_fear_greed(
    target: Dict[str, Any],
    errors: list[str],
    timeout: int,
    sources: dict[str, dict[str, Any]] | None = None,
) -> None:
    try:
        response = requests.get(FEAR_GREED, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network errors are mocked in tests
        reason = _safe_error(exc)
        logger.warning("Failed to fetch fear/greed index: %s", reason)
        errors.append(f"fear_greed: {reason}")
        _set_source(sources, "fear_greed", status="missing", error=reason)
        return

    collected_at = time.time()
    observed_at: str | None = None
    try:
        data = response.json().get("data", [])
        if not isinstance(data, list):
            raise ValueError("Fear & Greed data must be a list")
        if not data:
            _set_source(sources, "fear_greed", status="missing", collected_at=collected_at)
            errors.append("fear_greed: no observation returned")
            return
        entry = data[0]
        value = _integer_value(entry.get("value"))
        classification = entry.get("value_classification")
        observed_epoch = _integer_value(entry.get("timestamp"))
        if observed_epoch is not None:
            observed_at = _utc_iso(observed_epoch)
        if value is None or not 0 <= value <= 100:
            raise ValueError("Fear & Greed value outside integer range 0..100")
        if not isinstance(classification, str) or not classification.strip():
            raise ValueError("Fear & Greed classification missing")
        if observed_epoch is None:
            raise ValueError("Fear & Greed provider timestamp invalid")
        age = collected_at - observed_epoch
        if age < 0 or age > FEAR_GREED_MAX_AGE_SECONDS:
            raise ValueError("Fear & Greed observation stale or future-dated")
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        reason = _safe_error(exc) or "invalid payload"
        logger.warning("Invalid fear/greed index: %s", reason)
        errors.append(f"fear_greed: {reason}")
        _set_source(
            sources,
            "fear_greed",
            status="invalid",
            observed_at=observed_at,
            collected_at=collected_at,
            error=reason,
        )
        return

    target["fear_greed"] = {
        "value": value,
        "classification": classification.strip(),
    }
    _set_source(
        sources,
        "fear_greed",
        status="fresh",
        observed_at=observed_at,
        collected_at=collected_at,
        age_seconds=age,
    )


def _load_btc_ticker(
    target: Dict[str, Any],
    errors: list[str],
    timeout: int,
    sources: dict[str, dict[str, Any]] | None = None,
) -> None:
    try:
        response = requests.get(BTC_TICKER, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network errors are mocked in tests
        reason = _safe_error(exc)
        logger.warning("Failed to fetch BTC 24h ticker: %s", reason)
        errors.append(f"binance_ticker: {reason}")
        _set_source(sources, "btc_24h", status="missing", error=reason)
        return

    collected_at = time.time()
    try:
        payload = response.json()
        price = _finite_number(payload.get("lastPrice"))
        change = _finite_number(payload.get("priceChangePercent"))
        volume = _finite_number(payload.get("quoteVolume"))
        if price is None or price <= 0:
            raise ValueError("BTC ticker price must be positive and finite")
        if change is None:
            raise ValueError("BTC ticker 24h change must be finite")
        if volume is not None and volume < 0:
            raise ValueError("BTC ticker quote volume must be nonnegative")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        reason = _safe_error(exc) or "invalid payload"
        logger.warning("Invalid BTC 24h ticker: %s", reason)
        errors.append(f"binance_ticker: {reason}")
        _set_source(
            sources,
            "btc_24h",
            status="invalid",
            collected_at=collected_at,
            error=reason,
        )
        return

    target["btc_24h"] = {
        "price": price,
        "price_change_percent": change,
        "volume_usdt": volume,
    }
    _set_source(
        sources,
        "btc_24h",
        status="fresh",
        collected_at=collected_at,
        age_seconds=0.0,
    )


def _set_source(
    sources: dict[str, dict[str, Any]] | None,
    name: str,
    *,
    status: str,
    observed_at: str | None = None,
    collected_at: float | None = None,
    age_seconds: float | None = None,
    cache_used: bool = False,
    error: str | None = None,
) -> None:
    if sources is None:
        return
    sources[name] = {
        "status": status,
        "observed_at": observed_at,
        "collected_at": _utc_iso(collected_at) if collected_at is not None else None,
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "cache_used": cache_used,
        "error": error,
    }


def _utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _safe_error(exc: BaseException) -> str:
    message = str(exc).strip() or type(exc).__name__
    message = re.sub(r"https?://\S+", "[redacted URL]", message, flags=re.IGNORECASE)
    message = re.sub(
        r"(?i)(authorization\s*[=:]\s*)(?:(?:bearer|basic)\s+)?[^\s&,;]+",
        r"\1[redacted]",
        message,
    )
    message = re.sub(
        r"(?i)\bBearer\s+[^\s&,;]+",
        "Bearer [redacted]",
        message,
    )
    message = re.sub(
        r"(?i)(api[_-]?key|token|secret|password|passwd)(\s*[=:]\s*)[^\s&,;]+",
        r"\1\2[redacted]",
        message,
    )
    return message[:240]


__all__ = [
    "DEFAULT_COINGECKO_CACHE_PATH",
    "DEFAULT_COINGECKO_CACHE_TTL",
    "FEAR_GREED_MAX_AGE_SECONDS",
    "MacroSnapshot",
    "fetch_macro_snapshot",
]
