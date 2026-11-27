from __future__ import annotations

import contextlib
import os
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql
from todos import todo_store
from vergil import client_edits, signin_names


def logins(names: dict[str, str] | None = None) -> dict[str, str]:
    source = signin_names.parse(os.environ.get(signin_names.ENV_NAME, "")) if names is None else names
    return {client_edits.personal_user(email): name for email, name in sorted(source.items()) if "@" in email}


def _resolve(who: str, people: dict[str, str]) -> str:
    wanted = " ".join(str(who or "").split()).lower()
    if not wanted:
        return ""
    hits = sorted({key for key, name in people.items() if key == wanted or name.lower() == wanted})
    return hits[0] if len(hits) == 1 else ""


def _candidates(conn_cursor: Any) -> list[dict[str, Any]]:
    conn_cursor.execute(
        "SELECT todo_id, assignee, created_by FROM client_todos "
        "WHERE owner = '' AND source = 'manual' AND deleted_utc IS NULL ORDER BY created_utc, todo_id"
    )
    return [{"todo_id": r[0], "assignee": r[1], "created_by": r[2]} for r in conn_cursor.fetchall()]


def _plan(rows: list[dict[str, Any]], people: dict[str, str]) -> list[tuple[str, list[str]]]:
    plan = []
    for row in rows:
        owner = _resolve(row["assignee"], people) or _resolve(row["created_by"], people)
        plan.append((row["todo_id"], [owner] if owner else sorted(people)))
    return plan


def _summary(plan: list[tuple[str, list[str]]], people: dict[str, str], automatic: int, *, applied: bool) -> dict[str, Any]:
    by_owner: Counter[str] = Counter()
    for _, owners in plan:
        for owner in owners:
            by_owner[owner] += 1
    own = sum(1 for _, owners in plan if len(owners) == 1)
    return {
        "applied": applied,
        "logins": len(people),
        "tasks_to_move": len(plan),
        "given_to_one_login": own,
        "copied_to_every_login": len(plan) - own,
        "rows_after": sum(len(owners) for _, owners in plan),
        "per_login": dict(sorted(by_owner.items())),
        "automatic_left_alone": automatic,
    }


@contextlib.contextmanager
def _use_db(db_path: str | Path | None):
    key = clientdb_sql._SQLITE_ENV_KEY
    before = os.environ.get(key)
    if db_path:
        os.environ[key] = str(db_path)
    try:
        yield
    finally:
        if db_path:
            if before is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = before


def _automatic(cursor: Any) -> int:
    cursor.execute("SELECT COUNT(*) FROM client_todos WHERE source <> 'manual'")
    return int(cursor.fetchone()[0])


def audit(*, db_path: str | Path | None = None, names: dict[str, str] | None = None) -> dict[str, Any]:
    people = logins(names)
    with _use_db(db_path), clientdb_sql.get_connection() as conn:
        todo_store.ensure_tables(conn)
        cursor = conn.cursor()
        plan = _plan(_candidates(cursor), people) if people else []
        cursor.execute("SELECT COUNT(*) FROM client_todos WHERE migrated_from <> ''")
        moved = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM client_todos WHERE owner = '' AND source = 'manual' AND deleted_utc IS NOT NULL")
        hidden = int(cursor.fetchone()[0])
        automatic = _automatic(cursor)
    return {**_summary(plan, people, automatic, applied=False), "already_moved_rows": moved, "deleted_left_alone": hidden}


def migrate(*, db_path: str | Path | None = None, apply: bool = False, names: dict[str, str] | None = None) -> dict[str, Any]:
    people = logins(names)
    with _use_db(db_path), clientdb_sql.get_connection() as conn:
        todo_store.ensure_tables(conn)
        cursor = conn.cursor()
        plan = _plan(_candidates(cursor), people) if people else []
        automatic = _automatic(cursor)
        if apply:
            columns = [c for c in todo_store._COLUMN_NAMES]
            for todo_id, owners in plan:
                cursor.execute(f"SELECT {', '.join(columns)} FROM client_todos WHERE todo_id = ?", (todo_id,))
                original = dict(zip(columns, cursor.fetchone()))
                cursor.execute("UPDATE client_todos SET owner = ?, migrated_from = ? WHERE todo_id = ?", (owners[0], todo_id, todo_id))
                for owner in owners[1:]:
                    copy = {**original, "todo_id": uuid.uuid4().hex, "owner": owner, "migrated_from": todo_id}
                    cursor.execute(
                        f"INSERT INTO client_todos ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                        tuple(copy[c] for c in columns),
                    )
    return _summary(plan, people, automatic, applied=apply)


def rollback(*, db_path: str | Path | None = None, apply: bool = False) -> dict[str, Any]:
    with _use_db(db_path), clientdb_sql.get_connection() as conn:
        todo_store.ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM client_todos WHERE migrated_from <> '' AND migrated_from <> todo_id")
        copies = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM client_todos WHERE migrated_from = todo_id")
        originals = int(cursor.fetchone()[0])
        if apply:
            cursor.execute("DELETE FROM client_todos WHERE migrated_from <> '' AND migrated_from <> todo_id")
            cursor.execute("UPDATE client_todos SET owner = '', migrated_from = '' WHERE migrated_from = todo_id")
    return {"applied": apply, "copies_removed": copies, "originals_restored": originals}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Personal to-dos: audit (default), migrate or rollback. Dry run unless --apply; use --db on a SQLite copy."
    )
    parser.add_argument("action", nargs="?", default="audit", choices=("audit", "migrate", "rollback"))
    parser.add_argument("--db", default=None, help="a SQLite copy of the task table; defaults to the configured database")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--names", default=None, help="email=Name;email=Name (default: the SIGNIN_NAMES environment variable)")
    args = parser.parse_args()
    given = signin_names.parse(args.names) if args.names is not None else None
    fn = {
        "audit": lambda: audit(db_path=args.db, names=given),
        "migrate": lambda: migrate(db_path=args.db, apply=args.apply, names=given),
        "rollback": lambda: rollback(db_path=args.db, apply=args.apply),
    }[args.action]
    print(json.dumps(fn(), indent=2))
