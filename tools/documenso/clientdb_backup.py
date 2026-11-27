#!/usr/bin/env python3
"Back up caseforge-clientdb (the migrated Azure SQL database) to OneDrive."
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import backup_crypto
import graph_files
from rag.qdrant_snapshot_backup import (
    _onedrive_folder,
    _utc_stamp,
    compose_dir_for,
    ensure_onedrive_folder,
)


def _compose_dir() -> Path:
    return compose_dir_for(override_env="CASEFORGE_CLIENTDB_COMPOSE_DIR", container="caseforge-postgres")


CONTAINER = "caseforge-postgres"


def _container_running() -> bool:
    "True while the caseforge-postgres container is up. When it is not (the native cluster has"
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def dump_clientdb(dest: Path) -> None:
    import os
    import urllib.parse

    dsn = os.environ.get("CASEFORGE_CLIENTDB_PG_URL", "")
    parsed = urllib.parse.urlparse(dsn) if dsn else None
    password = parsed.password if parsed else None
    env = {**os.environ, "PGPASSWORD": password} if password else os.environ

    with dest.open("wb") as fh:
        if _container_running():
            subprocess.run(
                ["docker", "compose", "exec", "-T", "-e", "PGPASSWORD", "postgres",
                 "pg_dump", "-U", "valclientdb", "-d", "valclientdb", "--no-owner"],
                cwd=_compose_dir(), stdout=fh, check=True, timeout=1800, env=env,
            )
            return
        if not parsed or not parsed.hostname:
            raise RuntimeError(
                f"{CONTAINER} is not running and CASEFORGE_CLIENTDB_PG_URL is not set, so there is nothing to dump from"
            )
        subprocess.run(
            ["pg_dump", "-h", parsed.hostname, "-p", str(parsed.port or 5432),
             "-U", "valclientdb", "-d", "valclientdb", "--no-owner"],
            stdout=fh, check=True, timeout=1800, env=env,
        )


def run() -> dict:
    import tempfile

    folder = _onedrive_folder()
    with tempfile.TemporaryDirectory(prefix="caseforge-clientdb-backup-") as tmp:
        tmp_path = Path(tmp)
        stamp = _utc_stamp()

        dump = tmp_path / f"valclientdb-pgdump-{stamp}.sql"
        dump_clientdb(dump)

        plain_bytes = dump.stat().st_size
        encrypted = backup_crypto.encrypt_file(dump)

        ensure_onedrive_folder(folder)
        graph_files.upload(encrypted, f"{folder}/{encrypted.name}", conflict_behavior="replace")

        return {
            "ok": True,
            "pg_dump": encrypted.name,
            "pg_dump_bytes": plain_bytes,
            "onedrive_folder": folder,
            "utc": stamp,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    t0 = time.time()
    result = run()
    result["elapsed_s"] = round(time.time() - t0, 1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
