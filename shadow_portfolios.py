from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Mapping

from binance_client import Balance, SymbolFilters
from market_insights import (
    load_shadow_aggregates_in_transaction,
    persist_shadow_aggregates_in_transaction,
)
from portfolio import (
    TradeInstruction,
    build_trades,
    compute_current_weights,
    decide_rebalance,
    filter_dust_positions,
    rebalance_has_tradable_orders,
)


POLICY_VERSION = "shadow_policy_v1"
SHADOW_SCHEMA_VERSION = 2
DEFAULT_SHADOW_DB_PATH = Path("state/shadow_portfolios.db")
DEFAULT_MARKET_DB_PATH = Path("state/market_insights.db")
DECIMAL_PRECISION = 48
POLICY_NAMES = ("hold", "baseline", "volatility_guard_v1")
DEFAULT_FEE_RATE = Decimal("0.001")
DEFAULT_SLIPPAGE_RATE = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class ShadowRun:
    session_id: str
    run_id: str
    observed_at: datetime
    quote_asset: str
    spot_balances: Mapping[str, Decimal]
    earn_balances: Mapping[str, Decimal]
    prices: Mapping[str, Decimal]
    target_weights: Mapping[str, Decimal]
    drift_threshold: Decimal
    btc_vol30: Decimal | None
    symbol_filters: Mapping[str, SymbolFilters]
    snapshot_complete: bool = True
    min_notional: Decimal = Decimal("10")
    min_notional_uplift_tolerance: Decimal = Decimal(0)
    max_slippage: Decimal = Decimal("0.003")
    advice_action: str = "redistribute"


@dataclass(frozen=True, slots=True)
class ShadowCosts:
    fee_rate: Decimal = DEFAULT_FEE_RATE
    slippage_rate: Decimal = DEFAULT_SLIPPAGE_RATE


@dataclass(frozen=True, slots=True)
class SimulatedTrade:
    symbol: str
    asset: str
    side: str
    quantity: Decimal
    reference_price: Decimal
    gross_notional: Decimal
    modeled_cost: Decimal


@dataclass(frozen=True, slots=True)
class PolicyResult:
    policy: str
    status: str
    initial_equity: Decimal | None
    equity: Decimal | None
    net_return: Decimal | None
    modeled_cost: Decimal | None
    gross_turnover: Decimal | None
    relative_turnover: Decimal | None
    max_drawdown: Decimal | None
    residual_drift: Decimal | None
    trades: tuple[SimulatedTrade, ...] = ()
    skipped_orders: tuple[str, ...] = ()
    incomplete_symbols: tuple[str, ...] = ()
    trade_count: int = 0
    skipped_count: int = 0
    policy_version: str = POLICY_VERSION


@dataclass(frozen=True, slots=True)
class ShadowRunResult:
    session_id: str
    run_id: str
    input_fingerprint: str
    policies: Mapping[str, PolicyResult]
    policy_fingerprints: Mapping[str, str]


def simulate_shadow_run(
    run: ShadowRun,
    *,
    shadow_db_path: str | Path = DEFAULT_SHADOW_DB_PATH,
    market_db_path: str | Path = DEFAULT_MARKET_DB_PATH,
    costs: ShadowCosts = ShadowCosts(),
) -> ShadowRunResult:
    """Advance isolated virtual portfolios from captured inputs only."""
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return _simulate_shadow_run(run, shadow_db_path, market_db_path, costs)


