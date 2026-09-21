from __future__ import annotations

from performance import compare_snapshots
from performance_store import load_external_flows, record_external_flow


def _snapshot(*, phase: str, btc_price: str, btc_value: str, total: str) -> dict:
    return {
        "run_id": "run-1",
        "phase": phase,
        "timestamp": f"2026-09-21T12:00:0{'0' if phase == 'before' else '1'}+00:00",
        "quote_asset": "USDT",
        "spot_value": total,
        "earn_value": "0.00",
        "total_value": total,
        "prices": {"BTC": btc_price},
        "asset_values": {"spot:BTC": btc_value},
        "data_quality": "complete",
        "external_flow_status": "unknown",
        "missing_prices": [],
    }


def test_compare_snapshots_reports_observed_change_and_hold_benchmark() -> None:
    result = compare_snapshots(
        _snapshot(phase="before", btc_price="100", btc_value="100", total="100"),
        _snapshot(phase="after", btc_price="110", btc_value="110", total="110"),
    )

    assert result["observed_change"] == "10.00"
    assert result["hold_value"] == "110.00"
    assert result["hold_change"] == "10.00"
    assert result["attribution_status"] == "not_attributed"
    assert result["profit"] is None


def test_compare_snapshots_does_not_invent_hold_when_final_price_is_missing() -> None:
    before = _snapshot(phase="before", btc_price="100", btc_value="100", total="100")
    after = _snapshot(phase="after", btc_price="100", btc_value="100", total="100")
    after["prices"] = {}

    result = compare_snapshots(before, after)

    assert result["hold_value"] is None
    assert result["hold_change"] is None
    assert result["attribution_status"] == "incomplete"
    assert result["missing_assets"] == ["BTC"]


def test_external_flow_round_trip(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    record_external_flow(
        db_path,
        {
            "flow_id": "flow-1",
            "timestamp": "2026-09-21T12:00:00+00:00",
            "asset": "USDT",
            "quote_value": "100.00",
            "direction": "in",
            "source": "manual",
            "confidence": "confirmed",
        },
    )

    assert load_external_flows(db_path) == [
        {
            "flow_id": "flow-1",
            "timestamp": "2026-09-21T12:00:00+00:00",
            "asset": "USDT",
            "quote_value": "100.00",
            "direction": "in",
            "source": "manual",
            "confidence": "confirmed",
        }
    ]
