from __future__ import annotations

import sqlite3

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
            "commission_by_asset": {"BNB": "0.00003"},
            "commission_conversion_details": {
                "BNB": {
                    "commission": "0.00003",
                    "status": "converted",
                    "reference_price": "600",
                    "quote_amount": "0.01800000",
                    "reason": None,
                }
            },
            "commission_data_issues": {},
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
            "commission_by_asset": {"BNB": "0.00003"},
            "commission_conversion_details": {
                "BNB": {
                    "commission": "0.00003",
                    "status": "converted",
                    "reference_price": "600",
                    "quote_amount": "0.01800000",
                    "reason": None,
                }
            },
            "commission_data_issues": {},
        }
    ]


def test_v2_cost_schema_migrates_additively_and_preserves_legacy_values(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE execution_costs (
                run_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                gross_notional TEXT NOT NULL,
                commission_quote TEXT,
                commission_bps TEXT,
                conversion_status TEXT NOT NULL,
                PRIMARY KEY (run_id, order_id)
            )
            """
        )
        connection.execute(
            "INSERT INTO execution_costs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-run",
                "legacy-order",
                "2026-09-21T12:00:00+00:00",
                "BTCUSDT",
                "BUY",
                "1000.00",
                "0.01800000",
                "0.180000",
                "complete",
            ),
        )

    record_execution_cost(
        db_path,
        {
            "run_id": "new-run",
            "order_id": "new-order",
            "timestamp": "2026-09-21T12:01:00+00:00",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "gross_notional": "50.00",
            "commission_quote": None,
            "commission_bps": None,
            "conversion_status": "unknown",
            "commission_by_asset": {"BNB": "0.00003"},
            "commission_conversion_details": {
                "BNB": {
                    "commission": "0.00003",
                    "status": "unknown",
                    "reference_price": None,
                    "quote_amount": None,
                    "reason": "reference_price_missing",
                }
            },
            "commission_data_issues": {"commission_amount_missing": 1},
        },
    )

    costs = load_execution_costs(db_path)
    legacy = next(cost for cost in costs if cost["run_id"] == "legacy-run")
    assert legacy["commission_quote"] == "0.01800000"
    assert legacy["conversion_status"] == "complete"
    assert legacy["commission_by_asset"] == {}
    assert legacy["commission_conversion_details"] == {}
    assert legacy["commission_data_issues"] == {}
    new = next(cost for cost in costs if cost["run_id"] == "new-run")
    assert new["commission_quote"] is None
    assert new["commission_by_asset"] == {"BNB": "0.00003"}
    assert new["commission_conversion_details"]["BNB"]["reason"] == "reference_price_missing"
    assert new["commission_data_issues"] == {"commission_amount_missing": 1}


def test_reading_v2_cost_schema_does_not_migrate_or_write(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE execution_costs (
                run_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                gross_notional TEXT NOT NULL,
                commission_quote TEXT,
                commission_bps TEXT,
                conversion_status TEXT NOT NULL,
                PRIMARY KEY (run_id, order_id)
            )
            """
        )
        connection.execute(
            "INSERT INTO execution_costs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy", "1", "2026-09-21T12:00:00+00:00", "BTCUSDT", "BUY", "1", None, None, "unknown"),
        )

    assert load_execution_costs(db_path)[0]["commission_conversion_details"] == {}
    assert load_execution_costs(db_path)[0]["commission_data_issues"] == {}
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(execution_costs)")}
    assert "commission_conversion_details_json" not in columns


def test_cost_upsert_replaces_breakdown_without_duplicating_order(tmp_path) -> None:
    db_path = tmp_path / "performance.db"
    base = {
        "run_id": "run-1",
        "order_id": "10",
        "timestamp": "2026-09-21T12:00:00+00:00",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "gross_notional": "100.00",
        "commission_quote": None,
        "commission_bps": None,
        "conversion_status": "unknown",
        "commission_by_asset": {"BNB": "0.00003"},
        "commission_conversion_details": {"BNB": {"reason": "reference_price_missing"}},
    }
    record_execution_cost(db_path, base)
    record_execution_cost(
        db_path,
        {
            **base,
            "commission_quote": "0.01800000",
            "commission_bps": "1.800000",
            "conversion_status": "complete",
            "commission_by_asset": {"BNB": "0.00003"},
            "commission_conversion_details": {"BNB": {"reason": None, "status": "converted"}},
        },
    )

    costs = load_execution_costs(db_path)
    assert len(costs) == 1
    assert costs[0]["conversion_status"] == "complete"
    assert costs[0]["commission_conversion_details"]["BNB"]["status"] == "converted"
