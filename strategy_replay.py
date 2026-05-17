from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ReplayCase:
    run_id: str
    max_abs_drift: float
    planned_trade_notionals: Sequence[float]
    realized_volatility: float


@dataclass(frozen=True, slots=True)
class ScenarioBPolicy:
    base_drift_threshold: float
    high_volatility_threshold: float
    high_volatility_multiplier: float
    min_trade_notional: float
    fee_rate: float
    slippage_rate: float


@dataclass(frozen=True, slots=True)
class ReplayDecision:
    run_id: str
    action: str
    effective_threshold: float
    tradable_order_count: int
    skipped_small_trade_count: int
    turnover_proxy: float
    estimated_cost_proxy: float


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    decisions: list[ReplayDecision]
    order_count: int
    skipped_small_trade_count: int
    turnover_proxy: float
    estimated_cost_proxy: float
    drift_breach_count: int


def replay_scenario_b(
    cases: Sequence[ReplayCase], policy: ScenarioBPolicy
) -> ReplaySummary:
    decisions: list[ReplayDecision] = []
    drift_breach_count = 0
    total_order_count = 0
    total_skipped_small_trade_count = 0
    total_turnover_proxy = 0.0
    total_estimated_cost_proxy = 0.0

    for case in cases:
        threshold = _effective_threshold(case.realized_volatility, policy)
        if case.max_abs_drift <= threshold:
            decisions.append(
                ReplayDecision(
                    run_id=case.run_id,
                    action="skip_drift",
                    effective_threshold=threshold,
                    tradable_order_count=0,
                    skipped_small_trade_count=0,
                    turnover_proxy=0.0,
                    estimated_cost_proxy=0.0,
                )
            )
            continue

        drift_breach_count += 1
        tradable_notionals = [
            notional
            for notional in case.planned_trade_notionals
            if notional >= policy.min_trade_notional
        ]
        skipped_small_trade_count = len(case.planned_trade_notionals) - len(
            tradable_notionals
        )
        turnover_proxy = sum(tradable_notionals)
        estimated_cost_proxy = turnover_proxy * (policy.fee_rate + policy.slippage_rate)
        action = "rebalance" if tradable_notionals else "skip_cost"

        decisions.append(
            ReplayDecision(
                run_id=case.run_id,
                action=action,
                effective_threshold=threshold,
                tradable_order_count=len(tradable_notionals),
                skipped_small_trade_count=skipped_small_trade_count,
                turnover_proxy=turnover_proxy,
                estimated_cost_proxy=estimated_cost_proxy,
            )
        )
        total_order_count += len(tradable_notionals)
        total_skipped_small_trade_count += skipped_small_trade_count
        total_turnover_proxy += turnover_proxy
        total_estimated_cost_proxy += estimated_cost_proxy

    return ReplaySummary(
        decisions=decisions,
        order_count=total_order_count,
        skipped_small_trade_count=total_skipped_small_trade_count,
        turnover_proxy=total_turnover_proxy,
        estimated_cost_proxy=total_estimated_cost_proxy,
        drift_breach_count=drift_breach_count,
    )


def _effective_threshold(realized_volatility: float, policy: ScenarioBPolicy) -> float:
    if realized_volatility >= policy.high_volatility_threshold:
        return policy.base_drift_threshold * policy.high_volatility_multiplier
    return policy.base_drift_threshold
