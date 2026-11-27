#!/usr/bin/env python3
"Prove the nightly caseforge-clientdb backup is actually restorable, and restore"
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import backup_crypto

THROWAWAY_CONTAINER = "caseforge-postgres-restore-verify"
THROWAWAY_PORT = "5532"
LIVE_CONTAINER = "caseforge-postgres"
_POSTGRES_DEFAULTS = Path(__file__).resolve().parents[2] / "deploy/ansible/roles/postgres/defaults/main.yml"
PSQL_RESTORE_FLAGS = ["-v", "ON_ERROR_STOP=1", "--single-transaction"]


def _postgres_image() -> str:
    "The production image, read from the Ansible defaults: a restore check on another 16.x point"
    match = re.search(r'^postgres_image:\s*"([^"]+)"', _POSTGRES_DEFAULTS.read_text(), re.M)
    if not match:
        raise RuntimeError(f"postgres_image not found in {_POSTGRES_DEFAULTS}")
    return match.group(1)


THROWAWAY_IMAGE = _postgres_image()


def dump_table_count(dump_text: str) -> int:
    "How many tables the dump itself defines, to compare with what the restore produced."
    return len(re.findall(r"^CREATE TABLE ", dump_text, re.M))


_OWN_ROLE = "valclientdb"
_ROLE_REF = re.compile(r"^(?:GRANT|REVOKE)\b.*?\b(?:TO|FROM)\s+(.+?);\s*$|^ALTER\b.*?\bOWNER TO\s+(.+?);\s*$", re.M)


def dump_roles(dump_text: str) -> list[str]:
    "Roles the dump's GRANT, REVOKE and OWNER lines name (``telemetry_writer``), bar the owner."
    found: set[str] = set()
    for m in _ROLE_REF.finditer(dump_text):
        for raw in (m.group(1) or m.group(2)).split(","):
            name = raw.strip().strip('"')
            if name and name.upper() not in {"PUBLIC", "CURRENT_USER", "SESSION_USER"} and name != _OWN_ROLE:
                found.add(name)
    return sorted(found)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, **kw)


def verify(dump_path: Path) -> int:
    print(f"[verify] restoring {dump_path} into a throwaway container ({THROWAWAY_CONTAINER}, port {THROWAWAY_PORT})")
    run(["docker", "rm", "-f", THROWAWAY_CONTAINER])
    try:
        up = run(
            [
                "docker", "run", "-d", "--name", THROWAWAY_CONTAINER,
                "-e", "POSTGRES_PASSWORD=verify-only-throwaway",
                "-e", "POSTGRES_DB=valclientdb",
                "-e", "POSTGRES_USER=valclientdb",
                "-p", f"127.0.0.1:{THROWAWAY_PORT}:5432",
                THROWAWAY_IMAGE,
            ]
        )
        if up.returncode != 0:
            print(f"[verify] FAILED to start throwaway container: {up.stderr}", file=sys.stderr)
            return 1

        ready = run(
            [
                "docker", "exec", THROWAWAY_CONTAINER,
                "bash", "-c",
                "for i in $(seq 1 30); do pg_isready -U valclientdb -d valclientdb && exit 0; sleep 1; done; exit 1",
            ]
        )
        if ready.returncode != 0:
            print("[verify] FAILED: throwaway postgres never became ready", file=sys.stderr)
            return 1

        dump_text = dump_path.read_text()
        for role in dump_roles(dump_text):
            run(["docker", "exec", THROWAWAY_CONTAINER, "psql", "-U", "valclientdb", "-d", "valclientdb",
                 "-c", f'CREATE ROLE "{role}" NOLOGIN'])
        restore = run(
            ["docker", "exec", "-i", THROWAWAY_CONTAINER, "psql", "-U", "valclientdb", "-d", "valclientdb",
             *PSQL_RESTORE_FLAGS],
            input=dump_text,
        )
        if restore.returncode != 0:
            print(f"[verify] FAILED to restore dump: {restore.stderr}", file=sys.stderr)
            return 1

        tables = run(
            [
                "docker", "exec", THROWAWAY_CONTAINER, "psql", "-U", "valclientdb", "-d", "valclientdb",
                "-tAc",
                "select format('%I.%I', table_schema, table_name) from information_schema.tables "
                "where table_type = 'BASE TABLE' and table_schema not in ('pg_catalog', 'information_schema')",
            ]
        )
        if tables.returncode != 0 or not tables.stdout.strip():
            print("[verify] FAILED: restore produced zero tables -- the dump is empty or invalid", file=sys.stderr)
            return 1

        restored_tables = [t.strip() for t in tables.stdout.strip().splitlines() if t.strip()]
        expected_tables = dump_table_count(dump_text)
        if len(restored_tables) < expected_tables:
            print(f"[verify] FAILED: the dump defines {expected_tables} tables but only {len(restored_tables)} "
                  "were restored.", file=sys.stderr)
            return 1

        print("[verify] restore succeeded. Row counts:")
        any_rows = False
        for table in tables.stdout.strip().splitlines():
            table = table.strip()
            if not table:
                continue
            count = run(
                ["docker", "exec", THROWAWAY_CONTAINER, "psql", "-U", "valclientdb", "-d", "valclientdb", "-tAc",
                 f"select count(*) from {table}"]
            )
            n = count.stdout.strip() if count.returncode == 0 else "?"
            print(f"  {table}: {n}")
            if n not in ("0", "?"):
                any_rows = True

        if not any_rows:
            print("[verify] WARNING: every table restored with zero rows. A dump that restores structurally "
                  "but has no data is still not proof the backup is usable -- treat this as a failed "
                  "verification, not a pass.", file=sys.stderr)
            return 1

        print("[verify] PASS -- this dump is restorable and contains data.")
        return 0
    finally:
        run(["docker", "rm", "-f", THROWAWAY_CONTAINER])
        print(f"[verify] throwaway container removed")


