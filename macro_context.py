from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
FEAR_GREED = "https://api.alternative.me/fng/?limit=1"
BTC_TICKER = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"


@dataclass(slots=True)
class MacroSnapshot:
    data: Dict[str, Any]
    errors: list[str]


def fetch_macro_snapshot(timeout: int = 10) -> MacroSnapshot:
    snapshot: Dict[str, Any] = {}
    errors: list[str] = []

    _load_coingecko(snapshot, errors, timeout)
    _load_fear_greed(snapshot, errors, timeout)
    _load_btc_ticker(snapshot, errors, timeout)

    return MacroSnapshot(data=snapshot, errors=errors)


def _load_coingecko(target: Dict[str, Any], errors: list[str], timeout: int) -> None:
    try:
        response = requests.get(COINGECKO_GLOBAL, timeout=timeout)
        response.raise_for_status()
        payload = response.json().get("data", {})
        target["crypto_global"] = {
            "market_cap_usd": payload.get("total_market_cap", {}).get("usd"),
            "market_cap_change_24h": payload.get("market_cap_change_percentage_24h_usd"),
            "btc_dominance": payload.get("market_cap_percentage", {}).get("btc"),
        }
    except Exception as exc:  # pragma: no cover - best-effort telemetry
        logger.warning("Failed to fetch CoinGecko global data: %s", exc)
        errors.append(f"coingecko: {exc}")


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


__all__ = ["MacroSnapshot", "fetch_macro_snapshot"]
