import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"


def _load_clientdb_sql(monkeypatch, db_path: Path):
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db_path))
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import clientdb_sql

    return importlib.reload(clientdb_sql)


def _empty_db(db_path: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


def test_query_budget_trips_past_the_limit(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "budget.sqlite"
    _empty_db(db_path)
    monkeypatch.setenv("CASEFORGE_SQL_QUERY_BUDGET", "5")
    clientdb_sql = _load_clientdb_sql(monkeypatch, db_path)

    with pytest.raises(RuntimeError, match="query budget exceeded"):
        with clientdb_sql.get_connection() as conn:
            for _ in range(10):
                conn.execute("SELECT 1")


def test_query_budget_allows_normal_usage_under_the_limit(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "budget.sqlite"
    _empty_db(db_path)
    monkeypatch.setenv("CASEFORGE_SQL_QUERY_BUDGET", "50")
    clientdb_sql = _load_clientdb_sql(monkeypatch, db_path)

    with clientdb_sql.get_connection() as conn:
        for _ in range(10):
            conn.execute("SELECT 1")


def test_query_budget_resets_between_separate_connections(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "budget.sqlite"
    _empty_db(db_path)
    monkeypatch.setenv("CASEFORGE_SQL_QUERY_BUDGET", "5")
    clientdb_sql = _load_clientdb_sql(monkeypatch, db_path)

    with clientdb_sql.get_connection() as conn:
        for _ in range(5):
            conn.execute("SELECT 1")

    with clientdb_sql.get_connection() as conn:
        conn.execute("SELECT 1")
