from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Mapping, Sequence

from binance_client import Balance, BinanceClient
from config import (
    ConfigError,
    expand_buckets,
    load_bucket_config,
    load_cli_defaults,
    load_env_settings,
    parse_targets_arg,
    select_profile_targets,
)
from execution import execute_trades
from logging_audit import AuditLogger, load_recent_runs, load_run_detail
from portfolio import (
    PortfolioError,
    PortfolioSnapshot,
    ai_refine_targets,
    build_trades,
    compute_current_weights,
    decide_rebalance,
    filter_dust_positions,
    validate_target_map,
)

logger = logging.getLogger("rebalance")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    defaults = load_cli_defaults()
    parser = argparse.ArgumentParser(description="Binance portfolio rebalancing CLI")
    subcommands = parser.add_subparsers(dest="command", required=True)

    rebalance_parser = subcommands.add_parser("rebalance", help="Execute (or simulate) a rebalance run")
    rebalance_parser.add_argument("--dry-run", default=defaults.dry_run, type=_parse_bool, help="Simulate only")
    rebalance_parser.add_argument(
        "--profile",
        default=defaults.profile,
        choices=["moderate", "aggressive", "conservative"],
        help="Risk profile for preset targets",
    )
    rebalance_parser.add_argument("--targets", default=None, help="Manual targets mapping, e.g. btc=0.4,eth=0.2")
    rebalance_parser.add_argument(
        "--drift", type=float, default=defaults.drift, help="Absolute drift threshold before triggering trades"
    )
    rebalance_parser.add_argument(
        "--max-slippage", type=float, default=defaults.max_slippage, help="Max tolerated slippage fraction"
    )
    rebalance_parser.add_argument(
        "--min-notional", type=float, default=defaults.min_notional, help="Minimum notional per order"
    )
    rebalance_parser.add_argument("--quote", default=defaults.quote, help="Quote asset to trade against")
    rebalance_parser.add_argument("--recv-window", type=int, default=5000, help="Binance recvWindow setting")
    rebalance_parser.add_argument("--config-path", default="config.toml", help="Path to bucket configuration file")

    audit_parser = subcommands.add_parser("audit", help="Inspect past runs stored in SQLite logs")
    audit_parser.add_argument("--run-id", help="Show detailed information for a specific run")
    audit_parser.add_argument("--limit", type=int, default=5, help="Number of recent runs to list (default 5)")

    normalized = _normalize_argv(argv)
    args = parser.parse_args(normalized)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
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
    config_snapshot = {
        "profile": args.profile,
        "targets": target_weights,
        "dry_run": args.dry_run,
        "quote": args.quote,
        "drift": args.drift,
        "max_slippage": args.max_slippage,
        "min_notional": args.min_notional,
    }
    auditor.start_run(profile=args.profile, dry_run=args.dry_run, config_snapshot=config_snapshot)
    auditor.log_step(name="connect_binance", status="info", detail=f"Endpoint {env_settings.base_url}")
    pendings: list[str] = []

    try:
        balances = client.get_account_balances()
        auditor.log_step(name="fetch_assets", status="info", detail=f"Fetched {len(balances)} balances")
        asset_prices = _fetch_asset_prices(client, balances, target_weights, args.quote)
        full_snapshot = compute_current_weights(balances, asset_prices, args.quote)
        listed_assets = ", ".join(sorted(full_snapshot.positions.keys())[:20])
        suffix = " ..." if len(full_snapshot.positions) > 20 else ""
        auditor.log_step(name="list_assets", status="info", detail=f"{listed_assets}{suffix}")
        model_chain = [
            env_settings.model_name or "openrouter/gpt-4o-mini",
            env_settings.model_fallback,
        ]
        models = [model for model in model_chain if model]
        detail_msg = (
            "Consulting AI models"
            if models and env_settings.openrouter_api_key
            else "Skipping AI (no API key configured)"
        )
        auditor.log_step(name="ai_consult", status="info", detail=detail_msg)
        refined_targets, rationale = ai_refine_targets(
            api_key=env_settings.openrouter_api_key,
            models=models,
            portfolio_value=full_snapshot.total_value,
            current_weights={asset: pos.weight for asset, pos in full_snapshot.positions.items()},
            proposed_weights=target_weights,
        )
        if rationale:
            auditor.log_step(name="ai_consult", status="info", detail=rationale)
        asset_prices = _ensure_target_prices(client, asset_prices, refined_targets, args.quote)
        symbols = _collect_symbols(full_snapshot, refined_targets, args.quote)
        if symbols:
            try:
                exchange_filters = client.get_exchange_info(symbols=symbols)
            except Exception as exc:
                logger.warning("Failed to fetch filtered exchange info (%s); loading full listing.", exc)
                exchange_filters = client.get_exchange_info()
        else:
            exchange_filters = client.get_exchange_info()
        snapshot, dust_positions = filter_dust_positions(full_snapshot, exchange_filters, args.min_notional)
        if dust_positions:
            dust_detail = ", ".join(
                f"{asset} ({pos.value:.2f})" for asset, pos in dust_positions.items()
            )
            auditor.log_step(name="dust_filter", status="info", detail=f"Ignored: {dust_detail}")
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
        pendings: list[str] = []
        if rejections:
            pendings.extend(rejections)
        auditor.log_step(
            name="rebalance_check",
            status="info",
            detail=f"{len(trades)} trades planned" if trades else "No trades required after filters",
        )
        if not trades:
            if pendings:
                _log_pendings(auditor, pendings)
            auditor.finalize_run("noop")
            logger.info("No eligible trades after applying filters and notional limits.")
            return 0

        available_balances = _init_available_balances(snapshot, full_snapshot, balances)
        auditor.log_step(name="execution", status="in_progress", detail=f"{len(trades)} trades planned")
        execute_trades(
            trades=trades,
            client=client,
            auditor=auditor,
            dry_run=args.dry_run,
            available_balances=available_balances,
            pendings=pendings,
        )
        auditor.log_step(name="execution", status="completed", detail="Trades processed")
        final_snapshot = snapshot
        try:
            final_balances = client.get_account_balances()
            latest_prices = _fetch_asset_prices(client, final_balances, refined_targets, args.quote)
            final_snapshot = compute_current_weights(final_balances, latest_prices, args.quote)
        except Exception as exc:  # pragma: no cover - defensive refresh
            logger.warning("Failed to refresh final balances: %s", exc)
        _print_summary(full_snapshot, final_snapshot)
        if pendings:
            _log_pendings(auditor, pendings)
        auditor.finalize_run("completed")
    except Exception as exc:
        auditor.log_exception(error=str(exc))
        if pendings:
            _log_pendings(auditor, pendings)
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
            f"{run['run_id']} | {run.get('started_at','-')} -> {run.get('completed_at','-')} | "
            f"{run.get('status','pending')} | {dry_flag} | profile={run.get('profile','?')}"
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
    missing_assets = [asset for asset in targets if asset != quote_asset and asset not in prices]
    if not missing_assets:
        return prices
    pairs = [f"{asset}{quote_asset}" for asset in missing_assets]
    fetched = client.get_prices(symbols=pairs)
    for symbol, price in fetched.items():
        if symbol.endswith(quote_asset):
            asset = symbol[: -len(quote_asset)]
            prices[asset] = price
    return prices


def _collect_symbols(snapshot: PortfolioSnapshot, targets: Mapping[str, float], quote: str) -> list[str]:
    quote_asset = quote.upper()
    assets = set(targets.keys())
    assets.update(snapshot.positions.keys())
    symbols = [f"{asset}{quote_asset}" for asset in assets if asset != quote_asset]
    return symbols


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
        f"Started: {run['started_at']}  Completed: {run.get('completed_at','-')}  Status: {run.get('status','pending')}  "
        f"Profile: {run['profile']}  Dry-run: {bool(run['dry_run'])}"
    )
    if snapshot:
        print("Config snapshot:", json.dumps(snapshot, indent=2))
    if detail["steps"]:
        print("Steps:")
        for step in detail["steps"]:
            print(f"  {step['timestamp']} | {step['name']} | {step['status']} | {step['detail']}")
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
    available: Dict[str, float] = {asset: pos.quantity for asset, pos in snapshot.positions.items()}
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
