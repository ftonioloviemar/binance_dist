from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Mapping, Sequence

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
from execution import execute_trades
from logging_audit import AuditLogger, load_recent_runs, load_run_detail
from macro_context import MacroSnapshot, fetch_macro_snapshot
from portfolio import (
    AIAdvice,
    AIModelFailure,
    PortfolioError,
    PortfolioSnapshot,
    ai_refine_targets,
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

logger = logging.getLogger("rebalance")


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

    audit_parser = subcommands.add_parser(
        "audit", help="Inspect past runs stored in SQLite logs"
    )
    audit_parser.add_argument(
        "--run-id", help="Show detailed information for a specific run"
    )
    audit_parser.add_argument(
        "--limit", type=int, default=5, help="Number of recent runs to list (default 5)"
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

    # Config snapshot will be updated after adaptive logic
    initial_config_snapshot = {
        "profile": args.profile,
        "targets": target_weights,
        "dry_run": args.dry_run,
        "quote": args.quote,
        "drift": args.drift,
        "max_slippage": args.max_slippage,
        "min_notional": args.min_notional,
    }
    initial_config_snapshot["simple_earn"] = {
        "enabled": env_settings.simple_earn_enabled,
        "fast_redeem": env_settings.simple_earn_fast_redeem,
        "exclude": sorted(env_settings.simple_earn_exclude_assets or []),
    }
    pendings: list[str] = []
    simple_earn_positions: list[SimpleEarnPosition] = []
    simple_earn_products: dict[str, SimpleEarnProduct] = {}
    simple_earn_by_asset: dict[str, SimpleEarnProduct] = {}

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
        combined_balances = list(balances)
        if earn_balances:
            combined_balances.extend(earn_balances)
        price_source = combined_balances or balances
        asset_prices = _fetch_asset_prices(
            client, price_source, target_weights, args.quote
        )
        consolidated_snapshot = compute_current_weights(
            price_source, asset_prices, args.quote
        )
        macro_snapshot = fetch_macro_snapshot()

        # Adaptive Strategy Logic
        adaptive_manager = get_adaptive_manager()
        adaptive_config = None
        adaptive_failure_detail: str | None = None
        current_sentiment: MarketSentiment | None = None

        if args.adaptive and not macro_snapshot.errors:
            try:
                fg = macro_snapshot.data.get("fear_greed", {})
                btc_data = macro_snapshot.data.get("btc_24h", {})
                crypto_global = macro_snapshot.data.get("crypto_global", {})

                fear_greed_value = fg.get("value", 50)
                fear_greed_classification = fg.get("classification", "Neutral")
                btc_change_24h = btc_data.get("price_change_percent", 0.0)
                market_cap_change_24h = crypto_global.get("market_cap_change_24h", 0.0)

                # Determinar sentimento de mercado
                current_sentiment = adaptive_manager.get_market_sentiment(
                    fear_greed_value, fear_greed_classification
                )

                # Calcular configuração adaptativa
                adaptive_config = adaptive_manager.calculate_adaptive_config(
                    current_sentiment=current_sentiment,
                    btc_change_24h=btc_change_24h,
                    market_cap_change_24h=market_cap_change_24h,
                    current_profile=args.profile,
                )

                # Aplicar configuração adaptativa
                if adaptive_config:
                    # Sobrescrever parâmetros
                    args.drift = adaptive_config.drift_threshold
                    args.max_slippage = adaptive_config.max_slippage

                    # Sobrescrever targets se não forem explícitos
                    if not explicit_targets:
                        target_weights = adaptive_config.targets

                        # Log da decisão adaptativa
                        summary = adaptive_manager.get_recommendation_summary(
                            adaptive_config,
                            current_sentiment,
                            fear_greed_value,
                            btc_change_24h,
                        )
                        logger.info(summary)

                summary = fg.get("classification") or "ok"

            except Exception as e:
                logger.warning(
                    f"Adaptive strategy failed: {e}. Using standard parameters."
                )
                adaptive_failure_detail = f"Failed to apply adaptive strategy: {e}"

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
                f"targets_changed={targets_changed}",
            )
        elif adaptive_failure_detail:
            auditor.log_step(
                name="adaptive_strategy",
                status="failed",
                detail=adaptive_failure_detail,
            )

        # Comportamento padrão quando adaptive está desabilitado ou falha
        if not args.adaptive or macro_snapshot.errors:
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
        else:
            fg = macro_snapshot.data.get("fear_greed", {})
            summary = fg.get("classification") or "ok"
            auditor.log_step(
                name="macro_context",
                status="info",
                detail=f"Snapshot loaded ({summary})",
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
        detail_msg = (
            f"Consulting {len(models)} AI model(s) on consolidated holdings"
            if models and env_settings.openrouter_api_key
            else "Skipping AI (no API key configured)"
        )
        auditor.log_step(name="ai_consult", status="info", detail=detail_msg)
        advice: AIAdvice = ai_refine_targets(
            api_key=env_settings.openrouter_api_key,
            models=models,
            portfolio_value=consolidated_snapshot.total_value,
            current_weights={
                asset: pos.weight
                for asset, pos in consolidated_snapshot.positions.items()
            },
            proposed_weights=target_weights,
            portfolio_context=holdings_context,
        )
        refined_targets = advice.targets
        if advice.rationale:
            auditor.log_step(name="ai_consult", status="info", detail=advice.rationale)
        for failure in advice.model_failures:
            status = f" status={failure.status_code}" if failure.status_code else ""
            auditor.log_step(
                name="ai_model_failure",
                status="warning",
                detail=f"{failure.model} {failure.error_type}{status}: {failure.detail}",
            )
        if advice.model_used:
            auditor.log_step(
                name="ai_model_used",
                status="info",
                detail=advice.model_used,
            )
        if advice.first_model_failed and models:
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
        full_snapshot = compute_current_weights(price_source, asset_prices, args.quote)
        listed_assets = ", ".join(sorted(full_snapshot.positions.keys())[:20])
        suffix = " ..." if len(full_snapshot.positions) > 20 else ""
        auditor.log_step(
            name="list_assets", status="info", detail=f"{listed_assets}{suffix}"
        )

        asset_prices = _ensure_target_prices(
            client, asset_prices, refined_targets, args.quote
        )
        exchange_filters = client.get_exchange_info()
        auditor.log_step(
            name="exchange_info",
            status="info",
            detail=f"Loaded {len(exchange_filters)} symbols for filters",
        )
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
            auditor.finalize_run("skipped")
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
        if not rebalance_has_tradable_orders(
            snapshot=snapshot,
            decision=decision,
            prices=asset_prices,
            filters=exchange_filters,
            min_notional=args.min_notional,
            rejections=tradability_rejections,
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
                    + (f"; floors: {floor_detail}" if floor_detail else "")
                ),
            )
            if pendings:
                _log_pendings(auditor, pendings)
            auditor.finalize_run("skipped")
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
            rejections=rejections,
        )
        if rejections:
            pendings.extend(rejections)
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
            auditor.finalize_run("noop")
            logger.info(
                "No eligible trades after applying filters and notional limits."
            )
            return 0

        execution_balances: Sequence[Balance] = balances
        if env_settings.simple_earn_enabled and simple_earn_positions and trades:
            _redeem_simple_earn_positions(
                client=client,
                positions=simple_earn_positions,
                products_by_id=simple_earn_products,
                fast=env_settings.simple_earn_fast_redeem,
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
            snapshot, full_snapshot, execution_balances
        )
        auditor.log_step(
            name="execution",
            status="in_progress",
            detail=f"{len(trades)} trades planned",
        )
        execute_trades(
            trades=trades,
            client=client,
            auditor=auditor,
            dry_run=args.dry_run,
            available_balances=available_balances,
            pendings=pendings,
        )
        auditor.log_step(
            name="execution", status="completed", detail="Trades processed"
        )
        final_snapshot = snapshot
        latest_balances = balances
        try:
            final_balances = client.get_account_balances()
            latest_prices = _fetch_asset_prices(
                client, final_balances, refined_targets, args.quote
            )
            final_snapshot = compute_current_weights(
                final_balances, latest_prices, args.quote
            )
            latest_balances = final_balances
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

        _print_summary(full_snapshot, final_snapshot)
        if env_settings.simple_earn_enabled and simple_earn_by_asset:
            _subscribe_simple_earn_balances(
                client=client,
                balances=latest_balances,
                products_by_asset=simple_earn_by_asset,
                dry_run=args.dry_run,
                auditor=auditor,
                pendings=pendings,
            )
        if pendings:
            _log_pendings(auditor, pendings)
        auditor.finalize_run("completed")
    except Exception as exc:
        auditor.log_exception(error=str(exc))
        if pendings:
            _log_pendings(auditor, pendings)
        if run_started:
            auditor.finalize_run("failed")
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