def _simulate_shadow_run(
    run: ShadowRun,
    shadow_db_path: str | Path,
    market_db_path: str | Path,
    costs: ShadowCosts,
) -> ShadowRunResult:
    shadow_path = Path(shadow_db_path)
    market_path = Path(market_db_path)
    if shadow_path.resolve() == market_path.resolve():
        raise ValueError("Shadow state and market insights require separate databases")
    if market_path.name.lower() == "performance.db":
        raise ValueError("Shadow results must not be written to performance.db")
    costs = ShadowCosts(_decimal(costs.fee_rate), _decimal(costs.slippage_rate))
    _validate_identity(run, costs)
    normalized = _normalize_run(run)
    run_fingerprint = _fingerprint(normalized, costs)

    shadow_path.parent.mkdir(parents=True, exist_ok=True)
    market_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(shadow_path, timeout=5)) as connection, connection:
        connection.row_factory = sqlite3.Row
        _ensure_shadow_schema(connection)
        connection.commit()
        connection.execute("ATTACH DATABASE ? AS market_insights", (str(market_path),))
        journal_modes = {
            schema: connection.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0].lower()
            for schema in ("main", "market_insights")
        }
        if any(mode == "wal" for mode in journal_modes.values()):
            raise ValueError("Shadow cross-database transaction requires SQLite journal mode other than WAL")
        persist_shadow_aggregates_in_transaction(connection, (), schema="market_insights")
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        completed = _read_completed(connection, run, normalized, costs)
        if completed is not None:
            result = completed
        else:
            sessions = {
                row["policy"]: row
                for row in connection.execute(
                    "SELECT * FROM shadow_sessions WHERE session_id = ?",
                    (run.session_id,),
                )
            }
            persisted_assets = {
                asset
                for state in sessions.values()
                for asset in _read_inventory(state["inventory_json"])
            }
            missing_prices = _missing_price_symbols(normalized, persisted_assets)
            if (
                not run.snapshot_complete
                or missing_prices
                or run.btc_vol30 is None
                or not normalized["inventory"]
                or _equity(normalized["inventory"], normalized["prices"]) <= 0
            ):
                incomplete_symbols = set(missing_prices)
                if run.btc_vol30 is None:
                    incomplete_symbols.add("BTCUSDT")
                result = _incomplete_result(
                    run, run_fingerprint, POLICY_NAMES, tuple(sorted(incomplete_symbols))
                )
            elif not sessions:
                result = _seed_sessions(connection, run, normalized, costs)
            else:
                if set(sessions) != set(POLICY_NAMES):
                    raise ValueError("Shadow session is missing a policy state")
                result = _advance_sessions(
                    connection, run, normalized, costs, sessions
                )
        _persist_aggregates(connection, run, result)
        connection.commit()
    return result


def _seed_sessions(
    connection: sqlite3.Connection,
    run: ShadowRun,
    normalized: Mapping[str, object],
    costs: ShadowCosts,
) -> ShadowRunResult:
    inventory = _initial_inventory(normalized)
    prices = normalized["prices"]
    assert isinstance(prices, dict)
    equity = _equity(inventory, prices)
    results: dict[str, PolicyResult] = {}
    for policy in POLICY_NAMES:
        fingerprint = _fingerprint(normalized, costs)
        result = PolicyResult(
            policy=policy,
            status="seeded",
            initial_equity=equity,
            equity=equity,
            net_return=Decimal(0),
            modeled_cost=Decimal(0),
            gross_turnover=Decimal(0),
            relative_turnover=Decimal(0),
            max_drawdown=Decimal(0),
            residual_drift=_residual_drift(inventory, prices, normalized["targets"]),
            trade_count=0,
            skipped_count=0,
        )
        _write_session(
            connection,
            run,
            policy,
            inventory,
            initial_equity=equity,
            equity=equity,
            peak_equity=equity,
            cumulative_cost=Decimal(0),
            cumulative_turnover=Decimal(0),
            max_drawdown=Decimal(0),
            fingerprint=fingerprint,
        )
        _write_completed(connection, run, result, fingerprint)
        results[policy] = result
    fingerprints = {policy: _fingerprint(normalized, costs) for policy in POLICY_NAMES}
    return ShadowRunResult(run.session_id, run.run_id, _fingerprint(normalized, costs), results, fingerprints)


