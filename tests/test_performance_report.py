from __future__ import annotations

import json

from external_flow_import import import_external_flows_csv
from performance import build_performance_report, render_performance_report
from performance_store import (
    build_portfolio_snapshot,
    record_execution_cost,
    record_portfolio_snapshot,
)
from app import parse_args


def _record_pair(db_path, run_id: str, timestamp: str, before: str, after: str) -> None:
    for phase, value in (("before", before), ("after", after)):
        record_portfolio_snapshot(
            db_path,
            build_portfolio_snapshot(
                run_id=run_id,
                phase=phase,
                quote_asset="USDT",
                spot_balances=[{"asset": "USDT", "quantity": value}],
                earn_positions=[],
                prices={},
                timestamp=timestamp,
            ),
        )


def _record_endpoint(db_path, run_id: str, phase: str, timestamp: str, value: str, quote: str = "USDT") -> None:
    record_portfolio_snapshot(
        db_path,
        build_portfolio_snapshot(
            run_id=run_id,
            phase=phase,
            quote_asset=quote,
            spot_balances=[{"asset": quote, "quantity": value}],
            earn_positions=[],
            prices={},
            timestamp=timestamp,
        ),
    )


def _certify_flows(db_path, tmp_path, start: str, end: str, rows: str = "") -> None:
    csv_path = tmp_path / "certified-flows.csv"
    csv_path.write_text(
        "flow_id,timestamp_utc,asset,quote_value,direction\n" + rows,
        encoding="utf-8",
    )
    import_external_flows_csv(
        db_path=db_path,
        csv_path=csv_path,
        quote_asset="USDT",
        coverage_start=start,
        coverage_end=end,
        confirm_complete=True,
    )


def _record_timed_pair(
    db_path,
    start: str,
    end: str,
    before: str = "100",
    after: str = "130",
    run_id: str = "timed-run",
) -> None:
    _record_endpoint(db_path, run_id, "before", start, before)
    _record_endpoint(db_path, run_id, "after", end, after)


