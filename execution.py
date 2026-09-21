from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping

import requests

from binance_client import BinanceClient
from logging_audit import AuditLogger
from portfolio import ExecutionResult, TradeInstruction
from performance_store import record_execution_cost


_TRADE_EPSILON = 1e-12


def execute_trades(
    *,
    trades: Iterable[TradeInstruction],
    client: BinanceClient,
    auditor: AuditLogger,
    dry_run: bool,
    available_balances: Dict[str, float] | None = None,
    pendings: list[str] | None = None,
    reference_prices: Mapping[str, Decimal | float | str] | None = None,
) -> List[ExecutionResult]:
    reports: List[ExecutionResult] = []
    balances = available_balances if available_balances is not None else {}
    pending_log = pendings if pendings is not None else []

    for trade in trades:
        asset_balance = balances.get(trade.asset, 0.0)
        quote_balance = balances.get(trade.quote, 0.0)

        if trade.side == "SELL" and trade.quantity > asset_balance + _TRADE_EPSILON:
            message = (
                f"{trade.symbol}: insufficient {trade.asset} balance (need {trade.quantity:.8f}, have {asset_balance:.8f})"
            )
            pending_log.append(message)
            auditor.log_step(name=f"plan_{trade.symbol}", status="skipped", detail=message)
            continue
        if trade.side == "BUY" and trade.notional > quote_balance + _TRADE_EPSILON:
            message = (
                f"{trade.symbol}: insufficient {trade.quote} balance (need {trade.notional:.2f}, have {quote_balance:.2f})"
            )
            pending_log.append(message)
            auditor.log_step(name=f"plan_{trade.symbol}", status="skipped", detail=message)
            continue

        if dry_run:
            report = ExecutionResult(
                instruction=trade,
                status="DRY_RUN",
                order_id=None,
                detail={"notional": trade.notional},
            )
            auditor.log_order(
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.limit_price or trade.price,
                status="simulated",
                detail="dry run",
            )
        else:
            client_order_id = f"rebalance_{int(time.time() * 1000)}_{trade.symbol.lower()}"
            try:
                response = client.place_order(
                    symbol=trade.symbol,
                    side=trade.side,
                    order_type=trade.order_type,
                    quantity=trade.quantity,
                    price=trade.limit_price if trade.order_type == "LIMIT" else None,
                    client_order_id=client_order_id,
                )
            except requests.HTTPError as exc:
                body = exc.response.text if exc.response is not None else str(exc)
                auditor.log_exception(error=f"Order {trade.symbol} failed: {body}")
                pending_log.append(f"{trade.symbol}: exchange rejected order ({body})")
                auditor.log_step(name=f"plan_{trade.symbol}", status="failed", detail=body)
                continue
            except Exception as exc:
                auditor.log_exception(error=f"Order {trade.symbol} failed: {exc}")
                pending_log.append(f"{trade.symbol}: {exc}")
                auditor.log_step(name=f"plan_{trade.symbol}", status="failed", detail=str(exc))
                continue
            report = ExecutionResult(
                instruction=trade,
                status=str(response.get("status", "UNKNOWN")),
                order_id=str(response.get("orderId", client_order_id)),
                detail=response,
            )
            auditor.log_order(
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.limit_price or trade.price,
                status=report.status,
                detail=_format_order_detail(
                    response,
                    client_order_id,
                    quote_asset=trade.quote,
                    reference_prices=reference_prices or {},
                ),
            )
            try:
                summary = summarize_execution_cost(
                    response,
                    quote_asset=trade.quote,
                    reference_prices=reference_prices or {},
                )
                if auditor.run_id and summary["order_id"]:
                    record_execution_cost(
                        None,
                        {
                            **summary,
                            "run_id": auditor.run_id,
                            "order_id": summary["order_id"],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "side": trade.side,
                        },
                    )
            except Exception as exc:  # pragma: no cover - defensive persistence guard
                auditor.log_step(
                    name="execution_cost",
                    status="warning",
                    detail=f"Persistence skipped: {exc}",
                )

        if trade.side == "SELL":
            balances[trade.asset] = max(0.0, asset_balance - trade.quantity)
            balances[trade.quote] = quote_balance + trade.notional
        else:
            balances[trade.quote] = max(0.0, quote_balance - trade.notional)
            balances[trade.asset] = asset_balance + trade.quantity

        auditor.log_step(
            name=f"plan_{trade.symbol}",
            status="completed",
            detail=f"{report.status} ({trade.order_type})",
        )
        reports.append(report)

    return reports


