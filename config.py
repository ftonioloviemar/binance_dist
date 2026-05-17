from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BUCKETS_JSON = '{"stable":["USDT"],"alt":["BNB","AVAX","ADA"]}'
PROFILE_TARGET_FALLBACKS = {
    "moderate": "BTC=0.40,ETH=0.20,SOL=0.15,STABLE=0.15,ALT=0.10",
    "aggressive": "BTC=0.30,ETH=0.25,SOL=0.20,ALT=0.15,STABLE=0.10",
    "conservative": "BTC=0.35,ETH=0.15,SOL=0.05,ALT=0.05,STABLE=0.40",
}
STABLE_ASSETS_FALLBACK = "USDT,USDC,BUSD,TUSD,FDUSD,DAI"
DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH = Path("state/openrouter_models.json")
DEFAULT_OPENROUTER_FREE_MODELS = (
    "openrouter/owl-alpha",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "deepseek/deepseek-v4-flash:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "openai/gpt-oss-120b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "z-ai/glm-4.5-air:free",
    "arcee-ai/trinity-large-thinking:free",
    "minimax/minimax-m2.5:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "poolside/laguna-m.1:free",
    "poolside/laguna-xs.2:free",
    "baidu/cobuddy:free",
    "openai/gpt-oss-20b:free",
    "liquid/lfm-2.5-1.2b-thinking:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "openrouter/free",
)


@dataclass(slots=True)
class EnvSettings:
    api_key: str
    api_secret: str
    testnet: bool
    base_url: str
    recv_window: int
    openrouter_api_key: str | None = None
    openrouter_models: tuple[str, ...] = ()
    model_name: str | None = None
    model_fallback: str | None = None
    model_second_fallback: str | None = None
    simple_earn_enabled: bool = False
    simple_earn_fast_redeem: bool = True
    simple_earn_exclude_assets: set[str] | None = None


@dataclass(slots=True)
class BucketConfig:
    buckets: Dict[str, list[str]]

    def symbols_for(self, bucket: str) -> list[str]:
        return self.buckets.get(bucket.lower(), [])


@dataclass(slots=True)
class CliDefaults:
    dry_run: bool
    profile: str
    drift: float
    max_slippage: float
    min_notional: float
    quote: str


class ConfigError(RuntimeError):
    """Raised when the runtime configuration is invalid."""


def load_env_settings(recv_window: int) -> EnvSettings:
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise ConfigError("Missing BINANCE_API_KEY or BINANCE_API_SECRET environment variables")

    testnet = os.getenv("TESTNET", "false").lower() == "true"
    base_url = "https://testnet.binance.vision" if testnet else "https://api.binance.com"

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    openrouter_models = _load_openrouter_models()
    model_name = openrouter_models[0] if openrouter_models else None
    model_fallback = openrouter_models[1] if len(openrouter_models) > 1 else None
    model_second_fallback = openrouter_models[2] if len(openrouter_models) > 2 else None
    simple_earn_enabled = _parse_bool(os.getenv("SIMPLE_EARN_ENABLED", "false"))
    simple_earn_fast_redeem = _parse_bool(os.getenv("SIMPLE_EARN_FAST_REDEEM", "true"))
    exclude_assets = {
        token.strip().upper()
        for token in os.getenv("SIMPLE_EARN_EXCLUDE_ASSETS", "").split(",")
        if token.strip()
    }

    return EnvSettings(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        base_url=base_url,
        recv_window=recv_window,
        openrouter_api_key=openrouter_api_key,
        openrouter_models=openrouter_models,
        model_name=model_name,
        model_fallback=model_fallback,
        model_second_fallback=model_second_fallback,
        simple_earn_enabled=simple_earn_enabled,
        simple_earn_fast_redeem=simple_earn_fast_redeem,
        simple_earn_exclude_assets=exclude_assets,
    )


def load_bucket_config(path: str | Path | None = None) -> BucketConfig:
    bucket_map = _load_default_buckets()
    cfg_path = Path(path) if path else Path("config.toml")
    if not cfg_path.exists():
        return BucketConfig(buckets=bucket_map)

    import tomllib  # local import to avoid dependency during linting

    with cfg_path.open("rb") as handle:
        data = tomllib.load(handle)

    buckets = data.get("buckets", {})
    for name, symbols in buckets.items():
        if not isinstance(symbols, Iterable):
            continue
        cleaned = [str(sym).upper() for sym in symbols if sym]
        if cleaned:
            bucket_map[str(name).lower()] = cleaned

    return BucketConfig(buckets=bucket_map)


def load_cli_defaults() -> CliDefaults:
    return CliDefaults(
        dry_run=_parse_bool(os.getenv("DEFAULT_DRY_RUN", "true")),
        profile=os.getenv("DEFAULT_PROFILE", "moderate").lower(),
        drift=float(os.getenv("DEFAULT_DRIFT", "0.10")),
        max_slippage=float(os.getenv("DEFAULT_MAX_SLIPPAGE", "0.003")),
        min_notional=float(os.getenv("DEFAULT_MIN_NOTIONAL", "10")),
        quote=os.getenv("DEFAULT_QUOTE", "USDT").upper(),
    )


def load_stable_assets() -> set[str]:
    raw = os.getenv("STABLE_ASSETS", STABLE_ASSETS_FALLBACK)
    return {token.strip().upper() for token in raw.split(",") if token.strip()}