def _advance_sessions(
    connection: sqlite3.Connection,
    run: ShadowRun,
    normalized: Mapping[str, object],
    costs: ShadowCosts,
    sessions: Mapping[str, sqlite3.Row],
) -> ShadowRunResult:
    persisted_assets = {
        asset
        for state in sessions.values()
        for asset in _read_inventory(state["inventory_json"])
    }
    missing_prices = _missing_price_symbols(normalized, persisted_assets)
    if missing_prices:
        return _incomplete_result(
            run, _fingerprint(normalized, costs), POLICY_NAMES, missing_prices
        )

    results: dict[str, PolicyResult] = {}
    run_fingerprint = _fingerprint(normalized, costs)
    fingerprints = {policy: run_fingerprint for policy in POLICY_NAMES}
    pending_updates: dict[str, dict[str, object]] = {}
    for policy in POLICY_NAMES:
        state = sessions[policy]
        if state["policy_version"] != POLICY_VERSION:
            raise ValueError("Shadow policy version changed; start a new session")
        fingerprint = run_fingerprint
        if state["last_run_id"] == run.run_id:
            if state["last_fingerprint"] != fingerprint:
                raise ValueError("Conflicting completed shadow run fingerprint")
            raise ValueError("Completed shadow run is missing its replay record")
        observed = _timestamp(run.observed_at)
        if observed <= state["last_observed_at"]:
            raise ValueError("Shadow runs must advance in observation time")
        inventory = _read_inventory(state["inventory_json"])
        prices = normalized["prices"]
        targets = normalized["targets"]
        assert isinstance(prices, dict) and isinstance(targets, dict)
        current_equity = _equity(inventory, prices)
        threshold = _threshold(run, policy)
        if threshold is None:
            results[policy] = _incomplete_policy(policy, ("BTCUSDT",))
            continue
        trades: tuple[SimulatedTrade, ...] = ()
        skipped: tuple[str, ...] = ()
        if policy != "hold":
            planned, skipped = _plan_policy_orders(inventory, prices, targets, threshold, run)
            if planned is None:
                results[policy] = _incomplete_policy(policy, skipped)
                continue
            inventory, trades, funding_skips = _execute_orders(
                inventory, prices, planned, run, costs
            )
            skipped += funding_skips
        resulting_equity = _equity(inventory, prices)
        cumulative_cost = _decimal(state["cumulative_cost"]) + sum(
            (trade.modeled_cost for trade in trades), Decimal(0)
        )
        cumulative_turnover = _decimal(state["cumulative_turnover"]) + sum(
            (trade.gross_notional for trade in trades), Decimal(0)
        )
        initial_equity = _decimal(state["initial_equity"])
        peak_equity = max(_decimal(state["peak_equity"]), resulting_equity)
        drawdown = max(
            _decimal(state["max_drawdown"]),
            (peak_equity - resulting_equity) / peak_equity if peak_equity else Decimal(0),
        )
        result = PolicyResult(
            policy=policy,
            status="complete",
            initial_equity=initial_equity,
            equity=resulting_equity,
            net_return=resulting_equity / initial_equity - 1,
            modeled_cost=cumulative_cost,
            gross_turnover=cumulative_turnover,
            relative_turnover=cumulative_turnover / initial_equity,
            max_drawdown=drawdown,
            residual_drift=_residual_drift(inventory, prices, targets),
            trades=trades,
            skipped_orders=skipped,
            trade_count=len(trades),
            skipped_count=len(skipped),
        )
        pending_updates[policy] = {
            "inventory": inventory,
            "initial_equity": initial_equity,
            "equity": resulting_equity,
            "peak_equity": peak_equity,
            "cumulative_cost": cumulative_cost,
            "cumulative_turnover": cumulative_turnover,
            "max_drawdown": drawdown,
            "fingerprint": fingerprint,
        }
        results[policy] = result

    if any(item.status == "incomplete" for item in results.values()):
        symbols = {
            policy: results[policy].incomplete_symbols
            if policy in results and results[policy].status == "incomplete" else ()
            for policy in POLICY_NAMES
        }
        paused = {policy: _incomplete_policy(policy, symbols[policy]) for policy in POLICY_NAMES}
        return ShadowRunResult(run.session_id, run.run_id, run_fingerprint, paused, fingerprints)

    for policy, update in pending_updates.items():
        _write_session(connection, run, policy, **update)
        _write_completed(connection, run, results[policy], str(update["fingerprint"]))
    return ShadowRunResult(run.session_id, run.run_id, run_fingerprint, results, fingerprints)


