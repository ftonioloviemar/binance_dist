from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from market_insights import DEFAULT_DB_PATH


POLICIES = ("hold", "baseline", "volatility_guard_v1")
DEFAULT_COST_RATE = Decimal("0.002")
STRESS_COST_RATE = Decimal("0.004")
REPORT_SCHEMA_VERSION = 1


def build_market_insights_report(
    *, db_path: str | Path = DEFAULT_DB_PATH, days: int = 30, now: datetime | None = None
) -> dict[str, Any]:
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError("days must be a positive integer")
    reference = _utc(now or datetime.now(UTC))
    cutoff = reference - timedelta(days=days)
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Market insights database does not exist: {path}")
    uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            rows = connection.execute(
                "SELECT session_id, run_id, policy, observed_at, payload_json "
                "FROM shadow_policy_observations ORDER BY observed_at, session_id, run_id, policy"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError("Market insights database is invalid or lacks report data") from exc

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        observed_at = _parse_timestamp(row["observed_at"])
        if cutoff <= observed_at <= reference:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError as exc:
                raise ValueError("Market insights database contains invalid report data") from exc
            if not isinstance(payload, dict):
                raise ValueError("Market insights database contains invalid report data")
            groups[(str(row["session_id"]), str(row["run_id"]))].append(
                {
                    "session_id": str(row["session_id"]),
                    "run_id": str(row["run_id"]),
                    "policy": str(row["policy"]),
                    "observed_at": observed_at,
                    **payload,
                }
            )

    observations = []
    for (session_id, run_id), items in groups.items():
        items.sort(key=lambda item: item["policy"])
        observed_at = min(item["observed_at"] for item in items)
        by_policy = {item["policy"]: item for item in items}
        comparison_status = _comparison_status(by_policy)
        policy_reports: dict[str, Any] = {}
        for policy in POLICIES:
            item = by_policy.get(policy)
            policy_reports[policy] = (
                _policy_report(item, by_policy.get("hold"), comparison_status)
                if item
                else None
            )
        observations.append(
            {
                "session_id": session_id,
                "run_id": run_id,
                "observed_at": observed_at.isoformat(),
                "status": comparison_status,
                "policies": policy_reports,
            }
        )
    observations.sort(key=lambda item: (item["observed_at"], item["session_id"], item["run_id"]))
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "label": "simulated_conditional",
        "days": days,
        "assumptions": {
            "basis": "previously_observed_targets_and_advice",
            "cost_sensitivity": "fixed_trade_path_estimate",
            "default_fee_plus_slippage_per_side": _decimal_text(DEFAULT_COST_RATE),
            "stress_fee_plus_slippage_per_side": _decimal_text(STRESS_COST_RATE),
            "trade_path_fixed": True,
        },
        "observations": observations,
    }


def render_market_insights_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def render_market_insights_text(report: Mapping[str, Any]) -> str:
    lines = [
        "Shadow market insights (simulated; conditional on previously observed targets/advice)",
        "Cost overlays are estimates with a fixed trade path; quantities, affordability, and decisions are not re-simulated.",
        f"Lookback: {report['days']} days | observations: {len(report['observations'])}",
    ]
    for observation in report["observations"]:
        lines.append(
            f"{observation['observed_at']} | {observation['session_id']} | "
            f"{observation['run_id']} | {observation['status']}"
        )
        for policy in POLICIES:
            result = observation["policies"][policy]
            if result is None:
                lines.append(f"  {policy}: missing")
                continue
            delta = result["net_return_delta_vs_hold"]
            lines.append(
                f"  {policy} v{result['policy_version']}: net={result['net_return']}; "
                f"delta_vs_hold={delta}; turnover={result['gross_turnover']}; "
                f"drawdown={result['max_drawdown']}; residual_drift={result['residual_drift']}"
            )
            costs = result["cost_sensitivity"]
            if costs is not None:
                lines.append(
                    f"    estimated net after costs: default={costs['default']['estimated_net_return']}; "
                    f"stress={costs['stress']['estimated_net_return']}"
                )
    return "\n".join(lines)


def _comparison_status(items: Mapping[str, Mapping[str, Any]]) -> str:
    if set(items) != set(POLICIES):
        return "incomplete"
    seeds = set()
    statuses = set()
    for policy in POLICIES:
        item = items[policy]
        status = item.get("status")
        if status not in {"complete", "seeded"}:
            return "incomplete"
        statuses.add(status)
        try:
            seed = _decimal(item.get("initial_equity"))
            if _decimal(item.get("modeled_cost")) < 0 or _decimal(item.get("gross_turnover")) < 0:
                return "incomplete"
            for key in (
                "net_return",
                "modeled_cost",
                "gross_turnover",
                "relative_turnover",
                "max_drawdown",
                "residual_drift",
            ):
                _decimal(item.get(key))
            if int(item.get("trade_count", -1)) < 0 or int(item.get("skipped_count", -1)) < 0:
                return "incomplete"
            if seed <= 0:
                return "incomplete"
            seeds.add(seed)
        except (ValueError, TypeError, ArithmeticError):
            return "incomplete"
    if len(seeds) != 1 or len(statuses) != 1:
        return "incomplete"
    return statuses.pop()


def _policy_report(
    item: Mapping[str, Any], hold: Mapping[str, Any] | None, comparison_status: str
) -> dict[str, Any]:
    policy = str(item["policy"])
    complete = item.get("status") in {"complete", "seeded"}
    report: dict[str, Any] = {
        "status": str(item.get("status", "incomplete")),
        "policy_version": str(item.get("policy_version", "unknown")),
        "net_return": None,
        "net_return_delta_vs_hold": None,
        "modeled_cost": None,
        "gross_turnover": None,
        "relative_turnover": None,
        "max_drawdown": None,
        "residual_drift": None,
        "trade_count": int(item.get("trade_count", 0)),
        "skipped_count": int(item.get("skipped_count", 0)),
        "cost_sensitivity": None,
    }
    if not complete:
        return report
    net_return = _decimal(item["net_return"])
    modeled_cost = _decimal(item["modeled_cost"])
    turnover = _decimal(item["gross_turnover"])
    equity = _decimal(item["initial_equity"])
    report.update(
        {
            "net_return": _decimal_text(net_return),
            "modeled_cost": _decimal_text(modeled_cost),
            "gross_turnover": _decimal_text(turnover),
            "relative_turnover": _decimal_text(_decimal(item["relative_turnover"])),
            "max_drawdown": _decimal_text(_decimal(item["max_drawdown"])),
            "residual_drift": _decimal_text(_decimal(item["residual_drift"])),
        }
    )
    if comparison_status == "complete" and hold is not None:
        report["net_return_delta_vs_hold"] = _decimal_text(
            net_return - _decimal(hold["net_return"])
        )
        with localcontext() as context:
            context.prec = 48
            gross_return = net_return + modeled_cost / equity
            report["cost_sensitivity"] = {
                "assumption": "fixed_trade_path",
                "default": {
                    "estimated_cost": _decimal_text(turnover * DEFAULT_COST_RATE),
                    "estimated_net_return": _decimal_text(
                        gross_return - turnover * DEFAULT_COST_RATE / equity
                    ),
                },
                "stress": {
                    "estimated_cost": _decimal_text(turnover * STRESS_COST_RATE),
                    "estimated_net_return": _decimal_text(
                        gross_return - turnover * STRESS_COST_RATE / equity
                    ),
                },
            }
    return report


def _decimal(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Report metric must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Report timestamps must be timezone-aware")
    return value.astimezone(UTC)
