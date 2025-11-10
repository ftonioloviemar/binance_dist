from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

import json
import logging
import math
import re
import time

import requests

from binance_client import Balance, SymbolFilters
from config import load_guardrails, load_stable_assets

logger = logging.getLogger(__name__)

STABLE_ASSETS = load_stable_assets()
STABLE_GUARDRAIL, BTC_GUARDRAIL = load_guardrails()
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(slots=True)
class AssetPosition:
    asset: str
    quantity: float
    price: float
    value: float
    weight: float


@dataclass(slots=True)
class PortfolioSnapshot:
    quote_asset: str
    total_value: float
    positions: Dict[str, AssetPosition]

    def weight(self, asset: str) -> float:
        position = self.positions.get(asset.upper())
        return position.weight if position else 0.0


@dataclass(slots=True)
class RebalanceDecision:
    rebalance_needed: bool
    deltas: Dict[str, float]


@dataclass(slots=True)
class TradeInstruction:
    symbol: str
    asset: str
    quote: str
    side: str
    quantity: float
    price: float
    notional: float
    order_type: str
    limit_price: float | None


@dataclass(slots=True)
class ExecutionResult:
    instruction: TradeInstruction
    status: str
    order_id: str | None
    detail: Mapping[str, object] | None


@dataclass(slots=True)
class AIAdvice:
    targets: Dict[str, float]
    action: str
    rationale: str | None = None


class PortfolioError(RuntimeError):
    pass


def compute_current_weights(
    balances: Sequence[Balance],
    asset_prices: Mapping[str, float],
    quote_asset: str,
) -> PortfolioSnapshot:
    quote = quote_asset.upper()
    positions: Dict[str, AssetPosition] = {}
    total_value = 0.0
    for balance in balances:
        asset = balance.asset.upper()
        quantity = balance.total
        if quantity <= 0:
            continue
        if asset == quote:
            price = 1.0
        else:
            price = asset_prices.get(asset)
            if price is None:
                logger.debug("Skipping asset %s because no quote price was found", asset)
                continue
        value = quantity * price
        total_value += value
        positions[asset] = AssetPosition(
            asset=asset,
            quantity=quantity,
            price=price,
            value=value,
            weight=0.0,
        )

    if total_value == 0:
        raise PortfolioError("Unable to compute weights for an empty portfolio")

    for asset, position in positions.items():
        position.weight = position.value / total_value
    return PortfolioSnapshot(quote_asset=quote, total_value=total_value, positions=positions)


def validate_target_map(raw: Mapping[str, float]) -> Dict[str, float]:
    cleaned: Dict[str, float] = {}
    for asset, weight in raw.items():
        weight_value = float(weight)
        if weight_value < 0:
            raise PortfolioError(f"Negative weight provided for {asset}")
        cleaned[asset.upper()] = cleaned.get(asset.upper(), 0.0) + weight_value
    total = sum(cleaned.values())
    if total <= 0:
        raise PortfolioError("Target weights must sum to more than zero")
    normalized = {asset: value / total for asset, value in cleaned.items()}
    return normalized


def ai_refine_targets(
    *,
    api_key: str | None,
    models: Sequence[str],
    portfolio_value: float,
    current_weights: Mapping[str, float],
    proposed_weights: Mapping[str, float],
    portfolio_context: Mapping[str, Any] | None = None,
) -> AIAdvice:
    default_advice = AIAdvice(targets=dict(proposed_weights), action="redistribute", rationale=None)
    if not api_key or not models:
        return default_advice

    rationale: str | None = None
    for model_name in models:
        weights, rationale, action = _call_openrouter_model(
            api_key=api_key,
            model_name=model_name,
            portfolio_value=portfolio_value,
            current_weights=current_weights,
            proposed_weights=proposed_weights,
            portfolio_context=portfolio_context,
        )
        if weights or action:
            guarded = _apply_ai_guardrails(weights or proposed_weights, proposed_weights)
            normalized_action = _normalize_action(action)
            return AIAdvice(targets=guarded, action=normalized_action, rationale=rationale)
    return default_advice