def load_guardrails() -> tuple[float, float]:
    stable_guardrail = float(os.getenv("STABLE_GUARDRAIL", "0.10"))
    btc_guardrail = float(os.getenv("BTC_GUARDRAIL", "0.25"))
    return stable_guardrail, btc_guardrail


def parse_targets_arg(raw: str | None) -> Dict[str, float]:
    if not raw:
        return {}
    targets: Dict[str, float] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ConfigError(f"Invalid target token '{chunk}', expected format symbol=weight")
        symbol, weight = chunk.split("=", 1)
        try:
            targets[symbol.upper()] = float(weight)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ConfigError(f"Invalid weight for '{symbol}': {weight}") from exc
    return targets


def select_profile_targets(profile: str, explicit: Dict[str, float] | None = None) -> Dict[str, float]:
    if explicit:
        return explicit
    mapping = _load_profile_targets()
    try:
        preset = mapping[profile.lower()]
    except KeyError as exc:
        raise ConfigError(f"Unsupported profile '{profile}'") from exc
    return {k.upper(): v for k, v in preset.items()}


def expand_buckets(targets: Dict[str, float], bucket_config: BucketConfig) -> Dict[str, float]:
    expanded: Dict[str, float] = {}
    for key, weight in targets.items():
        bucket_symbols = bucket_config.symbols_for(key.lower())
        if bucket_symbols:
            per_symbol = weight / len(bucket_symbols)
            for symbol in bucket_symbols:
                expanded[symbol.upper()] = expanded.get(symbol.upper(), 0.0) + per_symbol
        else:
            expanded[key.upper()] = expanded.get(key.upper(), 0.0) + weight

    total = sum(expanded.values())
    if total <= 0:
        raise ConfigError("Target weights must sum to a positive value")

    normalized = {symbol: weight / total for symbol, weight in expanded.items()}
    return normalized


def _load_profile_targets() -> Dict[str, Dict[str, float]]:
    mapping: Dict[str, Dict[str, float]] = {}
    for name, fallback in PROFILE_TARGET_FALLBACKS.items():
        env_key = f"PROFILE_TARGETS_{name.upper()}"
        raw = os.getenv(env_key, fallback)
        parsed = parse_targets_arg(raw)
        if not parsed:
            raise ConfigError(f"Profile '{name}' must define at least one target")
        mapping[name] = parsed
    return mapping


def _load_default_buckets() -> Dict[str, list[str]]:
    raw = os.getenv("BUCKETS_JSON", DEFAULT_BUCKETS_JSON)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("BUCKETS_JSON must be valid JSON") from exc
    bucket_map: Dict[str, list[str]] = {}
    for name, symbols in data.items():
        if not isinstance(symbols, Iterable):
            continue
        cleaned = [str(sym).upper() for sym in symbols if sym]
        if cleaned:
            bucket_map[str(name).lower()] = cleaned
    if not bucket_map:
        raise ConfigError("At least one bucket must be configured")
    return bucket_map


def _parse_bool(value: str) -> bool:
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}
    normalized = value.strip().lower()
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    raise ConfigError(f"Invalid boolean value '{value}'")


def _load_openrouter_models() -> tuple[str, ...]:
    registry_models = _load_openrouter_model_registry()
    if registry_models:
        return registry_models

    raw_models = os.getenv("OPENROUTER_MODELS")
    if raw_models is not None:
        models = _parse_model_list(raw_models)
        if not models:
            raise ConfigError("OPENROUTER_MODELS must contain at least one model id")
        return models

    legacy_chain = _parse_model_list(
        ",".join(
            value
            for value in (
                os.getenv("MODEL_NAME", ""),
                os.getenv("MODEL_FALLBACK", ""),
                os.getenv("MODEL_SECOND_FALLBACK", ""),
            )
            if value.strip()
        )
    )
    if legacy_chain:
        return legacy_chain
    return DEFAULT_OPENROUTER_FREE_MODELS


def _load_openrouter_model_registry() -> tuple[str, ...]:
    if os.getenv("OPENROUTER_MODELS_MODE", "").strip().lower() == "manual":
        return ()
    registry_path = Path(
        os.getenv(
            "OPENROUTER_MODELS_REGISTRY",
            str(DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH),
        )
    )
    if not registry_path.exists():
        return ()
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    raw_models = data.get("active_models", [])
    if not isinstance(raw_models, list):
        return ()
    return tuple(str(model).strip() for model in raw_models if str(model).strip())


def _parse_model_list(raw: str) -> tuple[str, ...]:
    seen: set[str] = set()
    models: list[str] = []
    for token in re.split(r"[,;\n\r]+", raw):
        model = token.strip()
        if not model or model in seen:
            continue
        seen.add(model)
        models.append(model)
    return tuple(models)


__all__ = [
    "DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH",
    "DEFAULT_OPENROUTER_FREE_MODELS",
    "BucketConfig",
    "CliDefaults",
    "ConfigError",
    "EnvSettings",
    "expand_buckets",
    "load_bucket_config",
    "load_cli_defaults",
    "load_env_settings",
    "load_guardrails",
    "load_stable_assets",
    "parse_targets_arg",
    "select_profile_targets",
]
