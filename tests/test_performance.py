from __future__ import annotations

from performance import _aggregate_execution_costs, compare_snapshots
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


def test_execution_cost_aggregate_explains_unknown_commissions_without_partial_total() -> None:
    result = _aggregate_execution_costs(
        [
            {
                "gross_notional": "100.00",
                "commission_quote": "0.10",
                "conversion_status": "complete",
                "commission_by_asset": {"USDT": "0.10"},
                "commission_conversion_details": {
                    "USDT": {
                        "commission": "0.10",
                        "status": "quote_asset",
                        "reference_price": "1",
                        "quote_amount": "0.10",
                        "reason": None,
                    }
                },
            },
            {
                "gross_notional": "50.00",
                "commission_quote": None,
                "conversion_status": "partial",
                "commission_by_asset": {"BNB": "0.00003", "USDT": "0.02"},
                "commission_conversion_details": {
                    "BNB": {
                        "commission": "0.00003",
                        "status": "unknown",
                        "reference_price": None,
                        "quote_amount": None,
                        "reason": "reference_price_missing",
                    },
                    "USDT": {
                        "commission": "0.02",
                        "status": "quote_asset",
                        "reference_price": "1",
                        "quote_amount": "0.02",
                        "reason": None,
                    },
                },
            },
            {
                "gross_notional": "25.00",
                "commission_quote": None,
                "conversion_status": "incomplete",
                "commission_by_asset": {},
                "commission_conversion_details": {},
                "commission_data_issues": {"commission_amount_missing": 1},
            },
            {
                "gross_notional": "20.00",
                "commission_quote": None,
                "conversion_status": "incomplete",
                "commission_by_asset": {"BNB": None},
                "commission_conversion_details": {
                    "BNB": {
                        "commission": None,
                        "known_commission_subtotal": "0.00001",
                        "known_commission_quote_subtotal": "0.00600000",
                        "status": "incomplete",
                        "reason": "commission_amount_missing",
                    }
                },
                "commission_data_issues": {"commission_amount_missing": 1},
            },
        ]
    )

    assert result["orders"] == 4
    assert result["conversion_complete_orders"] == 1
    assert result["conversion_unknown_orders"] == 3
    assert result["commission_quote"] is None
    assert result["converted_commission_quote_subtotal"] == "0.126"
    assert result["unconverted_commission_by_asset"] == {"BNB": "0.00003"}
    assert result["unknown_orders_without_asset_breakdown"] == 1
    assert result["unknown_conversion_reasons"] == {"reference_price_missing": 1}
    assert result["commission_data_issues"] == {"commission_amount_missing": 2}
