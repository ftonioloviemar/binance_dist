from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import main
from external_flow_import import import_external_flows_csv
from performance_store import (
    build_portfolio_snapshot,
    load_certified_external_flow_ledger,
    load_external_flows,
    load_portfolio_snapshots,
    record_portfolio_snapshot,
)


START = "2026-10-01T00:00:00Z"
END = "2026-10-15T00:00:00Z"
HEADER = "flow_id,timestamp_utc,asset,quote_value,direction\n"


def _write_csv(tmp_path: Path, body: str, name: str = "flows.csv") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8", newline="")
    return path


def _import(
    db_path: Path,
    csv_path: Path,
    *,
    quote_asset: str = "USDT",
    coverage_start: str = START,
    coverage_end: str = END,
    confirm_complete: bool = True,
) -> dict[str, object]:
    return import_external_flows_csv(
        db_path=db_path,
        csv_path=csv_path,
        quote_asset=quote_asset,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        confirm_complete=confirm_complete,
    )


def test_import_certifies_utc_flows_and_ignores_extra_columns(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        HEADER.rstrip("\n") + ",note\n"
        + "deposit-1,2026-10-05T12:30:00Z,btc,125.5000,in,ignored\n",
    )

    result = _import(tmp_path / "performance.db", csv_path, quote_asset="usdt")
    ledger = load_certified_external_flow_ledger(tmp_path / "performance.db", "USDT")

    assert result["row_count"] == 1
    assert ledger is not None
    assert ledger["quote_asset"] == "USDT"
    assert ledger["coverage_start"] == "2026-10-01T00:00:00+00:00"
    assert ledger["coverage_end"] == "2026-10-15T00:00:00+00:00"
    assert ledger["source_sha256"] == hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert datetime.fromisoformat(ledger["certified_at"]).tzinfo == timezone.utc
    assert ledger["flows"] == [
        {
            "flow_id": "deposit-1",
            "timestamp": "2026-10-05T12:30:00+00:00",
            "asset": "BTC",
            "quote_value": "125.5",
            "direction": "in",
        }
    ]


def test_import_accepts_empty_certified_ledger(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path, HEADER)

    result = _import(tmp_path / "performance.db", csv_path)

    assert result["row_count"] == 0
    ledger = load_certified_external_flow_ledger(tmp_path / "performance.db", "USDT")
    assert ledger is not None
    assert ledger["flows"] == []


def test_import_preserves_arbitrary_decimal_precision(tmp_path: Path) -> None:
    precise_value = "123456789012345678901234567891.12345678901234567890123456789"
    csv_path = _write_csv(
        tmp_path,
        HEADER + f"deposit-precise,2026-10-05T12:30:00Z,BTC,{precise_value},in\n",
    )

    _import(tmp_path / "performance.db", csv_path)

    ledger = load_certified_external_flow_ledger(tmp_path / "performance.db", "USDT")
    assert ledger is not None
    assert ledger["flows"][0]["quote_value"] == precise_value


def test_import_rejects_malformed_csv_syntax(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        HEADER + 'flow-1,2026-10-05T12:30:00Z,"BTC,1,in\n',
    )

    with pytest.raises(ValueError, match="CSV syntax"):
        _import(tmp_path / "performance.db", csv_path)


