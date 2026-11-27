
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import clientdb_sql as vs




def test_get_connection_falls_back_to_local_sql_server_when_unconfigured(monkeypatch):
    monkeypatch.setattr(vs, "_sqlite_path", lambda: "")
    monkeypatch.setattr(vs, "_pg_url", lambda: "")
    monkeypatch.setattr(vs, "_require_pyodbc", lambda: None)
    monkeypatch.setattr(vs, "_connection_string", lambda: "fake-conn-string")
    monkeypatch.setattr(vs, "_record_sql_probe", lambda *a, **k: None)

    seen_kwargs = {}

    class _FakeConn:
        def commit(self):
            pass

        def close(self):
            pass

    def fake_connect(conn_str, timeout=None):
        seen_kwargs["conn_str"] = conn_str
        seen_kwargs["timeout"] = timeout
        return _FakeConn()

    monkeypatch.setattr(vs, "pyodbc", SimpleNamespace(connect=fake_connect), raising=False)

    with vs.get_connection():
        pass

    assert seen_kwargs["conn_str"] == "fake-conn-string"
    assert seen_kwargs["timeout"] == vs._LOCAL_SQL_CONNECT_TIMEOUT_SECONDS


def test_get_connection_makes_one_attempt_and_raises_on_failure(monkeypatch):
    monkeypatch.setattr(vs, "_sqlite_path", lambda: "")
    monkeypatch.setattr(vs, "_pg_url", lambda: "")
    monkeypatch.setattr(vs, "_require_pyodbc", lambda: None)
    monkeypatch.setattr(vs, "_connection_string", lambda: "fake-conn-string")
    monkeypatch.setattr(vs, "_record_sql_probe", lambda *a, **k: None)

    attempts = {"n": 0}

    def always_fails(conn_str, timeout=None):
        attempts["n"] += 1
        raise RuntimeError("connection refused")

    monkeypatch.setattr(vs, "pyodbc", SimpleNamespace(connect=always_fails), raising=False)

    import pytest
    with pytest.raises(RuntimeError):
        with vs.get_connection():
            pass

    assert attempts["n"] == 1


def test_require_pyodbc_raises_a_clear_error_when_unavailable(monkeypatch):
    monkeypatch.setattr(vs, "_sqlite_path", lambda: "")
    monkeypatch.setattr(vs, "_PYODBC_AVAILABLE", False)

    import pytest
    with pytest.raises(RuntimeError, match="pyodbc is not installed"):
        vs._require_pyodbc()


def test_require_pyodbc_is_a_no_op_in_sqlite_mode(monkeypatch):
    monkeypatch.setattr(vs, "_sqlite_path", lambda: "/tmp/whatever.sqlite")
    monkeypatch.setattr(vs, "_PYODBC_AVAILABLE", False)

    vs._require_pyodbc()


def test_require_pyodbc_is_a_no_op_in_postgres_mode(monkeypatch):
    monkeypatch.setattr(vs, "_sqlite_path", lambda: "")
    monkeypatch.setattr(vs, "_pg_url", lambda: "postgresql://user:pass@host/db")
    monkeypatch.setattr(vs, "_PYODBC_AVAILABLE", False)

    vs._require_pyodbc()




def test_pg_translator_covers_the_codebase_tsql_subset():
    t = vs._translate_tsql_pg
    assert t("SELECT TOP 5 * FROM [people] WHERE name = ?") == 'SELECT * FROM "people" WHERE name = %s\nLIMIT 5'
    assert t("SELECT GETUTCDATE()") == "SELECT (now() at time zone 'utc')"
    assert t("SELECT ISNULL(a, ?) FROM dbo.matters") == "SELECT COALESCE(a, %s) FROM matters"
    assert t("WHERE n LIKE '%[0-9]%'") == "WHERE n ILIKE '%%[0-9]%%'"
    assert t("WHERE a = '?'") == "WHERE a = '?'"


def test_pg_translator_relocates_a_top_nested_inside_a_subquery():
    sql = (
        "SELECT DISTINCT TOP (8) m.matter_id, "
        "(SELECT TOP (1) mr.ref_value FROM matter_references mr "
        "WHERE mr.matter_id = m.matter_id ORDER BY mr.reference_id) AS case_reference "
        "FROM matters m ORDER BY m.matter_id"
    )
    out = vs._translate_tsql_pg(sql)
    assert out == (
        "SELECT DISTINCT m.matter_id, "
        "(SELECT mr.ref_value FROM matter_references mr "
        "WHERE mr.matter_id = m.matter_id ORDER BY mr.reference_id\n"
        "LIMIT 1) AS case_reference "
        "FROM matters m ORDER BY m.matter_id\n"
        "LIMIT 8"
    )


def test_pg_translator_makes_like_case_insensitive():
    t = vs._translate_tsql_pg
    assert t("WHERE p.canonical_name LIKE ?") == "WHERE p.canonical_name ILIKE %s"
    assert t("WHERE p.canonical_name NOT LIKE ?") == "WHERE p.canonical_name NOT ILIKE %s"
    assert t("where n like ?") == "where n ILIKE %s"


