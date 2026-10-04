from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from binance_client import SymbolFilters
import shadow_portfolios
from shadow_portfolios import ShadowRun, ShadowCosts, simulate_shadow_run


def _run(**changes) -> ShadowRun:
    base = ShadowRun(
        session_id="session-001",
        run_id="run-001",
        observed_at=datetime(2026, 10, 1, tzinfo=UTC),
        quote_asset="USDT",
        spot_balances={"BTC": Decimal("0.01"), "USDT": Decimal("700")},
        earn_balances={"ETH": Decimal("0.2")},
        prices={"BTC": Decimal("30000"), "ETH": Decimal("1000"), "USDT": Decimal("1")},
        target_weights={"BTC": Decimal("0.4"), "ETH": Decimal("0.2"), "USDT": Decimal("0.4")},
        drift_threshold=Decimal("0.03"),
        btc_vol30=Decimal("0.04"),
        symbol_filters={
            "BTCUSDT": SymbolFilters("BTCUSDT", 0.0001, 0.0001, 1000, 5, 0.01),
            "ETHUSDT": SymbolFilters("ETHUSDT", 0.001, 0.001, 1000, 5, 0.01),
        },
    )
    return replace(base, **changes)


def _simulate(tmp_path, run: ShadowRun, costs: ShadowCosts = ShadowCosts()):
    return simulate_shadow_run(
        run,
        shadow_db_path=tmp_path / "shadow_portfolios.db",
        market_db_path=tmp_path / "market_insights.db",
        costs=costs,
    )


def test_first_complete_run_seeds_isolated_hold_and_candidate_portfolios(tmp_path) -> None:
    run = _run()

    shadow_db_path = tmp_path / "shadow_portfolios.db"
    result = simulate_shadow_run(
        run,
        shadow_db_path=shadow_db_path,
        market_db_path=tmp_path / "market_insights.db",
    )

    assert set(result.policies) == {"hold", "baseline", "volatility_guard_v1"}
    seeded = [result.policies[name] for name in result.policies]
    assert {policy.status for policy in seeded} == {"seeded"}
    assert {policy.initial_equity for policy in seeded} == {Decimal("1200")}
    assert all(policy.gross_turnover == 0 for policy in seeded)
    assert all(policy.modeled_cost == 0 for policy in seeded)
    with sqlite3.connect(shadow_db_path) as connection:
        inventories = connection.execute(
            "SELECT inventory_json FROM shadow_sessions ORDER BY policy"
        ).fetchall()
    assert len(inventories) == 3
    assert len({json.dumps(json.loads(row[0]), sort_keys=True) for row in inventories}) == 1


def test_complete_runs_evolve_independent_portfolios_sell_first_and_charge_costs(tmp_path) -> None:
    _simulate(tmp_path, _run())
    second = _run(
        run_id="run-002",
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
        target_weights={"BTC": Decimal("0.1"), "ETH": Decimal("0.3"), "USDT": Decimal("0.6")},
    )

    result = _simulate(tmp_path, second)

    baseline = result.policies["baseline"]
    assert baseline.status == "complete"
    assert [trade.side for trade in baseline.trades] == ["SELL", "BUY"]
    assert baseline.trades[0].symbol == "BTCUSDT"
    assert baseline.trades[1].symbol == "ETHUSDT"
    assert baseline.trades[0].gross_notional == Decimal("180.0000")
    assert baseline.trades[1].gross_notional == Decimal("160.000")
    assert baseline.modeled_cost == Decimal("0.6800000")
    assert baseline.gross_turnover == Decimal("340.0000")
    assert abs(baseline.relative_turnover * baseline.initial_equity - baseline.gross_turnover) < Decimal("1e-40")
    assert baseline.equity == Decimal("1199.3200000")
    assert abs(baseline.net_return - (baseline.equity / baseline.initial_equity - 1)) < Decimal("1e-27")
    with localcontext() as context:
        context.prec = 48
        expected_drift = max(
            abs(Decimal("120") / baseline.equity - Decimal("0.1")),
            abs(Decimal("360") / baseline.equity - Decimal("0.3")),
            abs(Decimal("719.32") / baseline.equity - Decimal("0.6")),
        )
    assert baseline.residual_drift == expected_drift
    assert result.policies["hold"].trades == ()
    assert result.policies["hold"].modeled_cost == 0
    assert result.policies["hold"].gross_turnover == 0


