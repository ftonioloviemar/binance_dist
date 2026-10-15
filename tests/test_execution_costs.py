from __future__ import annotations

from decimal import Decimal

import pytest

from execution import _format_order_detail, summarize_execution_cost


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
    assert summary["commission_conversion_details"] == {
        "BNB": {
            "commission": "0.00003",
            "status": "converted",
            "source": "supplied_reference_price",
            "reference_price": "600",
            "quote_amount": "0.01800000",
            "reason": None,
        }
    }


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
    assert summary["commission_conversion_details"] == {
        "BNB": {
            "commission": "0.00003",
            "status": "unknown",
            "source": "reference_price_lookup",
            "reference_price": None,
            "quote_amount": None,
            "reason": "reference_price_missing",
        }
    }


def test_summarize_execution_cost_records_invalid_reference_price_reason() -> None:
    summary = summarize_execution_cost(
        {
            "executedQty": "1",
            "cummulativeQuoteQty": "100",
            "fills": [
                {"price": "100", "qty": "1", "commission": "0.1", "commissionAsset": "BNB"}
            ],
        },
        quote_asset="USDT",
        reference_prices={"BNB": "invalid"},
    )

    detail = summary["commission_conversion_details"]["BNB"]
    assert detail["status"] == "unknown"
    assert detail["reason"] == "reference_price_invalid"
    assert summary["commission_quote"] is None


@pytest.mark.parametrize(
    ("commission", "expected_issue"),
    [
        (None, "commission_amount_missing"),
        ("invalid", "commission_amount_invalid"),
        ("NaN", "commission_amount_invalid"),
        ("-0.1", "commission_amount_negative"),
    ],
)
def test_summarize_execution_cost_marks_missing_or_invalid_fill_commission_incomplete(
    commission: str | None,
    expected_issue: str,
) -> None:
    fill = {"price": "100", "qty": "1", "commissionAsset": "BNB"}
    if commission is not None:
        fill["commission"] = commission
    summary = summarize_execution_cost(
        {"executedQty": "1", "cummulativeQuoteQty": "100", "fills": [fill]},
        quote_asset="USDT",
        reference_prices={"BNB": "600"},
    )

    assert summary["conversion_status"] == "incomplete"
    assert summary["commission_quote"] is None
    assert summary["commission_bps"] is None
    assert summary["commission_by_asset"] == {"BNB": None}
    assert summary["commission_conversion_details"]["BNB"]["status"] == "incomplete"
    assert summary["commission_conversion_details"]["BNB"]["reason"] == expected_issue
    assert summary["commission_data_issues"] == {expected_issue: 1}


def test_summarize_execution_cost_marks_missing_fill_commission_asset_incomplete() -> None:
    summary = summarize_execution_cost(
        {
            "executedQty": "1",
            "cummulativeQuoteQty": "100",
            "fills": [{"price": "100", "qty": "1", "commission": "0.01"}],
        },
        quote_asset="USDT",
        reference_prices={},
    )

    assert summary["conversion_status"] == "incomplete"
    assert summary["commission_quote"] is None
    assert summary["commission_data_issues"] == {"commission_asset_missing": 1}


def test_order_audit_discloses_missing_commission_component() -> None:
    detail = _format_order_detail(
        {
            "orderId": 9,
            "executedQty": "1",
            "cummulativeQuoteQty": "100",
            "fills": [
                {"price": "100", "qty": "1", "commissionAsset": "BNB"}
            ],
        },
        "client-9",
        quote_asset="USDT",
        reference_prices={"BNB": "600"},
    )

    assert "commission_data_incomplete=commission_amount_missing:1" in detail


def test_order_audit_labels_known_fees_as_subtotal_when_another_fill_is_incomplete() -> None:
    detail = _format_order_detail(
        {
            "orderId": 10,
            "executedQty": "2",
            "cummulativeQuoteQty": "200",
            "fills": [
                {"price": "100", "qty": "1", "commission": "0.01", "commissionAsset": "BNB"},
                {"price": "100", "qty": "1", "commissionAsset": "BNB"},
            ],
        },
        "client-10",
        quote_asset="USDT",
        reference_prices={"BNB": "600"},
    )

    assert "commission_known_subtotal=0.01 BNB" in detail
    assert "conversion=incomplete" in detail


@pytest.mark.parametrize("invalid_commission", ["NaN", "Infinity", "-0.1", "invalid"])
def test_order_audit_never_logs_invalid_commission_values(invalid_commission: str) -> None:
    detail = _format_order_detail(
        {
            "executedQty": "2",
            "cummulativeQuoteQty": "200",
            "fills": [
                {"price": "100", "qty": "1", "commission": "0.01", "commissionAsset": "BNB"},
                {"price": "100", "qty": "1", "commission": invalid_commission, "commissionAsset": "BNB"},
            ],
        },
        "client-1",
        quote_asset="USDT",
        reference_prices={"BNB": "600"},
    )

    fee_detail = detail.split("; gross_notional=", maxsplit=1)[0]
    assert invalid_commission not in fee_detail
    assert "commission_known_subtotal=0.01 BNB" in detail
    assert "commission_data_incomplete=commission_amount_" in detail


def test_summarize_execution_cost_converts_only_known_part_of_incomplete_asset_fee() -> None:
    summary = summarize_execution_cost(
        {
            "executedQty": "2",
            "cummulativeQuoteQty": "200",
            "fills": [
                {"price": "100", "qty": "1", "commission": "0.00001", "commissionAsset": "BNB"},
                {"price": "100", "qty": "1", "commissionAsset": "BNB"},
            ],
        },
        quote_asset="USDT",
        reference_prices={"BNB": "600"},
    )

    assert summary["conversion_status"] == "incomplete"
    assert summary["commission_quote"] is None
    detail = summary["commission_conversion_details"]["BNB"]
    assert detail["commission"] is None
    assert detail["known_commission_subtotal"] == "0.00001"
    assert detail["known_commission_quote_subtotal"] == "0.00600000"


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
