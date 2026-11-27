from __future__ import annotations

import pytest

import clientdb_sql


@pytest.fixture(autouse=True)
def _sqlite_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(tmp_path / "instance-control-test.sqlite"))
    monkeypatch.delenv("LOCAL_SQL_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_SQL_CONNECTION_STRING", raising=False)


def _assign(job_name: str, hostname: str) -> None:
    with clientdb_sql.get_connection() as conn:
        clientdb_sql._ensure_instance_control_table(conn)
        conn.execute(
            "INSERT INTO instance_control (job_name, active_hostname, updated_by, updated_utc) "
            "VALUES (?, ?, 'test', '2026-01-01T00:00:00Z')",
            (job_name, hostname),
        )


def test_is_active_host_false_when_no_row_exists():
    assert clientdb_sql.is_active_host("startup-monitor") is False


def test_is_active_host_true_for_assigned_host_false_for_other(monkeypatch):
    monkeypatch.setattr(clientdb_sql.socket, "gethostname", lambda: "prod-1")
    _assign("startup-monitor", "prod-1")
    assert clientdb_sql.is_active_host("startup-monitor") is True

    monkeypatch.setattr(clientdb_sql.socket, "gethostname", lambda: "caseforge-automation-hetzner")
    assert clientdb_sql.is_active_host("startup-monitor") is False


def test_is_active_host_case_insensitive_hostname_match(monkeypatch):
    monkeypatch.setattr(clientdb_sql.socket, "gethostname", lambda: "prod-1")
    _assign("startup-monitor", "prod-1")

    monkeypatch.setattr(clientdb_sql.socket, "gethostname", lambda: "PROD-1")
    assert clientdb_sql.is_active_host("startup-monitor") is True


def test_is_active_host_prefers_val_instance_hostname_env_override(monkeypatch):
    monkeypatch.setattr(clientdb_sql.socket, "gethostname", lambda: "0a28b4ae7592")
    _assign("scanned-docs-monitor", "prod-1")

    assert clientdb_sql.is_active_host("scanned-docs-monitor") is False

    monkeypatch.setenv("CASEFORGE_INSTANCE_HOSTNAME", "prod-1")
    assert clientdb_sql.is_active_host("scanned-docs-monitor") is True


def test_is_active_host_fails_closed_on_error(monkeypatch):
    def _boom():
        raise RuntimeError("Azure SQL unreachable")

    monkeypatch.setattr(clientdb_sql, "get_connection", _boom)
    assert clientdb_sql.is_active_host("startup-monitor") is False


def test_is_active_host_caches_the_db_read_within_ttl(monkeypatch):
    monkeypatch.setattr(clientdb_sql.socket, "gethostname", lambda: "prod-1")
    _assign("startup-monitor", "prod-1")

    from contextlib import contextmanager

    real_get_connection = clientdb_sql.get_connection
    call_count = {"n": 0}

    @contextmanager
    def counting_get_connection():
        call_count["n"] += 1
        with real_get_connection() as conn:
            yield conn

    monkeypatch.setattr(clientdb_sql, "get_connection", counting_get_connection)
    assert clientdb_sql.is_active_host("startup-monitor") is True
    assert clientdb_sql.is_active_host("startup-monitor") is True
    assert call_count["n"] == 1


def test_list_instance_control_returns_all_rows_sorted_by_job_name():
    _assign("hub-api", "prod-2")
    _assign("graph-index-refresh", "prod-1")
    rows = clientdb_sql.list_instance_control()
    assert [r["job_name"] for r in rows] == ["graph-index-refresh", "hub-api"]