def test_modeled_fee_and_slippage_rates_are_configurable(tmp_path) -> None:
    seed = _run()
    _simulate(tmp_path, seed)
    second = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        target_weights={"BTC": Decimal("0.1"), "ETH": Decimal("0.3"), "USDT": Decimal("0.6")},
    )

    result = _simulate(
        tmp_path,
        second,
        ShadowCosts(fee_rate=Decimal("0.002"), slippage_rate=Decimal("0.004")),
    )

    assert result.policies["baseline"].gross_turnover == Decimal("340.000")
    assert result.policies["baseline"].modeled_cost == Decimal("2.04000")


def test_volatility_guard_doubles_only_its_shadow_threshold_at_six_percent(tmp_path) -> None:
    seed = _run(
        spot_balances={"BTC": Decimal("0.01"), "USDT": Decimal("900")},
        earn_balances={},
        target_weights={"BTC": Decimal("0.25"), "USDT": Decimal("0.75")},
    )
    _simulate(tmp_path, seed)
    observed = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        spot_balances=seed.spot_balances,
        earn_balances=seed.earn_balances,
        target_weights={"BTC": Decimal("0.30"), "USDT": Decimal("0.70")},
        btc_vol30=Decimal("0.06"),
    )

    result = _simulate(tmp_path, observed)

    assert result.policies["baseline"].trade_count == 1
    assert result.policies["volatility_guard_v1"].trade_count == 0
    assert result.policies["volatility_guard_v1"].gross_turnover == 0


def test_planner_may_execute_subthreshold_asset_delta_after_global_trigger(tmp_path) -> None:
    seed = _run(
        spot_balances={"BTC": Decimal("0.0104"), "ETH": Decimal("0.216"), "USDT": Decimal("672")},
        earn_balances={},
        target_weights={"BTC": Decimal("0.26"), "ETH": Decimal("0.18"), "USDT": Decimal("0.56")},
    )
    _simulate(tmp_path, seed)
    observed = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        spot_balances=seed.spot_balances,
        earn_balances={},
        target_weights={"BTC": Decimal("0.30"), "ETH": Decimal("0.19"), "USDT": Decimal("0.51")},
    )

    result = _simulate(tmp_path, observed)

    baseline = result.policies["baseline"]
    assert baseline.trade_count == 2
    assert {trade.asset for trade in baseline.trades} == {"BTC", "ETH"}
    assert baseline.trades[1].gross_notional == Decimal("12.000")


def test_nonactionable_skip_is_counted_once_independent_of_delta_order(tmp_path, monkeypatch) -> None:
    original_decide = shadow_portfolios.decide_rebalance

    def decide_with_stable_delta_order(*args, **kwargs):
        decision = original_decide(*args, **kwargs)
        decision.deltas = dict(sorted(decision.deltas.items()))
        return decision

    monkeypatch.setattr(shadow_portfolios, "decide_rebalance", decide_with_stable_delta_order)
    seed = _run()
    _simulate(tmp_path, seed)
    observed = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        target_weights={"BTC": Decimal("0.251"), "ETH": Decimal("0.300"), "USDT": Decimal("0.449")},
    )

    result = _simulate(tmp_path, observed).policies["baseline"]

    assert result.trade_count == 1
    assert result.skipped_count == 1
    assert len(result.skipped_orders) == 1
    assert result.skipped_orders[0].startswith("BTCUSDT: notional")


