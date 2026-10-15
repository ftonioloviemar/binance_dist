from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from performance_store import (
    load_certified_external_flow_ledger,
    load_execution_costs,
    load_portfolio_snapshots,
)


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
            "24h": _build_horizon(
                db_path, pairs, execution_costs, current - timedelta(hours=24), current
            ),
            "7d": _build_horizon(
                db_path, pairs, execution_costs, current - timedelta(days=7), current
            ),
            "30d": _build_horizon(
                db_path, pairs, execution_costs, current - timedelta(days=30), current
            ),
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
        else:
            observed_change = data.get("observed_change")
            observed_label = (
                observed_change if observed_change is not None else "unknown"
            )
            lines.append(
                f"{horizon}: observed={observed_label} "
                f"hold={data['hold_change'] or 'unknown'} "
                f"attribution={data['attribution_status']} runs={data['runs']}"
            )
        pnl = data.get("net_pnl_quote")
        dietz = data.get("modified_dietz_return_pct")
        return_label = f"{dietz}% (approx., not annualized)" if dietz is not None else "unknown"
        coverage_range = ""
        if data.get("flow_coverage_start") and data.get("flow_coverage_end"):
            coverage_range = (
                f" range={data['flow_coverage_start']}..{data['flow_coverage_end']}"
            )
        source_hash = data.get("flow_source_sha256")
        source_label = f" source_sha256={source_hash}" if source_hash else ""
        lines.append(
            "  flow-adjusted: "
            f"net_pnl={pnl if pnl is not None else 'unknown'} "
            f"Modified_Dietz={return_label} "
            f"coverage={data.get('flow_coverage_status', 'unknown')}"
            f"{coverage_range}{source_label} basis=user-certified "
            "interpretation=flow-adjusted return, not strategy alpha"
        )
        cost = data.get("execution_cost", {})
        lines.append(
            "  fees: "
            f"converted_quote_subtotal={cost.get('converted_commission_quote_subtotal', '0.00')} "
            f"converted_orders={cost.get('conversion_complete_orders', 0)} "
            f"unknown_orders={cost.get('conversion_unknown_orders', 0)} "
            f"unknown_without_asset_detail={cost.get('unknown_orders_without_asset_breakdown', 0)}"
        )
        unknown_by_asset = cost.get("unconverted_commission_by_asset", {})
        if unknown_by_asset:
            details = ", ".join(
                f"{asset}={amount}"
                for asset, amount in sorted(unknown_by_asset.items())
            )
            lines.append(f"  unconverted commissions by asset: {details}")
        data_issues = cost.get("commission_data_issues", {})
        if data_issues:
            details = ", ".join(
                f"{reason}={count}"
                for reason, count in sorted(data_issues.items())
            )
            lines.append(f"  incomplete fill commission data: {details}")
    return "\n".join(lines)


