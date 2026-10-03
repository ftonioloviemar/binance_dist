from __future__ import annotations

import json

import requests
import pytest

import macro_context


def _coingecko_payload() -> dict[str, object]:
    return {
        "data": {
            "total_market_cap": {"usd": 123.0},
            "market_cap_change_percentage_24h_usd": 1.5,
            "market_cap_percentage": {"btc": 52.0},
        }
    }


def test_coingecko_reuses_recent_snapshot_as_explicit_stale_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 100.0)

    class SuccessResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return _coingecko_payload()

    calls = 0

    def fake_get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SuccessResponse()
        raise requests.Timeout("rate limited")

    monkeypatch.setattr(macro_context.requests, "get", fake_get)

    target: dict[str, object] = {}
    errors: list[str] = []
    cache_path = tmp_path / "macro-cache.json"
    macro_context._load_coingecko(target, errors, timeout=1, cache_path=cache_path)
    monkeypatch.setattr(macro_context.time, "time", lambda: 110.0)
    macro_context._load_coingecko(
        target, errors, timeout=1, cache_path=cache_path
    )

    assert target["crypto_global"]["market_cap_usd"] == 123.0
    assert target["crypto_global_stale"] is True
    assert target["crypto_global_age_seconds"] == 10.0
    assert errors == ["coingecko: rate limited"]


def test_coingecko_does_not_use_expired_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 100.0)

    class SuccessResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return _coingecko_payload()

    calls = 0

    def fake_get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SuccessResponse()
        raise requests.Timeout("timeout")

    monkeypatch.setattr(macro_context.requests, "get", fake_get)

    target: dict[str, object] = {}
    errors: list[str] = []
    cache_path = tmp_path / "macro-cache.json"
    macro_context._load_coingecko(
        target, errors, timeout=1, cache_ttl=60, cache_path=cache_path
    )
    monkeypatch.setattr(macro_context.time, "time", lambda: 200.0)
    expired_target: dict[str, object] = {}
    macro_context._load_coingecko(
        expired_target, errors, timeout=1, cache_ttl=60, cache_path=cache_path
    )

    assert "crypto_global" not in expired_target
    assert errors == ["coingecko: timeout"]


def _response(payload: object):
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return payload

    return Response()


def _fear_payload(*, value: object = "55", timestamp: object = "996400") -> dict[str, object]:
    return {
        "data": [
            {
                "value": value,
                "value_classification": "Neutral",
                "timestamp": timestamp,
            }
        ]
    }


def _btc_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "lastPrice": "60000",
        "priceChangePercent": "1.25",
        "quoteVolume": "123456",
    }
    payload.update(updates)
    return payload


