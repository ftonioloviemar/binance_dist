from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

import hashlib
import hmac
import json
import logging
import time
import urllib.parse

import requests

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v3"


@dataclass(slots=True)
class SymbolFilters:
    symbol: str
    lot_step: float
    min_qty: float
    max_qty: float
    min_notional: float
    price_tick: float

    @classmethod
    def from_exchange(cls, payload: Mapping[str, Any]) -> "SymbolFilters":
        filters: Dict[str, Mapping[str, Any]] = {f["filterType"]: f for f in payload.get("filters", [])}
        lot = filters.get("LOT_SIZE", {})
        price = filters.get("PRICE_FILTER", {})
        min_notional = filters.get("MIN_NOTIONAL", {})
        return cls(
            symbol=str(payload["symbol"]),
            lot_step=float(lot.get("stepSize", "1")),
            min_qty=float(lot.get("minQty", "0")),
            max_qty=float(lot.get("maxQty", "0")),
            min_notional=float(min_notional.get("minNotional", "0")),
            price_tick=float(price.get("tickSize", "0.01")),
        )


@dataclass(slots=True)
class Balance:
    asset: str
    free: float
    locked: float

    @property
    def total(self) -> float:
        return self.free + self.locked


def create_signature(secret: str, query_string: str) -> str:
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()


class BinanceClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str,
        recv_window: int = 5000,
        timeout: int = 15,
        max_retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.recv_window = recv_window
        self.session = session or requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": api_key})
        self._timestamp_offset_ms = 0

    def close(self) -> None:
        self.session.close()

    # --- public REST helpers -------------------------------------------------
    def get_exchange_info(self, symbols: Sequence[str] | None = None) -> Dict[str, SymbolFilters]:
        params: Dict[str, Any] = {}
        if symbols:
            params["symbols"] = json.dumps(list(symbols))
        data = self._request("GET", f"{API_PREFIX}/exchangeInfo", params=params, signed=False)
        result: Dict[str, SymbolFilters] = {}
        for symbol_payload in data.get("symbols", []):
            filt = SymbolFilters.from_exchange(symbol_payload)
            result[filt.symbol] = filt
        return result

    def get_account_balances(self) -> list[Balance]:
        account = self._request("GET", f"{API_PREFIX}/account", signed=True)
        balances = []
        for entry in account.get("balances", []):
            free = float(entry.get("free", "0"))
            locked = float(entry.get("locked", "0"))
            if free == 0.0 and locked == 0.0:
                continue
            balances.append(Balance(asset=entry["asset"], free=free, locked=locked))
        return balances

    def get_prices(self, symbols: Sequence[str] | None = None) -> Dict[str, float]:
        params: Dict[str, Any] = {}
        if symbols:
            params["symbols"] = json.dumps(list(symbols))
        payload = self._request("GET", f"{API_PREFIX}/ticker/price", params=params, signed=False)
        prices: Dict[str, float] = {}
        if isinstance(payload, list):
            iterable: Iterable[Mapping[str, Any]] = payload
        else:
            iterable = [payload]
        for item in iterable:
            prices[str(item["symbol"])] = float(item["price"])
        return prices

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        client_order_id: str | None = None,
        time_in_force: str = "GTC",
    ) -> Mapping[str, Any]:
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "timestamp": self._timestamp_ms(),
            "recvWindow": self.recv_window,
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id

        if order_type == "MARKET":
            params["quantity"] = _format_decimal(quantity)
        else:
            params["quantity"] = _format_decimal(quantity)
            if price is None:
                raise ValueError("Limit orders require price")
            params["price"] = _format_decimal(price)
            params["timeInForce"] = time_in_force

        return self._request("POST", f"{API_PREFIX}/order", params=params, signed=True)

    # --- internal helpers ----------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        params: MutableMapping[str, Any] | None = None,
        *,
        signed: bool,
    ) -> Mapping[str, Any]:
        url = f"{self.base_url}{path}"
        params = params or {}
        for attempt in range(self.max_retries):
            prepared_params = dict(params)
            if signed:
                prepared_params.setdefault("timestamp", self._timestamp_ms())
                prepared_params.setdefault("recvWindow", self.recv_window)
                query = urllib.parse.urlencode(prepared_params, doseq=True)
                signature = create_signature(self.api_secret, query)
                prepared_params["signature"] = signature
            response = self.session.request(
                method=method,
                url=url,
                params=None if method.upper() == "POST" else prepared_params,
                data=prepared_params if method.upper() == "POST" else None,
                timeout=self.timeout,
            )
            if response.status_code == 400:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                if payload.get("code") == -1021:  # timestamp
                    logger.warning("Binance timestamp drift detected, syncing time")
                    self._sync_timestamp()
                    continue
            if response.status_code in {418, 429} and attempt < self.max_retries - 1:
                sleep_for = 2 ** attempt
                logger.warning("Rate limited by Binance, backing off for %s seconds", sleep_for)
                time.sleep(sleep_for)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("Exceeded maximum retries while calling Binance API")

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000) + self._timestamp_offset_ms

    def _sync_timestamp(self) -> None:
        response = self.session.get(f"{self.base_url}{API_PREFIX}/time", timeout=self.timeout)
        response.raise_for_status()
        server_time = int(response.json()["serverTime"])
        self._timestamp_offset_ms = server_time - int(time.time() * 1000)


def _format_decimal(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


__all__ = [
    "Balance",
    "BinanceClient",
    "SymbolFilters",
    "create_signature",
]