def _build_horizon(
    db_path: str | Path | None,
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
        result = {"status": "no_data", "runs": 0}
        result.update(_empty_flow_adjusted_metrics("no_data"))
        return result
    eligible.sort(key=lambda item: item[0])
    first_before = eligible[0][2]
    last_after = max(eligible, key=lambda item: item[1])[3]
    result = compare_snapshots(first_before, last_after)
    result.update(_flow_adjusted_metrics(db_path, first_before, last_after))
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


def _flow_adjusted_metrics(
    db_path: str | Path | None,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    result = _empty_flow_adjusted_metrics("missing")
    if before.get("data_quality") != "complete" or after.get("data_quality") != "complete":
        result["flow_coverage_status"] = "incomplete_snapshots"
        return result

    before_quote = str(before.get("quote_asset", "")).upper()
    after_quote = str(after.get("quote_asset", "")).upper()
    if not before_quote or before_quote != after_quote:
        result["flow_coverage_status"] = "quote_mismatch"
        return result

    ledger = load_certified_external_flow_ledger(db_path, before_quote)
    if ledger is None:
        return result
    result.update(
        {
            "flow_coverage_start": ledger.get("coverage_start"),
            "flow_coverage_end": ledger.get("coverage_end"),
            "flow_certified_at": ledger.get("certified_at"),
            "flow_source_sha256": ledger.get("source_sha256"),
        }
    )

    try:
        start = _parse_timestamp(before.get("timestamp"))
        end = _parse_timestamp(after.get("timestamp"))
        coverage_start = _parse_certified_timestamp(ledger.get("coverage_start"))
        coverage_end = _parse_certified_timestamp(ledger.get("coverage_end"))
        _parse_certified_timestamp(ledger.get("certified_at"))
    except (TypeError, ValueError):
        result["flow_coverage_status"] = "invalid_certificate"
        return result
    source_hash = ledger.get("source_sha256")
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != 64
        or any(character not in "0123456789abcdef" for character in source_hash.lower())
        or ledger.get("quote_asset", "").upper() != before_quote
    ):
        result["flow_coverage_status"] = "invalid_certificate"
        return result
    if start >= end or coverage_start > start or coverage_end < end:
        result["flow_coverage_status"] = "insufficient"
        return result

    flows = ledger.get("flows")
    if not isinstance(flows, list) or ledger.get("flow_count") != len(flows):
        result["flow_coverage_status"] = "invalid_certificate"
        return result

    start_value = _finite_decimal(before.get("total_value"))
    end_value = _finite_decimal(after.get("total_value"))
    if start_value is None or end_value is None:
        result["flow_coverage_status"] = "invalid_snapshots"
        return result

    duration_seconds = _elapsed_seconds(end - start)
    eligible_flows: list[tuple[datetime, Decimal, str]] = []
    for flow in flows:
        if not isinstance(flow, Mapping):
            result["flow_coverage_status"] = "invalid_certificate"
            return result
        value = _finite_decimal(flow.get("quote_value"))
        direction = flow.get("direction")
        try:
            flow_time = _parse_certified_timestamp(flow.get("timestamp"))
        except (TypeError, ValueError):
            result["flow_coverage_status"] = "invalid_certificate"
            return result
        if (
            value is None
            or value <= 0
            or direction not in {"in", "out"}
            or not str(flow.get("asset", "")).strip()
            or flow_time < coverage_start
            or flow_time > coverage_end
        ):
            result["flow_coverage_status"] = "invalid_certificate"
            return result
        if flow_time <= start or flow_time > end:
            continue
        eligible_flows.append((flow_time, value, direction))

    operands = [start_value, end_value, *(flow[1] for flow in eligible_flows)]
    precision = _calculation_precision(operands)
    with localcontext() as context:
        context.prec = precision
        external_net_flow = Decimal("0")
        weighted_flows = Decimal("0")
        for flow_time, value, direction in eligible_flows:
            signed_value = value if direction == "in" else -value
            external_net_flow += signed_value
            weighted_flows += signed_value * (
                _elapsed_seconds(end - flow_time) / duration_seconds
            )

        net_pnl = end_value - start_value - external_net_flow
        denominator = start_value + weighted_flows
        result.update(
            {
                "net_pnl_quote": _money(net_pnl),
                "external_net_flow_quote": _money(external_net_flow),
                "flow_coverage_status": "complete",
            }
        )
        if denominator <= 0:
            result["modified_dietz_return_reason"] = "nonpositive_denominator"
            return result
        return_pct = (net_pnl / denominator * Decimal("100")).quantize(
            Decimal("0.000001")
        )
    result["modified_dietz_return_pct"] = format(return_pct, "f")
    return result


def _empty_flow_adjusted_metrics(status: str) -> dict[str, Any]:
    return {
        "net_pnl_quote": None,
        "external_net_flow_quote": None,
        "modified_dietz_return_pct": None,
        "modified_dietz_return_reason": None,
        "return_method": "modified_dietz_approximate",
        "flow_coverage_status": status,
        "flow_coverage_basis": "user_certified",
        "flow_coverage_start": None,
        "flow_coverage_end": None,
        "flow_certified_at": None,
        "flow_source_sha256": None,
    }


def _finite_decimal(value: Any) -> Decimal | None:
    parsed = _decimal(value)
    return parsed if parsed is not None and parsed.is_finite() else None


def _elapsed_seconds(value: timedelta) -> Decimal:
    return (
        Decimal(value.days * 86400 + value.seconds)
        + Decimal(value.microseconds) / Decimal("1000000")
    )


def _calculation_precision(values: list[Decimal]) -> int:
    nonzero = [value for value in values if value]
    if not nonzero:
        return 50
    max_adjusted = max(value.adjusted() for value in nonzero)
    min_exponent = min(value.as_tuple().exponent for value in nonzero)
    return max(50, max_adjusted - min_exponent + len(str(len(values))) + 16)


def _parse_certified_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Certified timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Certified timestamp must use UTC")
    return parsed.astimezone(timezone.utc)


def _aggregate_execution_costs(costs: list[Mapping[str, Any]]) -> dict[str, Any]:
    gross = sum((_decimal(cost.get("gross_notional")) or Decimal("0") for cost in costs), Decimal("0"))
    commission = sum(
        (_decimal(cost.get("commission_quote")) or Decimal("0") for cost in costs),
        Decimal("0"),
    )
    unknown = sum(1 for cost in costs if cost.get("conversion_status") != "complete")
    complete = len(costs) - unknown
    unknown_by_asset: dict[str, Decimal] = {}
    unknown_reasons: dict[str, int] = {}
    commission_data_issues: dict[str, int] = {}
    unknown_without_breakdown = 0
    converted_subtotal = Decimal("0")
    for cost in costs:
        details = cost.get("commission_conversion_details") or {}
        if isinstance(details, Mapping) and details:
            for detail in details.values():
                if isinstance(detail, Mapping) and detail.get("status") in {
                    "converted", "quote_asset"
                }:
                    converted_subtotal += _decimal(detail.get("quote_amount")) or Decimal("0")
                elif isinstance(detail, Mapping) and detail.get("status") == "incomplete":
                    converted_subtotal += (
                        _decimal(detail.get("known_commission_quote_subtotal"))
                        or Decimal("0")
                    )
        elif cost.get("conversion_status") == "complete":
            converted_subtotal += _decimal(cost.get("commission_quote")) or Decimal("0")
        if cost.get("conversion_status") == "complete":
            continue
        for reason, count in (cost.get("commission_data_issues") or {}).items():
            try:
                issue_count = int(count)
            except (TypeError, ValueError):
                issue_count = 0
            if issue_count > 0:
                key = str(reason)
                commission_data_issues[key] = commission_data_issues.get(key, 0) + issue_count
        if not isinstance(details, Mapping) or not details:
            unknown_without_breakdown += 1
            continue
        has_unknown_detail = False
        for asset, detail in details.items():
            if not isinstance(detail, Mapping) or detail.get("status") not in {
                "unknown", "incomplete"
            }:
                continue
            has_unknown_detail = True
            amount = _decimal(detail.get("commission"))
            if amount is not None:
                key = str(asset).upper()
                unknown_by_asset[key] = unknown_by_asset.get(key, Decimal("0")) + amount
            if detail.get("status") == "unknown":
                reason = str(detail.get("reason") or "unknown_reason")
                unknown_reasons[reason] = unknown_reasons.get(reason, 0) + 1
        if not has_unknown_detail:
            unknown_without_breakdown += 1
    return {
        "orders": len(costs),
        "gross_notional": _money(gross),
        "commission_quote": _money(commission) if unknown == 0 else None,
        "converted_commission_quote_subtotal": _decimal_text(converted_subtotal),
        "conversion_unknown_orders": unknown,
        "conversion_complete_orders": complete,
        "unknown_orders_without_asset_breakdown": unknown_without_breakdown,
        "unconverted_commission_by_asset": {
            asset: _decimal_text(amount)
            for asset, amount in sorted(unknown_by_asset.items())
        },
        "unknown_conversion_reasons": dict(sorted(unknown_reasons.items())),
        "commission_data_issues": dict(sorted(commission_data_issues.items())),
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
    digits = len(value.as_tuple().digits)
    exponent = value.as_tuple().exponent
    with localcontext() as context:
        context.prec = max(50, digits + max(0, exponent) + 2)
        return format(value.quantize(Decimal("0.01")), "f")


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")
