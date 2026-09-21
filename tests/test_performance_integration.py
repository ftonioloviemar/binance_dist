from __future__ import annotations

import json
from decimal import Decimal

from app import _build_performance_snapshot_payload
from binance_client import Balance, SimpleEarnPosition


def test_build_performance_snapshot_payload_separates_spot_and_earn() -> None:
    payload = _build_performance_snapshot_payload(
        run_id="run-1",
        phase="before",
        quote="USDT",
        spot_balances=[Balance(asset="USDT", free=100.0, locked=0.0)],
        earn_positions=[
            SimpleEarnPosition(
                product_id="p1",
                asset="BTC",
                total_amount=0.01,
                redeemable_amount=0.01,
                can_fast_redeem=True,
            )
        ],
        prices={"BTC": 20000.0},
        timestamp="2026-09-21T12:00:00+00:00",
    )

    assert payload["spot_value"] == "100.00"
    assert payload["earn_value"] == "200.00"
    assert json.loads(json.dumps(payload))["data_quality"] == "complete"


def test_build_performance_snapshot_payload_marks_simulation() -> None:
    payload = _build_performance_snapshot_payload(
        run_id="run-1",
        phase="after",
        quote="USDT",
        spot_balances=[],
        earn_positions=[],
        prices={},
        timestamp="2026-09-21T12:00:00+00:00",
        data_quality="simulation",
    )

    assert payload["data_quality"] == "simulation"
    assert payload["total_value"] == "0.00"
