from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests

from config import DEFAULT_OPENROUTER_FREE_MODELS
from portfolio import OPENROUTER_ENDPOINT, _extract_plan_from_message

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_ENDPOINT = "https://openrouter.ai/api/v1/models"
DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH = Path("state/openrouter_models.json")

_POOR_FIT_TOKENS = (
    "lyria",
    "music",
    "clip",
    "uncensored",
    "venice",
)
_KNOWN_PRIORITY = {
    model_id: index for index, model_id in enumerate(DEFAULT_OPENROUTER_FREE_MODELS)
}


@dataclass(frozen=True, slots=True)
class FreeModelCandidate:
    model_id: str
    name: str
    context_length: int
    max_completion_tokens: int | None
    supported_parameters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OpenRouterModelRegistry:
    active_models: tuple[str, ...]
    quarantined_models: dict[str, str]
    generated_at: str

    @classmethod
    def load(cls, path: str | Path = DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH) -> "OpenRouterModelRegistry":
        registry_path = Path(path)
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        return cls(
            active_models=tuple(str(model) for model in data.get("active_models", [])),
            quarantined_models={
                str(model): str(reason)
                for model, reason in data.get("quarantined_models", {}).items()
            },
            generated_at=str(data.get("generated_at", "")),
        )

    def save(self, path: str | Path = DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH) -> None:
        registry_path = Path(path)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": self.generated_at,
            "active_models": list(self.active_models),
            "quarantined_models": self.quarantined_models,
        }
        registry_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def refresh_openrouter_models(
    *,
    api_key: str | None,
    current_models: Sequence[str],
    failed_primary_model: str,
    failure_reason: str,
    registry_path: str | Path = DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH,
    test_models: bool = True,
    max_test_models: int = 8,
) -> OpenRouterModelRegistry:
    response = requests.get(OPENROUTER_MODELS_ENDPOINT, timeout=30)
    response.raise_for_status()
    candidates = rank_free_model_candidates(_parse_catalog(response.json()))
    quarantined = {failed_primary_model: failure_reason}

    ranked_ids = [candidate.model_id for candidate in candidates]
    active_ids = [model_id for model_id in ranked_ids if model_id not in quarantined]

    if api_key and test_models:
        active_ids = _promote_json_valid_models(
            api_key=api_key,
            model_ids=active_ids,
            max_test_models=max_test_models,
        )

    if not active_ids:
        active_ids = [model for model in current_models if model != failed_primary_model]

    registry = OpenRouterModelRegistry(
        active_models=tuple(_dedupe(active_ids)),
        quarantined_models=quarantined,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    registry.save(registry_path)
    logger.info(
        "OpenRouter model registry refreshed after %s failed: %s",
        failed_primary_model,
        failure_reason,
    )
    return registry


def rank_free_model_candidates(
    candidates: Sequence[FreeModelCandidate],
) -> list[FreeModelCandidate]:
    useful = [candidate for candidate in candidates if not _is_poor_fit(candidate)]
    return sorted(useful, key=_candidate_sort_key)


def _parse_catalog(data: Mapping[str, Any]) -> list[FreeModelCandidate]:
    candidates: list[FreeModelCandidate] = []
    for raw_model in data.get("data", []):
        if not isinstance(raw_model, Mapping):
            continue
        pricing = raw_model.get("pricing", {})
        architecture = raw_model.get("architecture", {})
        if not isinstance(pricing, Mapping) or not isinstance(architecture, Mapping):
            continue
        if str(pricing.get("prompt")) != "0" or str(pricing.get("completion")) != "0":
            continue
        if "text" not in architecture.get("input_modalities", []):
            continue
        if "text" not in architecture.get("output_modalities", []):
            continue
        top_provider = raw_model.get("top_provider", {})
        max_completion = None
        if isinstance(top_provider, Mapping):
            raw_max = top_provider.get("max_completion_tokens")
            max_completion = int(raw_max) if isinstance(raw_max, int) else None
        candidates.append(
            FreeModelCandidate(
                model_id=str(raw_model.get("id", "")),
                name=str(raw_model.get("name", "")),
                context_length=int(raw_model.get("context_length", 0) or 0),
                max_completion_tokens=max_completion,
                supported_parameters=tuple(
                    str(value) for value in raw_model.get("supported_parameters", [])
                ),
            )
        )
    return [candidate for candidate in candidates if candidate.model_id]


def _candidate_sort_key(candidate: FreeModelCandidate) -> tuple[int, int, int]:
    known_priority = _KNOWN_PRIORITY.get(candidate.model_id, 10_000)
    capability_score = 0
    params = set(candidate.supported_parameters)
    if "response_format" in params:
        capability_score += 500
    if "structured_outputs" in params:
        capability_score += 400
    if "reasoning" in params or "include_reasoning" in params:
        capability_score += 120
    if candidate.context_length >= 1_000_000:
        capability_score += 200
    elif candidate.context_length >= 262_144:
        capability_score += 100
    elif candidate.context_length >= 131_072:
        capability_score += 50
    return (known_priority, -capability_score, -candidate.context_length)


def _is_poor_fit(candidate: FreeModelCandidate) -> bool:
    haystack = f"{candidate.model_id} {candidate.name}".lower()
    return any(token in haystack for token in _POOR_FIT_TOKENS)


def _promote_json_valid_models(
    *,
    api_key: str,
    model_ids: Sequence[str],
    max_test_models: int,
) -> list[str]:
    tested = list(model_ids[:max_test_models])
    untested = list(model_ids[max_test_models:])
    valid = [model_id for model_id in tested if _model_returns_valid_json(api_key, model_id)]
    return valid + untested if valid else list(model_ids)


def _model_returns_valid_json(api_key: str, model_id: str) -> bool:
    payload = {
        "model": model_id,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Output JSON only."},
            {
                "role": "user",
                "content": (
                    'Return {"action":"redistribute","targets":{"BTC":0.4,"USDT":0.6},'
                    '"rationale":"ok"} and nothing else.'
                ),
            },
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(
            OPENROUTER_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OpenRouter model validation failed for %s: %s", model_id, exc)
        return False
    weights, _rationale, action = _extract_plan_from_message(str(content))
    return bool(action and weights)


def _dedupe(model_ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model_id in model_ids:
        if model_id in seen:
            continue
        seen.add(model_id)
        result.append(model_id)
    return result


__all__ = [
    "DEFAULT_OPENROUTER_MODEL_REGISTRY_PATH",
    "FreeModelCandidate",
    "OpenRouterModelRegistry",
    "rank_free_model_candidates",
    "refresh_openrouter_models",
]
