#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

LOG_TABLE = "clientdb_change_log"
LOG_COLUMNS = ("id", "at", "table_name", "op", "pk", "old_row", "new_row", "changed_columns", "actor", "app", "txid")
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ChangeLogError(RuntimeError):
    pass


def _ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ChangeLogError(f"refusing an unexpected identifier {name!r}")
    return f'"{name}"'


def _pk_key(table: str, pk: dict) -> tuple:
    return (table, json.dumps(pk, sort_keys=True, default=str))



@dataclass
class Step:

    entry_id: int
    table: str
    pk: dict
    action: str
    columns: list[str] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def describe(self) -> str:
        key = ", ".join(f"{k}={v}" for k, v in sorted(self.pk.items())) if self.pk else "no key"
        head = f"#{self.entry_id} {self.table} ({key})"
        if self.action == "update":
            return f"{head}: restore {len(self.columns)} column(s): {', '.join(self.columns)}"
        if self.action == "insert":
            return f"{head}: re-insert the deleted row ({len(self.columns)} columns)"
        if self.action == "delete":
            return f"{head}: delete the inserted row"
        if self.action == "noop":
            return f"{head}: nothing to do, {self.reason}"
        return f"{head}: REFUSED, {self.reason}"


def _matches(current: dict, expected: dict, columns: Iterable[str] | None = None) -> bool:
    keys = list(columns) if columns is not None else list(expected)
    return all(current.get(k) == expected.get(k) for k in keys)


def plan_step(entry: dict, current: dict | None, *, force: bool = False, live_columns: Iterable[str] | None = None) -> Step:
    table, op, pk = entry["table_name"], entry["op"], entry.get("pk") or {}
    old, new = entry.get("old_row") or {}, entry.get("new_row") or {}
    step = Step(entry_id=int(entry["id"]), table=table, pk=dict(pk), action="refuse")
    keep = set(live_columns) if live_columns is not None else None

    def _cols(row: dict) -> list[str]:
        return [c for c in row if keep is None or c in keep]

    if not pk:
        step.reason = "the table has no primary key, so the row cannot be found again"
        return step
    if op == "INSERT":
        if current is None:
            step.action, step.reason = "noop", "the inserted row is already gone"
        elif _matches(current, new) or force:
            step.action = "delete"
        else:
            step.reason = "the row has changed since it was inserted (use --force to delete it anyway)"
        return step
    if op == "UPDATE":
        changed = list(entry.get("changed_columns") or [c for c in new if new.get(c) != old.get(c)])
        changed = [c for c in changed if keep is None or c in keep]
        if current is None:
            if force:
                step.action, step.columns = "insert", _cols(old)
                step.values = {c: old.get(c) for c in step.columns}
            else:
                step.reason = "the row has been deleted since (use --force to re-insert its old version)"
            return step
        if _matches(current, old, changed):
            step.action, step.reason = "noop", "the row already holds the old values"
        elif _matches(current, new) or force:
            step.action, step.columns = "update", changed
            step.values = {c: old.get(c) for c in changed}
        else:
            step.reason = "the row has changed since (use --force to restore the old values anyway)"
        return step
    if op == "DELETE":
        if current is None:
            step.action, step.columns = "insert", _cols(old)
            step.values = {c: old.get(c) for c in step.columns}
        elif _matches(current, old):
            step.action, step.reason = "noop", "the row is already back"
        elif force:
            step.action = "update"
            step.columns = [c for c in _cols(old) if c not in pk]
            step.values = {c: old.get(c) for c in step.columns}
        else:
            step.reason = "a row with that key exists again (use --force to overwrite it with the deleted version)"
        return step
    step.reason = f"unknown op {op!r}"
    return step


def apply_to_row(step: Step, current: dict | None) -> dict | None:
    if step.action == "delete":
        return None
    if step.action == "insert":
        return dict(step.values)
    if step.action == "update":
        return {**(current or {}), **step.values}
    return current


def plan_revert(entries: list[dict], store: "Store", *, force: bool = False) -> list[Step]:
    rows: dict[tuple, dict | None] = {}
    steps: list[Step] = []
    columns: dict[str, list[str]] = {}
    for entry in sorted(entries, key=lambda e: int(e["id"]), reverse=True):
        table, pk = entry["table_name"], entry.get("pk") or {}
        _ident(table)
        if table not in columns:
            columns[table] = store.table_columns(table)
        key = _pk_key(table, pk)
        if pk and key not in rows:
            rows[key] = store.current_row(table, pk)
        step = plan_step(entry, rows.get(key), force=force, live_columns=columns[table] or None)
        if pk:
            rows[key] = apply_to_row(step, rows.get(key))
        steps.append(step)
    return steps