def _plan_policy_orders(
    inventory: Mapping[str, Decimal],
    prices: Mapping[str, Decimal],
    targets: Mapping[str, Decimal],
    threshold: Decimal,
    run: ShadowRun,
) -> tuple[tuple[TradeInstruction, ...] | None, tuple[str, ...]]:
    quote = run.quote_asset.upper()
    filters = {key.upper(): value for key, value in run.symbol_filters.items()}
    balances = [Balance(asset=asset, free=float(qty), locked=0.0) for asset, qty in inventory.items()]
    float_prices = {asset: float(price) for asset, price in prices.items()}
    snapshot = compute_current_weights(balances, float_prices, quote)
    snapshot, _dust = filter_dust_positions(snapshot, filters, float(run.min_notional))
    decision = decide_rebalance(
        snapshot,
        {asset: float(weight) for asset, weight in targets.items()},
        float(threshold),
    )
    if not decision.rebalance_needed:
        return (), ()

    missing = tuple(sorted(
        f"{asset}{quote}"
        for asset, delta in decision.deltas.items()
        if asset != quote and delta != 0 and f"{asset}{quote}" not in filters
    ))
    if missing:
        return None, missing

    rejections: list[str] = []
    non_actionable: list[str] = []
    tradable = rebalance_has_tradable_orders(
        snapshot=snapshot,
        decision=decision,
        prices=float_prices,
        filters=filters,
        min_notional=float(run.min_notional),
        min_notional_uplift_tolerance=float(run.min_notional_uplift_tolerance),
        rejections=rejections,
        non_actionable_rejections=non_actionable,
    )
    if not tradable:
        return (), tuple(rejections + non_actionable)
    rejections.clear()
    non_actionable.clear()
    instructions = build_trades(
        snapshot=snapshot,
        decision=decision,
        prices=float_prices,
        filters=filters,
        min_notional=float(run.min_notional),
        max_slippage=float(run.max_slippage),
        min_notional_uplift_tolerance=float(run.min_notional_uplift_tolerance),
        rejections=rejections,
        non_actionable_rejections=non_actionable,
    )
    instructions.sort(key=lambda order: (order.side != "SELL", order.asset))
    return tuple(instructions), tuple(rejections + non_actionable)


def _execute_orders(
    inventory: dict[str, Decimal],
    prices: Mapping[str, Decimal],
    orders: tuple[TradeInstruction, ...],
    run: ShadowRun,
    costs: ShadowCosts,
) -> tuple[dict[str, Decimal], tuple[SimulatedTrade, ...], tuple[str, ...]]:
    simulated: list[SimulatedTrade] = []
    skipped: list[str] = []
    quote_asset = run.quote_asset.upper()
    quote = inventory.get(quote_asset, Decimal(0))
    for order in orders:
        side, asset = order.side, order.asset
        quantity = _decimal(str(order.quantity))
        price = prices[asset]
        notional = quantity * price
        modeled_cost = notional * (costs.fee_rate + costs.slippage_rate)
        if side == "SELL":
            if quantity > inventory.get(asset, Decimal(0)):
                skipped.append(f"{order.symbol}: sell exceeds virtual inventory")
                continue
            inventory[asset] = inventory.get(asset, Decimal(0)) - quantity
            quote += notional - modeled_cost
        else:
            if notional + modeled_cost > quote:
                skipped.append(f"{order.symbol}: insufficient quote balance")
                continue
            inventory[asset] = inventory.get(asset, Decimal(0)) + quantity
            quote -= notional + modeled_cost
        simulated.append(SimulatedTrade(
            symbol=order.symbol,
            asset=asset,
            side=side,
            quantity=quantity,
            reference_price=price,
            gross_notional=notional,
            modeled_cost=modeled_cost,
        ))
    inventory[quote_asset] = quote
    return inventory, tuple(simulated), tuple(skipped)


def _threshold(run: ShadowRun, policy: str) -> Decimal | None:
    if policy != "volatility_guard_v1":
        return _decimal(run.drift_threshold)
    if run.btc_vol30 is None:
        return None
    multiplier = Decimal(2) if _decimal(run.btc_vol30) >= Decimal("0.06") else Decimal(1)
    return _decimal(run.drift_threshold) * multiplier