def test_captured_min_notional_uplift_and_max_quantity_match_planner(tmp_path) -> None:
    seed = _run(
        spot_balances={"BTC": Decimal("0.01"), "USDT": Decimal("900")},
        earn_balances={},
        target_weights={"BTC": Decimal("0.25"), "USDT": Decimal("0.75")},
        symbol_filters={"BTCUSDT": SymbolFilters("BTCUSDT", 0.0001, 0.0001, 1000, 100, 0.01)},
    )
    _simulate(tmp_path, seed)
    lifted = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        spot_balances=seed.spot_balances,
        earn_balances={},
        target_weights={"BTC": Decimal("0.29"), "USDT": Decimal("0.71")},
        symbol_filters=seed.symbol_filters,
        min_notional=Decimal("10"),
        min_notional_uplift_tolerance=Decimal("0.6"),
    )
    uplifted = _simulate(tmp_path, lifted).policies["baseline"]
    assert uplifted.trade_count == 1
    assert uplifted.trades[0].gross_notional >= Decimal("100")

    limited_seed = _run(
        session_id="session-limits",
        spot_balances={"BTC": Decimal("0.01"), "USDT": Decimal("900")},
        earn_balances={},
        target_weights={"BTC": Decimal("0.25"), "USDT": Decimal("0.75")},
    )
    _simulate(tmp_path, limited_seed)
    limited = _run(
        session_id="session-limits",
        run_id="run-002",
        observed_at=limited_seed.observed_at + timedelta(days=1),
        spot_balances=limited_seed.spot_balances,
        earn_balances={},
        target_weights={"BTC": Decimal("0.30"), "USDT": Decimal("0.70")},
        symbol_filters={"BTCUSDT": SymbolFilters("BTCUSDT", 0.0001, 0.0001, 0.0001, 5, 0.01)},
    )
    limited_result = _simulate(tmp_path, limited).policies["baseline"]
    assert limited_result.trade_count == 0
    assert limited_result.skipped_count > 0

    for suffix, filters in (
        ("min-qty", SymbolFilters("BTCUSDT", 0.0001, 0.003, 1000, 5, 0.01)),
        ("max-notional", SymbolFilters("BTCUSDT", 0.0001, 0.0001, 1000, 5, 0.01, 50)),
    ):
        session_id = f"session-{suffix}"
        constrained_seed = _run(
            session_id=session_id,
            spot_balances={"BTC": Decimal("0.01"), "USDT": Decimal("900")},
            earn_balances={},
            target_weights={"BTC": Decimal("0.25"), "USDT": Decimal("0.75")},
        )
        _simulate(tmp_path, constrained_seed)
        constrained_run = _run(
            session_id=session_id,
            run_id="run-002",
            observed_at=constrained_seed.observed_at + timedelta(days=1),
            spot_balances=constrained_seed.spot_balances,
            earn_balances={},
            target_weights={"BTC": Decimal("0.30"), "USDT": Decimal("0.70")},
            symbol_filters={"BTCUSDT": filters},
        )
        constrained = _simulate(tmp_path, constrained_run).policies["baseline"]
        assert constrained.trade_count == 0, suffix
        assert constrained.skipped_count > 0


def test_unfunded_buy_is_skipped_whole_after_sell_costs_without_negative_balances(tmp_path) -> None:
    seed = _run(
        spot_balances={"BTC": Decimal("0.01"), "ETH": Decimal("0.9")},
        earn_balances={},
        target_weights={"BTC": Decimal("0.25"), "ETH": Decimal("0.75")},
    )
    _simulate(tmp_path, seed)
    observed = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        spot_balances=seed.spot_balances,
        earn_balances={},
        target_weights={"BTC": Decimal("0.5"), "ETH": Decimal("0.5")},
    )

    result = _simulate(tmp_path, observed)

    baseline = result.policies["baseline"]
    assert [trade.side for trade in baseline.trades] == ["SELL"]
    assert baseline.skipped_count >= 1
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        inventory = json.loads(connection.execute(
            "SELECT inventory_json FROM shadow_sessions WHERE policy='baseline'"
        ).fetchone()[0])
    assert all(Decimal(quantity) >= 0 for quantity in inventory.values())


def test_observed_drawdown_includes_seed_and_does_not_claim_intraday_data(tmp_path) -> None:
    seed = _run(target_weights={"BTC": Decimal("0.25"), "ETH": Decimal("0.1666666667"), "USDT": Decimal("0.5833333333")})
    _simulate(tmp_path, seed)
    drawdown = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        prices={"BTC": Decimal("15000"), "ETH": Decimal("1000"), "USDT": Decimal("1")},
        drift_threshold=Decimal("1"),
    )

    result = _simulate(tmp_path, drawdown)

    assert result.policies["hold"].equity == Decimal("1050.00")
    assert result.policies["hold"].net_return == Decimal("-0.125")
    assert result.policies["hold"].max_drawdown == Decimal("0.125")


def test_observed_drawdown_remains_after_recovery_to_previous_peak(tmp_path) -> None:
    seed = _run(target_weights={"BTC": Decimal("0.25"), "ETH": Decimal("0.1666666667"), "USDT": Decimal("0.5833333333")})
    _simulate(tmp_path, seed)
    trough = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        prices={"BTC": Decimal("15000"), "ETH": Decimal("1000"), "USDT": Decimal("1")},
        drift_threshold=Decimal("1"),
    )
    low = _simulate(tmp_path, trough).policies["hold"]
    recovered = _run(
        run_id="run-003",
        observed_at=seed.observed_at + timedelta(days=2),
        drift_threshold=Decimal("1"),
    )

    high = _simulate(tmp_path, recovered).policies["hold"]

    assert low.max_drawdown == Decimal("0.125")
    assert high.equity == Decimal("1200.00")
    assert high.max_drawdown == Decimal("0.125")


