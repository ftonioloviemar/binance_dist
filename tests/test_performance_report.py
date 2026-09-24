from __future__ import annotations

import json

from performance import build_performance_report, render_performance_report
from performance_store import build_portfolio_snapshot, record_portfolio_snapshot
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


def test_render_performance_report_json_is_machine_readable(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    report = build_performance_report(
        db_path,
        days=30,
        now="2026-09-21T13:00:00+00:00",
    )

    rendered = render_performance_report(report, json_output=True)
    assert json.loads(rendered)["horizons"]["30d"]["status"] == "no_data"


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
    assert (
        "incomplete data; observed=unknown hold=unknown"
        in render_performance_report(report)
    )


def test_performance_command_is_not_normalized_to_rebalance() -> None:
    args = parse_args(["performance", "--days", "30", "--json"])
    assert args.command == "performance"
    assert args.days == 30
    assert args.json is True
