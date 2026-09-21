from __future__ import annotations

from dataclasses import dataclass


VALID_MODES = {"off", "observe", "enforce"}


@dataclass(frozen=True, slots=True)
class CostGateDecision:
    mode: str
    status: str
    allowed: bool
    expected_benefit_bps: float | None
    estimated_cost_bps: float | None
    net_benefit_bps: float | None
    reason: str


def evaluate_cost_gate(
    *,
    mode: str,
    expected_benefit_bps: float | None,
    estimated_cost_bps: float | None,
    min_net_benefit_bps: float | None,
) -> CostGateDecision:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in VALID_MODES:
        raise ValueError(f"Unsupported cost gate mode: {mode}")
    if normalized_mode == "off":
        return CostGateDecision(
            mode=normalized_mode,
            status="disabled",
            allowed=True,
            expected_benefit_bps=expected_benefit_bps,
            estimated_cost_bps=estimated_cost_bps,
            net_benefit_bps=None,
            reason="cost gate disabled",
        )
    if (
        expected_benefit_bps is None
        or estimated_cost_bps is None
        or min_net_benefit_bps is None
    ):
        return CostGateDecision(
            mode=normalized_mode,
            status="uncalibrated",
            allowed=True,
            expected_benefit_bps=expected_benefit_bps,
            estimated_cost_bps=estimated_cost_bps,
            net_benefit_bps=None,
            reason="benefit, cost, and minimum net threshold are required",
        )

    net_benefit = expected_benefit_bps - estimated_cost_bps
    below_threshold = net_benefit < min_net_benefit_bps
    return CostGateDecision(
        mode=normalized_mode,
        status="blocked" if below_threshold and normalized_mode == "enforce" else "allowed",
        allowed=not below_threshold or normalized_mode != "enforce",
        expected_benefit_bps=expected_benefit_bps,
        estimated_cost_bps=estimated_cost_bps,
        net_benefit_bps=net_benefit,
        reason=(
            "net benefit below configured threshold"
            if below_threshold
            else "net benefit meets configured threshold"
        ),
    )
