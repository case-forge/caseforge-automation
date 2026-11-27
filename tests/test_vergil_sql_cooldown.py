from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import sql_cooldown


def test_sql_cooldown_file_lives_in_session_dir():
    assert sql_cooldown.sql_cooldown_file() == sql_cooldown.SESSION_DIR / "sql-cooldown.json"


def test_sql_cooldown_until_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_SQLITE_PATH", raising=False)
    monkeypatch.delenv("LOCAL_SQL_CONNECTION_STRING", raising=False)
    path = tmp_path / "sql-cooldown.json"
    monkeypatch.setattr(sql_cooldown, "sql_cooldown_file", lambda: path)
    assert sql_cooldown.sql_cooldown_until() == ""
    assert sql_cooldown.sql_cooldown_fail_count() == 0


def test_sql_cooldown_until_reports_london_date_while_active(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_SQLITE_PATH", raising=False)
    monkeypatch.delenv("LOCAL_SQL_CONNECTION_STRING", raising=False)
    path = tmp_path / "sql-cooldown.json"
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    path.write_text(
        json.dumps({"unavailable_until": until.strftime("%Y-%m-%dT%H:%M:%SZ"), "fail_count": 3}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sql_cooldown, "sql_cooldown_file", lambda: path)
    assert sql_cooldown.sql_cooldown_until() != ""
    assert sql_cooldown.sql_cooldown_fail_count() == 3


def test_sql_cooldown_until_empty_once_window_has_passed(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_SQLITE_PATH", raising=False)
    monkeypatch.delenv("LOCAL_SQL_CONNECTION_STRING", raising=False)
    path = tmp_path / "sql-cooldown.json"
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
    path.write_text(json.dumps({"unavailable_until": past.strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")
    monkeypatch.setattr(sql_cooldown, "sql_cooldown_file", lambda: path)
    assert sql_cooldown.sql_cooldown_until() == ""


def test_sql_cooldown_until_empty_when_local_sqlite_fallback_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(tmp_path / "local.db"))
    monkeypatch.delenv("LOCAL_SQL_CONNECTION_STRING", raising=False)
    path = tmp_path / "sql-cooldown.json"
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    path.write_text(json.dumps({"unavailable_until": until.strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")
    monkeypatch.setattr(sql_cooldown, "sql_cooldown_file", lambda: path)
    assert sql_cooldown.sql_cooldown_until() == ""


def test_sql_cooldown_until_fails_open_on_a_malformed_file(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_SQLITE_PATH", raising=False)
    monkeypatch.delenv("LOCAL_SQL_CONNECTION_STRING", raising=False)
    path = tmp_path / "sql-cooldown.json"
    path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(sql_cooldown, "sql_cooldown_file", lambda: path)
    assert sql_cooldown.sql_cooldown_until() == ""
    assert sql_cooldown.sql_cooldown_fail_count() == 0


def test_sql_cooldown_fail_count_zero_when_file_absent(tmp_path, monkeypatch):
    path = tmp_path / "sql-cooldown.json"
    monkeypatch.setattr(sql_cooldown, "sql_cooldown_file", lambda: path)
    assert sql_cooldown.sql_cooldown_fail_count() == 0


def test_a_timezone_naive_cooldown_never_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_SQLITE_PATH", raising=False)
    monkeypatch.delenv("LOCAL_SQL_CONNECTION_STRING", raising=False)
    path = tmp_path / "sql-cooldown.json"
    naive = (dt.datetime.now() + dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps({"unavailable_until": naive}), encoding="utf-8")
    monkeypatch.setattr(sql_cooldown, "sql_cooldown_file", lambda: path)

    assert sql_cooldown.sql_cooldown_until() == ""
    assert sql_cooldown.is_sql_available() is True