def _parse_bool(value: str) -> bool:
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}
    normalized = value.strip().lower()
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


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
    for balance in spot_balances:
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
    products_by_id: Mapping[str, SimpleEarnProduct],
    fast: bool,
    dry_run: bool,
    auditor: AuditLogger,
    pendings: list[str],
) -> None:
    for position in positions:
        amount = position.redeemable_amount or position.total_amount
        if amount <= 0:
            continue
        product = products_by_id.get(position.product_id)
        allow_fast = fast and (
            (product and product.can_fast_redeem) or position.can_fast_redeem
        )
        detail = f"{position.asset} amount={amount:.8f} product={position.product_id}"
        if dry_run:
            auditor.log_step(name="earn_redeem", status="simulated", detail=detail)
            continue
        try:
            client.redeem_simple_earn_flexible(
                product_id=position.product_id,
                amount=amount,
                fast=allow_fast,
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
    missing_assets = [
        asset for asset in targets if asset != quote_asset and asset not in prices
    ]
    if not missing_assets:
        return prices
    pairs = [f"{asset}{quote_asset}" for asset in missing_assets]
    fetched = client.get_prices(symbols=pairs)
    for symbol, price in fetched.items():
        if symbol.endswith(quote_asset):
            asset = symbol[: -len(quote_asset)]
            prices[asset] = price
    return prices


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
    if not tokens or tokens[0] not in {"rebalance", "audit"}:
        return ["rebalance", *tokens]
    return tokens


def _init_available_balances(
    snapshot: PortfolioSnapshot,
    full_snapshot: PortfolioSnapshot,
    balances: Sequence[Balance],
) -> Dict[str, float]:
    available: Dict[str, float] = {
        asset: pos.quantity for asset, pos in snapshot.positions.items()
    }
    quote = snapshot.quote_asset
    if quote in full_snapshot.positions:
        available[quote] = full_snapshot.positions[quote].quantity
    else:
        for bal in balances:
            if bal.asset.upper() == quote:
                available[quote] = bal.total
                break
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
        return {
            asset: round(position.weight, 4)
            for asset, position in getattr(snapshot, "positions", {}).items()
        }

    logger.info("Before weights: %s", format_weights(before))
    logger.info("After  weights: %s", format_weights(after))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