def _pk_match(table: str, pk: dict) -> tuple[str, str]:
    cols = [_ident(c) for c in sorted(pk)]
    t = _ident(table)
    clause = (
        f"({', '.join('t.' + c for c in cols)}) = "
        f"(SELECT {', '.join('r.' + c for c in cols)} FROM jsonb_populate_record(NULL::{t}, ?::jsonb) AS r)"
    )
    return clause, json.dumps(pk, default=str)


def step_sql(step: Step) -> tuple[str, tuple]:
    t = _ident(step.table)
    if step.action == "delete":
        where, key = _pk_match(step.table, step.pk)
        return f"DELETE FROM {t} AS t WHERE {where}", (key,)
    payload = json.dumps(step.values, default=str)
    cols = [_ident(c) for c in step.columns]
    if step.action == "insert":
        return (
            f"INSERT INTO {t} ({', '.join(cols)}) "
            f"SELECT {', '.join('r.' + c for c in cols)} FROM jsonb_populate_record(NULL::{t}, ?::jsonb) AS r",
            (payload,),
        )
    if step.action == "update":
        where, key = _pk_match(step.table, step.pk)
        return (
            f"UPDATE {t} AS t SET ({', '.join(cols)}) = "
            f"(SELECT {', '.join('r.' + c for c in cols)} FROM jsonb_populate_record(NULL::{t}, ?::jsonb) AS r) "
            f"WHERE {where}",
            (payload, key),
        )
    raise ChangeLogError(f"step {step.action!r} writes nothing")


def _as_dict(row: Any, cursor: Any) -> dict:
    if hasattr(row, "_asdict"):
        return dict(row._asdict())
    return dict(zip([d[0] for d in cursor.description], row))


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


class Store:

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return [_as_dict(r, cur) for r in cur.fetchall()]

    def entries(self, where: str, params: tuple, limit: int, order: str = "DESC") -> list[dict]:
        rows = self._all(
            f"SELECT {', '.join(LOG_COLUMNS)} FROM {LOG_TABLE} WHERE {where} ORDER BY id {order} LIMIT {int(limit)}",
            params,
        )
        for r in rows:
            for k in ("pk", "old_row", "new_row"):
                r[k] = _json(r.get(k))
        return rows

    def table_columns(self, table: str) -> list[str]:
        return [
            r["column_name"]
            for r in self._all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ? ORDER BY ordinal_position",
                (table,),
            )
        ]

    def current_row(self, table: str, pk: dict) -> dict | None:
        where, key = _pk_match(table, pk)
        rows = self._all(f"SELECT to_jsonb(t) AS row FROM {_ident(table)} AS t WHERE {where}", (key,))
        return _json(rows[0]["row"]) if rows else None

    def apply(self, step: Step) -> None:
        sql, params = step_sql(step)
        self.conn.cursor().execute(sql, params)



OPS_LOG_TABLE = "ops_change_log"
_BLOB = "$blob"