@pytest.mark.parametrize(
    ("body", "coverage_start", "coverage_end"),
    [
        ("flow_id,timestamp_utc,asset,direction\n", START, END),
        (HEADER + "id,2026-10-05T12:00:00,BTC,1,in\n", START, END),
        (HEADER + "id,2026-10-05T12:00:00-03:00,BTC,1,in\n", START, END),
        (HEADER + "id,2026-10-16T00:00:00Z,BTC,1,in\n", START, END),
        (HEADER + ",2026-10-05T12:00:00Z,BTC,1,in\n", START, END),
        (HEADER + "id,2026-10-05T12:00:00Z,,1,in\n", START, END),
        (HEADER + "id,2026-10-05T12:00:00Z,BTC,NaN,in\n", START, END),
        (HEADER + "id,2026-10-05T12:00:00Z,BTC,0,in\n", START, END),
        (HEADER + "id,2026-10-05T12:00:00Z,BTC,1,transfer\n", START, END),
        (
            HEADER + "id,2026-10-05T12:00:00Z,BTC,1,in\n",
            "2026-10-15T00:00:00Z",
            START,
        ),
    ],
)
def test_invalid_csv_is_rejected_without_certifying(
    tmp_path: Path,
    body: str,
    coverage_start: str,
    coverage_end: str,
) -> None:
    db_path = tmp_path / "performance.db"
    csv_path = _write_csv(tmp_path, body)

    with pytest.raises(ValueError):
        _import(
            db_path,
            csv_path,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

    assert load_certified_external_flow_ledger(db_path, "USDT") is None


def test_import_requires_explicit_completeness_confirmation(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path, HEADER)

    with pytest.raises(ValueError, match="confirm"):
        _import(tmp_path / "performance.db", csv_path, confirm_complete=False)


def test_import_rejects_duplicate_ids_and_invalid_quote_values(tmp_path: Path) -> None:
    db_path = tmp_path / "performance.db"
    duplicate = _write_csv(
        tmp_path,
        HEADER
        + "same,2026-10-05T12:00:00Z,BTC,1,in\n"
        + "same,2026-10-06T12:00:00Z,ETH,2,out\n",
        "duplicate.csv",
    )
    with pytest.raises(ValueError):
        _import(db_path, duplicate)

    for value in ("bad", "Infinity", "-1"):
        invalid = _write_csv(
            tmp_path,
            HEADER + f"id,2026-10-05T12:00:00Z,BTC,{value},in\n",
            f"invalid-{value.replace('-', 'm')}.csv",
        )
        with pytest.raises(ValueError):
            _import(db_path, invalid)

    assert load_certified_external_flow_ledger(db_path, "USDT") is None


def test_reimport_replaces_only_selected_quote_ledger(tmp_path: Path) -> None:
    db_path = tmp_path / "performance.db"
    first_usdt = _write_csv(
        tmp_path,
        HEADER + "old,2026-10-05T12:00:00Z,BTC,1,in\n",
        "first-usdt.csv",
    )
    usdc = _write_csv(
        tmp_path,
        HEADER + "usdc,2026-10-05T12:00:00Z,ETH,2,out\n",
        "usdc.csv",
    )
    replacement = _write_csv(
        tmp_path,
        HEADER + "new,2026-10-06T12:00:00Z,BTC,3,out\n",
        "replacement.csv",
    )

    _import(db_path, first_usdt)
    _import(db_path, usdc, quote_asset="USDC")
    _import(db_path, replacement)

    assert [flow["flow_id"] for flow in load_certified_external_flow_ledger(db_path, "USDT")["flows"]] == ["new"]
    assert [flow["flow_id"] for flow in load_certified_external_flow_ledger(db_path, "USDC")["flows"]] == ["usdc"]


def test_invalid_reimport_preserves_prior_certified_ledger(tmp_path: Path) -> None:
    db_path = tmp_path / "performance.db"
    valid = _write_csv(
        tmp_path,
        HEADER + "keep,2026-10-05T12:00:00Z,BTC,1,in\n",
        "valid.csv",
    )
    invalid = _write_csv(
        tmp_path,
        HEADER
        + "new,2026-10-06T12:00:00Z,ETH,2,in\n"
        + "bad,2026-10-16T12:00:00Z,BTC,3,out\n",
        "invalid.csv",
    )
    _import(db_path, valid)
    before = load_certified_external_flow_ledger(db_path, "USDT")

    with pytest.raises(ValueError):
        _import(db_path, invalid)

    assert load_certified_external_flow_ledger(db_path, "USDT") == before


def test_import_preserves_legacy_unverified_flow_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "performance.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE external_flows (
                flow_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, asset TEXT NOT NULL,
                quote_value TEXT NOT NULL, direction TEXT NOT NULL,
                source TEXT NOT NULL, confidence TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO external_flows VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy", "2026-10-05T12:00:00+00:00", "BTC", "99", "in", "manual", "unknown"),
        )

    csv_path = _write_csv(tmp_path, HEADER)
    _import(db_path, csv_path)

    assert load_external_flows(db_path) == [
        {
            "flow_id": "legacy",
            "timestamp": "2026-10-05T12:00:00+00:00",
            "asset": "BTC",
            "quote_value": "99",
            "direction": "in",
            "source": "manual",
            "confidence": "unknown",
        }
    ]
    assert load_certified_external_flow_ledger(db_path, "USDT")["flows"] == []


