from __future__ import annotations

from decimal import Decimal

from execution import summarize_execution_cost


def test_summarize_execution_cost_converts_commission_to_quote() -> None:
    summary = summarize_execution_cost(
        {
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "orderId": 10,
            "executedQty": "0.1",
            "cummulativeQuoteQty": "1000",
            "fills": [
                {"price": "9990", "qty": "0.04", "commission": "0.00001", "commissionAsset": "BNB"},
                {"price": "10010", "qty": "0.06", "commission": "0.00002", "commissionAsset": "BNB"},
            ],
        },
        quote_asset="USDT",
        reference_prices={"BNB": Decimal("600")},
    )

    assert summary["executed_quantity"] == "0.10000000"
    assert summary["gross_notional"] == "1000.00"
    assert summary["average_fill_price"] == "10000.00000000"
    assert summary["commission_by_asset"] == {"BNB": "0.00003"}
    assert summary["commission_quote"] == "0.01800000"
    assert summary["conversion_status"] == "complete"
    assert summary["commission_bps"] == "0.180000"


def test_summarize_execution_cost_does_not_invent_unknown_conversion() -> None:
    summary = summarize_execution_cost(
        {
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "executedQty": "0.1",
            "cummulativeQuoteQty": "10000",
            "fills": [
                {"price": "100000", "qty": "0.1", "commission": "0.00003", "commissionAsset": "BNB"}
            ],
        },
        quote_asset="USDT",
        reference_prices={},
    )

    assert summary["commission_by_asset"] == {"BNB": "0.00003"}
    assert summary["commission_quote"] is None
    assert summary["commission_bps"] is None
    assert summary["conversion_status"] == "unknown"


def test_summarize_execution_cost_uses_fill_totals_when_quote_total_missing() -> None:
    summary = summarize_execution_cost(
        {
            "symbol": "ETHUSDT",
            "fills": [
                {"price": "2000", "qty": "1", "commission": "2", "commissionAsset": "USDT"},
                {"price": "2100", "qty": "1", "commission": "2", "commissionAsset": "USDT"},
            ],
        },
        quote_asset="USDT",
        reference_prices={},
    )

    assert summary["executed_quantity"] == "2.00000000"
    assert summary["gross_notional"] == "4100.00"
    assert summary["average_fill_price"] == "2050.00000000"
    assert summary["commission_quote"] == "4.00000000"
    assert summary["conversion_status"] == "complete"
