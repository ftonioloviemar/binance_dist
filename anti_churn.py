from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from portfolio import RebalanceDecision, TradeInstruction


@dataclass(slots=True)
class HistoricalOrder:
    timestamp: datetime
    symbol: str
    side: str


def filter_anti_churn_trades(
    *,
    trades: Iterable[TradeInstruction],
    decision: RebalanceDecision,
    drift_threshold: float,
    logs_dir: Path,
    cooldown_hours: float,
    override_multiplier: float,
    now: datetime | None = None,
    blocked: list[str] | None = None,
) -> list[TradeInstruction]:
    if cooldown_hours <= 0:
        return list(trades)

    current_time = now or datetime.now().astimezone()
    since = current_time - timedelta(hours=cooldown_hours)
    historical_orders = _load_historical_orders(logs_dir, since)
    blocked_log = blocked if blocked is not None else []
    allowed: list[TradeInstruction] = []
    override_drift = max(0.0, drift_threshold * override_multiplier)

    for trade in trades:
        current_drift = abs(decision.deltas.get(trade.asset, 0.0))
        prior = _latest_opposite_order(
            historical_orders=historical_orders,
            symbol=trade.symbol,
            side=trade.side,
        )
        if prior and current_drift <= override_drift:
            age_hours = (current_time - prior.timestamp).total_seconds() / 3600
            blocked_log.append(
                f"{trade.symbol}: {trade.side} blocked by anti-churn cooldown after "
                f"{prior.side} {age_hours:.2f}h ago; drift {current_drift:.2%} <= "
                f"override {override_drift:.2%}"
            )
            continue
        allowed.append(trade)

    return allowed


def _latest_opposite_order(
    *,
    historical_orders: list[HistoricalOrder],
    symbol: str,
    side: str,
) -> HistoricalOrder | None:
    opposite = "SELL" if side.upper() == "BUY" else "BUY"
    matching = [
        order
        for order in historical_orders
        if order.symbol == symbol.upper() and order.side == opposite
    ]
    if not matching:
        return None
    return max(matching, key=lambda order: order.timestamp)


def _load_historical_orders(logs_dir: Path, since: datetime) -> list[HistoricalOrder]:
    orders: list[HistoricalOrder] = []
    if not logs_dir.exists():
        return orders
    for path in sorted(logs_dir.glob("*.log"), reverse=True):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                order = _parse_order_line(line)
                if order and order.timestamp >= since:
                    orders.append(order)
    return orders


def _parse_order_line(line: str) -> HistoricalOrder | None:
    if " | order | " not in line:
        return None
    parts = [part.strip() for part in line.strip().split("|")]
    if len(parts) < 3:
        return None
    try:
        timestamp = datetime.fromisoformat(parts[0])
    except ValueError:
        return None
    fields: dict[str, str] = {}
    for chunk in parts[2:]:
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        fields[key.strip()] = value.strip()
    if fields.get("status") != "FILLED":
        return None
    symbol = fields.get("symbol", "").upper()
    side = fields.get("side", "").upper()
    if not symbol or side not in {"BUY", "SELL"}:
        return None
    return HistoricalOrder(timestamp=timestamp, symbol=symbol, side=side)


__all__ = ["filter_anti_churn_trades"]
