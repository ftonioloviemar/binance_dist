from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable

DEFAULT_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "14"))


class AuditLogger:
    def __init__(self, *, logs_dir: Path | None = None, retention_days: int | None = None) -> None:
        self.logs_dir = logs_dir or Path("logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days or DEFAULT_RETENTION_DAYS
        self.run_id: str | None = None
        self._current_date: str | None = None
        self._current_path: Path | None = None

    def close(self) -> None:  # pragma: no cover - compatibility shim
        return None

    # --- lifecycle ----------------------------------------------------------
    def start_run(self, *, profile: str, dry_run: bool, config_snapshot: dict[str, Any]) -> str:
        run_id = uuid.uuid4().hex
        self.run_id = run_id
        timestamp = _now_local()
        record = {
            "event": "run_start",
            "timestamp": timestamp,
            "run_id": run_id,
            "status": "started",
            "profile": profile,
            "dry_run": dry_run,
            "config": config_snapshot,
        }
        self._write_record(record)
        return run_id

    def finalize_run(self, status: str) -> None:
        if not self.run_id:
            return
        record = {
            "event": "run_end",
            "timestamp": _now_local(),
            "run_id": self.run_id,
            "status": status,
        }
        self._write_record(record)

    # --- logging helpers ----------------------------------------------------
    def log_step(self, *, name: str, status: str, detail: str | None = None) -> None:
        if not self.run_id:
            return
        record = {
            "event": "step",
            "timestamp": _now_local(),
            "run_id": self.run_id,
            "status": status,
            "name": name,
            "detail": detail or "",
        }
        self._write_record(record)

    def log_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None,
        status: str,
        detail: str | None = None,
    ) -> None:
        if not self.run_id:
            return
        record = {
            "event": "order",
            "timestamp": _now_local(),
            "run_id": self.run_id,
            "status": status,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "detail": detail or "",
        }
        self._write_record(record)

    def log_exception(self, *, error: str) -> None:
        if not self.run_id:
            return
        record = {
            "event": "exception",
            "timestamp": _now_local(),
            "run_id": self.run_id,
            "status": "failed",
            "detail": error,
        }
        self._write_record(record)

    # --- internal -----------------------------------------------------------
    def _write_record(self, record: dict[str, Any]) -> None:
        path = self._ensure_log_path()
        line = _format_record(record)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _ensure_log_path(self) -> Path:
        date_str = datetime.utcnow().strftime("%Y%m%d")
        if self._current_date != date_str:
            self._current_date = date_str
            self._current_path = self.logs_dir / f"{date_str}.log"
            self._purge_old_logs()
        assert self._current_path is not None  # for type checkers
        return self._current_path

    def _purge_old_logs(self) -> None:
        if self.retention_days <= 0:
            return
        threshold = datetime.utcnow() - timedelta(days=self.retention_days)
        for file_path in self.logs_dir.glob("*.log"):
            try:
                file_date = datetime.strptime(file_path.stem, "%Y%m%d")
            except ValueError:
                continue
            if file_date < threshold:
                file_path.unlink(missing_ok=True)


# --- public readers ---------------------------------------------------------

def load_recent_runs(limit: int = 5, logs_dir: Path | None = None) -> list[dict[str, Any]]:
    reader = _AuditLogReader(logs_dir or Path("logs"))
    return reader.load_recent_runs(limit)


def load_run_detail(run_id: str, logs_dir: Path | None = None) -> dict[str, Any] | None:
    reader = _AuditLogReader(logs_dir or Path("logs"))
    return reader.load_run_detail(run_id)


class _AuditLogReader:
    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir

    def load_recent_runs(self, limit: int) -> list[dict[str, Any]]:
        cache: Dict[str, dict[str, Any]] = {}
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in self._iter_records_newest_first():
            run_id = record.get("run_id")
            if not run_id:
                continue
            entry = cache.setdefault(run_id, {"run_id": run_id})
            event = record.get("event")
            if event == "run_end":
                entry["completed_at"] = record.get("timestamp")
                entry["status"] = record.get("status")
            elif event == "run_start":
                entry["started_at"] = record.get("timestamp")
                entry["profile"] = record.get("profile")
                entry["dry_run"] = record.get("dry_run")
                entry.setdefault("status", record.get("status"))
                if run_id not in seen:
                    results.append(entry.copy())
                    seen.add(run_id)
                    if len(results) >= limit:
                        break
        return results

    def load_run_detail(self, run_id: str) -> dict[str, Any] | None:
        run_info: dict[str, Any] = {}
        steps: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []
        found = False
        for record in self._iter_records_oldest_first():
            if record.get("run_id") != run_id:
                continue
            found = True
            event = record.get("event")
            if event == "run_start":
                run_info = {
                    "run_id": run_id,
                    "started_at": record.get("timestamp"),
                    "completed_at": None,
                    "status": record.get("status"),
                    "profile": record.get("profile"),
                    "dry_run": record.get("dry_run"),
                    "config_snapshot": record.get("config"),
                }
            elif event == "run_end":
                run_info["completed_at"] = record.get("timestamp")
                run_info["status"] = record.get("status")
            elif event == "step":
                steps.append(
                    {
                        "timestamp": record.get("timestamp"),
                        "name": record.get("name"),
                        "status": record.get("status"),
                        "detail": record.get("detail"),
                    }
                )
            elif event == "order":
                orders.append(
                    {
                        "timestamp": record.get("timestamp"),
                        "symbol": record.get("symbol"),
                        "side": record.get("side"),
                        "quantity": _coerce_float(record.get("quantity")),
                        "price": _coerce_float(record.get("price")),
                        "status": record.get("status"),
                        "detail": record.get("detail"),
                    }
                )
            elif event == "exception":
                steps.append(
                    {
                        "timestamp": record.get("timestamp"),
                        "name": "exception",
                        "status": record.get("status"),
                        "detail": record.get("detail"),
                    }
                )
        if not found:
            return None
        return {"run": run_info, "steps": steps, "orders": orders}

    def _iter_records_newest_first(self) -> Iterable[dict[str, Any]]:
        for path in sorted(self.logs_dir.glob("*.log"), reverse=True):
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
            for line in reversed(lines):
                record = _parse_line(line)
                if record:
                    yield record

    def _iter_records_oldest_first(self) -> Iterable[dict[str, Any]]:
        for path in sorted(self.logs_dir.glob("*.log")):
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    record = _parse_line(line)
                    if record:
                        yield record


def _format_record(record: dict[str, Any]) -> str:
    timestamp = record.get("timestamp", _now_local())
    event = record.get("event", "info")
    pieces = [timestamp, event]
    for key, value in record.items():
        if key in {"timestamp", "event"}:
            continue
        pieces.append(f"{key}={_stringify(value)}")
    return " | ".join(pieces)


def _parse_line(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    parts = [part.strip() for part in text.split("|")]
    if len(parts) < 2:
        # try legacy JSON fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    record: Dict[str, Any] = {"timestamp": parts[0], "event": parts[1]}
    for chunk in parts[2:]:
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        record[key.strip()] = _coerce_value(value.strip())
    return record


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value).replace("\n", " ")


def _coerce_value(value: str) -> Any:
    if value in {"true", "false"}:
        return value == "true"
    if value == "null":
        return None
    if value.startswith("{") or value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _now_local() -> str:
    return datetime.now().astimezone().isoformat()


__all__ = ["AuditLogger", "load_recent_runs", "load_run_detail"]
