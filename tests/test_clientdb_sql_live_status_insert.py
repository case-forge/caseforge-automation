
import importlib
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"


def _load_clientdb_sql(monkeypatch, db_path: Path):
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db_path))
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import clientdb_sql

    return importlib.reload(clientdb_sql)


def _make_live_shape_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE matter_live_status (
                matter_id INTEGER PRIMARY KEY,
                latest_live_status TEXT,
                order_status TEXT,
                sealed_order_status TEXT,
                service_status TEXT,
                next_hearing_text TEXT,
                awaiting_next_step TEXT,
                last_client_chase TEXT,
                last_material_email_received TEXT,
                last_material_email_subject TEXT,
                status_changed_at TEXT,
                created_utc TEXT NOT NULL,
                updated_utc TEXT NOT NULL,
                draft_order_status TEXT,
                waiting_for_sealed_order INTEGER NOT NULL
            )
            """
        )


def _row(db_path: Path, matter_id: int) -> sqlite3.Row:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM matter_live_status WHERE matter_id = ?", (matter_id,)).fetchone()


def test_insert_with_no_fields_succeeds_and_starts_not_waiting(tmp_path, monkeypatch):
    db_path = tmp_path / "clientdb.sqlite"
    _make_live_shape_db(db_path)
    clientdb_sql = _load_clientdb_sql(monkeypatch, db_path)

    result = clientdb_sql.upsert_matter_live_status(617)

    assert result["action"] == "insert"
    row = _row(db_path, 617)
    assert row["waiting_for_sealed_order"] == 0
    assert row["created_utc"] and row["updated_utc"]


def test_insert_with_an_order_status_keeps_it(tmp_path, monkeypatch):
    db_path = tmp_path / "clientdb.sqlite"
    _make_live_shape_db(db_path)
    clientdb_sql = _load_clientdb_sql(monkeypatch, db_path)

    clientdb_sql.upsert_matter_live_status(612, order_status="NMO")

    row = _row(db_path, 612)
    assert row["order_status"] == "NMO"
    assert row["waiting_for_sealed_order"] == 0


def test_supplied_waiting_flag_is_stored_as_a_boolean(tmp_path, monkeypatch):
    db_path = tmp_path / "clientdb.sqlite"
    _make_live_shape_db(db_path)
    clientdb_sql = _load_clientdb_sql(monkeypatch, db_path)

    clientdb_sql.upsert_matter_live_status(1, waiting_for_sealed_order=1)
    clientdb_sql.upsert_matter_live_status(2, waiting_for_sealed_order="0")
    clientdb_sql.upsert_matter_live_status(3, waiting_for_sealed_order="true")

    assert [_row(db_path, m)["waiting_for_sealed_order"] for m in (1, 2, 3)] == [1, 0, 1]


def test_updating_an_existing_row_does_not_reset_the_waiting_flag(tmp_path, monkeypatch):
    db_path = tmp_path / "clientdb.sqlite"
    _make_live_shape_db(db_path)
    clientdb_sql = _load_clientdb_sql(monkeypatch, db_path)

    clientdb_sql.upsert_matter_live_status(5, waiting_for_sealed_order=True)
    result = clientdb_sql.upsert_matter_live_status(5, order_status="FOA")

    assert result["action"] == "update"
    row = _row(db_path, 5)
    assert row["waiting_for_sealed_order"] == 1
    assert row["order_status"] == "FOA"
