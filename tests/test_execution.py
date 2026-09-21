from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from execution import execute_trades
from logging_audit import AuditLogger, load_run_detail
from portfolio import TradeInstruction


class FillCommissionClient:
    def place_order(self, **_: object) -> Mapping[str, Any]:
        return {
            "status": "FILLED",
            "orderId": 123,
            "clientOrderId": "cid-123",
            "fills": [
                {"commission": "0.00001000", "commissionAsset": "BNB"},
                {"commission": "0.00002000", "commissionAsset": "BNB"},
            ],
        }


class FullFillClient:
    def place_order(self, **_: object) -> Mapping[str, Any]:
        return {
            "status": "FILLED",
            "orderId": 456,
            "clientOrderId": "cid-456",
            "symbol": "BTCUSDT",
            "executedQty": "0.1",
            "cummulativeQuoteQty": "1000",
            "fills": [
                {
                    "price": "10000",
                    "qty": "0.1",
                    "commission": "0.00003",
                    "commissionAsset": "BNB",
                }
            ],
        }


def _trade() -> TradeInstruction:
    return TradeInstruction(
        symbol="BTCUSDT",
        asset="BTC",
        quote="USDT",
        side="BUY",
        quantity=0.1,
        price=100.0,
        notional=10.0,
        order_type="MARKET",
        limit_price=None,
    )


def test_execute_trades_logs_fill_commissions(tmp_path: Path) -> None:
    auditor = AuditLogger(logs_dir=tmp_path)
    run_id = auditor.start_run(profile="moderate", dry_run=False, config_snapshot={})

    execute_trades(
        trades=[_trade()],
        client=FillCommissionClient(),  # type: ignore[arg-type]
        auditor=auditor,
        dry_run=False,
        available_balances={"BTC": 0.0, "USDT": 100.0},
    )

    detail = load_run_detail(run_id, logs_dir=tmp_path)

    assert detail is not None
    assert detail["orders"][0]["detail"] == "clientOrderId=cid-123; commission=0.00003000 BNB"


def test_execute_trades_logs_converted_effective_cost(tmp_path: Path) -> None:
    auditor = AuditLogger(logs_dir=tmp_path)
    run_id = auditor.start_run(profile="moderate", dry_run=False, config_snapshot={})

    execute_trades(
        trades=[_trade()],
        client=FullFillClient(),  # type: ignore[arg-type]
        auditor=auditor,
        dry_run=False,
        available_balances={"BTC": 0.0, "USDT": 100.0},
        reference_prices={"BNB": 600.0},
    )

    detail = load_run_detail(run_id, logs_dir=tmp_path)

    assert detail is not None
    assert "gross_notional=1000.00" in detail["orders"][0]["detail"]
    assert "commission_quote=0.01800000" in detail["orders"][0]["detail"]
    assert "commission_bps=0.180000" in detail["orders"][0]["detail"]
    assert "conversion=complete" in detail["orders"][0]["detail"]
