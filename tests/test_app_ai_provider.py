from __future__ import annotations

from types import SimpleNamespace

import app
import pytest
from ai_contract import AnalysisRequest
from portfolio import AIAdvice, AIModelFailure


class FakeAuditor:
    def __init__(self) -> None:
        self.steps = []

    def log_step(self, **kwargs) -> None:
        self.steps.append(kwargs)


def _settings(provider: str) -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider=provider,
        openrouter_api_key="secret-openrouter",
        openrouter_models=("secret/model",),
        codex_cli_executable=None,
        codex_cli_timeout_seconds=120,
    )


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        portfolio_value=1000.0,
        current_weights={"BTC": 0.5, "ETH": 0.4, "USDT": 0.1},
        proposed_weights={"BTC": 0.5, "ETH": 0.4, "USDT": 0.1},
        portfolio_context={"sensitive": "holdings-secret"},
    )


def test_codex_selection_never_calls_openrouter_and_preserves_maintain(monkeypatch) -> None:
    monkeypatch.setattr(
        app,
        "analyze_with_codex",
        lambda request, settings: AIAdvice(
            targets=dict(request.proposed_weights),
            action="maintain",
            rationale="sensitive rationale",
            model_used="gpt-6-luna",
            provider="codex_cli",
            reasoning_effort="medium",
            duration_seconds=1.25,
        ),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("OpenRouter called")),
    )
    monkeypatch.setattr(
        app,
        "refresh_openrouter_models",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("curator called")),
    )
    auditor = FakeAuditor()

    advice = app._resolve_ai_advice(_settings("codex_cli"), _request(), auditor)

    assert advice.action == "maintain"
    assert advice.provider == "codex_cli"
    audit_text = " ".join(str(step) for step in auditor.steps)
    assert "gpt-6-luna" in audit_text
    assert "medium" in audit_text
    assert "secret-openrouter" not in audit_text
    assert "holdings-secret" not in audit_text
    assert "sensitive rationale" not in audit_text


def test_codex_failure_returns_proposed_targets_without_openrouter(monkeypatch) -> None:
    request = AnalysisRequest(
        portfolio_value=1000.0,
        current_weights={"BTC": 0.1, "USDT": 0.9},
        proposed_weights={"BTC": 0.1, "USDT": 0.9},
    )
    proposed = dict(request.proposed_weights)
    monkeypatch.setattr(
        app,
        "analyze_with_codex",
        lambda request, settings: AIAdvice(
            targets=dict(request.proposed_weights),
            action="redistribute",
            provider="codex_cli",
            model_failures=(AIModelFailure("gpt-6-luna", "timeout", "safe"),),
        ),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("OpenRouter called")),
    )
    monkeypatch.setattr(
        app,
        "refresh_openrouter_models",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("curator called")),
    )

    advice = app._resolve_ai_advice(_settings("codex_cli"), request, FakeAuditor())

    assert advice.targets == proposed
    assert advice.action == "redistribute"


def test_refresh_gate_never_refreshes_for_codex_or_off(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(app, "refresh_openrouter_models", lambda **kwargs: calls.append(kwargs))
    advice = AIAdvice(
        targets={"BTC": 1.0},
        action="redistribute",
        first_model_failed=True,
    )

    for provider in ("codex_cli", "off"):
        app._refresh_openrouter_models_after_failure(
            SimpleNamespace(ai_provider=provider, openrouter_api_key="key"),
            advice,
            ["model"],
            FakeAuditor(),
        )

    assert calls == []


def test_refresh_gate_preserves_legacy_openrouter_refresh(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(app, "refresh_openrouter_models", lambda **kwargs: calls.append(kwargs))
    advice = AIAdvice(
        targets={"BTC": 1.0},
        action="redistribute",
        first_model_failed=True,
    )

    app._refresh_openrouter_models_after_failure(
        SimpleNamespace(ai_provider="openrouter", openrouter_api_key="key"),
        advice,
        ["model"],
        FakeAuditor(),
    )

    assert len(calls) == 1


def test_codex_recommendation_keeps_existing_weight_guardrails(monkeypatch) -> None:
    monkeypatch.setattr(
        app,
        "analyze_with_codex",
        lambda request, settings: AIAdvice(
            targets={"BTC": 0.9, "ETH": 0.1, "USDT": 0.0},
            action="redistribute",
            provider="codex_cli",
        ),
    )

    advice = app._resolve_ai_advice(_settings("codex_cli"), _request(), FakeAuditor())

    assert advice.targets == pytest.approx({"BTC": 0.55, "ETH": 0.35, "USDT": 0.1})


def test_off_provider_returns_proposed_weights_without_any_ai_call(monkeypatch) -> None:
    monkeypatch.setattr(
        app,
        "analyze_with_codex",
        lambda *args: (_ for _ in ()).throw(AssertionError("Codex called")),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("OpenRouter called")),
    )

    advice = app._resolve_ai_advice(_settings("off"), _request(), FakeAuditor())

    assert advice.targets == dict(_request().proposed_weights)
    assert advice.action == "redistribute"
    assert advice.provider == "off"


def test_legacy_provider_still_dispatches_to_openrouter(monkeypatch) -> None:
    expected = AIAdvice(targets={"BTC": 1.0}, action="maintain")
    calls = []
    monkeypatch.setattr(app, "ai_refine_targets", lambda **kwargs: calls.append(kwargs) or expected)

    advice = app._resolve_ai_advice(_settings("openrouter"), _request(), FakeAuditor())

    assert advice is expected
    assert calls[0]["api_key"] == "secret-openrouter"
