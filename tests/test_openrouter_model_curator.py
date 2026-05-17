from __future__ import annotations

import json
from pathlib import Path

import requests

from openrouter_model_curator import (
    FreeModelCandidate,
    OpenRouterModelRegistry,
    rank_free_model_candidates,
    refresh_openrouter_models,
)


def test_rank_free_model_candidates_prioritizes_useful_json_models() -> None:
    candidates = [
        FreeModelCandidate(
            model_id="google/lyria-3-pro-preview",
            name="Google: Lyria 3 Pro Preview",
            context_length=1048576,
            max_completion_tokens=65536,
            supported_parameters=("response_format",),
        ),
        FreeModelCandidate(
            model_id="small/tiny:free",
            name="Tiny free",
            context_length=32768,
            max_completion_tokens=8192,
            supported_parameters=("temperature",),
        ),
        FreeModelCandidate(
            model_id="nvidia/nemotron-3-super-120b-a12b:free",
            name="NVIDIA: Nemotron 3 Super (free)",
            context_length=1000000,
            max_completion_tokens=262144,
            supported_parameters=("response_format", "structured_outputs"),
        ),
    ]

    ranked = rank_free_model_candidates(candidates)

    assert [candidate.model_id for candidate in ranked] == [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "small/tiny:free",
    ]


def test_refresh_openrouter_models_quarantines_failed_primary_and_persists(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "openrouter_models.json"

    class CatalogResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {
                        "id": "broken/primary:free",
                        "name": "Broken Primary",
                        "context_length": 131072,
                        "pricing": {"prompt": "0", "completion": "0"},
                        "architecture": {
                            "input_modalities": ["text"],
                            "output_modalities": ["text"],
                        },
                        "top_provider": {"max_completion_tokens": 8192},
                        "supported_parameters": ["response_format"],
                    },
                    {
                        "id": "openrouter/owl-alpha",
                        "name": "Owl Alpha",
                        "context_length": 1048756,
                        "pricing": {"prompt": "0", "completion": "0"},
                        "architecture": {
                            "input_modalities": ["text"],
                            "output_modalities": ["text"],
                        },
                        "top_provider": {"max_completion_tokens": 262144},
                        "supported_parameters": ["response_format", "structured_outputs"],
                    },
                ]
            }

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: CatalogResponse())

    registry = refresh_openrouter_models(
        api_key=None,
        current_models=("broken/primary:free", "openrouter/owl-alpha"),
        failed_primary_model="broken/primary:free",
        failure_reason="404",
        registry_path=registry_path,
        test_models=False,
    )

    assert registry.active_models == ("openrouter/owl-alpha",)
    assert registry.quarantined_models["broken/primary:free"] == "404"
    assert json.loads(registry_path.read_text(encoding="utf-8"))["active_models"] == [
        "openrouter/owl-alpha"
    ]
    assert OpenRouterModelRegistry.load(registry_path).active_models == (
        "openrouter/owl-alpha",
    )
