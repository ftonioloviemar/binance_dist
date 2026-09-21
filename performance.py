from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


def compare_snapshots(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    start_value = _decimal(before.get("total_value")) or Decimal("0")
    end_value = _decimal(after.get("total_value")) or Decimal("0")
    observed_change = end_value - start_value
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

    hold_change = hold_value - start_value if not missing_assets else None
    attribution_status = "complete"
    if missing_assets:
        attribution_status = "incomplete"
    elif before.get("external_flow_status") != "reconciled" or after.get("external_flow_status") != "reconciled":
        attribution_status = "not_attributed"

    return {
        "start_value": _money(start_value),
        "end_value": _money(end_value),
        "observed_change": _money(observed_change),
        "hold_value": _money(hold_value) if hold_change is not None else None,
        "hold_change": _money(hold_change) if hold_change is not None else None,
        "attribution_status": attribution_status,
        "missing_assets": sorted(missing_assets),
        "profit": None,
    }


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