def _install_market_responses(monkeypatch, *, fear=None, btc=None, coingecko=None) -> None:
    responses = {
        macro_context.COINGECKO_GLOBAL: _response(
            _coingecko_payload() if coingecko is None else coingecko
        ),
        macro_context.FEAR_GREED: _response(
            _fear_payload() if fear is None else fear
        ),
        macro_context.BTC_TICKER: _response(
            _btc_payload() if btc is None else btc
        ),
    }

    def fake_get(url, **_kwargs):
        result = responses[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(macro_context.requests, "get", fake_get)


def test_macro_snapshot_source_metadata_and_legacy_constructor(monkeypatch, tmp_path) -> None:
    now = 1_000_000.0
    monkeypatch.setattr(macro_context.time, "time", lambda: now)
    _install_market_responses(monkeypatch)

    legacy = macro_context.MacroSnapshot({}, [])
    assert legacy.sources == {}

    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    assert set(snapshot.sources) == {"fear_greed", "btc_24h", "crypto_global"}
    assert snapshot.sources["fear_greed"]["status"] == "fresh"
    assert snapshot.sources["fear_greed"]["observed_at"] == "1970-01-12T12:46:40Z"
    assert snapshot.sources["fear_greed"]["collected_at"] == "1970-01-12T13:46:40Z"
    assert snapshot.sources["fear_greed"]["age_seconds"] == 3600.0
    assert snapshot.sources["btc_24h"]["status"] == "fresh"
    assert snapshot.sources["btc_24h"]["cache_used"] is False
    assert snapshot.sources["crypto_global"]["status"] == "fresh"
    assert snapshot.data["fear_greed"]["value"] == 55
    assert snapshot.data["btc_24h"]["price"] == 60000.0
    assert snapshot.errors == []


@pytest.mark.parametrize(
    "value,timestamp",
    [
        ("101", "996400"),
        ("55.5", "996400"),
        ("55", None),
        ("55", "not-a-timestamp"),
        ("55", "870399"),
        ("55", "1000000001"),
    ],
)
def test_invalid_fear_payload_is_not_replaced_with_neutral_defaults(
    monkeypatch, tmp_path, value, timestamp
) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    _install_market_responses(monkeypatch, fear=_fear_payload(value=value, timestamp=timestamp))

    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    assert snapshot.sources["fear_greed"]["status"] == "invalid"
    if timestamp is not None and timestamp != "not-a-timestamp":
        assert snapshot.sources["fear_greed"]["observed_at"] is not None
    assert "fear_greed" not in snapshot.data
    assert any(error.startswith("fear_greed:") for error in snapshot.errors)


@pytest.mark.parametrize(
    "updates",
    [
        {"lastPrice": "0"},
        {"lastPrice": "-1"},
        {"lastPrice": "NaN"},
        {"priceChangePercent": "Infinity"},
        {"priceChangePercent": "bad"},
    ],
)
def test_invalid_btc_ticker_is_marked_invalid(monkeypatch, tmp_path, updates) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    _install_market_responses(monkeypatch, btc=_btc_payload(**updates))

    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    assert snapshot.sources["btc_24h"]["status"] == "invalid"
    assert "btc_24h" not in snapshot.data
    assert any(error.startswith("binance_ticker:") for error in snapshot.errors)


def test_btc_ticker_without_optional_volume_remains_usable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    _install_market_responses(
        monkeypatch,
        btc={"lastPrice": "60000", "priceChangePercent": "1.25"},
    )

    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    assert snapshot.sources["btc_24h"]["status"] == "fresh"
    assert snapshot.data["btc_24h"]["volume_usdt"] is None


def test_coingecko_cache_is_marked_cached_and_preserves_age(monkeypatch, tmp_path) -> None:
    now = 1_000_000.0
    monkeypatch.setattr(macro_context.time, "time", lambda: now)
    calls = 0

    def fake_get(url, **_kwargs):
        nonlocal calls
        if url == macro_context.COINGECKO_GLOBAL:
            calls += 1
            if calls == 1:
                return _response(_coingecko_payload())
            raise requests.Timeout("rate limited")
        if url == macro_context.FEAR_GREED:
            return _response(_fear_payload())
        return _response(_btc_payload())

    monkeypatch.setattr(macro_context.requests, "get", fake_get)
    cache_path = tmp_path / "cache.json"
    macro_context.fetch_macro_snapshot(cache_path=cache_path)
    now += 10
    second = macro_context.fetch_macro_snapshot(cache_path=cache_path)

    assert second.sources["crypto_global"]["status"] == "cached"
    assert second.sources["crypto_global"]["cache_used"] is True
    assert second.sources["crypto_global"]["age_seconds"] == 10.0
    assert second.data["crypto_global_stale"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {"total_market_cap": {"usd": "NaN"}}},
        {
            "data": {
                "total_market_cap": {"usd": "100"},
                "market_cap_change_percentage_24h_usd": "Infinity",
                "market_cap_percentage": {"btc": "50"},
            }
        },
        {
            "data": {
                "total_market_cap": {"usd": "100"},
                "market_cap_change_percentage_24h_usd": "1",
                "market_cap_percentage": {"btc": "101"},
            }
        },
    ],
)
def test_invalid_coingecko_payload_is_not_cached_or_used(
    monkeypatch, tmp_path, payload
) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    _install_market_responses(monkeypatch, coingecko=payload)
    cache_path = tmp_path / "cache.json"

    snapshot = macro_context.fetch_macro_snapshot(cache_path=cache_path)

    assert snapshot.sources["crypto_global"]["status"] == "invalid"
    assert "crypto_global" not in snapshot.data
    assert not cache_path.exists()


