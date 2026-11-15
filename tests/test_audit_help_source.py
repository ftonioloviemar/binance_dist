import pytest

import app


def test_audit_help_identifies_daily_logs_not_legacy_sqlite(capsys):
    with pytest.raises(SystemExit) as exc:
        app.main(["audit", "--help"])

    assert exc.value.code == 0
    help_text = " ".join(capsys.readouterr().out.lower().split())
    assert "logs/yyyymmdd.log" in help_text
    assert "audit.db" in help_text
    assert "legacy" in help_text
