from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app
from ai_contract import AnalysisRequest, parse_analysis_response
from binance_client import Balance, SymbolFilters
from config import EnvSettings
from logging_audit import load_recent_runs, load_run_detail
from macro_context import MacroSnapshot
from portfolio import AIAdvice, AIModelFailure


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "codex_analysis" / "replay_v1.json"
REPLAY = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class ReplayClient:
    def __init__(self, portfolio: dict) -> None:
        self.portfolio = portfolio
        self.forbidden_calls: list[str] = []

    def get_account_balances(self) -> list[Balance]:
        return [Balance(**balance) for balance in self.portfolio["balances"]]

    def get_symbol_price(self, symbol: str) -> float:
        return self.portfolio["prices"][symbol]

    def get_prices(self, symbols=None) -> dict[str, float]:
        prices = self.portfolio["prices"]
        return {key: prices[key] for key in symbols or prices if key in prices}

    def get_exchange_info(self) -> dict[str, SymbolFilters]:
        return {
            symbol: SymbolFilters(
                symbol=symbol,
                lot_step=filters["lot_step"],
                min_qty=filters["min_qty"],
                max_qty=10000.0,
                min_notional=self.portfolio["min_notional"],
                price_tick=0.01,
            )
            for symbol, filters in self.portfolio["filters"].items()
        }

    def place_order(self, **kwargs):
        self.forbidden_calls.append("place_order")
        raise AssertionError("replay attempted a real order")

    def redeem_simple_earn_flexible(self, **kwargs):
        self.forbidden_calls.append("redeem_simple_earn_flexible")
        raise AssertionError("replay attempted an Earn redemption")

    def subscribe_simple_earn_flexible(self, **kwargs):
        self.forbidden_calls.append("subscribe_simple_earn_flexible")
        raise AssertionError("replay attempted an Earn subscription")

    def get_simple_earn_flexible_positions(self):
        self.forbidden_calls.append("get_simple_earn_flexible_positions")
        raise AssertionError("replay attempted an Earn endpoint")

    def get_simple_earn_flexible_products(self):
        self.forbidden_calls.append("get_simple_earn_flexible_products")
        raise AssertionError("replay attempted an Earn endpoint")

    def close(self) -> None:
        return None


def _macro_snapshot(kind: str, fixed_now: datetime) -> MacroSnapshot:
    if kind == "missing":
        return MacroSnapshot(data={}, errors=["synthetic missing macro"], sources={})
    age_minutes = 15 if kind == "btc_15m" else 16
    collected_at = fixed_now - timedelta(minutes=age_minutes)
    return MacroSnapshot(
        data={
            "fear_greed": {"value": 50, "classification": "Neutral"},
            "btc_24h": {"price": 50000.0, "price_change_percent": 0.0},
            "crypto_global": {"market_cap_change_24h": 0.0},
        },
        errors=[],
        sources={
            "fear_greed": {
                "status": "fresh",
                "observed_at": fixed_now.isoformat().replace("+00:00", "Z"),
                "collected_at": fixed_now.isoformat().replace("+00:00", "Z"),
                "error": None,
            },
            "btc_24h": {
                "status": "fresh",
                "observed_at": None,
                "collected_at": collected_at.isoformat().replace("+00:00", "Z"),
                "error": None,
            },
            "crypto_global": {
                "status": "fresh",
                "observed_at": None,
                "collected_at": fixed_now.isoformat().replace("+00:00", "Z"),
                "error": None,
            },
        },
    )


def _targets_arg(targets: dict[str, float]) -> str:
    return ",".join(f"{asset}={weight}" for asset, weight in targets.items())


