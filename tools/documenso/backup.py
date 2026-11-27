#!/usr/bin/env python3
"Back up the Documenso signing stack on the server to OneDrive: a pg_dump of"
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
    return compose_dir_for(override_env="CASEFORGE_DOCUMENSO_COMPOSE_DIR", container="documenso-postgres-1")


def _compose(*args: str, stdout=None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=_compose_dir(),
        stdout=stdout,
        check=check,
        timeout=1800,
    )


def dump_postgres(dest: Path) -> None:
    with dest.open("wb") as fh:
        _compose(
            "exec", "-T", "-u", "postgres", "postgres",
            "pg_dump", "-U", "documenso", "-d", "documenso", "--no-owner",
            stdout=fh,
        )


def tar_blobs(dest: Path) -> None:
    with dest.open("wb") as fh:
        proc = _compose("exec", "-T", "seaweedfs", "tar", "czf", "-", "--warning=no-file-changed", "-C", "/", "data",
                        stdout=fh, check=False)
        if proc.returncode not in (0, 1):
            raise subprocess.CalledProcessError(proc.returncode, proc.args)


def run() -> dict:
    import tempfile

    folder = _onedrive_folder()
    with tempfile.TemporaryDirectory(prefix="caseforge-documenso-backup-") as tmp:
        tmp_path = Path(tmp)
        stamp = _utc_stamp()

        db_dump = tmp_path / f"documenso-pgdump-{stamp}.sql"
        dump_postgres(db_dump)
        db_bytes = db_dump.stat().st_size
        db_encrypted = backup_crypto.encrypt_file(db_dump)

        ensure_onedrive_folder(folder)
        graph_files.upload(db_encrypted, f"{folder}/{db_encrypted.name}", conflict_behavior="replace")

        blob_tar = tmp_path / f"documenso-blobs-{stamp}.tar.gz"
        tar_blobs(blob_tar)
        blob_bytes = blob_tar.stat().st_size
        blob_encrypted = backup_crypto.encrypt_file(blob_tar)
        graph_files.upload(blob_encrypted, f"{folder}/{blob_encrypted.name}", conflict_behavior="replace")

        return {
            "ok": True,
            "pg_dump": db_encrypted.name,
            "pg_dump_bytes": db_bytes,
            "blob_tar": blob_encrypted.name,
            "blob_tar_bytes": blob_bytes,
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
