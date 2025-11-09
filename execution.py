from __future__ import annotations

import time
from typing import Dict, Iterable, List

import requests

from binance_client import BinanceClient
from logging_audit import AuditLogger
from portfolio import ExecutionResult, TradeInstruction


_TRADE_EPSILON = 1e-12


def execute_trades(
    *,
    trades: Iterable[TradeInstruction],
    client: BinanceClient,
    auditor: AuditLogger,
    dry_run: bool,
    available_balances: Dict[str, float] | None = None,
    pendings: list[str] | None = None,
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
                detail=str(response.get("clientOrderId", client_order_id)),
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


__all__ = ["execute_trades"]