def _call_openrouter_model(
    *,
    api_key: str,
    model_name: str,
    portfolio_value: float,
    current_weights: Mapping[str, float],
    proposed_weights: Mapping[str, float],
    portfolio_context: Mapping[str, Any] | None = None,
) -> tuple[Dict[str, float], str | None, str | None]:
    context_payload: Dict[str, Any] = {
        "currentWeights": current_weights,
        "proposedWeights": proposed_weights,
        "portfolioValue": portfolio_value,
    }
    if portfolio_context:
        context_payload["holdings"] = portfolio_context
    prompt = (
        "Analyze the consolidated crypto portfolio described by the following JSON context: {context}. "
        "Decide whether to maintain the current allocation ('maintain') or recommend a redistribution ('redistribute'). "
        "If redistribution is recommended, adjust target weights within +/-0.05 absolute weight from the proposed targets. "
        "Always respond with JSON containing: "
        "\"action\" (\"maintain\" or \"redistribute\"), "
        "\"targets\" (object mapping asset symbol to weight), and "
        "\"rationale\" (short string)."
    ).format(context=json.dumps(context_payload))
    payload = {
        "model": model_name,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a disciplined portfolio analyst. Output JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network guard
        logger.warning("OpenRouter request failed for model %s: %s", model_name, exc)
        return {}, None, None

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    weights, rationale, action = _extract_plan_from_message(content)
    return weights, rationale, action


def decide_rebalance(
    snapshot: PortfolioSnapshot,
    target_weights: Mapping[str, float],
    drift_threshold: float,
) -> RebalanceDecision:
    deltas: Dict[str, float] = {}
    rebalance = False
    for asset in set(snapshot.positions) | set(target_weights):
        target = target_weights.get(asset, 0.0)
        current = snapshot.weight(asset)
        delta = target - current
        deltas[asset] = delta
        if abs(delta) > drift_threshold:
            rebalance = True

    stable_weight = sum(
        snapshot.weight(asset) for asset in snapshot.positions if asset in STABLE_ASSETS or asset == snapshot.quote_asset
    )
    if stable_weight < STABLE_GUARDRAIL:
        rebalance = True

    return RebalanceDecision(rebalance_needed=rebalance, deltas=deltas)


def build_trades(
    *,
    snapshot: PortfolioSnapshot,
    decision: RebalanceDecision,
    prices: Mapping[str, float],
    filters: Mapping[str, SymbolFilters],
    min_notional: float,
    max_slippage: float,
    rejections: list[str] | None = None,
) -> list[TradeInstruction]:
    instructions: list[TradeInstruction] = []
    reject_log = rejections if rejections is not None else []
    quote = snapshot.quote_asset
    for asset, delta_weight in decision.deltas.items():
        if asset == quote:
            continue
        price = prices.get(asset)
        if price is None or price <= 0:
            reject_log.append(f"{asset}{quote}: missing price data")
            continue
        value_delta = snapshot.total_value * delta_weight
        if abs(value_delta) < min_notional:
            reject_log.append(f"{asset}{quote}: delta {value_delta:.4f} below min notional")
            continue
        quantity = value_delta / price
        if quantity == 0:
            continue
        side = "BUY" if quantity > 0 else "SELL"
        quantity = abs(quantity)
        symbol = f"{asset}{quote}"
        symbol_filters = filters.get(symbol)
        if not symbol_filters:
            logger.warning("Missing exchange filters for %s, skipping trade", symbol)
            reject_log.append(f"{symbol}: exchange info unavailable")
            continue
        quantity = _apply_lot_step(quantity, symbol_filters.lot_step)
        if quantity < symbol_filters.min_qty or quantity > symbol_filters.max_qty > 0:
            reject_log.append(
                f"{symbol}: quantity {quantity:.8f} outside lot bounds ({symbol_filters.min_qty}-{symbol_filters.max_qty})"
            )
            continue
        notional = quantity * price
        required_notional = max(min_notional, symbol_filters.min_notional)
        if notional < required_notional:
            reject_log.append(f"{symbol}: notional {notional:.4f} < min {required_notional}")
            continue
        order_type, limit_price = _select_order_type(
            price=price,
            max_slippage=max_slippage,
            tick_size=symbol_filters.price_tick,
            side=side,
        )
        instructions.append(
            TradeInstruction(
                symbol=symbol,
                asset=asset,
                quote=quote,
                side=side,
                quantity=quantity,
                price=price,
                notional=notional,
                order_type=order_type,
                limit_price=limit_price,
            )
        )
    return instructions


def filter_dust_positions(
    snapshot: PortfolioSnapshot,
    filters: Mapping[str, SymbolFilters],
    min_notional: float,
) -> tuple[PortfolioSnapshot, dict[str, AssetPosition]]:
    tradable: Dict[str, AssetPosition] = {}
    dust: Dict[str, AssetPosition] = {}
    quote = snapshot.quote_asset
    for asset, position in snapshot.positions.items():
        if asset == quote:
            tradable[asset] = position
            continue
        symbol = f"{asset}{quote}"
        symbol_filters = filters.get(symbol)
        required_notional = max(min_notional, symbol_filters.min_notional if symbol_filters else 0.0)
        if position.value >= required_notional:
            tradable[asset] = position
        else:
            dust[asset] = position

    total_value = sum(pos.value for pos in tradable.values())
    if total_value <= 0:
        return snapshot, dust

    normalized_positions: Dict[str, AssetPosition] = {}
    for asset, position in tradable.items():
        normalized_positions[asset] = AssetPosition(
            asset=position.asset,
            quantity=position.quantity,
            price=position.price,
            value=position.value,
            weight=position.value / total_value,
        )
    filtered_snapshot = PortfolioSnapshot(quote_asset=quote, total_value=total_value, positions=normalized_positions)
    return filtered_snapshot, dust


def _extract_plan_from_message(content: str) -> tuple[Dict[str, float], str | None, str | None]:
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {}, None, None
    try:
        payload = json.loads(match.group())
    except json.JSONDecodeError:
        return {}, None, None

    rationale = None
    action = None
    if isinstance(payload, dict) and "rationale" in payload:
        rationale = str(payload.pop("rationale"))
    if isinstance(payload, dict):
        raw_action = payload.get("action") or payload.get("decision") or payload.get("directive")
        if isinstance(raw_action, str):
            action = raw_action.lower()

    def _coerce_weights(data: Mapping[str, object]) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        for key, value in data.items():
            try:
                weights[key.upper()] = float(value)
            except (TypeError, ValueError):
                continue
        return weights

    if isinstance(payload, dict):
        weights = _coerce_weights(payload)
        if weights:
            return weights, rationale, action
        for candidate_key in ("targets", "target", "weights", "allocations", "allocation"):
            candidate = payload.get(candidate_key)
            if isinstance(candidate, Mapping):
                weights = _coerce_weights(candidate)
                if weights:
                    return weights, rationale, action
        for value in payload.values():
            if isinstance(value, Mapping):
                weights = _coerce_weights(value)
                if weights:
                    return weights, rationale, action
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        weights = _coerce_weights(item)
                        if weights:
                            return weights, rationale, action
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, Mapping):
                weights = _coerce_weights(item)
                if weights:
                    return weights, rationale, action

    return {}, rationale, action


