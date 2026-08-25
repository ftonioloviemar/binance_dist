from __future__ import annotations

import requests

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