def test_missing_actionable_filter_pauses_all_policies_and_retry_does_not_skip(tmp_path) -> None:
    seed = _run()
    _simulate(tmp_path, seed)
    missing = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        symbol_filters={"BTCUSDT": seed.symbol_filters["BTCUSDT"]},
    )

    paused = _simulate(tmp_path, missing)

    assert {item.status for item in paused.policies.values()} == {"incomplete"}
    assert "ETHUSDT" in paused.policies["baseline"].incomplete_symbols
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        assert set(connection.execute("SELECT last_run_id FROM shadow_sessions").fetchall()) == {("run-001",)}

    retried = _simulate(tmp_path, replace(missing, symbol_filters=seed.symbol_filters))
    assert {item.status for item in retried.policies.values()} == {"complete"}
    assert retried.policies["baseline"].trade_count > 0


def test_missing_required_price_pauses_without_advancing_and_returns_null_deltas(tmp_path) -> None:
    seed = _run()
    _simulate(tmp_path, seed)
    incomplete = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        prices={"BTC": Decimal("30000"), "USDT": Decimal("1")},
    )

    result = _simulate(tmp_path, incomplete)

    assert {item.status for item in result.policies.values()} == {"incomplete"}
    assert all(item.net_return is None and item.equity is None for item in result.policies.values())
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        assert set(connection.execute("SELECT last_run_id FROM shadow_sessions").fetchall()) == {("run-001",)}


def test_missing_price_for_persisted_virtual_only_asset_pauses_and_can_retry(tmp_path) -> None:
    seed = _run(
        spot_balances={"BTC": Decimal("0.01"), "DOGE": Decimal("0.0001"), "USDT": Decimal("700")},
        prices={"BTC": Decimal("30000"), "DOGE": Decimal("1"), "ETH": Decimal("1000"), "USDT": Decimal("1")},
    )
    _simulate(tmp_path, seed)
    later = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        prices={"BTC": Decimal("30000"), "ETH": Decimal("1000"), "USDT": Decimal("1")},
        snapshot_complete=False,
    )

    paused = _simulate(tmp_path, later)

    assert {item.status for item in paused.policies.values()} == {"incomplete"}
    financial_fields = (
        "initial_equity", "equity", "net_return", "modeled_cost", "gross_turnover",
        "relative_turnover", "max_drawdown", "residual_drift",
    )
    assert all(
        getattr(item, field) is None
        for item in paused.policies.values()
        for field in financial_fields
    )
    assert all("DOGEUSDT" in item.incomplete_symbols for item in paused.policies.values())
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        assert set(connection.execute("SELECT last_run_id FROM shadow_sessions").fetchall()) == {("run-001",)}

    retried = _simulate(
        tmp_path,
        replace(later, prices={**later.prices, "DOGE": Decimal("1")}, snapshot_complete=True),
    )
    assert {item.status for item in retried.policies.values()} == {"complete"}


def test_invalid_quote_price_is_incomplete_and_does_not_advance(tmp_path) -> None:
    seed = _run()
    _simulate(tmp_path, seed)
    invalid = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        prices={**seed.prices, "USDT": Decimal("0")},
    )

    paused = _simulate(tmp_path, invalid)

    assert {item.status for item in paused.policies.values()} == {"incomplete"}
    assert all(item.incomplete_symbols == ("USDT",) for item in paused.policies.values())
    financial_fields = (
        "initial_equity", "equity", "net_return", "modeled_cost", "gross_turnover",
        "relative_turnover", "max_drawdown", "residual_drift",
    )
    assert all(
        getattr(item, field) is None
        for item in paused.policies.values()
        for field in financial_fields
    )
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        assert set(connection.execute("SELECT last_run_id FROM shadow_sessions").fetchall()) == {("run-001",)}

    corrected = _simulate(tmp_path, replace(invalid, prices={**invalid.prices, "USDT": Decimal("1")}))
    assert {item.status for item in corrected.policies.values()} == {"complete"}


