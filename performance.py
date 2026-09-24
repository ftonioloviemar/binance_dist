from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from performance_store import load_execution_costs, load_portfolio_snapshots


def compare_snapshots(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    start_value = _decimal(before.get("total_value")) or Decimal("0")
    end_value = _decimal(after.get("total_value")) or Decimal("0")
    snapshots_complete = (
        before.get("data_quality") == "complete"
        and after.get("data_quality") == "complete"
    )
    observed_change = end_value - start_value if snapshots_complete else None
    missing_assets: set[str] = set()
    hold_value = Decimal("0")
    before_prices = before.get("prices", {})
    after_prices = after.get("prices", {})
    quote = str(before.get("quote_asset", "")).upper()

    for key, raw_value in dict(before.get("asset_values", {})).items():
        source, separator, asset = str(key).partition(":")
        if not separator or not asset:
            continue
        start_price = Decimal("1") if asset.upper() == quote else _decimal(before_prices.get(asset))
        end_price = Decimal("1") if asset.upper() == quote else _decimal(after_prices.get(asset))
        if start_price is None or start_price <= 0 or end_price is None or end_price < 0:
            missing_assets.add(asset.upper())
            continue
        asset_value = _decimal(raw_value)
        if asset_value is None:
            missing_assets.add(asset.upper())
            continue
        hold_value += asset_value / start_price * end_price

    hold_change = (
        hold_value - start_value
        if not missing_assets and snapshots_complete
        else None
    )
    attribution_status = "complete"
    if missing_assets or not snapshots_complete:
        attribution_status = "incomplete"
    elif before.get("external_flow_status") != "reconciled" or after.get("external_flow_status") != "reconciled":
        attribution_status = "not_attributed"

    return {
        "start_value": _money(start_value),
        "end_value": _money(end_value),
        "observed_change": (
            _money(observed_change) if observed_change is not None else None
        ),
        "hold_value": _money(hold_value) if hold_change is not None else None,
        "hold_change": _money(hold_change) if hold_change is not None else None,
        "attribution_status": attribution_status,
        "missing_assets": sorted(missing_assets),
        "profit": None,
    }


def build_performance_report(
    db_path: str | Path | None,
    *,
    days: int = 30,
    now: str | None = None,
) -> dict[str, Any]:
    current = _parse_timestamp(now) if now else datetime.now(timezone.utc)
    cutoff = current - timedelta(days=days)
    snapshots = [
        snapshot
        for snapshot in load_portfolio_snapshots(db_path)
        if _parse_timestamp(snapshot.get("timestamp")) >= cutoff
    ]
    execution_costs = [
        cost
        for cost in load_execution_costs(db_path)
        if cutoff <= _parse_timestamp(cost.get("timestamp")) <= current
    ]
    pairs: dict[str, dict[str, Mapping[str, Any]]] = {}
    for snapshot in snapshots:
        run_id = str(snapshot.get("run_id", ""))
        phase = str(snapshot.get("phase", ""))
        if run_id and phase in {"before", "after"}:
            pairs.setdefault(run_id, {})[phase] = snapshot

    report = {
        "days": days,
        "generated_at": current.isoformat(),
        "horizons": {
            "24h": _build_horizon(pairs, execution_costs, current - timedelta(hours=24), current),
            "7d": _build_horizon(pairs, execution_costs, current - timedelta(days=7), current),
            "30d": _build_horizon(pairs, execution_costs, current - timedelta(days=30), current),
        },
    }
    return report


def render_performance_report(
    report: Mapping[str, Any],
    *,
    json_output: bool = False,
) -> str:
    if json_output:
        return json.dumps(report, sort_keys=True, indent=2)
    lines = [f"Performance report (last {report.get('days', '?')} days)"]
    for horizon, data in report.get("horizons", {}).items():
        if data.get("status") == "no_data":
            lines.append(f"{horizon}: no data")
            continue
        if data.get("status") == "incomplete":
            lines.append(
                f"{horizon}: incomplete data; observed=unknown hold=unknown"
            )
            continue
        observed_change = data.get("observed_change")
        observed_label = (
            observed_change if observed_change is not None else "unknown"
        )
        lines.append(
            f"{horizon}: observed={observed_label} "
            f"hold={data['hold_change'] or 'unknown'} "
            f"attribution={data['attribution_status']} runs={data['runs']}"
        )
    return "\n".join(lines)


def _build_horizon(
    pairs: Mapping[str, Mapping[str, Mapping[str, Any]]],
    execution_costs: list[Mapping[str, Any]],
    cutoff: datetime,
    current: datetime,
) -> dict[str, Any]:
    eligible: list[tuple[datetime, datetime, Mapping[str, Any], Mapping[str, Any]]] = []
    for pair in pairs.values():
        before = pair.get("before")
        after = pair.get("after")
        if not before or not after:
            continue
        before_time = _parse_timestamp(before.get("timestamp"))
        after_time = _parse_timestamp(after.get("timestamp"))
        if cutoff <= before_time <= current and after_time <= current:
            eligible.append((before_time, after_time, before, after))
    if not eligible:
        return {"status": "no_data", "runs": 0}
    eligible.sort(key=lambda item: item[0])
    first_before = eligible[0][2]
    last_after = max(eligible, key=lambda item: item[1])[3]
    result = compare_snapshots(first_before, last_after)
    costs = [
        cost for cost in execution_costs
        if _parse_timestamp(cost.get("timestamp")) >= eligible[0][0]
        and _parse_timestamp(cost.get("timestamp")) <= max(eligible, key=lambda item: item[1])[1]
    ]
    result["execution_cost"] = _aggregate_execution_costs(costs)
    result.update(
        {
            "status": (
                "incomplete"
                if result["attribution_status"] == "incomplete"
                else "ok"
            ),
            "runs": len(eligible),
            "start_timestamp": first_before.get("timestamp"),
            "end_timestamp": last_after.get("timestamp"),
        }
    )
    return result


def _aggregate_execution_costs(costs: list[Mapping[str, Any]]) -> dict[str, Any]:
    gross = sum((_decimal(cost.get("gross_notional")) or Decimal("0") for cost in costs), Decimal("0"))
    commission = sum(
        (_decimal(cost.get("commission_quote")) or Decimal("0") for cost in costs),
        Decimal("0"),
    )
    unknown = sum(1 for cost in costs if cost.get("conversion_status") != "complete")
    return {
        "orders": len(costs),
        "gross_notional": _money(gross),
        "commission_quote": _money(commission) if unknown == 0 else None,
        "conversion_unknown_orders": unknown,
        "commission_bps": (
            format((commission / gross * Decimal("10000")).quantize(Decimal("0.000001")), "f")
            if gross > 0 and unknown == 0
            else None
        ),
    }


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