def _native_connection() -> tuple[list[str], dict] | None:
    "psql connection arguments and environment for the native cluster, from the same"
    import os
    import urllib.parse

    dsn = os.environ.get("CASEFORGE_CLIENTDB_PG_URL", "")
    parsed = urllib.parse.urlparse(dsn) if dsn else None
    if not parsed or not parsed.hostname:
        return None
    args = ["-h", parsed.hostname, "-p", str(parsed.port or 5432), "-U", "valclientdb", "-d", "valclientdb"]
    env = {**os.environ, "PGPASSWORD": parsed.password} if parsed.password else dict(os.environ)
    return args, env


def restore_live_native(dump_path: Path) -> int:
    "The restore-live checks, against the native cluster: its data directory must be on the"
    conn = _native_connection()
    if conn is None:
        print(f"[restore-live] REFUSED: {LIVE_CONTAINER} does not exist and CASEFORGE_CLIENTDB_PG_URL is not set, "
              "so there is no live database to restore into.", file=sys.stderr)
        return 1
    args, env = conn
    where = run(["psql", *args, "-tAc", "SHOW data_directory"], env=env)
    data_dir = where.stdout.strip()
    if where.returncode != 0 or not data_dir:
        print(f"[restore-live] REFUSED: could not read the native cluster's data directory: {where.stderr.strip()}",
              file=sys.stderr)
        return 1
    mountpoint = run(["findmnt", "-n", "-o", "TARGET", "--target", data_dir])
    on_encrypted_volume = "encrypted" in data_dir.lower() or (
        mountpoint.returncode == 0 and "encrypted" in mountpoint.stdout.lower()
    )
    if not on_encrypted_volume:
        print(f"[restore-live] REFUSED: the native cluster's data ({data_dir}) does not look like it's on the "
              "LUKS-encrypted volume. Refusing to restore real client data onto unencrypted storage.", file=sys.stderr)
        return 1
    existing = run(["psql", *args, "-tAc",
                    "select count(*) from information_schema.tables where table_schema='public'"], env=env)
    if existing.returncode != 0 or existing.stdout.strip() != "0":
        print(f"[restore-live] REFUSED: the target database is not empty or could not be checked "
              f"(tables: {existing.stdout.strip() or existing.stderr.strip()}). A restore appends to what is "
              "there; start from an empty database.", file=sys.stderr)
        return 1
    print(f"[restore-live] confirmed: native data is on {data_dir} (encrypted volume), target is empty. Proceeding.")
    restore = run(["psql", *args, *PSQL_RESTORE_FLAGS], input=dump_path.read_text(), env=env)
    if restore.returncode != 0:
        print(f"[restore-live] FAILED: {restore.stderr}", file=sys.stderr)
        return 1
    print("[restore-live] PASS -- restored into the native cluster.")
    return 0