def test_empty_fear_response_is_missing_without_default_sentiment(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    _install_market_responses(monkeypatch, fear={"data": []})

    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    assert snapshot.sources["fear_greed"]["status"] == "missing"
    assert "fear_greed" not in snapshot.data


def test_malformed_fear_data_shape_is_invalid(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    _install_market_responses(
        monkeypatch,
        fear={"data": {"value": "55", "value_classification": "Neutral"}},
    )

    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    assert snapshot.sources["fear_greed"]["status"] == "invalid"


def test_future_coin_gecko_cache_is_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps({"cached_at": 1_000_001.0, "crypto_global": {
            "market_cap_usd": 100.0,
            "market_cap_change_24h": 1.0,
            "btc_dominance": 50.0,
        }}),
        encoding="utf-8",
    )
    calls = 0

    def fake_get(url, **_kwargs):
        nonlocal calls
        calls += 1
        if url == macro_context.COINGECKO_GLOBAL:
            raise requests.Timeout("temporary failure")
        if url == macro_context.FEAR_GREED:
            return _response(_fear_payload())
        return _response(_btc_payload())

    monkeypatch.setattr(macro_context.requests, "get", fake_get)
    snapshot = macro_context.fetch_macro_snapshot(cache_path=cache_path)

    assert calls == 3
    assert snapshot.sources["crypto_global"]["status"] == "invalid"
    assert "crypto_global" not in snapshot.data


def test_corrupt_coin_gecko_cache_is_invalid(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("{not-json", encoding="utf-8")

    def fake_get(url, **_kwargs):
        if url == macro_context.COINGECKO_GLOBAL:
            raise requests.Timeout("temporary failure")
        if url == macro_context.FEAR_GREED:
            return _response(_fear_payload())
        return _response(_btc_payload())

    monkeypatch.setattr(macro_context.requests, "get", fake_get)
    snapshot = macro_context.fetch_macro_snapshot(cache_path=cache_path)

    assert snapshot.sources["crypto_global"]["status"] == "invalid"
    assert "crypto_global" not in snapshot.data


def test_non_utf8_coin_gecko_cache_is_invalid(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)
    cache_path = tmp_path / "cache.json"
    cache_path.write_bytes(b"\xff\xfe")

    def fake_get(url, **_kwargs):
        if url == macro_context.COINGECKO_GLOBAL:
            raise requests.Timeout("temporary failure")
        if url == macro_context.FEAR_GREED:
            return _response(_fear_payload())
        return _response(_btc_payload())

    monkeypatch.setattr(macro_context.requests, "get", fake_get)
    snapshot = macro_context.fetch_macro_snapshot(cache_path=cache_path)

    assert snapshot.sources["crypto_global"]["status"] == "invalid"
    assert "crypto_global" not in snapshot.data


def test_source_errors_do_not_echo_urls_or_query_secrets(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)

    def fake_get(url, **_kwargs):
        if url == macro_context.COINGECKO_GLOBAL:
            raise requests.Timeout(
                "request failed https://example.test/path?token=secret-value"
            )
        if url == macro_context.FEAR_GREED:
            return _response(_fear_payload())
        return _response(_btc_payload())

    monkeypatch.setattr(macro_context.requests, "get", fake_get)
    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    diagnostic = snapshot.sources["crypto_global"]["error"]
    assert diagnostic
    assert "https://" not in diagnostic
    assert "secret-value" not in diagnostic
    assert "secret-value" not in " ".join(snapshot.errors)


def test_source_errors_do_not_echo_bearer_authorization_tokens(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(macro_context.time, "time", lambda: 1_000_000.0)

    def fake_get(url, **_kwargs):
        if url == macro_context.COINGECKO_GLOBAL:
            raise requests.Timeout("Authorization: Bearer abc123secret")
        if url == macro_context.FEAR_GREED:
            return _response(_fear_payload())
        return _response(_btc_payload())

    monkeypatch.setattr(macro_context.requests, "get", fake_get)
    snapshot = macro_context.fetch_macro_snapshot(cache_path=tmp_path / "cache.json")

    assert "abc123secret" not in snapshot.sources["crypto_global"]["error"]
    assert "abc123secret" not in " ".join(snapshot.errors)
