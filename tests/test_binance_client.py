from __future__ import annotations

import time

import pytest

import binance_client
from binance_client import BinanceAPIError, BinanceClient, SymbolFilters, create_signature


class FakeResponse:
    def __init__(self, data: object, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> object:
        if isinstance(self._data, Exception):
            raise self._data
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class FakeSession:
    def __init__(self, payload: object, *, responses: list[FakeResponse] | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.payload = payload
        self.responses = list(responses or [])
        self.last_params: dict[str, object] | None = None
        self.requests: list[dict[str, object]] = []

    def request(self, *, method: str, url: str, params=None, data=None, timeout: int | None = None):  # type: ignore[override]
        self.last_params = params if params is not None else data
        self.requests.append({"method": method, "url": url, "params": self.last_params or {}})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(self.payload)

    def get(self, url: str, timeout: int | None = None):  # pragma: no cover - only used for timestamp sync
        return FakeResponse({"serverTime": int(time.time() * 1000)})


def test_create_signature_matches_known_value() -> None:
    query = "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1&recvWindow=5000&timestamp=1499827319559"
    secret = "Nh98s3u8asdfjh2389sdlfkj"
    expected = "067860d82dfb817f08c9d013b3a894955942b6b879727927103313acb8061ce0"
    assert create_signature(secret, query) == expected


def test_signed_request_includes_signature() -> None:
    payload = {"balances": [{"asset": "BTC", "free": "1", "locked": "0"}]}
    session = FakeSession(payload)
    client = BinanceClient(
        api_key="key",
        api_secret="secret",
        base_url="https://example.com",
        session=session,
    )
    balances = client.get_account_balances()
    assert balances[0].asset == "BTC"
    assert session.last_params is not None
    assert "signature" in session.last_params


def test_place_order_requests_full_response_by_default() -> None:
    session = FakeSession({"status": "FILLED"})
    client = BinanceClient(
        api_key="key",
        api_secret="secret",
        base_url="https://example.com",
        session=session,
    )

    client.place_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.1,
        client_order_id="cid-123",
    )

    assert session.last_params is not None
    assert session.last_params["newOrderRespType"] == "FULL"


def test_symbol_filters_prefers_notional_minimum_over_min_notional() -> None:
    filters = SymbolFilters.from_exchange(
        {
            "symbol": "ADAUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.1", "minQty": "0.1", "maxQty": "100000"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "1.0"},
                {
                    "filterType": "NOTIONAL",
                    "minNotional": "5.0",
                    "maxNotional": "10000.0",
                    "applyMinToMarket": True,
                    "applyMaxToMarket": False,
                },
            ],
        }
    )

    assert filters.min_notional == 5.0
    assert filters.max_notional == 10000.0


def test_symbol_filters_keeps_min_notional_when_it_is_more_restrictive() -> None:
    filters = SymbolFilters.from_exchange(
        {
            "symbol": "BNBUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "100000"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"},
                {"filterType": "NOTIONAL", "maxNotional": "50000.0"},
            ],
        }
    )

    assert filters.min_notional == 10.0
    assert filters.max_notional == 50000.0


def test_http_error_preserves_binance_code_and_sanitized_message() -> None:
    response = FakeResponse(
        {
            "code": -6009,
            "msg": (
                "Request frequency too high for amount 1.25 "
                "signature=FAKE_SIGNATURE_SENTINEL "
                "api_key=FAKE_API_KEY_SENTINEL secret=FAKE_SECRET_SENTINEL "
                "selector=FAKE_SEQUENCE_CANARY"
            ),
            "privateField": "DO_NOT_LOG_BODY",
        },
        status_code=400,
    )
    session = FakeSession({}, responses=[response])
    client = BinanceClient(
        api_key="FAKE_API_KEY_SENTINEL",
        api_secret="FAKE_SECRET_SENTINEL",
        base_url="https://example.invalid/private-path",
        session=session,
    )

    with pytest.raises(BinanceAPIError) as captured:
        client._request(
            "POST",
            "/sapi/v1/simple-earn/flexible/redeem",
            {
                "amount": "1.25",
                "signature": "FAKE_SIGNATURE_SENTINEL",
                "selector": ["FAKE_SEQUENCE_CANARY"],
            },
            signed=True,
        )

    detail = str(captured.value)
    assert captured.value.status_code == 400
    assert captured.value.code == -6009
    assert captured.value.message.startswith("Request frequency too high")
    assert "400" in detail
    assert "-6009" in detail
    assert "Request frequency too high" in detail
    for forbidden in (
        "example.invalid",
        "private-path",
        "FAKE_API_KEY_SENTINEL",
        "FAKE_SECRET_SENTINEL",
        "FAKE_SIGNATURE_SENTINEL",
        "FAKE_SEQUENCE_CANARY",
        "DO_NOT_LOG_BODY",
        "1.25",
    ):
        assert forbidden not in detail


