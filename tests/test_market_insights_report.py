from __future__ import annotations

import json
import sqlite3
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app import parse_args, run_market_insights
from market_insights import persist_shadow_aggregates
from market_insights_report import (
    build_market_insights_report,
    render_market_insights_json,
    render_market_insights_text,
)


POLICIES = ("hold", "baseline", "volatility_guard_v1")
NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)


def _observations(
    run_id: str,
    *,
    observed_at: datetime = NOW,
    status: str = "complete",
    missing: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    result = []
    for index, policy in enumerate(POLICIES):
        if policy in missing:
            continue
        result.append(
            {
                "session_id": "session-a",
                "run_id": run_id,
                "policy": policy,
                "input_fingerprint": f"fp-{run_id}-{policy}",
                "observed_at": observed_at.isoformat(),
                "policy_version": "shadow_v1",
                "status": status,
                "initial_equity": "100",
                "equity": str(101 + index),
                "net_return": str(Decimal("0.01") + Decimal(index) / 100),
                "modeled_cost": "0.10",
                "gross_turnover": str(50 + index * 10),
                "relative_turnover": str(Decimal(50 + index * 10) / 100),
                "max_drawdown": "0.03",
                "residual_drift": "0.04",
                "trade_count": 2 + index,
                "skipped_count": 1,
                "incomplete_symbols": [],
            }
        )
    return result


def _database(path, observations) -> None:
    persist_shadow_aggregates(observations, db_path=path)


def test_report_compares_policies_and_overlays_default_and_stress_costs(tmp_path):
    database = tmp_path / "market_insights.db"
    _database(database, _observations("run-1"))

    report = build_market_insights_report(db_path=database, days=30, now=NOW)

    comparison = report["observations"][0]
    assert comparison["status"] == "complete"
    assert comparison["policies"]["baseline"]["net_return_delta_vs_hold"] == "0.01"
    baseline_cost = comparison["policies"]["baseline"]["cost_sensitivity"]
    assert baseline_cost["default"]["estimated_net_return"] == "0.0198"
    assert baseline_cost["stress"]["estimated_net_return"] == "0.0186"
    assert baseline_cost["assumption"] == "fixed_trade_path"
    assert comparison["policies"]["baseline"]["gross_turnover"] == "60"
    assert comparison["policies"]["baseline"]["max_drawdown"] == "0.03"
    assert comparison["policies"]["baseline"]["residual_drift"] == "0.04"


@pytest.mark.parametrize(
    "observations",
    [
        _observations("run-missing", missing=("volatility_guard_v1",)),
        _observations("run-incomplete", status="incomplete"),
    ],
)
def test_incomplete_or_unpaired_comparison_has_null_deltas(tmp_path, observations):
    database = tmp_path / "market_insights.db"
    _database(database, observations)

    report = build_market_insights_report(db_path=database, days=30, now=NOW)

    comparison = report["observations"][0]
    assert comparison["status"] == "incomplete"
    assert comparison["policies"]["baseline"]["net_return_delta_vs_hold"] is None
    assert comparison["policies"]["baseline"]["cost_sensitivity"] is None


def test_mismatched_seed_equity_makes_comparison_incomplete(tmp_path):
    observations = _observations("run-seed")
    observations[-1]["initial_equity"] = "101"
    database = tmp_path / "market_insights.db"
    _database(database, observations)

    report = build_market_insights_report(db_path=database, days=30, now=NOW)

    assert report["observations"][0]["status"] == "incomplete"
    assert report["observations"][0]["policies"]["baseline"]["net_return_delta_vs_hold"] is None


def test_seeded_observation_is_not_misreported_as_incomplete_or_performance(tmp_path):
    database = tmp_path / "market_insights.db"
    seeded = _observations("seed", status="seeded")
    for row in seeded:
        row["net_return"] = "0"
        row["modeled_cost"] = "0"
        row["gross_turnover"] = "0"
        row["relative_turnover"] = "0"
    _database(database, seeded)

    report = build_market_insights_report(db_path=database, days=30, now=NOW)

    observation = report["observations"][0]
    assert observation["status"] == "seeded"
    assert observation["policies"]["baseline"]["net_return"] == "0"
    assert observation["policies"]["baseline"]["net_return_delta_vs_hold"] is None
    assert observation["policies"]["baseline"]["cost_sensitivity"] is None


def test_report_lookback_order_and_serialization_are_deterministic(tmp_path):
    database = tmp_path / "market_insights.db"
    _database(
        database,
        _observations("later", observed_at=NOW)
        + _observations("earlier", observed_at=NOW - timedelta(days=1))
        + _observations("stale", observed_at=NOW - timedelta(days=31)),
    )

    report = build_market_insights_report(db_path=database, days=30, now=NOW)

    assert [item["run_id"] for item in report["observations"]] == ["earlier", "later"]
    encoded = render_market_insights_json(report)
    assert encoded == render_market_insights_json(
        build_market_insights_report(db_path=database, days=30, now=NOW)
    )
    assert "generated_at" not in encoded
    assert "holdings" not in encoded and "balances" not in encoded
    assert json.loads(encoded)["label"] == "simulated_conditional"
    assert "fixed trade path" in render_market_insights_text(report).lower()


def test_read_only_report_does_not_create_missing_database(tmp_path):
    database = tmp_path / "missing.db"

    with pytest.raises((FileNotFoundError, ValueError)):
        build_market_insights_report(db_path=database, days=30, now=NOW)

    assert not database.exists()


def test_invalid_database_is_not_modified(tmp_path):
    database = tmp_path / "invalid.db"
    database.write_bytes(b"not a sqlite database")
    before = database.read_bytes()

    with pytest.raises(ValueError):
        build_market_insights_report(db_path=database, days=30, now=NOW)

    assert database.read_bytes() == before


def test_cli_parser_and_nonpositive_days_are_safe():
    args = parse_args(["insights", "--days", "0", "--json"])
    assert args.command == "insights"
    assert args.json is True
    assert run_market_insights(args) == 1


def test_malformed_timestamp_fails_closed(tmp_path):
    database = tmp_path / "market_insights.db"
    observations = _observations("bad-time")
    observations[0]["observed_at"] = "not-a-timestamp"
    _database(database, observations)

    with pytest.raises(ValueError):
        build_market_insights_report(db_path=database, days=30, now=NOW)


def test_report_does_not_access_financial_stores_or_network(tmp_path, monkeypatch):
    database = tmp_path / "market_insights.db"
    _database(database, _observations("isolated"))
    original_connect = sqlite3.connect
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: pytest.fail("report must not use the network"),
    )

    def guarded_connect(target, *args, **kwargs):
        assert str(target).startswith("file:")
        assert str(target).endswith("?mode=ro")
        assert database.name in str(target)
        assert kwargs.get("uri") is True
        return original_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)

    report = build_market_insights_report(db_path=database, days=30, now=NOW)

    assert report["observations"]