def _format_order_detail(
    response: Mapping[str, Any],
    fallback_client_order_id: str,
    *,
    quote_asset: str,
    reference_prices: Mapping[str, Decimal | float | str],
) -> str:
    client_order_id = str(response.get("clientOrderId", fallback_client_order_id))
    commissions = _summarize_commissions(response)
    detail = f"clientOrderId={client_order_id}"
    if commissions:
        detail += f"; commission={commissions}"
    cost = summarize_execution_cost(
        response,
        quote_asset=quote_asset,
        reference_prices=reference_prices,
    )
    if cost["gross_notional"] != "0.00":
        detail += (
            f"; gross_notional={cost['gross_notional']}"
            f"; avg_fill_price={cost['average_fill_price']}"
            f"; commission_quote={cost['commission_quote'] or 'unknown'}"
            f"; commission_bps={cost['commission_bps'] or 'unknown'}"
            f"; conversion={cost['conversion_status']}"
        )
    return detail


def summarize_execution_cost(
    response: Mapping[str, Any],
    *,
    quote_asset: str,
    reference_prices: Mapping[str, Decimal | float | str],
) -> dict[str, Any]:
    """Summarize exchange-reported fills without guessing missing conversions."""
    quote = quote_asset.upper()
    fills = response.get("fills")
    fill_rows = [fill for fill in fills if isinstance(fill, Mapping)] if isinstance(fills, list) else []
    executed_quantity = _decimal(response.get("executedQty")) or Decimal("0")
    fill_notional = Decimal("0")
    fill_quantity = Decimal("0")
    for fill in fill_rows:
        quantity = _decimal(fill.get("qty"))
        price = _decimal(fill.get("price"))
        if quantity is not None:
            fill_quantity += quantity
        if quantity is not None and price is not None:
            fill_notional += quantity * price
    if executed_quantity <= 0:
        executed_quantity = fill_quantity
    gross_notional = _decimal(response.get("cummulativeQuoteQty")) or fill_notional

    commission_totals: dict[str, Decimal] = {}
    for fill in fill_rows:
        asset = str(fill.get("commissionAsset", "")).upper()
        commission = _decimal(fill.get("commission"))
        if asset and commission is not None:
            commission_totals[asset] = commission_totals.get(asset, Decimal("0")) + commission

    converted_commission = Decimal("0")
    unknown_assets: list[str] = []
    normalized_prices = {asset.upper(): _decimal(value) for asset, value in reference_prices.items()}
    for asset, commission in commission_totals.items():
        if asset == quote:
            converted_commission += commission
            continue
        price = normalized_prices.get(asset)
        if price is None or price <= 0:
            unknown_assets.append(asset)
            continue
        converted_commission += commission * price

    if not commission_totals:
        conversion_status = "not_available"
    elif unknown_assets and len(unknown_assets) < len(commission_totals):
        conversion_status = "partial"
    elif unknown_assets:
        conversion_status = "unknown"
    else:
        conversion_status = "complete"

    commission_quote = (
        _money8(converted_commission)
        if commission_totals and not unknown_assets
        else None
    )
    commission_bps = (
        _bps(converted_commission, gross_notional)
        if commission_quote is not None and gross_notional > 0
        else None
    )
    return {
        "symbol": str(response.get("symbol", "")),
        "status": str(response.get("status", "")),
        "order_id": str(response.get("orderId", "")) or None,
        "executed_quantity": _quantity8(executed_quantity),
        "gross_notional": _money(gross_notional),
        "average_fill_price": _price8(gross_notional / executed_quantity) if executed_quantity > 0 else None,
        "commission_by_asset": {
            asset: _decimal_text(amount) for asset, amount in sorted(commission_totals.items())
        },
        "commission_quote": commission_quote,
        "commission_bps": commission_bps,
        "conversion_status": conversion_status,
        "unknown_conversion_assets": sorted(unknown_assets),
    }


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _quantity8(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")


def _price8(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _money8(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")


def _bps(value: Decimal, notional: Decimal) -> str:
    return format((value / notional * Decimal("10000")).quantize(Decimal("0.000001")), "f")


def _summarize_commissions(response: Mapping[str, Any]) -> str:
    fills = response.get("fills")
    if not isinstance(fills, list):
        return ""

    totals: dict[str, Decimal] = {}
    for fill in fills:
        if not isinstance(fill, Mapping):
            continue
        asset = str(fill.get("commissionAsset", "")).upper()
        raw_commission = fill.get("commission")
        if not asset or raw_commission in {None, ""}:
            continue
        try:
            commission = Decimal(str(raw_commission))
        except InvalidOperation:
            continue
        totals[asset] = totals.get(asset, Decimal("0")) + commission

    return ", ".join(
        f"{format(amount, 'f')} {asset}" for asset, amount in sorted(totals.items())
    )


__all__ = ["execute_trades"]