def test_http_error_message_is_bounded_and_redacts_controls_urls_and_credentials() -> None:
    long_message = (
        "Bad signature=FAKE_SIGNATURE_SENTINEL api_key=FAKE_API_KEY_SENTINEL "
        "https://example.invalid/secret\n" + ("x" * 300)
    )
    session = FakeSession(
        {},
        responses=[FakeResponse({"code": -1, "msg": long_message}, status_code=400)],
    )
    client = BinanceClient(
        api_key="FAKE_API_KEY_SENTINEL",
        api_secret="FAKE_SECRET_SENTINEL",
        base_url="https://example.invalid",
        session=session,
    )

    with pytest.raises(BinanceAPIError) as captured:
        client._request("POST", "/sapi/test", signed=True)

    detail = str(captured.value)
    assert len(detail.split(" message=", 1)[-1]) <= 160
    assert "FAKE_SIGNATURE_SENTINEL" not in detail
    assert "FAKE_API_KEY_SENTINEL" not in detail
    assert "example.invalid" not in detail
    assert "\n" not in detail


@pytest.mark.parametrize("status_code", [400, 503])
def test_non_json_http_error_keeps_status_without_body(status_code: int) -> None:
    session = FakeSession(
        {},
        responses=[FakeResponse(ValueError("RAW_BODY_SENTINEL"), status_code=status_code)],
    )
    client = BinanceClient(
        api_key="key",
        api_secret="secret",
        base_url="https://example.invalid",
        session=session,
    )

    with pytest.raises(BinanceAPIError) as captured:
        client._request("GET", "/api/v3/account", signed=True)

    assert str(status_code) in str(captured.value)
    assert "RAW_BODY_SENTINEL" not in str(captured.value)


def test_timestamp_error_still_syncs_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        {},
        responses=[
            FakeResponse({"code": -1021, "msg": "Timestamp outside recvWindow"}, status_code=400),
            FakeResponse({"ok": True}),
        ],
    )
    client = BinanceClient(
        api_key="key",
        api_secret="secret",
        base_url="https://example.invalid",
        session=session,
    )
    synced: list[bool] = []
    monkeypatch.setattr(client, "_sync_timestamp", lambda: synced.append(True))

    result = client._request("GET", "/api/v3/account", signed=True)

    assert result == {"ok": True}
    assert len(session.requests) == 2
    assert synced == [True]


@pytest.mark.parametrize("status_code", [418, 429])
def test_rate_limit_status_still_retries(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(binance_client.time, "sleep", lambda delay: sleeps.append(delay))
    session = FakeSession(
        {},
        responses=[FakeResponse({}, status_code=status_code), FakeResponse({"ok": True})],
    )
    client = BinanceClient(
        api_key="key",
        api_secret="secret",
        base_url="https://example.invalid",
        session=session,
    )

    result = client._request("GET", "/api/v3/account", signed=True)

    assert result == {"ok": True}
    assert len(session.requests) == 2
    assert sleeps == [1]


def test_exhausted_rate_limit_raises_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binance_client.time, "sleep", lambda _: None)
    session = FakeSession(
        {},
        responses=[
            FakeResponse({"code": -1003, "msg": "Too many requests"}, status_code=429),
            FakeResponse({"code": -1003, "msg": "Too many requests"}, status_code=429),
        ],
    )
    client = BinanceClient(
        api_key="key",
        api_secret="secret",
        base_url="https://example.invalid",
        max_retries=2,
        session=session,
    )

    with pytest.raises(BinanceAPIError) as captured:
        client._request("GET", "/api/v3/account", signed=True)

    assert "429" in str(captured.value)
    assert "-1003" in str(captured.value)
    assert len(session.requests) == 2
