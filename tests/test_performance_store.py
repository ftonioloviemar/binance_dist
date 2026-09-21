from __future__ import annotations

from decimal import Decimal

from performance_store import (
    build_portfolio_snapshot,
    load_portfolio_snapshots,
    record_portfolio_snapshot,
)


def test_snapshot_persists_spot_and_earn_values(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    payload = build_portfolio_snapshot(
        run_id="run-1",
        phase="before",
        quote_asset="USDT",
        spot_balances=[
            {"asset": "BTC", "quantity": Decimal("0.01")},
            {"asset": "USDT", "quantity": Decimal("100")},
        ],
        earn_positions=[{"asset": "BTC", "quantity": Decimal("0.02")}],
        prices={"BTC": Decimal("20000")},
        timestamp="2026-09-21T12:00:00+00:00",
    )

    record_portfolio_snapshot(db_path, payload)
    snapshots = load_portfolio_snapshots(db_path, run_id="run-1")

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["spot_value"] == "300.00"
    assert snapshot["earn_value"] == "400.00"
    assert snapshot["total_value"] == "700.00"
    assert snapshot["data_quality"] == "complete"
    assert snapshot["asset_values"] == {
        "spot:BTC": "200.00",
        "spot:USDT": "100.00",
        "earn:BTC": "400.00",
    }


def test_snapshot_is_idempotent_for_run_and_phase(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    first = build_portfolio_snapshot(
        run_id="run-1",
        phase="after",
        quote_asset="USDT",
        spot_balances=[{"asset": "USDT", "quantity": Decimal("10")}],
        earn_positions=[],
        prices={},
        timestamp="2026-09-21T12:00:00+00:00",
    )
    second = {**first, "total_value": "20.00", "spot_value": "20.00"}

    record_portfolio_snapshot(db_path, first)
    record_portfolio_snapshot(db_path, second)

    snapshots = load_portfolio_snapshots(db_path, run_id="run-1")
    assert len(snapshots) == 1
    assert snapshots[0]["total_value"] == "20.00"


def test_snapshot_marks_missing_price_as_incomplete(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    payload = build_portfolio_snapshot(
        run_id="run-2",
        phase="before",
        quote_asset="USDT",
        spot_balances=[{"asset": "ADA", "quantity": Decimal("5")}],
        earn_positions=[],
        prices={},
        timestamp="2026-09-21T12:00:00+00:00",
    )

    assert payload["data_quality"] == "incomplete"
    assert payload["missing_prices"] == ["ADA"]
    assert payload["total_value"] == "0.00"
