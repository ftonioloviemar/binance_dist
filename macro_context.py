from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
FEAR_GREED = "https://api.alternative.me/fng/?limit=1"
BTC_TICKER = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
DEFAULT_COINGECKO_CACHE_TTL = 24 * 60 * 60
DEFAULT_COINGECKO_CACHE_PATH = Path("state/macro_context_cache.json")


@dataclass(slots=True)
class MacroSnapshot:
    data: Dict[str, Any]
    errors: list[str]


def fetch_macro_snapshot(
    timeout: int = 10,
    cache_ttl: float = DEFAULT_COINGECKO_CACHE_TTL,
    cache_path: str | Path = DEFAULT_COINGECKO_CACHE_PATH,
) -> MacroSnapshot:
    snapshot: Dict[str, Any] = {}
    errors: list[str] = []

    _load_coingecko(snapshot, errors, timeout, cache_ttl, cache_path)
    _load_fear_greed(snapshot, errors, timeout)
    _load_btc_ticker(snapshot, errors, timeout)

    return MacroSnapshot(data=snapshot, errors=errors)


def _load_coingecko(
    target: Dict[str, Any],
    errors: list[str],
    timeout: int,
    cache_ttl: float = DEFAULT_COINGECKO_CACHE_TTL,
    cache_path: str | Path = DEFAULT_COINGECKO_CACHE_PATH,
) -> None:
    path = Path(cache_path)
    try:
        response = requests.get(COINGECKO_GLOBAL, timeout=timeout)
        response.raise_for_status()
        payload = response.json().get("data", {})
        crypto_global = {
            "market_cap_usd": payload.get("total_market_cap", {}).get("usd"),
            "market_cap_change_24h": payload.get("market_cap_change_percentage_24h_usd"),
            "btc_dominance": payload.get("market_cap_percentage", {}).get("btc"),
        }
        target["crypto_global"] = crypto_global
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"cached_at": time.time(), "crypto_global": crypto_global}) + "\n",
                encoding="utf-8",
            )
        except OSError as cache_exc:  # pragma: no cover - best-effort persistence
            logger.warning("Failed to persist CoinGecko cache: %s", cache_exc)
    except Exception as exc:  # pragma: no cover - best-effort telemetry
        logger.warning("Failed to fetch CoinGecko global data: %s", exc)
        errors.append(f"coingecko: {exc}")
        try:
            cached_payload = json.loads(path.read_text(encoding="utf-8"))
            cached = cached_payload["crypto_global"]
            cached_at = float(cached_payload["cached_at"])
            age = time.time() - cached_at
            if isinstance(cached, dict) and 0 <= age <= cache_ttl:
                target["crypto_global"] = dict(cached)
                target["crypto_global_stale"] = True
                target["crypto_global_age_seconds"] = round(age, 3)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return


def _load_fear_greed(target: Dict[str, Any], errors: list[str], timeout: int) -> None:
    try:
        response = requests.get(FEAR_GREED, timeout=timeout)
        response.raise_for_status()
        data = response.json().get("data", [])
        if data:
            entry = data[0]
            target["fear_greed"] = {
                "value": int(entry.get("value", 0)),
                "classification": entry.get("value_classification"),
            }
    except Exception as exc:  # pragma: no cover - best-effort telemetry
        logger.warning("Failed to fetch fear/greed index: %s", exc)
        errors.append(f"fear_greed: {exc}")


def _load_btc_ticker(target: Dict[str, Any], errors: list[str], timeout: int) -> None:
    try:
        response = requests.get(BTC_TICKER, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        target["btc_24h"] = {
            "price": float(payload.get("lastPrice", "0")),
            "price_change_percent": float(payload.get("priceChangePercent", "0")),
            "volume_usdt": float(payload.get("quoteVolume", "0")),
        }
    except Exception as exc:  # pragma: no cover - best-effort telemetry
        logger.warning("Failed to fetch BTC 24h ticker: %s", exc)
        errors.append(f"binance_ticker: {exc}")


__all__ = [
    "DEFAULT_COINGECKO_CACHE_PATH",
    "DEFAULT_COINGECKO_CACHE_TTL",
    "MacroSnapshot",
    "fetch_macro_snapshot",
]
