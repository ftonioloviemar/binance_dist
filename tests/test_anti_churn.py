from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from anti_churn import filter_anti_churn_trades
from portfolio import RebalanceDecision, TradeInstruction


def _trade(symbol: str = "BTCUSDT", side: str = "SELL") -> TradeInstruction:
    return TradeInstruction(
        symbol=symbol,
        asset=symbol.removesuffix("USDT"),
        quote="USDT",
        side=side,
        quantity=0.1,
        price=100.0,
        notional=10.0,
        order_type="MARKET",
        limit_price=None,
    )


def _write_prior_order(logs_dir: Path, *, symbol: str, side: str, when: datetime) -> None:
    logs_dir.mkdir(exist_ok=True)
    (logs_dir / "20260801.log").write_text(
        "\n".join(
            [
                f"{when.isoformat()} | run_start | run_id=prior | status=started | profile=moderate | dry_run=false",
                f"{when.isoformat()} | order | run_id=prior | status=FILLED | symbol={symbol} | side={side} | quantity=0.1 | price=100.0 | detail=prior",
                f"{when.isoformat()} | run_end | run_id=prior | status=completed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_filter_anti_churn_blocks_opposite_side_inside_cooldown(tmp_path: Path) -> None:
    now = datetime.fromisoformat("2026-08-01T12:00:00-03:00")
    _write_prior_order(
        tmp_path,
        symbol="BTCUSDT",
        side="BUY",
        when=now - timedelta(hours=6),
    )
    blocked: list[str] = []

    allowed = filter_anti_churn_trades(
        trades=[_trade(side="SELL")],
        decision=RebalanceDecision(rebalance_needed=True, deltas={"BTC": -0.015}),
        drift_threshold=0.01,
        logs_dir=tmp_path,
        cooldown_hours=12.0,
        override_multiplier=2.0,
        now=now,
        blocked=blocked,
    )

    assert allowed == []
    assert blocked == [
        "BTCUSDT: SELL blocked by anti-churn cooldown after BUY 6.00h ago; drift 1.50% <= override 2.00%"
    ]


def test_filter_anti_churn_allows_same_side_inside_cooldown(tmp_path: Path) -> None:
    now = datetime.fromisoformat("2026-08-01T12:00:00-03:00")
    _write_prior_order(
        tmp_path,
        symbol="BTCUSDT",
        side="SELL",
        when=now - timedelta(hours=6),
    )

    allowed = filter_anti_churn_trades(
        trades=[_trade(side="SELL")],
        decision=RebalanceDecision(rebalance_needed=True, deltas={"BTC": -0.015}),
        drift_threshold=0.01,
        logs_dir=tmp_path,
        cooldown_hours=12.0,
        override_multiplier=2.0,
        now=now,
    )

    assert [trade.symbol for trade in allowed] == ["BTCUSDT"]


def test_filter_anti_churn_allows_opposite_side_when_drift_is_large(tmp_path: Path) -> None:
    now = datetime.fromisoformat("2026-08-01T12:00:00-03:00")
    _write_prior_order(
        tmp_path,
        symbol="BTCUSDT",
        side="BUY",
        when=now - timedelta(hours=6),
    )
    blocked: list[str] = []

    allowed = filter_anti_churn_trades(
        trades=[_trade(side="SELL")],
        decision=RebalanceDecision(rebalance_needed=True, deltas={"BTC": -0.021}),
        drift_threshold=0.01,
        logs_dir=tmp_path,
        cooldown_hours=12.0,
        override_multiplier=2.0,
        now=now,
        blocked=blocked,
    )

    assert [trade.symbol for trade in allowed] == ["BTCUSDT"]
    assert blocked == []
