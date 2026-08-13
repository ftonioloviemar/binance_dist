from __future__ import annotations

import pytest
import json

from config import ConfigError, load_cli_defaults, load_env_settings


def _set_required_binance_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_API_SECRET", "secret")


def test_load_cli_defaults_uses_notional_aware_three_percent_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEFAULT_DRIFT", raising=False)

    defaults = load_cli_defaults()

    assert defaults.drift == 0.03
    assert defaults.min_notional_uplift_tolerance == 0.10


def test_load_env_settings_uses_ordered_free_openrouter_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_binance_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_MODELS_MODE", "manual")
    monkeypatch.delenv("OPENROUTER_MODELS_REGISTRY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODELS", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("MODEL_FALLBACK", raising=False)
    monkeypatch.delenv("MODEL_SECOND_FALLBACK", raising=False)

    settings = load_env_settings(5000)

    assert settings.openrouter_models[:5] == (
        "openrouter/owl-alpha",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "deepseek/deepseek-v4-flash:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "google/gemma-4-31b-it:free",
    )
    assert len(settings.openrouter_models) > 3
    assert "openrouter/polaris-alpha" not in settings.openrouter_models


def test_load_env_settings_accepts_unlimited_openrouter_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_binance_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_MODELS_MODE", "manual")
    monkeypatch.delenv("OPENROUTER_MODELS_REGISTRY", raising=False)
    monkeypatch.setenv(
        "OPENROUTER_MODELS",
        "model/a:free, model/b:free\nmodel/c:free; model/d:free",
    )

    settings = load_env_settings(5000)

    assert settings.openrouter_models == (
        "model/a:free",
        "model/b:free",
        "model/c:free",
        "model/d:free",
    )


def test_load_env_settings_keeps_legacy_model_chain_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_binance_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_MODELS_MODE", "manual")
    monkeypatch.delenv("OPENROUTER_MODELS_REGISTRY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODELS", raising=False)
    monkeypatch.setenv("MODEL_NAME", "legacy/first:free")
    monkeypatch.setenv("MODEL_FALLBACK", "legacy/second:free")
    monkeypatch.setenv("MODEL_SECOND_FALLBACK", "legacy/third:free")

    settings = load_env_settings(5000)

    assert settings.openrouter_models[:3] == (
        "legacy/first:free",
        "legacy/second:free",
        "legacy/third:free",
    )


def test_load_env_settings_rejects_empty_openrouter_model_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_binance_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_MODELS_MODE", "manual")
    monkeypatch.delenv("OPENROUTER_MODELS_REGISTRY", raising=False)
    monkeypatch.setenv("OPENROUTER_MODELS", " , \n ; ")

    with pytest.raises(ConfigError, match="OPENROUTER_MODELS"):
        load_env_settings(5000)


def test_load_env_settings_prefers_openrouter_model_registry(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_required_binance_env(monkeypatch)
    registry_path = tmp_path / "openrouter_models.json"
    registry_path.write_text(
        json.dumps({"active_models": ["registry/first:free", "registry/second:free"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_MODELS_REGISTRY", str(registry_path))
    monkeypatch.setenv("OPENROUTER_MODELS", "env/first:free,env/second:free")

    settings = load_env_settings(5000)

    assert settings.openrouter_models == (
        "registry/first:free",
        "registry/second:free",
    )
