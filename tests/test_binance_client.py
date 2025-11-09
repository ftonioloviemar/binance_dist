from __future__ import annotations

import time

from binance_client import BinanceClient, create_signature


class FakeResponse:
    def __init__(self, data: dict[str, object], status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class FakeSession:
    def __init__(self, payload: dict[str, object]) -> None:
        self.headers: dict[str, str] = {}
        self.payload = payload
        self.last_params: dict[str, object] | None = None

    def request(self, *, method: str, url: str, params=None, data=None, timeout: int | None = None):  # type: ignore[override]
        self.last_params = params if params is not None else data
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
