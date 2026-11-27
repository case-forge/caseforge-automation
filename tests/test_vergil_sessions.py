from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import sessions


def _write_archive(archive_dir: Path, name: str, *, age_days: float, starred: bool = False) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{name}.json"
    stamp = time.time() - age_days * 86400
    import datetime as dt

    path.write_text(
        json.dumps({
            "id": name,
            "title": name,
            "starred": starred,
            "updated_utc": dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
            .isoformat().replace("+00:00", "Z"),
        }),
        encoding="utf-8",
    )
    return path


def test_load_valid_usernames_reads_and_lowercases(tmp_path):
    secrets = tmp_path / "secrets.toml"
    secrets.write_text(
        '[credentials.usernames.Sam]\nname = "Sam"\n'
        '[credentials.usernames.riley]\nname = "Riley"\n',
        encoding="utf-8",
    )
    assert sessions.load_valid_usernames(secrets) == {"sam", "riley"}


@pytest.mark.parametrize("content", [None, "", "not toml at all ]["])
def test_load_valid_usernames_returns_empty_on_unreadable(tmp_path, content):
    secrets = tmp_path / "secrets.toml"
    if content is not None:
        secrets.write_text(content, encoding="utf-8")
    assert sessions.load_valid_usernames(secrets) == set()


def test_orphaned_session_files_groups_by_owner(tmp_path):
    (tmp_path / "sam.history.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sam.provider-state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sam-sessions").mkdir()
    (tmp_path / "riley.history.json").write_text("{}", encoding="utf-8")

    orphaned = sessions.orphaned_session_files(tmp_path, {"riley"})

    assert set(orphaned) == {"sam"}
    assert len(orphaned["sam"]) == 3


def test_shared_state_files_are_never_orphaned(tmp_path):
    for name in sessions.SHARED_STATE_FILES:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert sessions.orphaned_session_files(tmp_path, {"riley"}) == {}


def test_unreadable_credentials_reports_nothing_orphaned(tmp_path):
    (tmp_path / "sam.history.json").write_text("{}", encoding="utf-8")
    assert sessions.orphaned_session_files(tmp_path, set()) == {}


def test_delete_orphaned_session_files_removes_files_and_directories(tmp_path):
    target_file = tmp_path / "sam.history.json"
    target_file.write_text("{}", encoding="utf-8")
    target_dir = tmp_path / "sam-sessions"
    target_dir.mkdir()
    (target_dir / "one.json").write_text("{}", encoding="utf-8")

    deleted, errors = sessions.delete_orphaned_session_files([target_file, target_dir], tmp_path)

    assert (deleted, errors) == (2, [])
    assert not target_file.exists()
    assert not target_dir.exists()


def test_delete_refuses_paths_outside_the_session_directory(tmp_path):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    outsider = tmp_path / "important.json"
    outsider.write_text("keep me", encoding="utf-8")
    traversal = session_dir / ".." / "important.json"

    deleted, errors = sessions.delete_orphaned_session_files([traversal], session_dir)

    assert deleted == 0
    assert errors and "outside the session directory" in errors[0]
    assert outsider.exists()
    assert outsider.read_text(encoding="utf-8") == "keep me"


def test_delete_reports_per_path_errors_without_aborting(tmp_path):
    good = tmp_path / "a.history.json"
    good.write_text("{}", encoding="utf-8")
    missing = tmp_path / "gone.history.json"

    deleted, errors = sessions.delete_orphaned_session_files([missing, good], tmp_path)

    assert deleted == 2
    assert errors == []
    assert not good.exists()


def test_expired_session_files_finds_only_old_unstarred_chats(tmp_path):
    archive = tmp_path / "archive"
    old = _write_archive(archive, "old", age_days=120)
    _write_archive(archive, "recent", age_days=3)
    _write_archive(archive, "old-but-starred", age_days=400, starred=True)

    expired = sessions.expired_session_files(archive, 90)

    assert expired == [old]


def test_ttl_of_zero_disables_retention(tmp_path):
    archive = tmp_path / "archive"
    _write_archive(archive, "ancient", age_days=5000)
    assert sessions.expired_session_files(archive, 0) == []
    assert sessions.prune_expired_sessions(archive, 0) == 0


def test_prune_deletes_expired_and_keeps_the_rest(tmp_path):
    archive = tmp_path / "archive"
    _write_archive(archive, "old", age_days=120)
    keep = _write_archive(archive, "recent", age_days=3)
    starred = _write_archive(archive, "starred", age_days=400, starred=True)

    assert sessions.prune_expired_sessions(archive, 90) == 1
    assert keep.exists()
    assert starred.exists()
    assert not (archive / "old.json").exists()


def test_unparsable_archive_is_left_alone(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir(parents=True)
    broken = archive / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    assert sessions.prune_expired_sessions(archive, 1) == 0
    assert broken.exists()


def test_missing_updated_utc_falls_back_to_mtime(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir(parents=True)
    path = archive / "no-stamp.json"
    path.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    import os

    old = time.time() - 200 * 86400
    os.utime(path, (old, old))

    assert sessions.expired_session_files(archive, 90) == [path]


def test_throttle_runs_once_then_skips_within_the_interval(tmp_path):
    archive = tmp_path / "archive"
    _write_archive(archive, "old", age_days=120)
    state: dict[str, float] = {}
    base = time.time()

    first = sessions.prune_expired_sessions_throttled(
        archive, 90, key="val", state=state, interval_seconds=900, now=base
    )
    _write_archive(archive, "older", age_days=200)
    second = sessions.prune_expired_sessions_throttled(
        archive, 90, key="val", state=state, interval_seconds=900, now=base + 100
    )

    assert first == 1
    assert second == 0, "a second call inside the interval must not scan again"
    assert (archive / "older.json").exists()


def test_throttle_runs_again_after_the_interval(tmp_path):
    archive = tmp_path / "archive"
    _write_archive(archive, "old", age_days=120)
    state: dict[str, float] = {}
    base = time.time()

    sessions.prune_expired_sessions_throttled(
        archive, 90, key="val", state=state, interval_seconds=900, now=base
    )
    _write_archive(archive, "older", age_days=200)
    again = sessions.prune_expired_sessions_throttled(
        archive, 90, key="val", state=state, interval_seconds=900, now=base + 1_000
    )

    assert again == 1


def test_throttle_is_per_key(tmp_path):
    archive = tmp_path / "archive"
    _write_archive(archive, "old", age_days=120)
    state: dict[str, float] = {}
    base = time.time()

    sessions.prune_expired_sessions_throttled(
        archive, 90, key="sam", state=state, interval_seconds=900, now=base
    )
    _write_archive(archive, "older", age_days=200)
    other = sessions.prune_expired_sessions_throttled(
        archive, 90, key="riley", state=state, interval_seconds=900, now=base + 10
    )

    assert other == 1
    assert set(state) == {"sam", "riley"}