def test_missing_btc_volatility_pauses_initial_seed_and_allows_retry(tmp_path) -> None:
    invalid = _run(btc_vol30=None)

    paused = _simulate(tmp_path, invalid)

    assert {item.status for item in paused.policies.values()} == {"incomplete"}
    assert all(item.incomplete_symbols == ("BTCUSDT",) for item in paused.policies.values())
    financial_fields = (
        "initial_equity", "equity", "net_return", "modeled_cost", "gross_turnover",
        "relative_turnover", "max_drawdown", "residual_drift",
    )
    assert all(
        getattr(item, field) is None
        for item in paused.policies.values()
        for field in financial_fields
    )
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM shadow_completed_runs").fetchone()[0] == 0

    corrected = _simulate(tmp_path, replace(invalid, btc_vol30=Decimal("0.04")))
    assert {item.status for item in corrected.policies.values()} == {"seeded"}


def test_missing_btc_volatility_pauses_all_policies_and_allows_retry(tmp_path) -> None:
    seed = _run()
    _simulate(tmp_path, seed)
    invalid = _run(
        run_id="run-002",
        observed_at=seed.observed_at + timedelta(days=1),
        btc_vol30=None,
    )

    paused = _simulate(tmp_path, invalid)

    assert {item.status for item in paused.policies.values()} == {"incomplete"}
    assert all(item.incomplete_symbols == ("BTCUSDT",) for item in paused.policies.values())
    financial_fields = (
        "initial_equity", "equity", "net_return", "modeled_cost", "gross_turnover",
        "relative_turnover", "max_drawdown", "residual_drift",
    )
    assert all(
        getattr(item, field) is None
        for item in paused.policies.values()
        for field in financial_fields
    )
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        assert set(connection.execute("SELECT last_run_id FROM shadow_sessions").fetchall()) == {("run-001",)}

    corrected = _simulate(tmp_path, replace(invalid, btc_vol30=Decimal("0.04")))
    assert {item.status for item in corrected.policies.values()} == {"complete"}


def test_matched_ld_earn_alias_is_not_counted_twice(tmp_path) -> None:
    run = _run(
        spot_balances={"LDABC": Decimal("2"), "USDT": Decimal("100")},
        earn_balances={"ABC": Decimal("3")},
        prices={"ABC": Decimal("10"), "USDT": Decimal("1")},
        target_weights={"ABC": Decimal("0.3"), "USDT": Decimal("0.7")},
    )
    result = _simulate(tmp_path, run)
    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        payload = json.loads(connection.execute("SELECT inventory_json FROM shadow_sessions WHERE policy='hold'").fetchone()[0])
    assert payload == {"ABC": "3", "USDT": "100"}
    assert result.policies["hold"].initial_equity == Decimal("130")


def test_completed_run_replay_is_idempotent_and_conflicting_replay_fails_closed(tmp_path) -> None:
    seed = _run()
    _simulate(tmp_path, seed)
    second = _run(run_id="run-002", observed_at=seed.observed_at + timedelta(days=1))
    first_result = _simulate(tmp_path, second)
    replay = _simulate(tmp_path, second)
    assert replay.policies["baseline"].gross_turnover == first_result.policies["baseline"].gross_turnover
    assert replay.policies["baseline"].policy_version == "shadow_policy_v1"
    with pytest.raises(ValueError, match="Conflicting completed"):
        _simulate(tmp_path, replace(second, prices={**second.prices, "BTC": Decimal("31000")}))


def test_market_database_contains_aggregates_only_and_performance_store_is_untouched(tmp_path) -> None:
    run = _run()
    _simulate(tmp_path, run)
    market_db = tmp_path / "market_insights.db"
    with sqlite3.connect(market_db) as connection:
        rows = connection.execute("SELECT payload_json FROM shadow_policy_observations").fetchall()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert len(rows) == 3
    assert all(json.loads(row[0])["policy_version"] == "shadow_policy_v1" for row in rows)
    assert all("inventory" not in row[0] and "balances" not in row[0] for row in rows)
    assert "shadow_sessions" not in tables
    assert not (tmp_path / "performance.db").exists()