def _apply_ai_guardrails(
    weights: Mapping[str, float],
    baseline: Mapping[str, float],
) -> Dict[str, float]:
    guarded = dict(weights)
    for asset, base_value in baseline.items():
        new_value = guarded.get(asset, base_value)
        delta = max(-0.05, min(0.05, new_value - base_value))
        guarded[asset] = base_value + delta

    stable_weight = sum(weight for asset, weight in guarded.items() if asset in STABLE_ASSETS)
    if stable_weight < STABLE_GUARDRAIL:
        target_asset = next((asset for asset in guarded if asset in STABLE_ASSETS), None)
        if target_asset:
            guarded[target_asset] = STABLE_GUARDRAIL
        else:
            guarded["USDT"] = STABLE_GUARDRAIL
    if guarded.get("BTC", 0.0) < BTC_GUARDRAIL:
        guarded["BTC"] = BTC_GUARDRAIL

    normalized = validate_target_map(guarded)
    return normalized


def _apply_lot_step(quantity: float, step_size: float) -> float:
    if step_size <= 0:
        return quantity
    steps = math.floor(quantity / step_size)
    return steps * step_size


def _select_order_type(
    *,
    price: float,
    max_slippage: float,
    tick_size: float,
    side: str,
) -> tuple[str, float | None]:
    if max_slippage <= 0 or tick_size <= 0:
        return "MARKET", None
    slippage_estimate = tick_size / price if price else 0.0
    if slippage_estimate <= max_slippage:
        return "MARKET", None
    adjust = 1 + max_slippage if side == "BUY" else 1 - max_slippage
    limit_price = _apply_tick_size(price * adjust, tick_size, side)
    return "LIMIT", limit_price


def _apply_tick_size(price: float, tick_size: float, side: str) -> float:
    if tick_size <= 0:
        return price
    steps = price / tick_size
    if side == "BUY":
        rounded_steps = math.ceil(steps)
    else:
        rounded_steps = math.floor(steps)
    return rounded_steps * tick_size


def _normalize_action(action: str | None) -> str:
    if not action:
        return "redistribute"
    normalized = action.strip().lower()
    if normalized.startswith(("maintain", "keep", "hold")):
        return "maintain"
    return "redistribute"


__all__ = [
    "AIAdvice",
    "AssetPosition",
    "ExecutionResult",
    "filter_dust_positions",
    "PortfolioError",
    "PortfolioSnapshot",
    "RebalanceDecision",
    "TradeInstruction",
    "ai_refine_targets",
    "build_trades",
    "compute_current_weights",
    "decide_rebalance",
    "validate_target_map",
]
