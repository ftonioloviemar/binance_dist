from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from anti_churn import filter_anti_churn_trades
from binance_client import (
    Balance,
    BinanceClient,
    SimpleEarnPosition,
    SimpleEarnProduct,
    SymbolFilters,
)
from config import (
    ConfigError,
    expand_buckets,
    load_bucket_config,
    load_cli_defaults,
    load_env_settings,
    parse_targets_arg,
    select_profile_targets,
)
from adaptive_strategy import get_adaptive_manager, MarketSentiment
from ai_contract import AnalysisRequest
from codex_cli_analyzer import CodexCliSettings, analyze_with_codex
from execution import execute_trades
from logging_audit import AuditLogger, load_recent_runs, load_run_detail
from macro_context import MacroSnapshot, fetch_macro_snapshot
from portfolio import (
    AIAdvice,
    AIModelFailure,
    PortfolioError,
    PortfolioSnapshot,
    ai_refine_targets,
    _apply_ai_guardrails,
    build_trades,
    compute_current_weights,
    decide_rebalance,
    RebalanceDecision,
    estimate_executable_trade_floor,
    filter_dust_positions,
    rebalance_has_tradable_orders,
    validate_target_map,
)
from openrouter_model_curator import refresh_openrouter_models
from external_flow_import import import_external_flows_csv
from performance_store import (
    DEFAULT_DB_PATH,
    build_portfolio_snapshot,
    record_portfolio_snapshot,
)
from performance import build_performance_report, render_performance_report
from market_insights_report import (
    build_market_insights_report,
    render_market_insights_json,
    render_market_insights_text,
)
from cost_gate import evaluate_cost_gate
from market_candles import SUPPORTED_ASSETS
from shadow_observation import (
    ShadowObservationResult,
    load_shadow_observation_settings,
    observe_shadow_run,
)
from shadow_portfolios import ShadowRun

logger = logging.getLogger("rebalance")


def _resolve_ai_advice(env_settings, request: AnalysisRequest, auditor) -> AIAdvice:
    provider = env_settings.ai_provider
    if provider == "off":
        advice = AIAdvice(
            targets=dict(request.proposed_weights), action="redistribute", provider="off"
        )
        auditor.log_step(
            name="ai_provider",
            status="info",
            detail="provider=off outcome=disabled fallback=deterministic",
        )
        return advice
    if provider == "codex_cli":
        advice = analyze_with_codex(
            request,
            CodexCliSettings(
                executable=env_settings.codex_cli_executable,
                timeout_seconds=env_settings.codex_cli_timeout_seconds,
            ),
        )
        if advice.model_failures:
            advice = replace(
                advice,
                targets=dict(request.proposed_weights),
                action="redistribute",
                provider="codex_cli",
            )
        else:
            guarded = _apply_ai_guardrails(advice.targets, request.proposed_weights)
            advice = replace(advice, targets=guarded, provider="codex_cli")
        outcome = "failure" if advice.model_failures else "success"
        fallback = "deterministic" if advice.model_failures else "none"
        auditor.log_step(
            name="ai_provider",
            status="warning" if advice.model_failures else "info",
            detail=(
                f"provider=codex_cli model=gpt-6-luna effort=medium "
                f"duration_seconds={advice.duration_seconds or 0:.3f} "
                f"outcome={outcome} fallback={fallback}"
            ),
        )
        for failure in advice.model_failures:
            auditor.log_step(
                name="ai_provider_failure",
                status="warning",
                detail=f"provider=codex_cli code={failure.error_type}",
            )
        return advice
    return ai_refine_targets(
        api_key=env_settings.openrouter_api_key,
        models=list(env_settings.openrouter_models),
        portfolio_value=request.portfolio_value,
        current_weights=dict(request.current_weights),
        proposed_weights=dict(request.proposed_weights),
        portfolio_context=request.portfolio_context,
    )


def _refresh_openrouter_models_after_failure(
    env_settings, advice: AIAdvice, models: list[str], auditor: AuditLogger
) -> None:
    if (
        env_settings.ai_provider != "openrouter"
        or not advice.first_model_failed
        or not models
    ):
        return
    first_failure = advice.model_failures[0] if advice.model_failures else None
    failed_primary_model = first_failure.model if first_failure else models[0]
    failure_reason = (
        f"{first_failure.error_type}: {first_failure.detail}"
        if first_failure
        else "unknown first model failure"
    )
    try:
        refresh_openrouter_models(
            api_key=env_settings.openrouter_api_key,
            current_models=models,
            failed_primary_model=failed_primary_model,
            failure_reason=failure_reason,
        )
        auditor.log_step(
            name="openrouter_model_refresh",
            status="completed",
            detail=f"Refreshed after first model failure: {failed_primary_model}",
        )
    except Exception as exc:
        auditor.log_step(
            name="openrouter_model_refresh",
            status="warning",
            detail=f"Refresh skipped/failed after first model failure: {exc}",
        )


@dataclass(frozen=True, slots=True)
class AdaptiveSourceAssessment:
    quality: str
    reason: str | None
    fear_greed_value: int | None = None
    fear_greed_classification: str | None = None
    btc_change_24h: float | None = None
    market_cap_change_24h: float | None = None
    btc_collected_at_utc: str | None = None
    decision_time_utc: str | None = None
    btc_age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class PostTradeSnapshotResult:
    payload: dict[str, Any]
    summary_weights: dict[str, float] | None


def _assess_adaptive_sources(
    snapshot: MacroSnapshot, *, now: datetime | None = None
) -> AdaptiveSourceAssessment:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() != timedelta(0):
        return AdaptiveSourceAssessment("unavailable", "decision time is not UTC-aware")

    sources = snapshot.sources if isinstance(snapshot.sources, dict) else {}
    data = snapshot.data if isinstance(snapshot.data, dict) else {}
    fear_meta = sources.get("fear_greed")
    btc_meta = sources.get("btc_24h")
    fear_data = data.get("fear_greed")
    btc_data = data.get("btc_24h")
    btc_time = (
        _parse_utc_timestamp(btc_meta.get("collected_at"))
        if isinstance(btc_meta, dict)
        else None
    )
    btc_age_seconds = (
        (current_time - btc_time).total_seconds() if btc_time else None
    )
    timing = {
        "btc_collected_at_utc": (
            btc_time.isoformat().replace("+00:00", "Z") if btc_time else None
        ),
        "decision_time_utc": current_time.isoformat().replace("+00:00", "Z"),
        "btc_age_seconds": btc_age_seconds,
    }

    def unavailable(reason: str) -> AdaptiveSourceAssessment:
        return AdaptiveSourceAssessment("unavailable", reason, **timing)

    if not isinstance(fear_meta, dict) or fear_meta.get("status") != "fresh":
        status = fear_meta.get("status", "unknown") if isinstance(fear_meta, dict) else "unknown"
        return unavailable(
            f"fear_greed required source is not fresh (status={status})"
        )
    if not isinstance(btc_meta, dict) or btc_meta.get("status") != "fresh":
        status = btc_meta.get("status", "unknown") if isinstance(btc_meta, dict) else "unknown"
        return unavailable(
            f"btc_24h required source is not fresh (status={status})"
        )
    if not isinstance(fear_data, dict):
        return unavailable("fear_greed data is missing")
    if not isinstance(btc_data, dict):
        return unavailable("btc_24h data is missing")

    fear_value = fear_data.get("value")
    fear_classification = fear_data.get("classification")
    if type(fear_value) is not int or not 0 <= fear_value <= 100:
        return unavailable("fear_greed value is not an integer in 0..100")
    if not isinstance(fear_classification, str) or not fear_classification.strip():
        return unavailable("fear_greed classification is missing")

    fear_time = _parse_utc_timestamp(fear_meta.get("observed_at"))
    if fear_time is None:
        return unavailable("fear_greed provider timestamp is missing or invalid")
    fear_age = (current_time - fear_time).total_seconds()
    if fear_age < 0 or fear_age > 36 * 60 * 60:
        return unavailable("fear_greed provider observation is outside 0..36h")

    btc_price = _finite_market_number(btc_data.get("price"))
    btc_change = _finite_market_number(btc_data.get("price_change_percent"))
    if btc_price is None or btc_price <= 0 or btc_change is None:
        return unavailable("btc_24h price or change is missing/invalid")
    if btc_time is None:
        return unavailable("btc_24h collection timestamp is missing or invalid")
    assert btc_age_seconds is not None
    if btc_age_seconds < 0 or btc_age_seconds > 15 * 60:
        return unavailable("btc_24h collection is outside 0..15m")

    global_meta = sources.get("crypto_global")
    global_data = data.get("crypto_global")
    market_cap_change = None
    degraded_reason = None
    if (
        isinstance(global_meta, dict)
        and global_meta.get("status") == "fresh"
        and global_meta.get("error") is None
        and isinstance(global_data, dict)
    ):
        market_cap_change = _finite_market_number(
            global_data.get("market_cap_change_24h")
        )
    if market_cap_change is None:
        status = global_meta.get("status", "unknown") if isinstance(global_meta, dict) else "unknown"
        degraded_reason = (
            f"crypto_global optional signal unavailable (status={status})"
        )

    quality = "degraded" if degraded_reason else "full"
    return AdaptiveSourceAssessment(
        quality=quality,
        reason=degraded_reason,
        fear_greed_value=fear_value,
        fear_greed_classification=fear_classification.strip(),
        btc_change_24h=btc_change,
        market_cap_change_24h=market_cap_change,
        **timing,
    )


