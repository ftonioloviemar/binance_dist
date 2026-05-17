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
    max_notional: float = 0.0

    @classmethod
    def from_exchange(cls, payload: Mapping[str, Any]) -> "SymbolFilters":
        filters: Dict[str, Mapping[str, Any]] = {f["filterType"]: f for f in payload.get("filters", [])}
        lot = filters.get("LOT_SIZE", {})
        price = filters.get("PRICE_FILTER", {})
        min_notional = filters.get("MIN_NOTIONAL", {})
        notional = filters.get("NOTIONAL", {})
        minimum_notional = max(
            float(min_notional.get("minNotional", "0")),
            float(notional.get("minNotional", "0")),
        )
        maximum_notional = float(notional.get("maxNotional", "0"))
        return cls(
            symbol=str(payload["symbol"]),
            lot_step=float(lot.get("stepSize", "1")),
            min_qty=float(lot.get("minQty", "0")),
            max_qty=float(lot.get("maxQty", "0")),
            min_notional=minimum_notional,
            price_tick=float(price.get("tickSize", "0.01")),
            max_notional=maximum_notional,
        )


@dataclass(slots=True)
class SimpleEarnProduct:
    product_id: str
    asset: str
    status: str
    can_purchase: bool
    can_redeem: bool
    can_fast_redeem: bool
    min_purchase_amount: float
    max_purchase_amount: float | None
    purchase_limit_per_user: float | None
    purchase_limit_per_day: float | None
    left_quota: float | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SimpleEarnProduct":
        def _float(value: Any | None) -> float | None:
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return cls(
            product_id=str(payload.get("productId")),
            asset=str(payload.get("asset", "")).upper(),
            status=str(payload.get("status", "")),
            can_purchase=bool(payload.get("canPurchase", False)),
            can_redeem=bool(payload.get("canRedeem", False)),
            can_fast_redeem=bool(payload.get("canFastRedeem", False)),
            min_purchase_amount=float(payload.get("minPurchaseAmount", "0") or 0),
            max_purchase_amount=_float(payload.get("maxPurchaseAmount")),
            purchase_limit_per_user=_float(payload.get("purchaseLimitPerUser")),
            purchase_limit_per_day=_float(payload.get("purchaseLimitPerDay")),
            left_quota=_float(payload.get("leftQuota")) or _float(payload.get("fastRedeemQuota")),
        )


@dataclass(slots=True)
class SimpleEarnPosition:
    product_id: str
    asset: str
    total_amount: float
    redeemable_amount: float
    can_fast_redeem: bool

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SimpleEarnPosition":
        def _float(value: Any | None) -> float:
            if value in (None, ""):
                return 0.0
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        return cls(
            product_id=str(payload.get("productId")),
            asset=str(payload.get("asset", "")).upper(),
            total_amount=_float(payload.get("totalAmount") or payload.get("amount")),
            redeemable_amount=_float(payload.get("redeemableAmount") or payload.get("totalAmount")),
            can_fast_redeem=bool(payload.get("canFastRedeem", False)),
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

    # --- Simple Earn helpers -----------------------------------------------
    def get_simple_earn_flexible_products(self, asset: str | None = None) -> Dict[str, SimpleEarnProduct]:
        params: Dict[str, Any] = {"current": 1, "size": 100}
        if asset:
            params["asset"] = asset.upper()
        payload = self._request("GET", "/sapi/v1/simple-earn/flexible/list", params=params, signed=True)
        rows = payload.get("rows") if isinstance(payload, Mapping) else payload
        products: Dict[str, SimpleEarnProduct] = {}
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, Mapping):
                    continue
                product = SimpleEarnProduct.from_payload(item)
                products[product.product_id] = product
        return products

    def get_simple_earn_flexible_positions(self) -> list[SimpleEarnPosition]:
        params: Dict[str, Any] = {"current": 1, "size": 100}
        payload = self._request("GET", "/sapi/v1/simple-earn/flexible/position", params=params, signed=True)
        rows = payload.get("rows") if isinstance(payload, Mapping) else payload
        positions: list[SimpleEarnPosition] = []
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, Mapping):
                    continue
                positions.append(SimpleEarnPosition.from_payload(item))
        return positions

    def redeem_simple_earn_flexible(
        self,
        *,
        product_id: str,
        amount: float,
        fast: bool,
    ) -> Mapping[str, Any]:
        params: Dict[str, Any] = {
            "productId": product_id,
            "amount": _format_decimal(amount),
            "type": "FAST" if fast else "STANDARD",
        }
        return self._request("POST", "/sapi/v1/simple-earn/flexible/redeem", params=params, signed=True)

    def subscribe_simple_earn_flexible(self, *, product_id: str, amount: float) -> Mapping[str, Any]:
        params: Dict[str, Any] = {"productId": product_id, "amount": _format_decimal(amount)}
        return self._request("POST", "/sapi/v1/simple-earn/flexible/subscribe", params=params, signed=True)

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
    "SimpleEarnPosition",
    "SimpleEarnProduct",
    "SymbolFilters",
    "create_signature",
]
