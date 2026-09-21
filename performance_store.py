from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
DEFAULT_DB_PATH = Path("state") / "performance.db"


def build_portfolio_snapshot(
    *,
    run_id: str,
    phase: str,
    quote_asset: str,
    spot_balances: Sequence[Mapping[str, Any]],
    earn_positions: Sequence[Mapping[str, Any]],
    prices: Mapping[str, Any],
    timestamp: str,
    data_quality: str | None = None,
    external_flow_status: str = "unknown",
) -> dict[str, Any]:
    quote = quote_asset.upper()
    normalized_prices = {
        str(asset).upper(): _decimal(value)
        for asset, value in prices.items()
        if _decimal(value) is not None and _decimal(value) >= 0
    }
    asset_values: dict[str, Decimal] = {}
    source_totals = {"spot": Decimal("0"), "earn": Decimal("0")}
    missing_prices: set[str] = set()

    for source, balances in (("spot", spot_balances), ("earn", earn_positions)):
        for balance in balances:
            asset = str(balance.get("asset", "")).upper()
            quantity = _decimal(balance.get("quantity"))
            if not asset or quantity is None or quantity <= 0:
                continue
            price = Decimal("1") if asset == quote else normalized_prices.get(asset)
            if price is None:
                missing_prices.add(asset)
                continue
            value = quantity * price
            key = f"{source}:{asset}"
            asset_values[key] = asset_values.get(key, Decimal("0")) + value
            source_totals[source] += value

    quality = data_quality or ("incomplete" if missing_prices else "complete")
    return {
        "run_id": run_id,
        "phase": phase,
        "timestamp": timestamp,
        "quote_asset": quote,
        "spot_value": _money(source_totals["spot"]),
        "earn_value": _money(source_totals["earn"]),
        "total_value": _money(source_totals["spot"] + source_totals["earn"]),
        "prices": {asset: _money(price) for asset, price in sorted(normalized_prices.items())},
        "asset_values": {
            key: _money(value) for key, value in sorted(asset_values.items())
        },
        "data_quality": quality,
        "external_flow_status": external_flow_status,
        "missing_prices": sorted(missing_prices),
    }


def record_portfolio_snapshot(
    db_path: str | Path | None,
    snapshot: Mapping[str, Any],
) -> None:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        connection.execute(
            """
            INSERT INTO portfolio_snapshots (
                run_id, phase, timestamp, quote_asset, spot_value, earn_value,
                total_value, prices_json, asset_values_json, data_quality,
                external_flow_status, missing_prices_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, phase) DO UPDATE SET
                timestamp=excluded.timestamp,
                quote_asset=excluded.quote_asset,
                spot_value=excluded.spot_value,
                earn_value=excluded.earn_value,
                total_value=excluded.total_value,
                prices_json=excluded.prices_json,
                asset_values_json=excluded.asset_values_json,
                data_quality=excluded.data_quality,
                external_flow_status=excluded.external_flow_status,
                missing_prices_json=excluded.missing_prices_json
            """,
            (
                str(snapshot["run_id"]),
                str(snapshot["phase"]),
                str(snapshot["timestamp"]),
                str(snapshot["quote_asset"]).upper(),
                str(snapshot["spot_value"]),
                str(snapshot["earn_value"]),
                str(snapshot["total_value"]),
                _json(snapshot.get("prices", {})),
                _json(snapshot.get("asset_values", {})),
                str(snapshot.get("data_quality", "unknown")),
                str(snapshot.get("external_flow_status", "unknown")),
                _json(snapshot.get("missing_prices", [])),
            ),
        )


def load_portfolio_snapshots(
    db_path: str | Path | None,
    *,
    run_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    if not path.exists():
        return []
    query = "SELECT * FROM portfolio_snapshots"
    parameters: list[Any] = []
    if run_id is not None:
        query += " WHERE run_id = ?"
        parameters.append(run_id)
    query += " ORDER BY timestamp ASC, run_id ASC, phase ASC"
    if limit is not None:
        query += " LIMIT ?"
        parameters.append(limit)

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()
    return [_decode_snapshot(dict(row)) for row in rows]


def record_external_flow(
    db_path: str | Path | None,
    flow: Mapping[str, Any],
) -> None:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        connection.execute(
            """
            INSERT INTO external_flows(
                flow_id, timestamp, asset, quote_value, direction, source, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(flow_id) DO UPDATE SET
                timestamp=excluded.timestamp,
                asset=excluded.asset,
                quote_value=excluded.quote_value,
                direction=excluded.direction,
                source=excluded.source,
                confidence=excluded.confidence
            """,
            (
                str(flow["flow_id"]),
                str(flow["timestamp"]),
                str(flow["asset"]).upper(),
                str(flow["quote_value"]),
                str(flow["direction"]).lower(),
                str(flow.get("source", "unknown")),
                str(flow.get("confidence", "unknown")),
            ),
        )


def load_external_flows(
    db_path: str | Path | None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    if not path.exists():
        return []
    query = "SELECT flow_id, timestamp, asset, quote_value, direction, source, confidence FROM external_flows ORDER BY timestamp ASC"
    parameters: list[Any] = []
    if limit is not None:
        query += " LIMIT ?"
        parameters.append(limit)
    with sqlite3.connect(path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    fields = ("flow_id", "timestamp", "asset", "quote_value", "direction", "source", "confidence")
    return [dict(zip(fields, row)) for row in rows]


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            run_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            quote_asset TEXT NOT NULL,
            spot_value TEXT NOT NULL,
            earn_value TEXT NOT NULL,
            total_value TEXT NOT NULL,
            prices_json TEXT NOT NULL,
            asset_values_json TEXT NOT NULL,
            data_quality TEXT NOT NULL,
            external_flow_status TEXT NOT NULL,
            missing_prices_json TEXT NOT NULL,
            PRIMARY KEY (run_id, phase)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS external_flows (
            flow_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            asset TEXT NOT NULL,
            quote_value TEXT NOT NULL,
            direction TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),),
    )


def _decode_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    row["prices"] = json.loads(row.pop("prices_json"))
    row["asset_values"] = json.loads(row.pop("asset_values_json"))
    row["missing_prices"] = json.loads(row.pop("missing_prices_json"))
    return row


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