def test_import_migrates_populated_v3_database_additively(tmp_path: Path) -> None:
    db_path = tmp_path / "performance.db"
    snapshot = build_portfolio_snapshot(
        run_id="legacy-run",
        phase="after",
        quote_asset="USDT",
        spot_balances=[{"asset": "USDT", "quantity": "42"}],
        earn_positions=[],
        prices={},
        timestamp="2026-10-10T12:00:00+00:00",
        external_flow_status="unknown",
    )
    record_portfolio_snapshot(db_path, snapshot)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES ('legacy_marker', 'preserve-me')"
        )
        connection.execute("DROP TABLE certified_external_flows")
        connection.execute("DROP TABLE certified_flow_coverage")
        connection.execute("UPDATE schema_meta SET value = '3' WHERE key = 'version'")

    csv_path = _write_csv(tmp_path, HEADER + "deposit,2026-10-10T12:00:00Z,BTC,5,in\n")
    _import(db_path, csv_path)

    assert load_portfolio_snapshots(db_path, run_id="legacy-run") == [snapshot]
    with sqlite3.connect(db_path) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM schema_meta"))
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert metadata["version"] == "4"
    assert metadata["legacy_marker"] == "preserve-me"
    assert {"certified_flow_coverage", "certified_external_flows"}.issubset(tables)


def test_cli_import_does_not_print_flow_ids_amounts_or_csv_contents(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sensitive_id = "private-transfer-reference-987"
    sensitive_amount = "987654.321"
    csv_path = _write_csv(
        tmp_path,
        HEADER
        + f"{sensitive_id},2026-10-05T12:00:00Z,BTC,{sensitive_amount},in\n",
    )

    result = main(
        [
            "flows",
            "import-csv",
            "--file",
            str(csv_path),
            "--quote-asset",
            "USDT",
            "--coverage-start",
            START,
            "--coverage-end",
            END,
            "--confirm-complete",
            "--db-path",
            str(tmp_path / "performance.db"),
        ]
    )
    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert result == 0
    assert "row_count=1" in output
    assert sensitive_id not in output
    assert sensitive_amount not in output
    assert HEADER.strip() not in output


def test_cli_rejects_bad_csv_without_echoing_row_values(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_id = "private-reference-456"
    sensitive_amount = "456789.123 private"
    csv_path = _write_csv(
        tmp_path,
        HEADER + f"{sensitive_id},2026-10-05T12:00:00Z,BTC,{sensitive_amount},in\n",
    )

    result = main(
        [
            "flows",
            "import-csv",
            "--file",
            str(csv_path),
            "--quote-asset",
            "USDT",
            "--coverage-start",
            START,
            "--coverage-end",
            END,
            "--confirm-complete",
            "--db-path",
            str(tmp_path / "performance.db"),
        ]
    )
    output = "\n".join(record.getMessage() for record in caplog.records)

    assert result == 1
    assert "invalid quote_value" in output
    assert sensitive_id not in output
    assert sensitive_amount not in output


def test_cli_requires_completeness_acknowledgement(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    csv_path = _write_csv(tmp_path, HEADER)

    result = main(
        [
            "flows",
            "import-csv",
            "--file",
            str(csv_path),
            "--quote-asset",
            "USDT",
            "--coverage-start",
            START,
            "--coverage-end",
            END,
            "--db-path",
            str(tmp_path / "performance.db"),
        ]
    )
    output = "\n".join(record.getMessage() for record in caplog.records)

    assert result == 1
    assert "confirm-complete" in output
    assert load_certified_external_flow_ledger(tmp_path / "performance.db", "USDT") is None