def test_build_performance_report_has_requested_horizons(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    _record_pair(db_path, "run-1", "2026-09-20T12:00:00+00:00", "100", "110")
    _record_pair(db_path, "run-2", "2026-09-21T12:00:00+00:00", "110", "120")

    report = build_performance_report(
        db_path,
        days=30,
        now="2026-09-21T13:00:00+00:00",
    )

    assert set(report["horizons"]) == {"24h", "7d", "30d"}
    assert report["horizons"]["24h"]["status"] == "ok"
    assert report["horizons"]["24h"]["observed_change"] == "10.00"
    assert report["horizons"]["24h"]["attribution_status"] == "not_attributed"


def test_certified_empty_ledger_reports_net_pnl_and_modified_dietz(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    start = "2026-09-21T10:00:00+00:00"
    end = "2026-09-21T12:00:00+00:00"
    _record_timed_pair(db_path, start, end, before="100", after="110")
    _certify_flows(db_path, tmp_path, start, end)
    record_execution_cost(
        db_path,
        {
            "run_id": "timed-run",
            "order_id": "fee-order",
            "timestamp": "2026-09-21T11:00:00+00:00",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "gross_notional": "100.00",
            "commission_quote": "5.00",
            "commission_bps": "500.000000",
            "conversion_status": "complete",
            "commission_by_asset": {"USDT": "5.00"},
            "commission_conversion_details": {},
            "commission_data_issues": {},
        },
    )

    report = build_performance_report(
        db_path, days=30, now="2026-09-21T13:00:00+00:00"
    )

    horizon = report["horizons"]["24h"]
    assert horizon["observed_change"] == "10.00"
    assert horizon["net_pnl_quote"] == "10.00"
    assert horizon["external_net_flow_quote"] == "0.00"
    assert horizon["modified_dietz_return_pct"] == "10.000000"
    assert horizon["execution_cost"]["commission_quote"] == "5.00"
    assert horizon["return_method"] == "modified_dietz_approximate"
    assert horizon["flow_coverage_status"] == "complete"
    assert len(horizon["flow_source_sha256"]) == 64
    assert horizon["flow_coverage_basis"] == "user_certified"
    rendered = render_performance_report(report)
    assert "Modified_Dietz=10.000000% (approx., not annualized)" in rendered
    assert "basis=user-certified" in rendered
    assert "source_sha256=" in rendered
    assert "not strategy alpha" in rendered


def test_modified_dietz_weights_inflows_and_end_time_outflows(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    start = "2026-09-21T10:00:00+00:00"
    midpoint = "2026-09-21T11:00:00+00:00"
    end = "2026-09-21T12:00:00+00:00"
    _record_timed_pair(db_path, start, end)
    _certify_flows(
        db_path,
        tmp_path,
        start,
        end,
        f"at-start,{start},USDT,50,in\n"
        f"mid-in,{midpoint},USDT,20,in\n"
        f"at-end,{end},USDT,10,out\n",
    )

    horizon = build_performance_report(
        db_path, days=30, now="2026-09-21T13:00:00+00:00"
    )["horizons"]["24h"]

    assert horizon["external_net_flow_quote"] == "10.00"
    assert horizon["net_pnl_quote"] == "20.00"
    assert horizon["modified_dietz_return_pct"] == "18.181818"
    assert horizon["flow_coverage_status"] == "complete"


def test_missing_or_partial_flow_coverage_keeps_adjusted_metrics_null(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    start = "2026-09-21T10:00:00+00:00"
    end = "2026-09-21T12:00:00+00:00"
    _record_timed_pair(db_path, start, end)

    missing = build_performance_report(
        db_path, days=30, now="2026-09-21T13:00:00+00:00"
    )["horizons"]["24h"]
    assert missing["flow_coverage_status"] == "missing"
    assert missing["net_pnl_quote"] is None
    assert missing["modified_dietz_return_pct"] is None

    _certify_flows(
        db_path,
        tmp_path,
        "2026-09-21T10:30:00+00:00",
        end,
        "flow,2026-09-21T11:00:00Z,USDT,5,in\n",
    )
    partial = build_performance_report(
        db_path, days=30, now="2026-09-21T13:00:00+00:00"
    )["horizons"]["24h"]
    assert partial["flow_coverage_status"] == "insufficient"
    assert partial["net_pnl_quote"] is None
    assert partial["modified_dietz_return_pct"] is None


def test_flow_coverage_is_evaluated_independently_for_each_horizon(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    _record_timed_pair(
        db_path,
        "2026-09-11T10:00:00+00:00",
        "2026-09-11T12:00:00+00:00",
        run_id="old-run",
    )
    _record_timed_pair(
        db_path,
        "2026-09-30T12:30:00+00:00",
        "2026-09-30T14:30:00+00:00",
        run_id="recent-run",
    )
    _certify_flows(
        db_path,
        tmp_path,
        "2026-09-20T00:00:00+00:00",
        "2026-10-01T12:00:00+00:00",
    )

    horizons = build_performance_report(
        db_path, days=30, now="2026-10-01T12:00:00+00:00"
    )["horizons"]

    assert horizons["24h"]["flow_coverage_status"] == "complete"
    assert horizons["7d"]["flow_coverage_status"] == "complete"
    assert horizons["30d"]["flow_coverage_status"] == "insufficient"
    assert horizons["30d"]["net_pnl_quote"] is None


def test_zero_modified_dietz_denominator_keeps_return_null(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    start = "2026-09-21T10:00:00+00:00"
    midpoint = "2026-09-21T11:00:00+00:00"
    end = "2026-09-21T12:00:00+00:00"
    _record_timed_pair(db_path, start, end, before="100", after="0")
    _certify_flows(
        db_path,
        tmp_path,
        start,
        end,
        f"out,{midpoint},USDT,200,out\n",
    )

    horizon = build_performance_report(
        db_path, days=30, now="2026-09-21T13:00:00+00:00"
    )["horizons"]["24h"]

    assert horizon["net_pnl_quote"] == "100.00"
    assert horizon["modified_dietz_return_pct"] is None
    assert horizon["modified_dietz_return_reason"] == "nonpositive_denominator"


def test_flow_adjusted_math_preserves_small_amounts_beside_large_flows(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    start = "2026-09-21T10:00:00+00:00"
    midpoint = "2026-09-21T11:00:00+00:00"
    end = "2026-09-21T12:00:00+00:00"
    for phase, timestamp, amount in (
        ("before", start, "10000000000000000000000000000"),
        ("after", end, "20000000000000000000000000000.01"),
    ):
        record_portfolio_snapshot(
            db_path,
            {
                "run_id": "large-flow-run",
                "phase": phase,
                "timestamp": timestamp,
                "quote_asset": "USDT",
                "spot_value": amount,
                "earn_value": "0",
                "total_value": amount,
                "prices": {"USDT": "1"},
                "asset_values": {"spot:USDT": amount},
                "data_quality": "complete",
                "external_flow_status": "unknown",
                "missing_prices": [],
            },
        )
    _certify_flows(
        db_path,
        tmp_path,
        start,
        end,
        f"a-large,{midpoint},USDT,10000000000000000000000000000,in\n"
        f"z-cents,{midpoint},USDT,0.01,in\n",
    )

    horizon = build_performance_report(
        db_path, days=30, now="2026-09-21T13:00:00+00:00"
    )["horizons"]["24h"]

    assert horizon["external_net_flow_quote"] == "10000000000000000000000000000.01"
    assert horizon["net_pnl_quote"] == "0.00"


def test_snapshot_quote_mismatch_suppresses_flow_adjusted_metrics(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    start = "2026-09-21T10:00:00+00:00"
    end = "2026-09-21T12:00:00+00:00"
    _record_endpoint(db_path, "quote-run", "before", start, "100", "USDT")
    _record_endpoint(db_path, "quote-run", "after", end, "100", "USDC")
    _certify_flows(db_path, tmp_path, start, end)

    horizon = build_performance_report(
        db_path, days=30, now="2026-09-21T13:00:00+00:00"
    )["horizons"]["24h"]

    assert horizon["flow_coverage_status"] == "quote_mismatch"
    assert horizon["net_pnl_quote"] is None
    assert horizon["external_net_flow_quote"] is None
    assert horizon["modified_dietz_return_pct"] is None


def test_render_performance_report_json_is_machine_readable(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    report = build_performance_report(
        db_path,
        days=30,
        now="2026-09-21T13:00:00+00:00",
    )

    rendered = render_performance_report(report, json_output=True)
    assert json.loads(rendered)["horizons"]["30d"]["status"] == "no_data"
    no_data_horizon = json.loads(rendered)["horizons"]["30d"]
    assert no_data_horizon["net_pnl_quote"] is None
    assert no_data_horizon["modified_dietz_return_pct"] is None
    assert no_data_horizon["flow_coverage_status"] == "no_data"


def test_incomplete_snapshots_do_not_report_observed_or_hold_change(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    for phase, amount, quality in (
        ("before", "100", "complete"),
        ("after", "110", "incomplete"),
    ):
        snapshot = build_portfolio_snapshot(
            run_id="run-incomplete",
            phase=phase,
            quote_asset="USDT",
            spot_balances=[{"asset": "USDT", "quantity": amount}],
            earn_positions=[],
            prices={},
            timestamp="2026-09-21T12:00:00+00:00",
            data_quality=quality,
        )
        record_portfolio_snapshot(db_path, snapshot)

    report = build_performance_report(
        db_path,
        days=30,
        now="2026-09-21T13:00:00+00:00",
    )

    for horizon in report["horizons"].values():
        assert horizon["status"] == "incomplete"
        assert horizon["observed_change"] is None
        assert horizon["hold_change"] is None
        assert horizon["attribution_status"] == "incomplete"
        assert horizon["flow_coverage_status"] == "incomplete_snapshots"
        assert horizon["net_pnl_quote"] is None
        assert horizon["modified_dietz_return_pct"] is None
    assert (
        "incomplete data; observed=unknown hold=unknown"
        in render_performance_report(report)
    )


def test_text_report_keeps_fee_gaps_visible_for_incomplete_horizon() -> None:
    report = {
        "days": 30,
        "horizons": {
            "30d": {
                "status": "incomplete",
                "execution_cost": {
                    "conversion_complete_orders": 4,
                    "conversion_unknown_orders": 2,
                    "unknown_orders_without_asset_breakdown": 1,
                    "converted_commission_quote_subtotal": "3.20",
                    "unconverted_commission_by_asset": {"BNB": "0.00003"},
                    "commission_data_issues": {"commission_amount_missing": 1},
                },
            }
        },
    }

    rendered = render_performance_report(report)

    assert "incomplete data; observed=unknown hold=unknown" in rendered
    assert "converted_quote_subtotal=3.20 converted_orders=4 unknown_orders=2 unknown_without_asset_detail=1" in rendered
    assert "unconverted commissions by asset: BNB=0.00003" in rendered
    assert "incomplete fill commission data: commission_amount_missing=1" in rendered


def test_performance_command_is_not_normalized_to_rebalance() -> None:
    args = parse_args(["performance", "--days", "30", "--json"])
    assert args.command == "performance"
    assert args.days == 30
    assert args.json is True