def restore_live(dump_path: Path) -> int:
    print(f"[restore-live] checking {LIVE_CONTAINER}'s actual bind mount before touching anything")
    inspect = run(
        ["docker", "inspect", LIVE_CONTAINER, "--format",
         "{{range .Mounts}}{{.Source}}={{.Destination}}\n{{end}}"]
    )
    if inspect.returncode != 0:
        print(f"[restore-live] {LIVE_CONTAINER} not found; checking for the native cluster instead")
        return restore_live_native(dump_path)

    data_mount_source = None
    for line in inspect.stdout.strip().splitlines():
        if line.endswith("=/var/lib/postgresql/data"):
            data_mount_source = line.split("=", 1)[0]

    if not data_mount_source:
        print(f"[restore-live] REFUSED: {LIVE_CONTAINER} has no bind mount at /var/lib/postgresql/data "
              "-- can't confirm where its data actually lives.", file=sys.stderr)
        return 1

    mountpoint = run(["findmnt", "-n", "-o", "TARGET", "--target", data_mount_source])
    on_encrypted_volume = mountpoint.returncode == 0 and "encrypted" in mountpoint.stdout.lower()
    if not on_encrypted_volume and "encrypted" in data_mount_source.lower():
        on_encrypted_volume = True

    if not on_encrypted_volume:
        print(f"[restore-live] REFUSED: {LIVE_CONTAINER}'s data ({data_mount_source}) does not look like it's "
              "on the LUKS-encrypted volume. Refusing to restore real client data onto unencrypted storage. "
              "If this is a false positive, fix the detection here rather than bypass it.", file=sys.stderr)
        return 1

    existing = run(
        ["docker", "exec", LIVE_CONTAINER, "psql", "-U", "valclientdb", "-d", "valclientdb", "-tAc",
         "select count(*) from information_schema.tables where table_schema='public'"]
    )
    if existing.returncode != 0 or existing.stdout.strip() != "0":
        print(f"[restore-live] REFUSED: the target database is not empty or could not be checked "
              f"(tables: {existing.stdout.strip() or existing.stderr.strip()}). A restore appends to what is "
              "there; start from an empty database.", file=sys.stderr)
        return 1

    print(f"[restore-live] confirmed: data is on {data_mount_source} (encrypted volume), target is empty. Proceeding.")
    restore = run(
        ["docker", "exec", "-i", LIVE_CONTAINER, "psql", "-U", "valclientdb", "-d", "valclientdb",
         *PSQL_RESTORE_FLAGS],
        input=dump_path.read_text(),
    )
    if restore.returncode != 0:
        print(f"[restore-live] FAILED: {restore.stderr}", file=sys.stderr)
        return 1
    print("[restore-live] PASS -- restored into the live container.")
    return 0


def record_drill() -> None:
    "Note that a restore drill passed, for the freshness check in ops_supervisor."
    import datetime
    import json

    dest = _TOOLS_DIR.parent / "telemetry" / "restore-drill.json"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    from atomic_json import atomic_write_json

    atomic_write_json(dest, {"timestamp_utc": stamp, "store": "clientdb"}, indent=None)
    print(f"[verify] drill recorded in {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dump_path", type=Path, help="Path to a pg_dump SQL file (plain format, matching tools/documenso/clientdb_backup.py's output), or its .age encrypted form with --identity")
    parser.add_argument("--record-drill", action="store_true",
                         help="With --verify: on PASS, write telemetry/restore-drill.json, which ops_supervisor reads (red after 35 days)")
    parser.add_argument("--identity", type=Path,
                         help="age private key file, to decrypt a .age dump (kept in the password manager, never on the host)")
    parser.add_argument("--restore-live", action="store_true",
                         help="Restore into the real caseforge-postgres container instead of a throwaway one. Refuses unless its data is confirmed on the LUKS-encrypted volume.")
    args = parser.parse_args()

    if not args.dump_path.exists():
        print(f"No such file: {args.dump_path}", file=sys.stderr)
        sys.exit(1)

    dump_path = args.dump_path
    with tempfile.TemporaryDirectory(prefix="caseforge-clientdb-restore-") as tmp:
        if dump_path.suffix == backup_crypto.SUFFIX:
            if not args.identity:
                print("An encrypted (.age) dump needs --identity <private key file>.", file=sys.stderr)
                sys.exit(1)
            dump_path = backup_crypto.decrypt_file(dump_path, args.identity, Path(tmp) / dump_path.stem)
        if args.restore_live:
            sys.exit(restore_live(dump_path))
        code = verify(dump_path)
        if code == 0 and args.record_drill:
            record_drill()
        sys.exit(code)


if __name__ == "__main__":
    main()
