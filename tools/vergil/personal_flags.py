from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
from vergil import client_edits, signin_names

MIGRATED_BY = "migration: personal flags"
_TAG = "migrated:"


def logins(names: dict[str, str] | None = None) -> list[str]:
    source = signin_names.parse(os.environ.get(signin_names.ENV_NAME, "")) if names is None else names
    return sorted({client_edits.personal_user(email) for email in source if "@" in email})


def _candidates(conn: Any) -> tuple[list[tuple[str, str, str, str]], int]:
    marks = ", ".join("?" for _ in client_edits.PERSONAL_FLAGS)
    rows = conn.execute(
        "SELECT matter_id, flag_name, set_by, set_at, reason FROM matter_flags "
        f"WHERE is_set = 1 AND flag_name IN ({marks})",
        client_edits.PERSONAL_FLAGS,
    ).fetchall()
    move, automatic = [], 0
    for matter, flag, set_by, set_at, reason in rows:
        if reason or str(set_by or "") == _AUTOMATIC:
            automatic += 1
        else:
            move.append((str(matter), str(flag), str(set_by or ""), str(set_at or "")))
    return move, automatic


_AUTOMATIC = "Automatic"


def _summary(move: list[Any], automatic: int, users: list[str], *, applied: bool) -> dict[str, Any]:
    return {
        "applied": applied,
        "logins": users,
        "to_move": len(move),
        "by_flag": dict(sorted(Counter(row[1] for row in move).items())),
        "personal_rows_to_make": len(move) * len(users),
        "stay_shared_automatic": automatic,
    }


def audit(*, db_path: str | Path | None = None, names: dict[str, str] | None = None) -> dict[str, Any]:
    users = logins(names)
    with ops_db.connect(db_path) as conn:
        move, automatic = _candidates(conn)
        personal = conn.execute("SELECT COUNT(*) FROM user_matter_flags").fetchone()[0]
        moved = conn.execute("SELECT COUNT(*) FROM matter_flags WHERE set_by = ?", (MIGRATED_BY,)).fetchone()[0]
    return {**_summary(move if users else [], automatic, users, applied=False), "personal_rows_now": personal, "already_moved": moved}


def migrate(*, db_path: str | Path | None = None, apply: bool = False, names: dict[str, str] | None = None) -> dict[str, Any]:
    users = logins(names)
    with ops_db.connect(db_path) as conn:
        move, automatic = _candidates(conn)
        move = move if users else []
        if apply:
            for matter, flag, set_by, set_at in move:
                made = []
                for user in users:
                    cur = conn.execute(
                        "INSERT INTO user_matter_flags (user_key, matter_id, flag_name, set_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(user_key, matter_id, flag_name) DO NOTHING",
                        (user, matter, flag, set_at or client_edits.utc_now()),
                    )
                    if cur.rowcount:
                        made.append(user)
                conn.execute(
                    "UPDATE matter_flags SET is_set = 0, set_by = ?, reason = ? WHERE matter_id = ? AND flag_name = ?",
                    (MIGRATED_BY, f"{_TAG}{set_by}|{','.join(made)}", matter, flag),
                )
            conn.commit()
    return _summary(move, automatic, users, applied=apply)


def rollback(*, db_path: str | Path | None = None, apply: bool = False) -> dict[str, Any]:
    restored = 0
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT matter_id, flag_name, reason FROM matter_flags WHERE set_by = ? AND reason LIKE ?",
            (MIGRATED_BY, f"{_TAG}%"),
        ).fetchall()
        for matter, flag, reason in rows:
            original, _, made = str(reason)[len(_TAG):].rpartition("|")
            restored += 1
            if apply:
                conn.execute(
                    "UPDATE matter_flags SET is_set = 1, set_by = ?, reason = NULL WHERE matter_id = ? AND flag_name = ?",
                    (original, matter, flag),
                )
                for user in filter(None, made.split(",")):
                    conn.execute("DELETE FROM user_matter_flags WHERE user_key = ? AND matter_id = ? AND flag_name = ?", (user, matter, flag))
        if apply:
            conn.commit()
    return {"applied": apply, "restored": restored}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Personal flags and stars: audit (default), migrate or rollback. Dry run unless --apply; use --db on a copy."
    )
    parser.add_argument("action", nargs="?", default="audit", choices=("audit", "migrate", "rollback"))
    parser.add_argument("--db", default=None, help="an ops database copy; defaults to the live one")
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
