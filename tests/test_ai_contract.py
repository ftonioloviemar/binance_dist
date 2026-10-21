from __future__ import annotations

import json

import pytest

from ai_contract import (
    AnalysisRequest,
    build_analysis_prompt,
    build_analysis_schema,
    parse_analysis_response,
)


@pytest.fixture
def request_data() -> AnalysisRequest:
    return AnalysisRequest(
        portfolio_value=1000.0,
        current_weights={"BTC": 0.5, "USDT": 0.5},
        proposed_weights={"BTC": 0.4, "USDT": 0.6},
        portfolio_context={"holdings": [{"asset": "BTC", "value": 500.0}]},
    )


def test_prompt_contains_existing_portfolio_context(request_data: AnalysisRequest) -> None:
    prompt = build_analysis_prompt(request_data)

    assert "maintain" in prompt
    assert "redistribute" in prompt
    assert '"portfolioValue": 1000.0' in prompt
    assert '"currentWeights": {"BTC": 0.5, "USDT": 0.5}' in prompt
    assert '"proposedWeights": {"BTC": 0.4, "USDT": 0.6}' in prompt
    assert '"holdings"' in prompt


def test_schema_locks_response_to_proposed_symbols(request_data: AnalysisRequest) -> None:
    schema = build_analysis_schema(request_data)

    assert schema["required"] == ["action", "targets", "rationale"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["action"]["enum"] == ["maintain", "redistribute"]
    targets_schema = schema["properties"]["targets"]
    assert targets_schema["required"] == ["BTC", "USDT"]
    assert targets_schema["additionalProperties"] is False
    assert set(targets_schema["properties"]) == {"BTC", "USDT"}
    assert all(
        field_schema == {"type": "number", "minimum": 0}
        for field_schema in targets_schema["properties"].values()
    )


@pytest.mark.parametrize("symbol", ["", 1, None])
def test_schema_rejects_invalid_symbols(symbol: object) -> None:
    request = AnalysisRequest(
        portfolio_value=1000.0,
        current_weights={},
        proposed_weights=dict.fromkeys([symbol], 1.0),
    )

    with pytest.raises(ValueError, match="non-empty strings"):
        build_analysis_schema(request)


def test_parse_maintain_preserves_action_and_weights(request_data: AnalysisRequest) -> None:
    content = json.dumps(
        {
            "action": "maintain",
            "targets": {"BTC": 0.4, "USDT": 0.6},
            "rationale": "Keep the proposed allocation.",
        }
    )

    targets, action, rationale = parse_analysis_response(content, request_data)

    assert targets == {"BTC": 0.4, "USDT": 0.6}
    assert action == "maintain"
    assert rationale == "Keep the proposed allocation."


@pytest.mark.parametrize(
    "targets",
    [
        {"BTC": True, "USDT": 0.6},
        {"BTC": -0.1, "USDT": 1.1},
        {"BTC": float("nan"), "USDT": 1.0},
        {"BTC": float("inf"), "USDT": 1.0},
        {"BTC": float("-inf"), "USDT": 1.0},
        {"BTC": 0.0, "USDT": 0.0},
        {"BTC": 0.4},
        {"BTC": 0.4, "USDT": 0.5, "SOL": 0.1},
        [],
    ],
)
def test_parse_rejects_invalid_target_values_and_symbols(
    request_data: AnalysisRequest, targets: object
) -> None:
    content = json.dumps(
        {"action": "redistribute", "targets": targets, "rationale": "Adjust."}
    )

    with pytest.raises(ValueError):
        parse_analysis_response(content, request_data)


@pytest.mark.parametrize(
    "payload",
    [
        {"targets": {"BTC": 0.4, "USDT": 0.6}, "rationale": "ok"},
        {
            "action": "hold",
            "targets": {"BTC": 0.4, "USDT": 0.6},
            "rationale": "ok",
        },
        {
            "action": "redistribute",
            "targets": {"BTC": 0.4, "USDT": 0.6},
            "rationale": None,
        },
        {
            "action": "redistribute",
            "targets": {"BTC": 0.4, "USDT": 0.6},
            "rationale": "x" * 2001,
        },
        {
            "action": "redistribute",
            "targets": {"BTC": 0.4, "USDT": 0.6},
            "rationale": "ok",
            "extra": "field",
        },
    ],
)
def test_parse_rejects_invalid_response_fields(
    request_data: AnalysisRequest, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        parse_analysis_response(json.dumps(payload), request_data)


@pytest.mark.parametrize("action", [[], {}])
def test_parse_rejects_non_string_action(
    request_data: AnalysisRequest, action: object
) -> None:
    content = json.dumps(
        {
            "action": action,
            "targets": {"BTC": 0.4, "USDT": 0.6},
            "rationale": "Invalid action type.",
        }
    )

    with pytest.raises(ValueError):
        parse_analysis_response(content, request_data)


@pytest.mark.parametrize("content", ["", "{", "null", "[]", '{"a": NaN}'])
def test_parse_rejects_empty_malformed_and_nonfinite_json(
    request_data: AnalysisRequest, content: str
) -> None:
    with pytest.raises(ValueError):
        parse_analysis_response(content, request_data)


def test_parse_accepts_rationale_at_maximum_length(request_data: AnalysisRequest) -> None:
    rationale = "x" * 2000
    content = json.dumps(
        {
            "action": "redistribute",
            "targets": {"BTC": 0.4, "USDT": 0.6},
            "rationale": rationale,
        }
    )

    targets, action, parsed_rationale = parse_analysis_response(content, request_data)

    assert targets == request_data.proposed_weights
    assert action == "redistribute"
    assert parsed_rationale == rationale


def test_parse_rejects_duplicate_json_object_keys(request_data: AnalysisRequest) -> None:
    content = (
        '{"action":"redistribute","targets":{"BTC":0.4,"BTC":0.3,'
        '"USDT":0.6},"rationale":"ambiguous"}'
    )

    with pytest.raises(ValueError):
        parse_analysis_response(content, request_data)


def test_parse_rejects_finite_weights_whose_sum_overflows(
    request_data: AnalysisRequest,
) -> None:
    content = json.dumps(
        {
            "action": "redistribute",
            "targets": {"BTC": 1e308, "USDT": 1e308},
            "rationale": "Weights overflow when summed.",
        }
    )

    with pytest.raises(ValueError, match="finite value greater than zero"):
        parse_analysis_response(content, request_data)
