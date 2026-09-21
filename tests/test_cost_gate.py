from __future__ import annotations

import pytest

from cost_gate import evaluate_cost_gate


def test_observe_is_safe_and_explicit_when_uncalibrated() -> None:
    decision = evaluate_cost_gate(
        mode="observe",
        expected_benefit_bps=None,
        estimated_cost_bps=None,
        min_net_benefit_bps=None,
    )

    assert decision.status == "uncalibrated"
    assert decision.allowed is True


def test_enforce_blocks_only_with_complete_calibrated_values() -> None:
    decision = evaluate_cost_gate(
        mode="enforce",
        expected_benefit_bps=8.0,
        estimated_cost_bps=6.0,
        min_net_benefit_bps=3.0,
    )

    assert decision.status == "blocked"
    assert decision.allowed is False
    assert decision.net_benefit_bps == 2.0


def test_enforce_allows_uncalibrated_data_without_inventing_block() -> None:
    decision = evaluate_cost_gate(
        mode="enforce",
        expected_benefit_bps=None,
        estimated_cost_bps=6.0,
        min_net_benefit_bps=3.0,
    )

    assert decision.status == "uncalibrated"
    assert decision.allowed is True


def test_invalid_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_cost_gate(
            mode="maybe",
            expected_benefit_bps=None,
            estimated_cost_bps=None,
            min_net_benefit_bps=None,
        )