def _normalize_run(run: ShadowRun) -> dict[str, object]:
    quote = run.quote_asset.upper()
    inventory: dict[str, Decimal] = {}
    earn_assets = {asset.upper() for asset, amount in run.earn_balances.items() if _decimal(amount) > 0}
    for source in (run.spot_balances, run.earn_balances):
        for raw_asset, amount in source.items():
            asset = raw_asset.upper()
            quantity = _decimal(amount)
            if quantity < 0:
                raise ValueError("Shadow balances cannot be negative")
            if source is run.spot_balances and asset.startswith("LD") and asset[2:] in earn_assets:
                continue
            inventory[asset] = inventory.get(asset, Decimal(0)) + quantity
    inventory = {asset: qty for asset, qty in inventory.items() if qty > 0}
    prices = {asset.upper(): _decimal(price) for asset, price in run.prices.items()}
    prices.setdefault(quote, Decimal(1))
    targets_raw = {asset.upper(): _decimal(weight) for asset, weight in run.target_weights.items()}
    if any(weight < 0 for weight in targets_raw.values()):
        raise ValueError("Shadow target weights cannot be negative")
    target_total = sum(targets_raw.values(), Decimal(0))
    if target_total <= 0:
        raise ValueError("Shadow target weights must sum to a positive value")
    targets = {asset: weight / target_total for asset, weight in targets_raw.items()}
    return {
        "quote": quote,
        "inventory": inventory,
        "prices": prices,
        "targets": targets,
        "filters": {key.upper(): value for key, value in run.symbol_filters.items()},
        "drift_threshold": _decimal(run.drift_threshold),
        "btc_vol30": _decimal(run.btc_vol30) if run.btc_vol30 is not None else None,
        "min_notional": _decimal(run.min_notional),
        "min_notional_uplift_tolerance": _decimal(run.min_notional_uplift_tolerance),
        "max_slippage": _decimal(run.max_slippage),
        "advice_action": run.advice_action.lower(),
        "observed_at": _timestamp(run.observed_at),
        "snapshot_complete": run.snapshot_complete,
    }


def _missing_price_symbols(
    normalized: Mapping[str, object], extra_assets: set[str] | None = None
) -> tuple[str, ...]:
    inventory = normalized["inventory"]
    prices = normalized["prices"]
    targets = normalized["targets"]
    quote = normalized["quote"]
    assert (
        isinstance(inventory, dict)
        and isinstance(prices, dict)
        and isinstance(targets, dict)
        and isinstance(quote, str)
    )
    assets = (set(inventory) | set(targets) | (extra_assets or set())) - {quote}
    missing = {
        f"{asset}{quote}"
        for asset in assets
        if asset not in prices or prices[asset] <= 0
    }
    if quote not in prices or prices[quote] <= 0:
        missing.add(quote)
    return tuple(sorted(missing))


def _initial_inventory(normalized: Mapping[str, object]) -> dict[str, Decimal]:
    inventory = normalized["inventory"]
    assert isinstance(inventory, dict)
    return dict(inventory)