def test_cursors_accept_pyodbc_varargs_and_dbapi_sequences():
    n = vs._normalise_params
    assert n(("Rosa Gannettest",)) == ("Rosa Gannettest",)
    assert n(("a", "b", 3)) == ("a", "b", 3)
    assert n((("a", "b"),)) == ("a", "b")
    assert n((["a", "b"],)) == ("a", "b")
    assert n(()) == ()


def test_pg_translator_converts_output_inserted_to_returning():
    t = vs._translate_tsql_pg
    assert t(
        "INSERT INTO people (a) OUTPUT INSERTED.person_id VALUES (?)"
    ) == "INSERT INTO people (a) VALUES (%s) RETURNING person_id"
    assert t(
        "insert into m (a) output inserted.matter_id values (?)"
    ) == "insert into m (a) values (%s) RETURNING matter_id"


def test_pg_translator_leaves_unrelated_output_words_alone():
    t = vs._translate_tsql_pg
    assert t("SELECT output FROM jobs") == "SELECT output FROM jobs"
    assert t("SELECT a FROM t WHERE note = 'output inserted.x'") == \
        "SELECT a FROM t WHERE note = 'output inserted.x'"


def test_pg_translator_leaves_like_inside_string_literals_alone():
    t = vs._translate_tsql_pg
    assert t("WHERE note = 'would like a callback'") == "WHERE note = 'would like a callback'"
    assert t("SELECT likelihood FROM m") == "SELECT likelihood FROM m"
    assert t("WHERE n ILIKE ?") == "WHERE n ILIKE %s"


def test_search_clients_pg_query_has_no_parameterised_top():
    import inspect

    src = inspect.getsource(vs._search_clients)
    assert "TOP (?)" not in src
    assert "TOP ({top})" in src


def test_pg_url_returns_the_configured_dsn(monkeypatch):
    monkeypatch.setenv(vs._PG_URL_ENV, "postgresql://u:p@h/db")
    assert vs._pg_url() == "postgresql://u:p@h/db"


def test_pg_url_empty_when_unset(monkeypatch):
    monkeypatch.delenv(vs._PG_URL_ENV, raising=False)
    assert vs._pg_url() == ""


def test_pg_url_falls_back_to_secrets_file_on_cold_miss(monkeypatch):
    monkeypatch.delenv(vs._PG_URL_ENV, raising=False)
    calls = []

    def fake_load_repo_secrets(*, required_keys):
        calls.append(required_keys)
        monkeypatch.setenv(vs._PG_URL_ENV, "postgresql://from-file@h/db")

    monkeypatch.setattr("env_bootstrap.load_repo_secrets", fake_load_repo_secrets)
    assert vs._pg_url() == "postgresql://from-file@h/db"
    assert calls == [(vs._PG_URL_ENV,)]


def test_pg_url_does_not_call_fallback_when_already_set(monkeypatch):
    monkeypatch.setenv(vs._PG_URL_ENV, "postgresql://already-set@h/db")
    calls = []
    monkeypatch.setattr(
        "env_bootstrap.load_repo_secrets",
        lambda **kwargs: calls.append(kwargs) or (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    assert vs._pg_url() == "postgresql://already-set@h/db"
    assert calls == []


def test_get_connection_resolves_postgres_on_the_first_call_not_the_second(monkeypatch):
    monkeypatch.setattr(vs, "_sqlite_path", lambda: "")
    monkeypatch.delenv(vs._PG_URL_ENV, raising=False)

    def fake_load_repo_secrets(*, required_keys):
        monkeypatch.setenv(vs._PG_URL_ENV, "postgresql://u:p@h/db")

    monkeypatch.setattr("env_bootstrap.load_repo_secrets", fake_load_repo_secrets)

    calls = []
    monkeypatch.setattr(vs, "_pg_get_connection", lambda: calls.append("postgres") or _noop_ctx())
    monkeypatch.setattr(vs, "_require_pyodbc", lambda: (_ for _ in ()).throw(AssertionError("must not reach local SQL Server path")))

    with vs.get_connection():
        pass
    assert calls == ["postgres"]


@contextmanager
def _noop_ctx():
    yield object()


def test_get_connection_uses_postgres_when_configured(monkeypatch):
    monkeypatch.setattr(vs, "_sqlite_path", lambda: "")
    monkeypatch.setenv(vs._PG_URL_ENV, "postgresql://u:p@h/db")
    sentinel = object()

    from contextlib import contextmanager

    @contextmanager
    def fake_pg():
        yield sentinel

    monkeypatch.setattr(vs, "_pg_get_connection", fake_pg)
    with vs.get_connection() as conn:
        assert conn is sentinel


def test_pgconn_execute_matches_sqliteconn_convenience_method(monkeypatch):
    class FakeCursor:
        description = [("matter_id",)]
        def execute(self, sql, params=None):
            self.description = [("matter_id",)]
            return self
        def fetchall(self):
            return [("42",)]

    class FakeRawConn:
        def cursor(self, cursor_factory=None):
            return FakeCursor()

    monkeypatch.setitem(sys.modules, "psycopg2.extras", type(sys)("psycopg2.extras"))
    sys.modules["psycopg2.extras"].NamedTupleCursor = object()

    conn = vs._PgConn(FakeRawConn())
    cur = conn.execute("SELECT matter_id FROM matters")
    assert cur.fetchall() == [("42",)]
