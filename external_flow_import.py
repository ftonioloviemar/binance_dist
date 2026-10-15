from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from performance_store import replace_certified_external_flow_ledger


REQUIRED_COLUMNS = {"flow_id", "timestamp_utc", "asset", "quote_value", "direction"}


def import_external_flows_csv(
    *,
    db_path: str | Path | None,
    csv_path: str | Path,
    quote_asset: str,
    coverage_start: str,
    coverage_end: str,
    confirm_complete: bool,
) -> dict[str, Any]:
    if not confirm_complete:
        raise ValueError("Explicit --confirm-complete acknowledgement is required")
    quote = quote_asset.strip().upper()
    if not quote:
        raise ValueError("Quote asset is required")

    start = _parse_utc_timestamp(coverage_start, "coverage start")
    end = _parse_utc_timestamp(coverage_end, "coverage end")
    if start >= end:
        raise ValueError("Coverage start must be earlier than coverage end")

    path = Path(csv_path)
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        raise ValueError("CSV file could not be read") from None
    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("CSV file must use UTF-8 encoding") from None

    reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
    try:
        fieldnames = reader.fieldnames or []
    except csv.Error:
        raise ValueError("CSV syntax is invalid") from None
    if len(fieldnames) != len(set(fieldnames)) or not REQUIRED_COLUMNS.issubset(fieldnames):
        raise ValueError("CSV header is missing required columns or contains duplicates")

    flows: list[dict[str, str]] = []
    flow_ids: set[str] = set()
    for row_number, row in _iter_csv_rows(reader):
        if None in row:
            raise ValueError(f"CSV row {row_number} has more fields than the header")
        flow_id = str(row.get("flow_id") or "").strip()
        timestamp = _parse_utc_timestamp(
            str(row.get("timestamp_utc") or ""), f"timestamp in row {row_number}"
        )
        asset = str(row.get("asset") or "").strip().upper()
        direction = str(row.get("direction") or "").strip()
        raw_quote_value = str(row.get("quote_value") or "").strip()
        try:
            quote_value = Decimal(raw_quote_value)
        except (InvalidOperation, ValueError):
            raise ValueError(f"CSV row {row_number} has an invalid quote_value") from None

        if not flow_id:
            raise ValueError(f"CSV row {row_number} has an empty flow_id")
        if flow_id in flow_ids:
            raise ValueError(f"CSV row {row_number} duplicates a flow_id")
        if not asset:
            raise ValueError(f"CSV row {row_number} has an empty asset")
        if not quote_value.is_finite() or quote_value <= 0:
            raise ValueError(f"CSV row {row_number} quote_value must be finite and positive")
        if direction not in {"in", "out"}:
            raise ValueError(f"CSV row {row_number} direction must be in or out")
        if timestamp < start or timestamp > end:
            raise ValueError(f"CSV row {row_number} timestamp is outside certified coverage")

        flow_ids.add(flow_id)
        flows.append(
            {
                "flow_id": flow_id,
                "timestamp": timestamp.isoformat(),
                "asset": asset,
                "quote_value": _decimal_text(quote_value),
                "direction": direction,
            }
        )

    certified_at = datetime.now(timezone.utc).isoformat()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    ledger = {
        "quote_asset": quote,
        "coverage_start": start.isoformat(),
        "coverage_end": end.isoformat(),
        "certified_at": certified_at,
        "source_sha256": source_sha256,
        "flows": flows,
    }
    replace_certified_external_flow_ledger(db_path, ledger)
    return {
        "quote_asset": quote,
        "coverage_start": ledger["coverage_start"],
        "coverage_end": ledger["coverage_end"],
        "certified_at": certified_at,
        "source_sha256": source_sha256,
        "row_count": len(flows),
    }


def _parse_utc_timestamp(value: str, field: str) -> datetime:
    try:
        text = value.strip()
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    except ValueError:
        raise ValueError(f"Invalid ISO-8601 UTC {field}") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"ISO-8601 UTC {field} must include a zero UTC offset")
    return parsed.astimezone(timezone.utc)


def _decimal_text(value: Decimal) -> str:
    text = str(value)
    if "e" not in text.lower() and "." in text:
        return text.rstrip("0").rstrip(".")
    return text


def _iter_csv_rows(reader: csv.DictReader) -> Any:
    try:
        yield from enumerate(reader, start=2)
    except csv.Error:
        raise ValueError("CSV syntax is invalid") from None