def _from_json(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {_BLOB}:
        return bytes.fromhex(str(value[_BLOB]))
    return value


def _to_json(value: Any) -> Any:
    return {_BLOB: bytes(value).hex().upper()} if isinstance(value, (bytes, bytearray, memoryview)) else value


def ops_step_sql(step: Step) -> tuple[str, tuple]:
    t = _ident(step.table)
    where = " AND ".join(f"{_ident(c)} = ?" for c in sorted(step.pk))
    key = tuple(_from_json(step.pk[c]) for c in sorted(step.pk))
    if step.action == "delete":
        return f"DELETE FROM {t} WHERE {where}", key
    cols = [_ident(c) for c in step.columns]
    vals = tuple(_from_json(step.values.get(c)) for c in step.columns)
    if step.action == "insert":
        return f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", vals
    if step.action == "update":
        return f"UPDATE {t} SET {', '.join(c + ' = ?' for c in cols)} WHERE {where}", vals + key
    raise ChangeLogError(f"step {step.action!r} writes nothing")


class OpsStore:

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def entries(self, where: str, params: tuple, limit: int, order: str = "DESC") -> list[dict]:
        cur = self.conn.execute(
            "SELECT l.id, l.at, l.table_name, l.op, l.pk, l.old_row, l.new_row, l.changed_columns, "
            "a.actor, a.app, a.conn_id AS conn "
            f"FROM {OPS_LOG_TABLE} AS l LEFT JOIN ops_change_log_actor AS a ON a.log_id = l.id "
            f"WHERE {where} ORDER BY l.id {order} LIMIT {int(limit)}",
            params,
        )
        rows = [_as_dict(r, cur) for r in cur.fetchall()]
        for r in rows:
            for k in ("pk", "old_row", "new_row", "changed_columns"):
                r[k] = _json(r.get(k))
            r["txid"] = None
        return rows

    def table_columns(self, table: str) -> list[str]:
        return [str(r[1]) for r in self.conn.execute(f"PRAGMA table_info({_ident(table)})").fetchall()]

    def current_row(self, table: str, pk: dict) -> dict | None:
        where = " AND ".join(f"{_ident(c)} = ?" for c in sorted(pk))
        cur = self.conn.execute(
            f"SELECT * FROM {_ident(table)} WHERE {where}", tuple(_from_json(pk[c]) for c in sorted(pk))
        )
        row = cur.fetchone()
        return {k: _to_json(v) for k, v in _as_dict(row, cur).items()} if row is not None else None

    def apply(self, step: Step) -> None:
        sql, params = ops_step_sql(step)
        self.conn.execute(sql, params)


def _ops_filters(args: argparse.Namespace) -> tuple[str, tuple]:
    clauses, params = ["1 = 1"], []
    if getattr(args, "txid", None) is not None:
        raise ChangeLogError("the ops log has no transaction id; use --conn (one connection's writes)")
    if args.id is not None:
        clauses.append("l.id = ?")
        params.append(args.id)
    if getattr(args, "table", None):
        _ident(args.table)
        clauses.append("l.table_name = ?")
        params.append(args.table)
    if getattr(args, "conn", None):
        clauses.append("a.conn_id = ?")
        params.append(args.conn)
    if getattr(args, "since", None):
        try:
            dt.date.fromisoformat(args.since[:10])
        except ValueError as exc:
            raise ChangeLogError("--since takes an ISO date or timestamp, e.g. 2026-10-16") from exc
        clauses.append("l.at >= ?")
        params.append(args.since)
    if getattr(args, "pk", None):
        try:
            pk = json.loads(args.pk)
        except ValueError:
            pk = None
        if isinstance(pk, dict):
            for k, v in sorted(pk.items()):
                clauses.append("json_extract(l.pk, ?) = ?")
                params.extend([f'$."{k}"', v])
        else:
            clauses.append("EXISTS (SELECT 1 FROM json_each(l.pk) AS k WHERE CAST(k.value AS TEXT) = ?)")
            params.append(str(args.pk))
    return " AND ".join(clauses), tuple(params)


def _ops_db():
    import ops_db

    return ops_db



def _show_filters(args: argparse.Namespace) -> tuple[str, tuple]:
    clauses, params = ["TRUE"], []
    if args.id is not None:
        clauses.append("id = ?")
        params.append(args.id)
    if args.table:
        _ident(args.table)
        clauses.append("table_name = ?")
        params.append(args.table)
    if args.txid is not None:
        clauses.append("txid = ?")
        params.append(args.txid)
    if args.since:
        try:
            dt.date.fromisoformat(args.since[:10])
        except ValueError as exc:
            raise ChangeLogError("--since takes an ISO date or timestamp, e.g. 2026-10-16") from exc
        clauses.append("at >= ?::timestamptz")
        params.append(args.since)
    if args.pk:
        try:
            pk = json.loads(args.pk)
        except ValueError:
            pk = None
        if isinstance(pk, dict):
            clauses.append("pk @> ?::jsonb")
            params.append(json.dumps(pk))
        else:
            clauses.append("EXISTS (SELECT 1 FROM jsonb_each_text(pk) AS k WHERE k.value = ?)")
            params.append(str(args.pk))
    return " AND ".join(clauses), tuple(params)


def format_entry(e: dict) -> str:
    key = ", ".join(f"{k}={v}" for k, v in sorted((e.get("pk") or {}).items())) or "no key"
    at = e["at"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(e.get("at"), "strftime") else str(e.get("at"))
    cols = e.get("changed_columns") or []
    what = f" [{', '.join(cols)}]" if cols else ""
    tx = f"txid {e['txid']}" if e.get("txid") is not None else f"conn {e.get('conn') or '?'}"
    return f"#{e['id']} {at} {tx} {e['op']} {e['table_name']} ({key}){what} by {e.get('actor') or '?'} via {e.get('app') or '?'}"


def format_values(e: dict) -> list[str]:
    old, new = e.get("old_row") or {}, e.get("new_row") or {}
    cols = e.get("changed_columns") or sorted(set(old) | set(new))
    return [f"  {c}: {json.dumps(old.get(c), default=str)} -> {json.dumps(new.get(c), default=str)}" for c in cols]


def _connect():
    import clientdb_sql

    if clientdb_sql.configured_backend() != "postgres":
        raise ChangeLogError("the change log lives in caseforge-clientdb (Postgres); CASEFORGE_CLIENTDB_PG_URL is not configured")
    return clientdb_sql


def cmd_show(args: argparse.Namespace) -> int:
    if args.db == "ops":
        where, params = _ops_filters(args)
        with _ops_db().connect(args.ops_path or None) as conn:
            entries = OpsStore(conn).entries(where, params, args.limit)
    else:
        if args.conn:
            raise ChangeLogError("--conn is for --db ops; caseforge-clientdb entries carry a --txid")
        clientdb_sql = _connect()
        where, params = _show_filters(args)
        with clientdb_sql.get_connection() as conn:
            entries = Store(conn).entries(where, params, args.limit)
    for e in entries:
        print(format_entry(e))
        if args.values and args.id is not None:
            print("\n".join(format_values(e)))
    if args.values and args.id is None:
        print("(values print only for a single entry: add --id N)")
    if not entries:
        print("no matching entries")
    return 0


def _run_revert(store: Any, entries: list[dict], target: str, args: argparse.Namespace, apply: bool) -> tuple[int, int]:
    if not entries:
        print(f"no change-log entry for {target}")
        return 1, 0
    steps = plan_revert(entries, store, force=args.force)
    for s in steps:
        print(("" if apply else "would: ") + s.describe())
    refused = [s for s in steps if s.action == "refuse"]
    if refused:
        print(f"{len(refused)} of {len(steps)} refused; nothing written")
        return 2, 0
    writes = [s for s in steps if s.action not in ("noop", "refuse")]
    if not apply:
        print(f"dry run: {len(writes)} write(s) planned; add --apply to make them")
        return 0, 0
    for s in writes:
        store.apply(s)
    return 0, len(writes)


def cmd_revert(args: argparse.Namespace) -> int:
    apply = bool(args.apply) and not args.dry_run
    who = getpass.getuser()
    if args.db == "ops":
        if args.txid is not None:
            raise ChangeLogError("the ops log has no transaction id; use --conn (one connection's writes)")
        ops_db = _ops_db()
        target = f"#{args.id}" if args.id is not None else f"conn {args.conn}"
        with ops_db.acting_as(f"change_log revert of {target} by {who}"):
            with ops_db.connect(args.ops_path or None) as conn:
                store = OpsStore(conn)
                if args.id is not None:
                    entries = store.entries("l.id = ?", (args.id,), 1)
                else:
                    entries = store.entries("a.conn_id = ?", (args.conn,), 10_000)
                code, made = _run_revert(store, entries, target, args, apply)
        log = OPS_LOG_TABLE
    else:
        if args.conn:
            raise ChangeLogError("--conn is for --db ops; caseforge-clientdb entries carry a --txid")
        clientdb_sql = _connect()
        target = f"#{args.id}" if args.id is not None else f"txid {args.txid}"
        with clientdb_sql.acting_as(f"change_log revert of {target} by {who}"):
            with clientdb_sql.get_connection() as conn:
                store = Store(conn)
                if args.id is not None:
                    entries = store.entries("id = ?", (args.id,), 1)
                else:
                    entries = store.entries("txid = ?", (args.txid,), 10_000)
                code, made = _run_revert(store, entries, target, args, apply)
        log = LOG_TABLE
    if code or not apply:
        return code
    print(f"reverted: {made} write(s), each logged in {log}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Show and revert caseforge-clientdb or ops-database change-log entries.")
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", choices=("clientdb", "ops"), default="clientdb",
                        help="clientdb (Postgres, the default) or ops (the SQLite ops database)")
    common.add_argument("--ops-path", help="with --db ops: the database file (default: ops_db's own resolution)")
    show = sub.add_parser("show", help="list entries, newest first", parents=[common])
    show.add_argument("--id", type=int)
    show.add_argument("--table")
    show.add_argument("--pk", help='key value (e.g. 435) or JSON (e.g. \'{"matter_id": 435}\')')
    show.add_argument("--since", help="ISO date or timestamp")
    show.add_argument("--txid", type=int)
    show.add_argument("--conn", help="with --db ops: one connection's entries")
    show.add_argument("--limit", type=int, default=20)
    show.add_argument("--values", action="store_true", help="with --id: print old and new values of the changed columns")
    rev = sub.add_parser("revert", help="undo one entry or one transaction (dry run unless --apply)", parents=[common])
    target = rev.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", type=int)
    target.add_argument("--txid", type=int)
    target.add_argument("--conn", help="with --db ops: every entry one connection wrote, newest first")
    rev.add_argument("--apply", action="store_true", help="make the writes (default is a dry run)")
    rev.add_argument("--dry-run", action="store_true", help="say what would happen and write nothing (the default)")
    rev.add_argument("--force", action="store_true", help="revert even where the row has changed since")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cmd_show(args) if args.cmd == "show" else cmd_revert(args)
    except ChangeLogError as exc:
        print(f"change_log: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