def _equity(inventory: Mapping[str, Decimal], prices: Mapping[str, Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return sum((quantity * prices[asset] for asset, quantity in inventory.items()), Decimal(0))


def _residual_drift(
    inventory: Mapping[str, Decimal],
    prices: Mapping[str, Decimal],
    targets: Mapping[str, Decimal],
) -> Decimal:
    equity = _equity(inventory, prices)
    if equity <= 0:
        return Decimal(0)
    assets = set(inventory) | set(targets)
    return max(
        (abs(targets.get(asset, Decimal(0)) - inventory.get(asset, Decimal(0)) * prices[asset] / equity)
         for asset in assets),
        default=Decimal(0),
    )


def _fingerprint(normalized: Mapping[str, object], costs: ShadowCosts) -> str:
    payload = _canonical_value({
        "normalized": normalized,
        "costs": costs,
        "policy_version": POLICY_VERSION,
    })
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, SymbolFilters):
        return {key: _canonical_value(item) for key, item in asdict(value).items()}
    if hasattr(value, "__dataclass_fields__"):
        return {key: _canonical_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def _validate_identity(run: ShadowRun, costs: ShadowCosts) -> None:
    if not run.session_id.strip() or not run.run_id.strip():
        raise ValueError("Shadow session_id and run_id are required")
    if not run.quote_asset.strip():
        raise ValueError("Shadow quote asset is required")
    if _decimal(run.drift_threshold) < 0:
        raise ValueError("Shadow drift threshold cannot be negative")
    if any(_decimal(value) < 0 for value in (
        run.min_notional, run.min_notional_uplift_tolerance, run.max_slippage
    )):
        raise ValueError("Shadow planner settings cannot be negative")
    if costs.fee_rate < 0 or costs.slippage_rate < 0:
        raise ValueError("Shadow cost rates cannot be negative")
    if costs.fee_rate + costs.slippage_rate > 1:
        raise ValueError("combined Shadow cost rates cannot exceed one")
    if not isinstance(run.advice_action, str):
        raise ValueError("Shadow advice action must be text")
    if not run.observed_at.tzinfo or run.observed_at.utcoffset() is None:
        raise ValueError("Shadow observation time must be timezone-aware")


def _ensure_shadow_schema(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS shadow_metadata (schema_version INTEGER NOT NULL)")
    version = connection.execute("SELECT schema_version FROM shadow_metadata").fetchone()
    if version is None:
        connection.execute("INSERT INTO shadow_metadata VALUES (?)", (SHADOW_SCHEMA_VERSION,))
    elif version[0] != SHADOW_SCHEMA_VERSION:
        raise ValueError(f"Unsupported shadow schema version: {version[0]}")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS shadow_sessions (
            session_id TEXT NOT NULL, policy TEXT NOT NULL, policy_version TEXT NOT NULL,
            initial_equity TEXT NOT NULL,
            equity TEXT NOT NULL, peak_equity TEXT NOT NULL, inventory_json TEXT NOT NULL,
            cumulative_cost TEXT NOT NULL, cumulative_turnover TEXT NOT NULL,
            max_drawdown TEXT NOT NULL, last_run_id TEXT NOT NULL, last_fingerprint TEXT NOT NULL,
            last_observed_at TEXT NOT NULL, PRIMARY KEY(session_id, policy))"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS shadow_completed_runs (
            session_id TEXT NOT NULL, run_id TEXT NOT NULL, policy TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL,
            PRIMARY KEY(session_id, run_id, policy))"""
    )


def _write_session(
    connection: sqlite3.Connection,
    run: ShadowRun,
    policy: str,
    inventory: Mapping[str, Decimal],
    initial_equity: Decimal,
    equity: Decimal,
    peak_equity: Decimal,
    cumulative_cost: Decimal,
    cumulative_turnover: Decimal,
    max_drawdown: Decimal,
    fingerprint: str,
) -> None:
    connection.execute(
        """INSERT INTO shadow_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id, policy) DO UPDATE SET
             policy_version=excluded.policy_version, equity=excluded.equity, peak_equity=excluded.peak_equity,
             inventory_json=excluded.inventory_json, cumulative_cost=excluded.cumulative_cost,
             cumulative_turnover=excluded.cumulative_turnover, max_drawdown=excluded.max_drawdown,
             last_run_id=excluded.last_run_id, last_fingerprint=excluded.last_fingerprint,
             last_observed_at=excluded.last_observed_at""",
        (run.session_id, policy, POLICY_VERSION, str(initial_equity), str(equity), str(peak_equity),
         json.dumps({asset: str(qty) for asset, qty in sorted(inventory.items())}, sort_keys=True),
         str(cumulative_cost), str(cumulative_turnover), str(max_drawdown), run.run_id,
         fingerprint, _timestamp(run.observed_at)),
    )


def _write_completed(
    connection: sqlite3.Connection, run: ShadowRun, result: PolicyResult, fingerprint: str
) -> None:
    existing = connection.execute(
        "SELECT input_fingerprint FROM shadow_completed_runs WHERE session_id=? AND run_id=? AND policy=?",
        (run.session_id, run.run_id, result.policy),
    ).fetchone()
    if existing:
        if existing[0] != fingerprint:
            raise ValueError("Conflicting completed shadow run fingerprint")
        return
    connection.execute(
        "INSERT INTO shadow_completed_runs VALUES (?, ?, ?, ?)",
        (run.session_id, run.run_id, result.policy, fingerprint),
    )


def _read_completed(
    connection: sqlite3.Connection,
    run: ShadowRun,
    normalized: Mapping[str, object],
    costs: ShadowCosts,
) -> ShadowRunResult | None:
    rows = connection.execute(
        "SELECT policy, input_fingerprint FROM shadow_completed_runs WHERE session_id=? AND run_id=?",
        (run.session_id, run.run_id),
    ).fetchall()
    if not rows:
        return None
    fingerprints: dict[str, str] = {}
    for row in rows:
        expected = _fingerprint(normalized, costs)
        if expected != row["input_fingerprint"]:
            raise ValueError("Conflicting completed shadow run fingerprint")
        fingerprints[row["policy"]] = row["input_fingerprint"]
    if set(fingerprints) != set(POLICY_NAMES):
        raise ValueError("Completed shadow run is missing a policy result")
    observations = load_shadow_aggregates_in_transaction(
        connection, run.session_id, run.run_id, schema="market_insights"
    )
    results = {str(item["policy"]): _policy_result_from_aggregate(item) for item in observations}
    if set(results) != set(POLICY_NAMES):
        raise ValueError("Completed shadow run is missing aggregate results")
    if any(item["input_fingerprint"] != fingerprints[str(item["policy"])] for item in observations):
        raise ValueError("Shadow state and market aggregate fingerprints diverged")
    fingerprint = _fingerprint(normalized, costs)
    return ShadowRunResult(run.session_id, run.run_id, fingerprint, results, fingerprints)


def _read_inventory(raw: str) -> dict[str, Decimal]:
    return {asset: _decimal(value) for asset, value in json.loads(raw).items()}


def _policy_result_from_aggregate(payload: Mapping[str, object]) -> PolicyResult:
    def optional_decimal(name: str) -> Decimal | None:
        value = payload[name]
        return _decimal(value) if value is not None else None

    return PolicyResult(
        policy=str(payload["policy"]),
        status=str(payload["status"]),
        initial_equity=optional_decimal("initial_equity"),
        equity=optional_decimal("equity"),
        net_return=optional_decimal("net_return"),
        modeled_cost=optional_decimal("modeled_cost"),
        gross_turnover=optional_decimal("gross_turnover"),
        relative_turnover=optional_decimal("relative_turnover"),
        max_drawdown=optional_decimal("max_drawdown"),
        residual_drift=optional_decimal("residual_drift"),
        incomplete_symbols=tuple(payload["incomplete_symbols"]),
        trade_count=int(payload["trade_count"]),
        skipped_count=int(payload["skipped_count"]),
        policy_version=str(payload.get("policy_version", POLICY_VERSION)),
    )


def _incomplete_policy(policy: str, symbols: tuple[str, ...]) -> PolicyResult:
    return PolicyResult(policy, "incomplete", None, None, None, None, None, None, None, None, incomplete_symbols=symbols)


def _incomplete_result(
    run: ShadowRun,
    fingerprint: str,
    policies: tuple[str, ...],
    symbols: tuple[str, ...] = (),
) -> ShadowRunResult:
    return ShadowRunResult(run.session_id, run.run_id, fingerprint, {
        policy: _incomplete_policy(policy, symbols) for policy in policies
    }, {policy: fingerprint for policy in policies})


def _persist_aggregates(
    connection: sqlite3.Connection, run: ShadowRun, result: ShadowRunResult
) -> None:
    observations = []
    for policy, item in result.policies.items():
        observations.append({
            "session_id": run.session_id,
            "run_id": run.run_id,
            "policy": policy,
            "policy_version": item.policy_version,
            "input_fingerprint": result.policy_fingerprints[policy],
            "observed_at": _timestamp(run.observed_at),
            "status": item.status,
            "initial_equity": _optional_string(item.initial_equity),
            "equity": _optional_string(item.equity),
            "net_return": _optional_string(item.net_return),
            "modeled_cost": _optional_string(item.modeled_cost),
            "gross_turnover": _optional_string(item.gross_turnover),
            "relative_turnover": _optional_string(item.relative_turnover),
            "max_drawdown": _optional_string(item.max_drawdown),
            "residual_drift": _optional_string(item.residual_drift),
            "trade_count": item.trade_count,
            "skipped_count": item.skipped_count,
            "incomplete_symbols": list(item.incomplete_symbols),
        })
    persist_shadow_aggregates_in_transaction(
        connection, observations, schema="market_insights"
    )


def _decimal(value: object) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Shadow numeric input must be finite")
    return result


def _optional_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
