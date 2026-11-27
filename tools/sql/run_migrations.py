#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS _migrations (
    migration_id   TEXT        NOT NULL PRIMARY KEY,
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc'),
    applied_by     TEXT        NULL
)
"""


def _get_conn_str() -> str:
    if os.getenv("LOCAL_SQLITE_PATH", "").strip():
        return os.getenv("LOCAL_SQLITE_PATH", "").strip()
    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from env_config import get as caseforge_env_get

    conn = (
        caseforge_env_get("CASEFORGE_CLIENTDB_PG_URL")
        or caseforge_env_get("LOCAL_SQL_CONNECTION_STRING")
    )
    if not conn:
        sys.exit(
            "[run_migrations] ERROR: No SQL connection configured.\n"
            "  SQLite:      export LOCAL_SQLITE_PATH='clients/caseforge-clientdb.sqlite'\n"
            "  Postgres:    eval \"$(python tools/load_kv_secrets.py --shell)\"\n"
            "               (sets CASEFORGE_CLIENTDB_PG_URL)\n"
            "  Local Docker SQL Server (dev/test dialect only): export LOCAL_SQL_CONNECTION_STRING='...'\n"
            "  (env_config also checks .secrets/caseforge-env automatically)"
        )
    return conn


def _get_connection():
    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from clientdb_sql import get_connection

    return get_connection()


def _split_batches(sql: str) -> list[str]:
    batches = re.split(r"^\s*GO\s*$", sql, flags=re.IGNORECASE | re.MULTILINE)
    result = []
    for b in batches:
        stripped = b.strip()
        if not stripped:
            continue
        has_sql = any(
            line.strip() and not line.strip().startswith("--")
            for line in stripped.splitlines()
        )
        if has_sql:
            result.append(stripped)
    return result


class LedgerUnreadable(RuntimeError):
    pass


def _applied_migrations(cursor) -> set[str]:
    try:
        cursor.execute("SELECT migration_id FROM dbo._migrations")
        return {row[0] for row in cursor.fetchall()}
    except Exception as exc:
        raise LedgerUnreadable(f"could not read the _migrations ledger, so nothing was run: {exc}") from exc


def run_status() -> None:
    _get_conn_str()
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("[run_migrations] No migration files found in tools/sql/migrations/")
        return

    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            applied = _applied_migrations(cursor)
    except Exception as exc:
        sys.exit(f"[run_migrations] ERROR: {exc}")

    print(f"{'Migration':<55} {'Status'}")
    print("-" * 65)
    for f in migration_files:
        status = "✅ applied" if f.name in applied else "⬜ pending"
        print(f"  {f.name:<53} {status}")


def run_migrations(dry_run: bool = False) -> int:
    _get_conn_str()
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("[run_migrations] No migration files found in tools/sql/migrations/")
        return 0

    applied_count = 0
    skipped_count = 0

    try:
        with _get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(CREATE_MIGRATIONS_TABLE)
            conn.commit()

            applied = _applied_migrations(cursor)

            for migration_file in migration_files:
                name = migration_file.name
                if name in applied:
                    print(f"[skip] {name} (already applied)")
                    skipped_count += 1
                    continue

                print(f"[run]  {name}", end="", flush=True)
                sql = migration_file.read_text(encoding="utf-8")
                batches = _split_batches(sql)

                if dry_run:
                    print(f" — DRY RUN ({len(batches)} batch(es), not applied)")
                    continue

                for batch in batches:
                    cursor.execute(batch)
                    conn.commit()

                import datetime as _dt

                cursor.execute(
                    "INSERT INTO dbo._migrations (migration_id, applied_at, applied_by) VALUES (?, ?, ?)",
                    name, _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None), "run_migrations.py"
                )
                conn.commit()
                print(" ✅")
                applied_count += 1
    except Exception as exc:
        print(f" ❌")
        print(f"[run_migrations] ERROR: {exc}", file=sys.stderr)
        return 1

    if dry_run:
        print(f"\n[run_migrations] Dry run complete — {len(migration_files)} file(s) scanned, 0 applied.")
    else:
        print(f"\n[run_migrations] Done — {applied_count} applied, {skipped_count} skipped.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply SQL migrations to caseforge-clientdb (Postgres).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--status", action="store_true", help="Show migration status only, no changes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.status:
        run_status()
    else:
        sys.exit(run_migrations(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
