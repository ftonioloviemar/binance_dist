from __future__ import annotations

from performance_store import load_execution_costs, record_execution_cost


def test_execution_cost_round_trip(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    record_execution_cost(
        db_path,
        {
            "run_id": "run-1",
            "order_id": "10",
            "timestamp": "2026-09-21T12:00:00+00:00",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "gross_notional": "1000.00",
            "commission_quote": "0.01800000",
            "commission_bps": "0.180000",
            "conversion_status": "complete",
        },
    )

    assert load_execution_costs(db_path) == [
        {
            "run_id": "run-1",
            "order_id": "10",
            "timestamp": "2026-09-21T12:00:00+00:00",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "gross_notional": "1000.00",
            "commission_quote": "0.01800000",
            "commission_bps": "0.180000",
            "conversion_status": "complete",
        }
    ]