def test_incomplete_market_observation_is_replaced_by_corrected_retry(tmp_path) -> None:
    invalid = _run(snapshot_complete=False)
    first = _simulate(tmp_path, invalid)
    assert {item.status for item in first.policies.values()} == {"incomplete"}
    corrected = _simulate(tmp_path, replace(invalid, snapshot_complete=True))
    assert {item.status for item in corrected.policies.values()} == {"seeded"}
    with sqlite3.connect(tmp_path / "market_insights.db") as connection:
        rows = connection.execute("SELECT payload_json FROM shadow_policy_observations").fetchall()
    assert all('"status":"seeded"' in row[0] for row in rows)


def test_combined_cost_rates_above_one_are_rejected_before_seeding(tmp_path) -> None:
    with pytest.raises(ValueError, match="combined Shadow cost rates cannot exceed one"):
        _simulate(
            tmp_path,
            _run(),
            ShadowCosts(fee_rate=Decimal("0.7"), slippage_rate=Decimal("0.4")),
        )

    shadow_db = tmp_path / "shadow_portfolios.db"
    assert not shadow_db.exists()


def test_sqlite_connection_is_closed_after_simulation(tmp_path, monkeypatch) -> None:
    original_connect = sqlite3.connect
    opened = []

    def capture_connection(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", capture_connection)

    _simulate(tmp_path, _run())

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_sqlite_connection_is_closed_after_simulator_rollback(tmp_path, monkeypatch) -> None:
    original_connect = sqlite3.connect
    original_persist = shadow_portfolios.persist_shadow_aggregates_in_transaction
    opened = []

    def capture_connection(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    def fail_final_aggregate_write(connection, observations, *, schema="main"):
        if observations:
            raise sqlite3.OperationalError("injected aggregate failure")
        return original_persist(connection, observations, schema=schema)

    monkeypatch.setattr(sqlite3, "connect", capture_connection)
    monkeypatch.setattr(
        shadow_portfolios, "persist_shadow_aggregates_in_transaction", fail_final_aggregate_write
    )

    with pytest.raises(sqlite3.OperationalError, match="injected aggregate failure"):
        _simulate(tmp_path, _run())

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")
    with original_connect(tmp_path / "shadow_portfolios.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()[0] == 0


def test_market_persistence_failure_rolls_back_shadow_state_before_retry(tmp_path) -> None:
    run = _run()
    shadow_db = tmp_path / "shadow_portfolios.db"
    market_db = tmp_path / "market_insights.db"
    with sqlite3.connect(market_db) as connection:
        connection.execute(
            "CREATE TABLE market_indicator_metadata (component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO market_indicator_metadata VALUES ('market_indicators', 1)")
        connection.execute(
            "CREATE TABLE market_indicator_snapshots (metrics_version TEXT NOT NULL, input_fingerprint TEXT NOT NULL, observed_at TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(metrics_version, input_fingerprint))"
        )
        connection.execute("CREATE TABLE shadow_policy_observations (wrong_column TEXT)")
    with pytest.raises(sqlite3.OperationalError):
        simulate_shadow_run(run, shadow_db_path=shadow_db, market_db_path=market_db)

    with sqlite3.connect(shadow_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM shadow_completed_runs").fetchone()[0] == 0
    with sqlite3.connect(market_db) as connection:
        connection.execute("DROP TABLE shadow_policy_observations")
    replay = simulate_shadow_run(run, shadow_db_path=shadow_db, market_db_path=market_db)

    assert {item.status for item in replay.policies.values()} == {"seeded"}
    with sqlite3.connect(shadow_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_completed_runs").fetchone()[0] == 3
    with sqlite3.connect(market_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_policy_observations").fetchone()[0] == 3


def test_wal_mode_fails_closed_before_any_shadow_session_advances(tmp_path) -> None:
    market_db = tmp_path / "market_insights.db"
    with sqlite3.connect(market_db) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"

    with pytest.raises(ValueError, match="requires SQLite journal mode other than WAL"):
        simulate_shadow_run(
            _run(),
            shadow_db_path=tmp_path / "shadow_portfolios.db",
            market_db_path=market_db,
        )

    with sqlite3.connect(tmp_path / "shadow_portfolios.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()[0] == 0


def test_timestamps_in_different_timezones_are_ordered_in_utc(tmp_path) -> None:
    seed = _run(observed_at=datetime(2026, 10, 1, 12, tzinfo=timezone(timedelta(hours=2))))
    _simulate(tmp_path, seed)
    later = _run(
        run_id="run-002",
        observed_at=datetime(2026, 10, 1, 10, 30, tzinfo=UTC),
    )

    result = _simulate(tmp_path, later)

    assert {item.status for item in result.policies.values()} == {"complete"}
