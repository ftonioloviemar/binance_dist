from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Mapping


MAX_RATIONALE_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    portfolio_value: float
    current_weights: Mapping[str, float]
    proposed_weights: Mapping[str, float]
    portfolio_context: Mapping[str, Any] | None = None


def build_analysis_prompt(request: AnalysisRequest) -> str:
    context_payload: dict[str, Any] = {
        "currentWeights": request.current_weights,
        "proposedWeights": request.proposed_weights,
        "portfolioValue": request.portfolio_value,
    }
    if request.portfolio_context:
        context_payload["holdings"] = request.portfolio_context

    return (
        "Analyze the consolidated crypto portfolio described by the following JSON context: {context}. "
        "Decide whether to maintain the current allocation ('maintain') or recommend a redistribution ('redistribute'). "
        "If redistribution is recommended, adjust target weights within +/-0.05 absolute weight from the proposed targets. "
        "Always respond with JSON containing: "
        '"action" ("maintain" or "redistribute"), '
        '"targets" (object mapping asset symbol to weight), and '
        '"rationale" (short string).'
    ).format(context=json.dumps(context_payload))


def build_analysis_schema(request: AnalysisRequest) -> dict[str, Any]:
    symbols = tuple(request.proposed_weights)
    if not symbols or any(not isinstance(symbol, str) or not symbol for symbol in symbols):
        raise ValueError("Proposed target symbols must be non-empty strings")

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["maintain", "redistribute"]},
            "targets": {
                "type": "object",
                "properties": {
                    symbol: {"type": "number", "minimum": 0} for symbol in symbols
                },
                "required": list(symbols),
                "additionalProperties": False,
            },
            "rationale": {"type": "string", "maxLength": MAX_RATIONALE_LENGTH},
        },
        "required": ["action", "targets", "rationale"],
        "additionalProperties": False,
    }


def parse_analysis_response(
    content: str, request: AnalysisRequest
) -> tuple[dict[str, float], str, str]:
    if not isinstance(content, str):
        raise ValueError("Analysis response must be text")

    try:
        payload = json.loads(
            content,
            parse_constant=_reject_non_finite_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Analysis response is not valid JSON") from exc

    if not isinstance(payload, dict) or set(payload) != {"action", "targets", "rationale"}:
        raise ValueError("Analysis response fields do not match the contract")

    action = payload["action"]
    if not isinstance(action, str) or action not in {"maintain", "redistribute"}:
        raise ValueError("Analysis action is not supported")

    raw_targets = payload["targets"]
    expected_symbols = set(request.proposed_weights)
    if not isinstance(raw_targets, dict) or set(raw_targets) != expected_symbols:
        raise ValueError("Analysis targets must match the proposed symbols")

    targets: dict[str, float] = {}
    for symbol, raw_weight in raw_targets.items():
        if isinstance(raw_weight, bool) or not isinstance(raw_weight, (int, float)):
            raise ValueError(f"Analysis target for {symbol} must be a number")
        weight = float(raw_weight)
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"Analysis target for {symbol} must be finite and non-negative")
        targets[symbol] = weight

    total_weight = sum(targets.values())
    if not math.isfinite(total_weight) or total_weight <= 0:
        raise ValueError("Analysis target weights must sum to a finite value greater than zero")

    rationale = payload["rationale"]
    if not isinstance(rationale, str) or len(rationale) > MAX_RATIONALE_LENGTH:
        raise ValueError("Analysis rationale must be text of at most 2000 characters")

    return targets, action, rationale


def _reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON value: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result