def _adaptive_timing_detail(assessment: AdaptiveSourceAssessment | None) -> str:
    if assessment is None:
        return (
            "btc_collected_at_utc=unavailable, decision_time_utc=unavailable, "
            "btc_age_seconds=unavailable"
        )
    btc_time = assessment.btc_collected_at_utc or "unavailable"
    decision_time = assessment.decision_time_utc or "unavailable"
    age = (
        f"{assessment.btc_age_seconds:.3f}"
        if assessment.btc_age_seconds is not None
        else "unavailable"
    )
    return (
        f"btc_collected_at_utc={btc_time}, "
        f"decision_time_utc={decision_time}, btc_age_seconds={age}"
    )


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(timezone.utc)


def _finite_market_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    defaults = load_cli_defaults()
    parser = argparse.ArgumentParser(description="Binance portfolio rebalancing CLI")
    subcommands = parser.add_subparsers(dest="command", required=True)

    rebalance_parser = subcommands.add_parser(
        "rebalance", help="Execute (or simulate) a rebalance run"
    )
    rebalance_parser.add_argument(
        "--dry-run", default=defaults.dry_run, type=_parse_bool, help="Simulate only"
    )
    rebalance_parser.add_argument(
        "--profile",
        default=defaults.profile,
        choices=["moderate", "aggressive", "conservative"],
        help="Risk profile for preset targets",
    )
    rebalance_parser.add_argument(
        "--targets", default=None, help="Manual targets mapping, e.g. btc=0.4,eth=0.2"
    )
    rebalance_parser.add_argument(
        "--drift",
        type=float,
        default=defaults.drift,
        help="Absolute drift threshold before triggering trades",
    )
    rebalance_parser.add_argument(
        "--max-slippage",
        type=float,
        default=defaults.max_slippage,
        help="Max tolerated slippage fraction",
    )
    rebalance_parser.add_argument(
        "--min-notional",
        type=float,
        default=defaults.min_notional,
        help="Minimum notional per order",
    )
    rebalance_parser.add_argument(
        "--min-notional-uplift-tolerance",
        type=float,
        default=defaults.min_notional_uplift_tolerance,
        help="Fraction below the executable notional floor that may be uplifted to the floor",
    )
    rebalance_parser.add_argument(
        "--anti-churn-cooldown-hours",
        type=float,
        default=defaults.anti_churn_cooldown_hours,
        help="Block opposite-side trades on the same symbol within this cooldown window",
    )
    rebalance_parser.add_argument(
        "--anti-churn-override-multiplier",
        type=float,
        default=defaults.anti_churn_override_multiplier,
        help="Allow cooldown override when drift exceeds this multiple of the active drift threshold",
    )
    rebalance_parser.add_argument(
        "--quote", default=defaults.quote, help="Quote asset to trade against"
    )
    rebalance_parser.add_argument(
        "--recv-window", type=int, default=5000, help="Binance recvWindow setting"
    )
    rebalance_parser.add_argument(
        "--config-path", default="config.toml", help="Path to bucket configuration file"
    )
    rebalance_parser.add_argument(
        "--adaptive",
        action="store_true",
        help="Enable adaptive strategy based on market sentiment",
    )
    rebalance_parser.add_argument(
        "--cost-gate-mode",
        choices=["off", "observe", "enforce"],
        default=defaults.cost_gate_mode,
        help="Cost gate policy mode (default: observe)",
    )
    rebalance_parser.add_argument(
        "--cost-gate-min-net-benefit-bps",
        type=float,
        default=defaults.cost_gate_min_net_benefit_bps,
        help="Minimum calibrated net benefit in basis points before enforcement",
    )

    audit_parser = subcommands.add_parser(
        "audit", help="Inspect past runs stored in SQLite logs"
    )
    audit_parser.add_argument(
        "--run-id", help="Show detailed information for a specific run"
    )
    audit_parser.add_argument(
        "--limit", type=int, default=5, help="Number of recent runs to list (default 5)"
    )

    performance_parser = subcommands.add_parser(
        "performance", help="Report persisted portfolio performance snapshots"
    )
    performance_parser.add_argument(
        "--days", type=int, default=30, help="Look back this many days (default 30)"
    )
    performance_parser.add_argument(
        "--json", action="store_true", help="Render machine-readable JSON"
    )

    flows_parser = subcommands.add_parser(
        "flows", help="Import a user-certified external-flow ledger"
    )
    flows_commands = flows_parser.add_subparsers(dest="flows_command", required=True)
    flow_import_parser = flows_commands.add_parser(
        "import-csv", help="Import a local CSV and certify its complete UTC interval"
    )
    flow_import_parser.add_argument("--file", type=Path, required=True, help="CSV file path")
    flow_import_parser.add_argument("--quote-asset", required=True, help="Quote asset used by CSV values")
    flow_import_parser.add_argument("--coverage-start", required=True, help="Inclusive ISO-8601 UTC start")
    flow_import_parser.add_argument("--coverage-end", required=True, help="Inclusive ISO-8601 UTC end")
    flow_import_parser.add_argument(
        "--confirm-complete",
        action="store_true",
        help="Confirm that the CSV includes every external flow in the declared interval",
    )
    flow_import_parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Performance database path (default: state/performance.db)",
    )

    insights_parser = subcommands.add_parser(
        "insights", help="Compare persisted shadow market scenarios"
    )
    insights_parser.add_argument(
        "--days", type=int, default=30, help="Look back this many days (default 30)"
    )
    insights_parser.add_argument(
        "--json", action="store_true", help="Render machine-readable JSON"
    )

    normalized = _normalize_argv(argv)
    args = parser.parse_args(normalized)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    args = parse_args(argv)
    if args.command == "audit":
        return run_audit(args)
    if args.command == "performance":
        return run_performance(args)
    if args.command == "flows":
        return run_external_flow_import(args)
    if args.command == "insights":
        return run_market_insights(args)
    return run_rebalance(args)