@pytest.mark.parametrize("case", REPLAY["cases"], ids=lambda case: case["id"])
def test_fixed_advice_replay_is_offline_and_preserves_trade_guards(
    case: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio = REPLAY["portfolio"]
    fixed_now = datetime.fromisoformat(REPLAY["decision_time_utc"].replace("Z", "+00:00"))
    client = ReplayClient(portfolio)
    captured_requests: list[AnalysisRequest] = []
    captured_advices: list[AIAdvice] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BUCKETS_JSON", '{"stable":["USDT"],"alt":["BNB","AVAX","ADA"]}')
    monkeypatch.setenv(
        "PROFILE_TARGETS_MODERATE",
        "BTC=0.40,ETH=0.20,SOL=0.15,STABLE=0.15,ALT=0.10",
    )
    monkeypatch.setenv("MARKET_CANDLE_COLLECTION_ENABLED", "false")
    monkeypatch.setenv("SHADOW_PORTFOLIO_SIMULATION_ENABLED", "false")
    monkeypatch.setattr(app, "BinanceClient", lambda **kwargs: client)
    monkeypatch.setattr(
        app,
        "load_env_settings",
        lambda recv_window: EnvSettings(
            api_key="synthetic-key",
            api_secret="synthetic-secret",
            testnet=True,
            base_url="https://synthetic.invalid",
            recv_window=recv_window,
            ai_provider="codex_cli",
            openrouter_api_key=None,
            openrouter_models=(),
        ),
    )
    monkeypatch.setattr(
        app, "fetch_macro_snapshot", lambda: _macro_snapshot(case["macro"], fixed_now)
    )
    original_assess = app._assess_adaptive_sources
    monkeypatch.setattr(
        app,
        "_assess_adaptive_sources",
        lambda snapshot: original_assess(snapshot, now=fixed_now),
    )
    monkeypatch.setattr(
        app,
        "ai_refine_targets",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("OpenRouter inference called")),
    )
    monkeypatch.setattr(
        app,
        "refresh_openrouter_models",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("OpenRouter refresh called")),
    )

    advice_fixture = case["advice"]

    def fixed_advice(request: AnalysisRequest, settings) -> AIAdvice:
        captured_requests.append(request)
        if "failure" in advice_fixture:
            return AIAdvice(
                targets=dict(request.proposed_weights),
                action="redistribute",
                model_failures=(
                    AIModelFailure("gpt-6-luna", advice_fixture["failure"], "synthetic"),
                ),
                first_model_failed=True,
                provider="codex_cli",
            )
        response_targets = advice_fixture["targets"]
        if response_targets == "moderate_targets":
            response_targets = REPLAY["moderate_targets"]
        response = json.dumps(
            {
                "action": advice_fixture["action"],
                "targets": response_targets,
                "rationale": advice_fixture["rationale"],
            }
        )
        targets, action, rationale = parse_analysis_response(response, request)
        return AIAdvice(
            targets=targets,
            action=action,
            rationale=rationale,
            model_used="gpt-6-luna",
            provider="codex_cli",
            reasoning_effort="medium",
            duration_seconds=0.01,
        )

    monkeypatch.setattr(app, "analyze_with_codex", fixed_advice)
    original_resolve = app._resolve_ai_advice

    def capture_resolved_advice(settings, request, auditor):
        advice = original_resolve(settings, request, auditor)
        captured_advices.append(advice)
        return advice

    monkeypatch.setattr(app, "_resolve_ai_advice", capture_resolved_advice)
    monkeypatch.setattr(
        app,
        "observe_shadow_run",
        lambda *args, **kwargs: type(
            "ShadowResult", (), {"status": "disabled", "deadline_exceeded": False, "error": None}
        )(),
    )

    previous_log = tmp_path / "historical" / "19990101.log"
    previous_log.parent.mkdir(parents=True)
    previous_log.write_bytes(b"historical synthetic record remains unchanged\n")
    historical_hash = hashlib.sha256(previous_log.read_bytes()).hexdigest()
    target_arg = (
        _targets_arg(case["proposed_targets"])
        if case["proposed_targets"] is not None
        else None
    )
    args = type(
        "Args",
        (),
        {
            "command": "rebalance",
            "dry_run": True,
            "profile": "moderate",
            "drift": portfolio["drift"],
            "max_slippage": portfolio["max_slippage"],
            "min_notional": portfolio["min_notional"],
            "targets": target_arg,
            "quote": portfolio["quote"],
            "recv_window": 5000,
            "config_path": Path("missing.toml"),
            "adaptive": case["adaptive"],
            "min_notional_uplift_tolerance": 0.0,
            "anti_churn_cooldown_hours": 0.0,
            "anti_churn_override_multiplier": 2.0,
            "cost_gate_mode": "observe",
            "cost_gate_min_net_benefit_bps": None,
        },
    )()

    assert app.run_rebalance(args) == 0

    [run] = load_recent_runs(limit=1, logs_dir=tmp_path / "logs")
    detail = load_run_detail(run["run_id"], logs_dir=tmp_path / "logs")
    assert detail is not None
    assert detail["run"]["dry_run"] is True
    assert detail["run"]["status"] == case["expected"]["status"]
    assert client.forbidden_calls == []
    assert previous_log.read_bytes() == b"historical synthetic record remains unchanged\n"
    assert hashlib.sha256(previous_log.read_bytes()).hexdigest() == historical_hash
    assert len(captured_requests) == 1
    if case["proposed_targets"] is not None:
        assert captured_requests[0].proposed_weights == pytest.approx(case["proposed_targets"])
    if "proposed_targets" in case["expected"]:
        assert captured_requests[0].proposed_weights == pytest.approx(
            case["expected"]["proposed_targets"]
        )
    orders = detail["orders"]
    if "order_symbols" in case["expected"]:
        assert [order["symbol"] for order in orders] == case["expected"]["order_symbols"]
    elif case["expected"]["status"] == "completed":
        assert orders
    if "orders" in case["expected"]:
        expected_orders = case["expected"]["orders"]
        assert len(orders) == len(expected_orders)
        assert {order["symbol"]: order["side"] for order in orders} == {
            order["symbol"]: order["side"] for order in expected_orders
        }
        assert {order["symbol"]: order["quantity"] for order in orders} == pytest.approx(
            {order["symbol"]: order["quantity"] for order in expected_orders}
        )
    assert all(order["status"] == "simulated" for order in orders)
    if "order_side" in case["expected"]:
        assert orders[0]["side"] == case["expected"]["order_side"]
        assert orders[0]["quantity"] == pytest.approx(case["expected"]["order_quantity"])
    assert len(captured_advices) == 1
    assert captured_advices[0].action == case["expected"]["action"]
    assert captured_advices[0].provider == "codex_cli"
    if not captured_advices[0].model_failures:
        assert captured_advices[0].model_used == "gpt-6-luna"
        assert captured_advices[0].reasoning_effort == "medium"
    if "rationale" in advice_fixture:
        assert all(
            advice_fixture["rationale"] not in str(step.get("detail", ""))
            for step in detail["steps"]
        )
    if "targets" in case["expected"]:
        assert captured_advices[0].targets == pytest.approx(case["expected"]["targets"])
    assert next(step for step in detail["steps"] if step["name"] == "ai_directive")["detail"] == (
        f"Action={case['expected']['action']}"
    )
    if "adaptive_status" in case["expected"]:
        adaptive_step = next(
            step for step in detail["steps"] if step["name"] == "adaptive_strategy"
        )
        assert adaptive_step["status"] == case["expected"]["adaptive_status"]
        assert case["expected"]["adaptive_detail"] in adaptive_step["detail"]
    if "btc_age_seconds" in case["expected"]:
        assert case["expected"]["btc_age_seconds"] in adaptive_step["detail"]
    if case["expected"].get("maintain_overridden"):
        assert any(step["name"] == "ai_directive_override" for step in detail["steps"])
    if "profile" in case["expected"]:
        assert detail["run"]["profile"] == case["expected"]["profile"]