def run_rebalance(args: argparse.Namespace) -> int:
    try:
        env_settings = load_env_settings(args.recv_window)
        bucket_config = load_bucket_config(args.config_path)
        explicit_targets = parse_targets_arg(args.targets)
        base_targets = select_profile_targets(args.profile, explicit_targets or None)
        expanded_targets = expand_buckets(base_targets, bucket_config)
        target_weights = validate_target_map(expanded_targets)
    except (ConfigError, PortfolioError) as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    client = BinanceClient(
        api_key=env_settings.api_key,
        api_secret=env_settings.api_secret,
        base_url=env_settings.base_url,
        recv_window=env_settings.recv_window,
    )
    auditor = AuditLogger()
    run_started = False
    shadow_run: ShadowRun | None = None
    shadow_capture_error: str | None = None

    def finalize_with_shadow(status: str) -> None:
        if shadow_run is None:
            auditor.log_step(
                name="market_insights_observation",
                status="warning" if shadow_capture_error else "skipped",
                detail=(
                    f"Could not capture shadow inputs: {shadow_capture_error}"
                    if shadow_capture_error
                    else "No complete pre-decision inputs were captured"
                ),
            )
        else:
            try:
                collect_enabled, simulate_enabled = load_shadow_observation_settings()
                market_assets = tuple(SUPPORTED_ASSETS) + tuple(
                    asset
                    for asset in shadow_run.target_weights
                    if asset.upper() != shadow_run.quote_asset
                )
                outcome: ShadowObservationResult = observe_shadow_run(
                    shadow_run,
                    assets=market_assets,
                    collect_enabled=collect_enabled,
                    simulate_enabled=simulate_enabled,
                )
                step_status = {
                    "completed": "completed",
                    "collection_only": "completed",
                    "incomplete": "warning",
                    "failed": "warning",
                    "disabled": "skipped",
                }.get(outcome.status, "warning")
                detail = f"status={outcome.status}"
                if outcome.deadline_exceeded:
                    detail += "; collection_deadline_exceeded=true"
                if outcome.error:
                    detail += f"; error={outcome.error}"
                auditor.log_step(
                    name="market_insights_observation",
                    status=step_status,
                    detail=detail,
                )
            except Exception as exc:  # Shadow observability must remain best-effort.
                auditor.log_step(
                    name="market_insights_observation",
                    status="warning",
                    detail=f"Shadow observation failed: {exc}",
                )
        auditor.finalize_run(status)

    # Config snapshot will be updated after adaptive logic
    initial_config_snapshot = {
        "profile": args.profile,
        "targets": target_weights,
        "dry_run": args.dry_run,
        "quote": args.quote,
        "drift": args.drift,
        "max_slippage": args.max_slippage,
        "min_notional": args.min_notional,
        "min_notional_uplift_tolerance": getattr(
            args, "min_notional_uplift_tolerance", 0.0
        ),
        "anti_churn_cooldown_hours": getattr(args, "anti_churn_cooldown_hours", 0.0),
        "anti_churn_override_multiplier": getattr(
            args, "anti_churn_override_multiplier", 2.0
        ),
        "cost_gate": {
            "mode": getattr(args, "cost_gate_mode", "observe"),
            "min_net_benefit_bps": getattr(
                args, "cost_gate_min_net_benefit_bps", None
            ),
        },
    }
    initial_config_snapshot["simple_earn"] = {
        "enabled": env_settings.simple_earn_enabled,
        "fast_redeem": env_settings.simple_earn_fast_redeem,
        "fast_redeem_configured": env_settings.simple_earn_fast_redeem_configured,
        "fast_redeem_supported_by_api": False,
        "exclude": sorted(env_settings.simple_earn_exclude_assets or []),
    }
    pendings: list[str] = []
    simple_earn_positions: list[SimpleEarnPosition] = []
    simple_earn_products: dict[str, SimpleEarnProduct] = {}
    simple_earn_by_asset: dict[str, SimpleEarnProduct] = {}
    simple_earn_snapshot_quality = "complete"

    try:
        balances = client.get_account_balances()
        auditor.log_step(
            name="fetch_assets",
            status="info",
            detail=f"Fetched {len(balances)} balances",
        )
        if env_settings.simple_earn_enabled:
            try:
                simple_earn_positions = client.get_simple_earn_flexible_positions()
                auditor.log_step(
                    name="earn_snapshot",
                    status="info",
                    detail=f"{len(simple_earn_positions)} Simple Earn flex positions",
                )
            except Exception as exc:
                pendings.append(f"Simple Earn snapshot failed: {exc}")
                auditor.log_step(name="earn_snapshot", status="failed", detail=str(exc))
                simple_earn_positions = []
                simple_earn_snapshot_quality = "incomplete"
            try:
                simple_earn_products = client.get_simple_earn_flexible_products()
                exclude = env_settings.simple_earn_exclude_assets or set()
                simple_earn_by_asset = _map_products_by_asset(
                    simple_earn_products.values(), exclude
                )
                auditor.log_step(
                    name="earn_products",
                    status="info",
                    detail=f"{len(simple_earn_by_asset)} assets eligible for Simple Earn",
                )
            except Exception as exc:
                pendings.append(f"Simple Earn product lookup failed: {exc}")
                auditor.log_step(name="earn_products", status="failed", detail=str(exc))
                simple_earn_products = {}
                simple_earn_by_asset = {}

        earn_balances = (
            _balances_from_earn(simple_earn_positions) if simple_earn_positions else []
        )
        combined_balances = _balances_for_valuation(
            spot_balances=balances, earn_positions=simple_earn_positions
        )
        price_source = combined_balances or balances
        asset_prices = _fetch_asset_prices(
            client, price_source, target_weights, args.quote
        )
        macro_snapshot = fetch_macro_snapshot()

        # Adaptive Strategy Logic
        adaptive_manager = get_adaptive_manager()
        adaptive_config = None
        adaptive_failure_detail: str | None = None
        adaptive_fallback_reason: str | None = None
        source_assessment: AdaptiveSourceAssessment | None = None
        current_sentiment: MarketSentiment | None = None

        if args.adaptive:
            source_assessment = _assess_adaptive_sources(macro_snapshot)
            if source_assessment.quality == "unavailable":
                adaptive_fallback_reason = source_assessment.reason
                logger.warning(
                    "Adaptive strategy not applied due to source quality: %s",
                    adaptive_fallback_reason,
                )
            else:
                try:
                    fear_greed_value = source_assessment.fear_greed_value
                    fear_greed_classification = (
                        source_assessment.fear_greed_classification
                    )
                    btc_change_24h = source_assessment.btc_change_24h
                    market_cap_change_24h = source_assessment.market_cap_change_24h

                    assert fear_greed_value is not None
                    assert fear_greed_classification is not None
                    assert btc_change_24h is not None

                    current_sentiment = adaptive_manager.get_market_sentiment(
                        fear_greed_value, fear_greed_classification
                    )
                    adaptive_config = adaptive_manager.calculate_adaptive_config(
                        current_sentiment=current_sentiment,
                        btc_change_24h=btc_change_24h,
                        market_cap_change_24h=market_cap_change_24h,
                        current_profile=args.profile,
                    )

                    if adaptive_config:
                        args.drift = adaptive_config.drift_threshold
                        args.max_slippage = adaptive_config.max_slippage

                    if adaptive_config and not explicit_targets:
                        target_weights = adaptive_config.targets
                        logger.info(
                            adaptive_manager.get_recommendation_summary(
                                adaptive_config,
                                current_sentiment,
                                fear_greed_value,
                                btc_change_24h,
                            )
                        )

                except Exception as e:
                    logger.warning(
                        f"Adaptive strategy failed: {e}. Using standard parameters."
                    )
                    adaptive_failure_detail = (
                        f"Failed to apply adaptive strategy: {e}; "
                        f"{_adaptive_timing_detail(source_assessment)}"
                    )

        # Atualizar config snapshot com possíveis mudanças adaptativas
        effective_profile = (
            adaptive_config.profile.value if adaptive_config else args.profile
        )
        final_config_snapshot = initial_config_snapshot.copy()
        final_config_snapshot.update(
            {
                "profile": effective_profile,
                "targets": target_weights,
                "drift": args.drift,
                "max_slippage": args.max_slippage,
            }
        )

        auditor.start_run(
            profile=effective_profile,
            dry_run=args.dry_run,
            config_snapshot=final_config_snapshot,
        )
        run_started = True
        auditor.log_step(
            name="connect_binance",
            status="info",
            detail=f"Endpoint {env_settings.base_url}",
        )
        if adaptive_config:
            targets_changed = "false" if explicit_targets else "true"
            auditor.log_step(
                name="adaptive_strategy",
                status="info",
                detail=f"Adaptive config applied: {adaptive_config.profile.value} profile, "
                f"drift={adaptive_config.drift_threshold:.2%}, "
                f"slippage={adaptive_config.max_slippage:.2%}, "
                f"sentiment={current_sentiment.value}, "
                f"source_quality={source_assessment.quality}, "
                f"source_reason={source_assessment.reason or 'none'}, "
                f"targets_changed={targets_changed}; "
                f"{_adaptive_timing_detail(source_assessment)}",
            )
        elif adaptive_fallback_reason:
            auditor.log_step(
                name="adaptive_strategy",
                status="warning",
                detail=(
                    f"Adaptive source-quality fallback: {adaptive_fallback_reason}; "
                    f"{_adaptive_timing_detail(source_assessment)}"
                ),
            )
        elif adaptive_failure_detail:
            auditor.log_step(
                name="adaptive_strategy",
                status="failed",
                detail=adaptive_failure_detail,
            )

        # Comportamento padrão quando adaptive está desabilitado ou falha
        if macro_snapshot.errors:
            auditor.log_step(
                name="macro_context",
                status="warning",
                detail="; ".join(macro_snapshot.errors[:3]),
            )
        else:
            fg = macro_snapshot.data.get("fear_greed", {})
            summary = fg.get("classification") or "ok"
            auditor.log_step(
                name="macro_context",
                status="info",
                detail=f"Snapshot loaded ({summary})",
            )

        _fail_closed_on_unpriced_holdings(
            auditor=auditor,
            run_id=auditor.run_id or "unknown",
            quote=args.quote,
            spot_balances=balances,
            earn_positions=simple_earn_positions,
            prices=asset_prices,
            data_quality=simple_earn_snapshot_quality,
        )
        consolidated_snapshot = compute_current_weights(
            price_source, asset_prices, args.quote
        )
        holdings_context = _build_holdings_context(
            spot_balances=balances,
            earn_positions=simple_earn_positions,
            prices=asset_prices,
            quote=args.quote,
            macro_snapshot=macro_snapshot,
        )
        spot_total_value = float(holdings_context.get("totals", {}).get("spot", 0.0))
        models = list(env_settings.openrouter_models)
        if env_settings.ai_provider == "codex_cli":
            detail_msg = "Consulting local Codex CLI on consolidated holdings"
        elif env_settings.ai_provider == "off":
            detail_msg = "AI disabled; using deterministic target allocation"
        else:
            detail_msg = (
                f"Consulting {len(models)} AI model(s) on consolidated holdings"
                if models and env_settings.openrouter_api_key
                else "Skipping AI (no API key configured)"
            )
        auditor.log_step(name="ai_consult", status="info", detail=detail_msg)
        advice: AIAdvice = _resolve_ai_advice(
            env_settings,
            AnalysisRequest(
                portfolio_value=consolidated_snapshot.total_value,
                current_weights={
                    asset: pos.weight
                    for asset, pos in consolidated_snapshot.positions.items()
                },
                proposed_weights=target_weights,
                portfolio_context=holdings_context,
            ),
            auditor,
        )
        refined_targets = advice.targets
        if advice.rationale and advice.provider != "codex_cli":
            auditor.log_step(name="ai_consult", status="info", detail=advice.rationale)
        for failure in advice.model_failures if advice.provider != "codex_cli" else ():
            status = f" status={failure.status_code}" if failure.status_code else ""
            auditor.log_step(
                name="ai_model_failure",
                status="warning",
                detail=f"{failure.model} {failure.error_type}{status}: {failure.detail}",
            )
        if advice.model_used and advice.provider != "codex_cli":
            auditor.log_step(
                name="ai_model_used",
                status="info",
                detail=advice.model_used,
            )
        _refresh_openrouter_models_after_failure(
            env_settings, advice, models, auditor
        )
        auditor.log_step(
            name="ai_directive", status="info", detail=f"Action={advice.action}"
        )

        if not (balances or earn_balances):
            auditor.log_step(
                name="rebalance_source",
                status="failed",
                detail="No Spot or Simple Earn balances available",
            )
            raise PortfolioError("No balances available to plan a rebalance")

        price_source = combined_balances or balances
        asset_prices = _fetch_asset_prices(
            client, price_source, refined_targets, args.quote
        )
        _fail_closed_on_unpriced_holdings(
            auditor=auditor,
            run_id=auditor.run_id or "unknown",
            quote=args.quote,
            spot_balances=balances,
            earn_positions=simple_earn_positions,
            prices=asset_prices,
            data_quality=simple_earn_snapshot_quality,
        )
        full_snapshot = compute_current_weights(price_source, asset_prices, args.quote)
        listed_assets = ", ".join(sorted(full_snapshot.positions.keys())[:20])
        suffix = " ..." if len(full_snapshot.positions) > 20 else ""
        auditor.log_step(
            name="list_assets", status="info", detail=f"{listed_assets}{suffix}"
        )

        asset_prices = _ensure_target_prices(
            client, asset_prices, refined_targets, args.quote
        )
        before_performance = _build_performance_snapshot_payload(
            run_id=auditor.run_id or "unknown",
            phase="before",
            quote=args.quote,
            spot_balances=balances,
            earn_positions=simple_earn_positions,
            prices=asset_prices,
            timestamp=_performance_timestamp(),
            data_quality=simple_earn_snapshot_quality,
        )
        _persist_performance_snapshot(auditor, before_performance)
        exchange_filters = client.get_exchange_info()
        auditor.log_step(
            name="exchange_info",
            status="info",
            detail=f"Loaded {len(exchange_filters)} symbols for filters",
        )
        try:
            shadow_run = _build_shadow_run(
                run_id=auditor.run_id or "unknown",
                quote=args.quote,
                spot_balances=balances,
                earn_positions=simple_earn_positions,
                prices=asset_prices,
                target_weights=refined_targets,
                drift_threshold=args.drift,
                symbol_filters=exchange_filters,
                snapshot_complete=simple_earn_snapshot_quality == "complete",
                min_notional=args.min_notional,
                min_notional_uplift_tolerance=getattr(
                    args, "min_notional_uplift_tolerance", 0.0
                ),
                max_slippage=args.max_slippage,
                advice_action=advice.action,
            )
        except Exception as exc:
            shadow_capture_error = " ".join(str(exc).split())[:240]
        snapshot, dust_positions = filter_dust_positions(
            full_snapshot, exchange_filters, args.min_notional
        )
        if dust_positions:
            dust_detail = ", ".join(
                f"{asset} ({pos.value:.2f})" for asset, pos in dust_positions.items()
            )
            auditor.log_step(
                name="dust_filter", status="info", detail=f"Ignored: {dust_detail}"
            )
        decision = decide_rebalance(snapshot, refined_targets, args.drift)
        auditor.log_step(
            name="decision",
            status="completed",
            detail=(
                "Distribuicao mantida (drift dentro do limite)"
                if not decision.rebalance_needed
                else "Distribuicao ajustada (drift acima do limite)"
            ),
        )
        if not decision.rebalance_needed:
            _persist_performance_snapshot(
                auditor, {**before_performance, "phase": "after"}
            )
            finalize_with_shadow("skipped")
            logger.info("No rebalance required. Portfolio within drift limits.")
            return 0
        if advice.action == "maintain":
            auditor.log_step(
                name="ai_directive_override",
                status="info",
                detail="AI maintain overridden by actionable drift",
            )

        pendings: list[str] = []
        tradability_rejections: list[str] = []
        non_actionable_rejections: list[str] = []
        if not rebalance_has_tradable_orders(
            snapshot=snapshot,
            decision=decision,
            prices=asset_prices,
            filters=exchange_filters,
            min_notional=args.min_notional,
            min_notional_uplift_tolerance=getattr(
                args, "min_notional_uplift_tolerance", 0.0
            ),
            rejections=tradability_rejections,
            non_actionable_rejections=non_actionable_rejections,
        ):
            if tradability_rejections:
                pendings.extend(tradability_rejections)
            floor_detail = _summarize_executable_floors(
                snapshot=snapshot,
                decision=decision,
                prices=asset_prices,
                filters=exchange_filters,
                min_notional=args.min_notional,
            )
            auditor.log_step(
                name="trade_floor",
                status="info",
                detail=(
                    "No tradable orders after filters"
                    + (
                        f"; non-actionable deltas: {', '.join(non_actionable_rejections)}"
                        if non_actionable_rejections
                        else ""
                    )
                    + (f"; floors: {floor_detail}" if floor_detail else "")
                ),
            )
            if pendings:
                _log_pendings(auditor, pendings)
            _persist_performance_snapshot(
                auditor, {**before_performance, "phase": "after"}
            )
            finalize_with_shadow("skipped")
            logger.info(
                "No tradable orders after applying filters and notional limits."
            )
            return 0

        rejections: list[str] = []
        trades = build_trades(
            snapshot=snapshot,
            decision=decision,
            prices=asset_prices,
            filters=exchange_filters,
            min_notional=args.min_notional,
            max_slippage=args.max_slippage,
            min_notional_uplift_tolerance=getattr(
                args, "min_notional_uplift_tolerance", 0.0
            ),
            rejections=rejections,
            non_actionable_rejections=non_actionable_rejections,
        )
        if rejections:
            pendings.extend(rejections)
        if non_actionable_rejections:
            auditor.log_step(
                name="trade_floor",
                status="info",
                detail=(
                    "Non-actionable deltas filtered: "
                    + "; ".join(non_actionable_rejections)
                ),
            )
        auditor.log_step(
            name="rebalance_check",
            status="info",
            detail=f"{len(trades)} trades planned"
            if trades
            else "No trades required after filters",
        )
        if not trades:
            if pendings:
                _log_pendings(auditor, pendings)
            _persist_performance_snapshot(
                auditor, {**before_performance, "phase": "after"}
            )
            finalize_with_shadow("noop")
            logger.info(
                "No eligible trades after applying filters and notional limits."
            )
            return 0

        cost_gate_decision = evaluate_cost_gate(
            mode=getattr(args, "cost_gate_mode", "observe"),
            expected_benefit_bps=None,
            estimated_cost_bps=None,
            min_net_benefit_bps=getattr(args, "cost_gate_min_net_benefit_bps", None),
        )
        auditor.log_step(
            name="cost_gate",
            status=cost_gate_decision.status,
            detail=json.dumps(
                {
                    "mode": cost_gate_decision.mode,
                    "allowed": cost_gate_decision.allowed,
                    "expected_benefit_bps": cost_gate_decision.expected_benefit_bps,
                    "estimated_cost_bps": cost_gate_decision.estimated_cost_bps,
                    "net_benefit_bps": cost_gate_decision.net_benefit_bps,
                    "reason": cost_gate_decision.reason,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        if not cost_gate_decision.allowed:
            if pendings:
                _log_pendings(auditor, pendings)
            _persist_performance_snapshot(
                auditor, {**before_performance, "phase": "after"}
            )
            finalize_with_shadow("blocked_cost")
            logger.info("Cost gate blocked planned trades.")
            return 0

        anti_churn_blocks: list[str] = []
        trades = filter_anti_churn_trades(
            trades=trades,
            decision=decision,
            drift_threshold=args.drift,
            logs_dir=Path("logs"),
            cooldown_hours=getattr(args, "anti_churn_cooldown_hours", 0.0),
            override_multiplier=getattr(args, "anti_churn_override_multiplier", 2.0),
            blocked=anti_churn_blocks,
        )
        if anti_churn_blocks:
            pendings.extend(anti_churn_blocks)
            auditor.log_step(
                name="anti_churn",
                status="info",
                detail=f"Blocked {len(anti_churn_blocks)} opposite-side trade(s)",
            )
        if not trades:
            if pendings:
                _log_pendings(auditor, pendings)
            _persist_performance_snapshot(
                auditor, {**before_performance, "phase": "after"}
            )
            finalize_with_shadow("skipped")
            logger.info("All planned trades blocked by anti-churn cooldown.")
            return 0

        execution_balances: Sequence[Balance] = balances
        if env_settings.simple_earn_enabled and simple_earn_positions and trades:
            _redeem_simple_earn_positions(
                client=client,
                positions=simple_earn_positions,
                legacy_fast_redeem_configured=(
                    env_settings.simple_earn_fast_redeem_configured
                ),
                legacy_fast_redeem_value=env_settings.simple_earn_fast_redeem,
                dry_run=args.dry_run,
                auditor=auditor,
                pendings=pendings,
            )
            if not args.dry_run:
                execution_balances = client.get_account_balances()
                auditor.log_step(
                    name="fetch_assets_post_redeem",
                    status="info",
                    detail=f"Fetched {len(execution_balances)} balances after Simple Earn redeem",
                )
        available_balances = _init_available_balances(
            snapshot,
            full_snapshot,
            execution_balances,
            earn_positions=simple_earn_positions,
            simulate_earn_redeem=(args.dry_run and env_settings.simple_earn_enabled),
        )
        auditor.log_step(
            name="execution",
            status="in_progress",
            detail=f"{len(trades)} trades planned",
        )
        fee_reference_prices = _fetch_fee_reference_prices(
            client, args.quote, asset_prices, auditor
        )
        execute_trades(
            trades=trades,
            client=client,
            auditor=auditor,
            dry_run=args.dry_run,
            available_balances=available_balances,
            pendings=pendings,
            reference_prices=fee_reference_prices,
        )
        auditor.log_step(
            name="execution", status="completed", detail="Trades processed"
        )
        latest_balances = balances
        latest_prices = asset_prices
        latest_balances_refresh_succeeded = False
        try:
            final_balances = client.get_account_balances()
            if not any(balance.total > 0 for balance in final_balances):
                raise PortfolioError("empty portfolio")
            latest_prices = _fetch_asset_prices(
                client, final_balances, refined_targets, args.quote
            )
            latest_balances = final_balances
            latest_balances_refresh_succeeded = True
        except PortfolioError as exc:
            detail = f"Failed to refresh final balances: {exc}"
            if args.dry_run and "empty portfolio" in str(exc).lower():
                detail = f"Skipped final balances refresh in dry-run: {exc}"
                auditor.log_step(
                    name="final_balances", status="skipped", detail=detail
                )
                logger.info(detail)
            else:
                auditor.log_step(name="final_balances", status="failed", detail=detail)
                logger.warning(detail)
        except Exception as exc:  # pragma: no cover - defensive refresh
            detail = f"Failed to refresh final balances: {exc}"
            auditor.log_step(name="final_balances", status="failed", detail=detail)
            logger.warning(detail)

        after_performance = _build_post_trade_performance_snapshot_payload(
            client=client,
            auditor=auditor,
            run_id=auditor.run_id or "unknown",
            quote=args.quote,
            spot_balances=latest_balances,
            earn_positions=simple_earn_positions,
            prices=latest_prices,
            targets=refined_targets,
            timestamp=_performance_timestamp(),
            products_by_asset=simple_earn_by_asset,
            simple_earn_enabled=env_settings.simple_earn_enabled,
            dry_run=args.dry_run,
            spot_balances_fresh=latest_balances_refresh_succeeded,
            pendings=pendings,
            initial_data_quality=simple_earn_snapshot_quality,
        )
        _print_summary(
            full_snapshot,
            after_performance.summary_weights,
        )
        _persist_performance_snapshot(auditor, after_performance.payload)
        if pendings:
            _log_pendings(auditor, pendings)
        finalize_with_shadow("completed")
    except Exception as exc:
        auditor.log_exception(error=str(exc))
        if pendings:
            _log_pendings(auditor, pendings)
        if run_started:
            finalize_with_shadow("failed")
        logger.exception("Rebalance run failed")
        return 1
    finally:
        client.close()
        auditor.close()
    return 0


def run_audit(args: argparse.Namespace) -> int:
    if args.run_id:
        detail = load_run_detail(args.run_id)
        if not detail:
            logger.error("Run %s not found", args.run_id)
            return 1
        _print_run_detail(detail)
        return 0
    runs = load_recent_runs(limit=args.limit)
    if not runs:
        print("No runs recorded yet.")
        return 0
    print(f"Showing {len(runs)} most recent runs:")
    for run in runs:
        dry_flag = "DRY" if run.get("dry_run") else "LIVE"
        print(
            f"{run['run_id']} | {run.get('started_at', '-')} -> {run.get('completed_at', '-')} | "
            f"{run.get('status', 'pending')} | {dry_flag} | profile={run.get('profile', '?')}"
        )
    return 0


def run_performance(args: argparse.Namespace) -> int:
    if args.days <= 0:
        logger.error("--days must be positive")
        return 1
    report = build_performance_report(None, days=args.days)
    print(render_performance_report(report, json_output=args.json))
    return 0


def run_external_flow_import(args: argparse.Namespace) -> int:
    try:
        result = import_external_flows_csv(
            db_path=args.db_path,
            csv_path=args.file,
            quote_asset=args.quote_asset,
            coverage_start=args.coverage_start,
            coverage_end=args.coverage_end,
            confirm_complete=args.confirm_complete,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        logger.error("External-flow CSV import rejected: %s", exc)
        return 1
    print(
        "Certified external-flow ledger imported: "
        f"quote={result['quote_asset']} row_count={result['row_count']} "
        f"coverage_start={result['coverage_start']} "
        f"coverage_end={result['coverage_end']}"
    )
    return 0


def run_market_insights(args: argparse.Namespace) -> int:
    if args.days <= 0:
        logger.error("--days must be positive")
        return 1
    try:
        report = build_market_insights_report(days=args.days)
    except (OSError, ValueError) as exc:
        logger.error("Could not build market insights report: %s", exc)
        return 1
    rendered = (
        render_market_insights_json(report)
        if args.json
        else render_market_insights_text(report)
    )
    print(rendered)
    return 0


def _parse_bool(value: str) -> bool:
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}
    normalized = value.strip().lower()
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def _build_shadow_run(
    *,
    run_id: str,
    quote: str,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
    prices: Mapping[str, float],
    target_weights: Mapping[str, float],
    drift_threshold: float,
    symbol_filters: Mapping[str, SymbolFilters],
    snapshot_complete: bool,
    min_notional: float,
    min_notional_uplift_tolerance: float,
    max_slippage: float,
    advice_action: str,
) -> ShadowRun:
    def aggregate(items: Sequence[tuple[str, float]]) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for asset, quantity in items:
            key = asset.strip().upper()
            result[key] = result.get(key, Decimal(0)) + Decimal(str(quantity))
        return result

    quote_asset = quote.upper()
    captured_prices = {
        asset.upper(): Decimal(str(price)) for asset, price in prices.items()
    }
    captured_prices[quote_asset] = Decimal(1)
    return ShadowRun(
        session_id=f"shadow-{quote_asset.lower()}-v1",
        run_id=run_id,
        observed_at=datetime.now(timezone.utc),
        quote_asset=quote_asset,
        spot_balances=aggregate(
            (balance.asset, balance.total) for balance in spot_balances
        ),
        earn_balances=aggregate(
            (position.asset, position.total_amount) for position in earn_positions
        ),
        prices=captured_prices,
        target_weights={
            asset.upper(): Decimal(str(weight))
            for asset, weight in target_weights.items()
        },
        drift_threshold=Decimal(str(drift_threshold)),
        btc_vol30=None,
        symbol_filters=dict(symbol_filters),
        snapshot_complete=snapshot_complete,
        min_notional=Decimal(str(min_notional)),
        min_notional_uplift_tolerance=Decimal(
            str(min_notional_uplift_tolerance)
        ),
        max_slippage=Decimal(str(max_slippage)),
        advice_action=advice_action,
    )


def _balances_from_earn(positions: Sequence[SimpleEarnPosition]) -> list[Balance]:
    aggregated: Dict[str, float] = {}
    for position in positions:
        amount = position.total_amount
        if amount <= 0:
            continue
        aggregated[position.asset.upper()] = (
            aggregated.get(position.asset.upper(), 0.0) + amount
        )
    return [
        Balance(asset=asset, free=amount, locked=0.0)
        for asset, amount in aggregated.items()
    ]


def _build_performance_snapshot_payload(
    *,
    run_id: str,
    phase: str,
    quote: str,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
    prices: Mapping[str, float],
    timestamp: str,
    data_quality: str | None = None,
) -> dict[str, Any]:
    snapshot_spot_balances = _spot_balances_for_valuation(
        spot_balances=spot_balances, earn_positions=earn_positions
    )
    return build_portfolio_snapshot(
        run_id=run_id,
        phase=phase,
        quote_asset=quote,
        spot_balances=[
            {"asset": balance.asset, "quantity": balance.total}
            for balance in snapshot_spot_balances
        ],
        earn_positions=[
            {"asset": position.asset, "quantity": position.total_amount}
            for position in earn_positions
        ],
        prices=prices,
        timestamp=timestamp,
        data_quality=data_quality,
    )


def _fail_closed_on_unpriced_holdings(
    *,
    auditor: AuditLogger,
    run_id: str,
    quote: str,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
    prices: Mapping[str, float],
    data_quality: str | None = None,
) -> None:
    invalid_assets = _unpriced_held_assets(
        spot_balances=spot_balances,
        earn_positions=earn_positions,
        prices=prices,
        quote=quote,
    )
    if not invalid_assets:
        return

    snapshot = _build_performance_snapshot_payload(
        run_id=run_id,
        phase="before",
        quote=quote,
        spot_balances=spot_balances,
        earn_positions=earn_positions,
        prices=prices,
        timestamp=_performance_timestamp(),
        data_quality=data_quality,
    )
    snapshot["data_quality"] = "incomplete"
    snapshot["missing_prices"] = sorted(
        set(snapshot.get("missing_prices", [])) | invalid_assets
    )
    detail = (
        "Positive Spot or Simple Earn balances have invalid market prices; "
        "run halted before planning or fund movement"
    )
    auditor.log_step(name="valuation_guard", status="failed", detail=detail)
    _persist_performance_snapshot(auditor, snapshot)
    raise PortfolioError(detail)


def _unpriced_held_assets(
    *,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
    prices: Mapping[str, float],
    quote: str,
) -> set[str]:
    quote_asset = quote.upper()
    valued_spot_balances = _spot_balances_for_valuation(
        spot_balances=spot_balances, earn_positions=earn_positions
    )
    invalid_assets = {
        balance.asset.upper()
        for balance in valued_spot_balances
        if balance.total > 0
        and balance.asset.upper() != quote_asset
        and not _valid_market_price(prices.get(balance.asset.upper()))
    }
    invalid_assets.update(
        position.asset.upper()
        for position in earn_positions
        if position.total_amount > 0
        and position.asset.upper() != quote_asset
        and not _valid_market_price(prices.get(position.asset.upper()))
    )
    return invalid_assets


def _spot_balances_for_valuation(
    *,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
) -> list[Balance]:
    earn_assets = {
        position.asset.upper()
        for position in earn_positions
        if position.total_amount > 0
    }
    return [
        balance
        for balance in spot_balances
        if not (
            balance.asset.upper().startswith("LD")
            and balance.asset.upper()[2:] in earn_assets
        )
    ]


def _balances_for_valuation(
    *,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
) -> list[Balance]:
    return [
        *_spot_balances_for_valuation(
            spot_balances=spot_balances, earn_positions=earn_positions
        ),
        *_balances_from_earn(earn_positions),
    ]


def _portfolio_weights_from_holdings(
    *,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
    prices: Mapping[str, float],
    quote: str,
    data_quality: str,
) -> dict[str, float] | None:
    if data_quality not in {"complete", "simulation"}:
        return None
    if _unpriced_held_assets(
        spot_balances=spot_balances,
        earn_positions=earn_positions,
        prices=prices,
        quote=quote,
    ):
        return None
    try:
        snapshot = compute_current_weights(
            _balances_for_valuation(
                spot_balances=spot_balances,
                earn_positions=earn_positions,
            ),
            prices,
            quote,
        )
    except PortfolioError:
        return None
    return {
        asset: position.weight
        for asset, position in snapshot.positions.items()
    }


def _build_post_trade_performance_snapshot_payload(
    *,
    client: BinanceClient,
    auditor: AuditLogger,
    run_id: str,
    quote: str,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
    prices: Mapping[str, float],
    targets: Mapping[str, float],
    timestamp: str,
    products_by_asset: Mapping[str, SimpleEarnProduct],
    simple_earn_enabled: bool,
    dry_run: bool,
    spot_balances_fresh: bool,
    pendings: list[str],
    initial_data_quality: str = "complete",
) -> PostTradeSnapshotResult:
    latest_balances = list(spot_balances)
    latest_earn_positions = list(earn_positions)
    latest_prices = dict(prices)
    data_quality = (
        "incomplete"
        if dry_run and initial_data_quality != "complete"
        else "simulation" if dry_run else "complete"
    )

    if simple_earn_enabled and products_by_asset:
        if dry_run or spot_balances_fresh:
            _subscribe_simple_earn_balances(
                client=client,
                balances=latest_balances,
                products_by_asset=products_by_asset,
                dry_run=dry_run,
                auditor=auditor,
                pendings=pendings,
            )
        else:
            detail = (
                "Skipped Simple Earn subscription because current Spot balances "
                "could not be confirmed"
            )
            pendings.append(detail)
            auditor.log_step(name="earn_subscribe", status="skipped", detail=detail)

    if not dry_run:
        try:
            latest_balances = client.get_account_balances()
            auditor.log_step(
                name="spot_snapshot_after",
                status="completed",
                detail=f"Fetched {len(latest_balances)} post-operation Spot balances",
            )
        except Exception:
            data_quality = "incomplete"
            detail = "Failed to refresh post-operation Spot balances; snapshot is incomplete"
            pendings.append(detail)
            auditor.log_step(name="spot_snapshot_after", status="failed", detail=detail)

        try:
            latest_earn_positions = client.get_simple_earn_flexible_positions()
            auditor.log_step(
                name="earn_snapshot_after",
                status="completed",
                detail=(
                    "Fetched "
                    f"{len(latest_earn_positions)} post-operation Simple Earn positions"
                ),
            )
        except Exception:
            # The positions captured before redemption are stale. Never reuse them
            # when the post-operation query fails.
            latest_earn_positions = []
            data_quality = "incomplete"
            detail = (
                "Failed to refresh post-operation Simple Earn positions; "
                "snapshot is incomplete"
            )
            pendings.append(detail)
            auditor.log_step(
                name="earn_snapshot_after", status="failed", detail=detail
            )

        combined_balances = _balances_for_valuation(
            spot_balances=latest_balances,
            earn_positions=latest_earn_positions,
        )
        try:
            latest_prices = _fetch_asset_prices(
                client, combined_balances, targets, quote
            )
        except Exception:
            data_quality = "incomplete"
            detail = "Failed to refresh post-operation asset prices; snapshot is incomplete"
            pendings.append(detail)
            auditor.log_step(name="prices_snapshot_after", status="failed", detail=detail)

    snapshot = _build_performance_snapshot_payload(
        run_id=run_id,
        phase="after",
        quote=quote,
        spot_balances=latest_balances,
        earn_positions=latest_earn_positions,
        prices=latest_prices,
        timestamp=timestamp,
        data_quality=data_quality,
    )
    unpriced_after_assets = _unpriced_held_assets(
        spot_balances=latest_balances,
        earn_positions=latest_earn_positions,
        prices=latest_prices,
        quote=quote,
    )
    if unpriced_after_assets:
        data_quality = "incomplete"
        snapshot["data_quality"] = data_quality
        snapshot["missing_prices"] = sorted(
            set(snapshot.get("missing_prices", [])) | unpriced_after_assets
        )
        detail = (
            "Post-operation valuation has invalid market prices; after snapshot is "
            "incomplete and completed operations remain in effect"
        )
        pendings.append(detail)
        auditor.log_step(name="prices_snapshot_after", status="warning", detail=detail)
    summary_weights = _portfolio_weights_from_holdings(
        spot_balances=latest_balances,
        earn_positions=latest_earn_positions,
        prices=latest_prices,
        quote=quote,
        data_quality=data_quality,
    )
    return PostTradeSnapshotResult(
        payload=snapshot,
        summary_weights=summary_weights,
    )


def _persist_performance_snapshot(
    auditor: AuditLogger,
    payload: Mapping[str, Any],
) -> None:
    try:
        record_portfolio_snapshot(None, payload)
        detail = json.dumps(
            {
                "phase": payload.get("phase"),
                "data_quality": payload.get("data_quality"),
                "missing_price_count": len(payload.get("missing_prices", [])),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        auditor.log_step(name="portfolio_snapshot", status="info", detail=detail)
    except Exception as exc:  # pragma: no cover - defensive persistence guard
        auditor.log_step(
            name="portfolio_snapshot",
            status="warning",
            detail=f"Persistence skipped: {exc}",
        )


def _performance_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_fee_reference_prices(
    client: BinanceClient,
    quote: str,
    prices: Mapping[str, float],
    auditor: AuditLogger,
) -> dict[str, float]:
    references = dict(prices)
    if quote.upper() == "BNB" or "BNB" in references:
        return references
    try:
        ticker_prices = client.get_prices(symbols=[f"BNB{quote.upper()}"])
        for symbol, price in ticker_prices.items():
            if symbol.upper() == f"BNB{quote.upper()}":
                references["BNB"] = price
    except Exception as exc:  # pragma: no cover - exchange/network guard
        auditor.log_step(
            name="fee_reference_prices",
            status="warning",
            detail=f"BNB conversion unavailable: {exc}",
        )
    return references


def _build_holdings_context(
    *,
    spot_balances: Sequence[Balance],
    earn_positions: Sequence[SimpleEarnPosition],
    prices: Mapping[str, float],
    quote: str,
    macro_snapshot: MacroSnapshot | None = None,
) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "spot": {},
        "earn": {},
        "totals": {"spot": 0.0, "earn": 0.0, "overall": 0.0},
    }
    quote_asset = quote.upper()
    valued_spot_balances = _spot_balances_for_valuation(
        spot_balances=spot_balances, earn_positions=earn_positions
    )
    for balance in valued_spot_balances:
        asset = balance.asset.upper()
        price = 1.0 if asset == quote_asset else prices.get(asset)
        if price is None:
            continue
        value = balance.total * price
        context["spot"][asset] = {"amount": balance.total, "value": value}
        context["totals"]["spot"] += value
    for position in earn_positions:
        asset = position.asset.upper()
        price = 1.0 if asset == quote_asset else prices.get(asset)
        if price is None:
            continue
        value = position.total_amount * price
        bucket = context["earn"].setdefault(asset, {"amount": 0.0, "value": 0.0})
        bucket["amount"] += position.total_amount
        bucket["value"] += value
        context["totals"]["earn"] += value
    context["totals"]["overall"] = context["totals"]["spot"] + context["totals"]["earn"]
    if macro_snapshot and macro_snapshot.data:
        context["macro"] = macro_snapshot.data
    return context


def _map_products_by_asset(
    products: Sequence[SimpleEarnProduct],
    exclude_assets: set[str],
) -> dict[str, SimpleEarnProduct]:
    mapping: dict[str, SimpleEarnProduct] = {}
    for product in products:
        if not isinstance(product, SimpleEarnProduct):
            continue
        asset = product.asset.upper()
        if asset in exclude_assets:
            continue
        if not product.can_purchase:
            continue
        status = product.status.upper()
        if status not in {"SUBSCRIBABLE", "LIVE", "PURCHASING", "PURCHASABLE"}:
            continue
        mapping.setdefault(asset, product)
    return mapping


def _redeem_simple_earn_positions(
    *,
    client: BinanceClient,
    positions: Sequence[SimpleEarnPosition],
    legacy_fast_redeem_configured: bool,
    legacy_fast_redeem_value: bool,
    dry_run: bool,
    auditor: AuditLogger,
    pendings: list[str],
) -> None:
    configured_detail = (
        f"configured={str(legacy_fast_redeem_value).lower()}"
        if legacy_fast_redeem_configured
        else "not explicitly configured"
    )
    auditor.log_step(
        name="earn_redeem_mode",
        status="info",
        detail=(
            "SIMPLE_EARN_FAST_REDEEM is legacy and has no effect on the current "
            f"Flexible Redeem API ({configured_detail}); request omits type and "
            "does not select FAST/STANDARD."
        ),
    )
    for position in positions:
        amount = position.redeemable_amount or position.total_amount
        if amount <= 0:
            continue
        detail = f"{position.asset} amount={amount:.8f} product={position.product_id}"
        if dry_run:
            auditor.log_step(name="earn_redeem", status="simulated", detail=detail)
            continue
        try:
            client.redeem_simple_earn_flexible(
                product_id=position.product_id,
                amount=amount,
            )
            auditor.log_step(name="earn_redeem", status="completed", detail=detail)
        except Exception as exc:
            message = f"Redeem {position.asset}: {exc}"
            pendings.append(message)
            auditor.log_step(name="earn_redeem", status="failed", detail=message)


def _subscribe_simple_earn_balances(
    *,
    client: BinanceClient,
    balances: Sequence[Balance],
    products_by_asset: Mapping[str, SimpleEarnProduct],
    dry_run: bool,
    auditor: AuditLogger,
    pendings: list[str],
) -> None:
    for balance in balances:
        asset = balance.asset.upper()
        product = products_by_asset.get(asset)
        if not product:
            continue
        available = balance.free
        if available <= 0:
            continue
        amount = _clamp_subscription_amount(available, product)
        if amount <= 0:
            continue
        detail = f"{asset} amount={amount:.8f} -> product {product.product_id}"
        if dry_run:
            auditor.log_step(name="earn_subscribe", status="simulated", detail=detail)
            continue
        try:
            client.subscribe_simple_earn_flexible(
                product_id=product.product_id, amount=amount
            )
            auditor.log_step(name="earn_subscribe", status="completed", detail=detail)
        except Exception as exc:
            message = f"Subscribe {asset}: {exc}"
            pendings.append(message)
            auditor.log_step(name="earn_subscribe", status="failed", detail=message)


def _clamp_subscription_amount(amount: float, product: SimpleEarnProduct) -> float:
    min_amount = max(product.min_purchase_amount, 0.0)
    if min_amount > 0 and amount < min_amount:
        return 0.0
    caps = [
        cap
        for cap in (
            product.max_purchase_amount,
            product.purchase_limit_per_day,
            product.purchase_limit_per_user,
            product.left_quota,
        )
        if cap and cap > 0
    ]
    if caps:
        amount = min(amount, min(caps))
    return max(amount, 0.0)


def _fetch_asset_prices(
    client: BinanceClient,
    balances: Sequence[Balance],
    targets: Mapping[str, float],
    quote: str,
) -> Dict[str, float]:
    quote_asset = quote.upper()
    assets = {quote_asset}
    for balance in balances:
        asset = balance.asset.upper()
        if asset != quote_asset:
            assets.add(asset)
    for asset in targets:
        if asset != quote_asset:
            assets.add(asset)
    prices_raw = client.get_prices()
    prices: Dict[str, float] = {quote_asset: 1.0}
    for symbol, price in prices_raw.items():
        if symbol.endswith(quote_asset):
            asset = symbol[: -len(quote_asset)]
            prices[asset] = price
    return prices


def _ensure_target_prices(
    client: BinanceClient,
    prices: Dict[str, float],
    targets: Mapping[str, float],
    quote: str,
) -> Dict[str, float]:
    quote_asset = quote.upper()
    required_assets = [
        asset
        for asset, weight in targets.items()
        if asset != quote_asset and weight > 0
    ]
    missing_assets = [
        asset for asset in required_assets if not _valid_market_price(prices.get(asset))
    ]
    if not missing_assets:
        return prices
    pairs = [f"{asset}{quote_asset}" for asset in missing_assets]
    fetched = client.get_prices(symbols=pairs)
    for symbol, price in fetched.items():
        if symbol.endswith(quote_asset) and _valid_market_price(price):
            asset = symbol[: -len(quote_asset)]
            prices[asset] = price
    if any(not _valid_market_price(prices.get(asset)) for asset in required_assets):
        raise PortfolioError(
            "Cannot plan rebalance because a target market price is invalid or unavailable"
        )
    return prices


def _valid_market_price(value: Any) -> bool:
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(price) and price > 0


def _print_run_detail(detail: Mapping[str, Any]) -> None:
    run = detail["run"]
    snapshot = run.get("config_snapshot") or {}
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except json.JSONDecodeError:
            snapshot = {}
    print(f"Run: {run['run_id']}")
    print(
        f"Started: {run['started_at']}  Completed: {run.get('completed_at', '-')}  Status: {run.get('status', 'pending')}  "
        f"Profile: {run['profile']}  Dry-run: {bool(run['dry_run'])}"
    )
    if snapshot:
        print("Config snapshot:", json.dumps(snapshot, indent=2))
    if detail["steps"]:
        print("Steps:")
        for step in detail["steps"]:
            print(
                f"  {step['timestamp']} | {step['name']} | {step['status']} | {step['detail']}"
            )
    if detail["orders"]:
        print("Orders:")
        for order in detail["orders"]:
            print(
                f"  {order['timestamp']} | {order['symbol']} {order['side']} {order['quantity']}@{order['price']} "
                f"| {order['status']} | {order['detail']}"
            )


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    tokens = list(argv or [])
    if not tokens or tokens[0] not in {"rebalance", "audit", "performance", "flows", "insights"}:
        return ["rebalance", *tokens]
    return tokens


def _init_available_balances(
    snapshot: PortfolioSnapshot,
    _full_snapshot: PortfolioSnapshot,
    balances: Sequence[Balance],
    *,
    earn_positions: Sequence[SimpleEarnPosition] = (),
    simulate_earn_redeem: bool = False,
) -> Dict[str, float]:
    available: Dict[str, float] = {}
    for balance in balances:
        asset = balance.asset.upper()
        available[asset] = available.get(asset, 0.0) + balance.free
    if simulate_earn_redeem:
        for position in earn_positions:
            amount = position.redeemable_amount or position.total_amount
            if amount > 0:
                asset = position.asset.upper()
                available[asset] = available.get(asset, 0.0) + amount
    quote = snapshot.quote_asset
    available.setdefault(quote, 0.0)
    return available


def _log_pendings(auditor: AuditLogger, pendings: list[str]) -> None:
    if not pendings:
        return
    preview = "; ".join(pendings[:5])
    if len(pendings) > 5:
        preview += f" (+{len(pendings) - 5} mais)"
    auditor.log_step(name="pendings", status="info", detail=preview)


def _summarize_executable_floors(
    *,
    snapshot: PortfolioSnapshot,
    decision: RebalanceDecision,
    prices: Mapping[str, float],
    filters: Mapping[str, SymbolFilters],
    min_notional: float,
) -> str:
    quote = snapshot.quote_asset
    summaries: list[str] = []
    for asset, delta_weight in decision.deltas.items():
        if asset == quote:
            continue
        price = prices.get(asset)
        symbol = f"{asset}{quote}"
        symbol_filters = filters.get(symbol)
        if price is None or price <= 0 or symbol_filters is None:
            continue
        executable_floor = estimate_executable_trade_floor(
            total_value=snapshot.total_value,
            price=price,
            filters=symbol_filters,
            min_notional=min_notional,
        )
        summaries.append(
            f"{asset}>={executable_floor.notional:.4f} ({executable_floor.weight:.2%})"
        )
    return ", ".join(summaries[:5])
    logger.info("Pendencias/itens ignorados: %s", preview)


def _print_summary(before: object, after: object) -> None:
    def format_weights(snapshot: object) -> Dict[str, float]:
        if snapshot is None:
            return {}
        if isinstance(snapshot, Mapping):
            return {
                str(asset): round(float(weight), 4)
                for asset, weight in snapshot.items()
            }
        return {
            asset: round(position.weight, 4)
            for asset, position in getattr(snapshot, "positions", {}).items()
        }

    logger.info("Before weights: %s", format_weights(before))
    if after is None:
        logger.info("After weights unavailable: no complete post-operation valuation")
    else:
        logger.info("After  weights: %s", format_weights(after))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
