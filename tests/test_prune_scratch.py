import datetime as dt
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from maintenance import prune_scratch as ps


def _age(path: Path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    (tmp_path / "telemetry" / "graph-api-calls").mkdir(parents=True)
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(ps, "REPO_ROOT", tmp_path)
    return tmp_path


def _rule(directory, age_days=14, pattern="*"):
    return (ps.PruneRule(directory, age_days=age_days, pattern=pattern),)


def test_old_log_is_prunable(scratch):
    f = scratch / "telemetry" / "graph-api-calls" / "2026-01-01.jsonl"
    f.write_text("x" * 100)
    _age(f, 40)
    plan = ps.build_plan(_rule("telemetry/graph-api-calls", pattern="*.jsonl"), repo_root=scratch)
    assert [c.path for c in plan] == ["telemetry/graph-api-calls/2026-01-01.jsonl"]


def test_recent_file_is_kept(scratch):
    f = scratch / "telemetry" / "graph-api-calls" / "today.jsonl"
    f.write_text("x")
    _age(f, 2)
    plan = ps.build_plan(_rule("telemetry/graph-api-calls", age_days=14, pattern="*.jsonl"), repo_root=scratch)
    assert plan == []


def test_protected_state_and_db_never_pruned(scratch):
    d = scratch / "telemetry" / "graph-api-calls"
    for name in ("state.json", "caseforge.sqlite3", "caseforge.db-wal", "latest-lint.json", "runs-active.json", ".gitkeep"):
        f = d / name
        f.write_text("x")
        _age(f, 90)
    plan = ps.build_plan(_rule("telemetry/graph-api-calls"), repo_root=scratch)
    assert plan == []


def test_symlink_is_never_pruned(scratch):
    d = scratch / "telemetry" / "graph-api-calls"
    target = d / "real.jsonl"
    target.write_text("x")
    _age(target, 90)
    link = d / "link.jsonl"
    link.symlink_to(target)
    _age(link, 90)
    plan = ps.build_plan(_rule("telemetry/graph-api-calls", pattern="*.jsonl"), repo_root=scratch)
    assert [c.path for c in plan] == ["telemetry/graph-api-calls/real.jsonl"]


def test_directory_outside_scratch_root_is_refused(scratch):
    (scratch / "context").mkdir()
    f = scratch / "context" / "emails.md"
    f.write_text("live doc")
    _age(f, 365)
    plan = ps.build_plan(_rule("context"), repo_root=scratch)
    assert plan == []


def test_min_age_override_raises_threshold(scratch):
    f = scratch / "tmp" / "scratch.txt"
    f.write_text("x")
    _age(f, 20)
    assert ps.build_plan(_rule("tmp", age_days=14), repo_root=scratch, min_age_days=30) == []
    assert ps.build_plan(_rule("tmp", age_days=14), repo_root=scratch, min_age_days=10)


def test_apply_deletes_only_planned_files(scratch):
    d = scratch / "tmp"
    old = d / "old.txt"
    old.write_text("x" * 50)
    _age(old, 40)
    keep = d / "keep.sqlite3"
    keep.write_text("db")
    _age(keep, 40)
    plan = ps.build_plan(_rule("tmp"), repo_root=scratch)
    result = ps.apply_plan(plan, repo_root=scratch)
    assert result["deleted"] == 1
    assert not old.exists()
    assert keep.exists()


def test_summarise_groups_by_rule(scratch):
    d = scratch / "tmp"
    for i in range(3):
        f = d / f"f{i}.txt"
        f.write_text("x" * 10)
        _age(f, 40)
    plan = ps.build_plan(_rule("tmp"), repo_root=scratch)
    summary = ps.summarise(plan)
    assert summary["files"] == 3
    assert summary["by_rule"]["tmp"]["files"] == 3


def test_dry_run_main_does_not_delete(scratch, capsys, monkeypatch):
    f = scratch / "tmp" / "old.txt"
    f.write_text("x" * 100)
    _age(f, 40)
    monkeypatch.setattr(ps, "DEFAULT_RULES", _rule("tmp"))
    rc = ps.main([])
    assert rc == 0
    assert f.exists()
    assert "Dry-run only" in capsys.readouterr().out


def test_symlinked_telemetry_root_is_walked_and_applied(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    volume = tmp_path / "encrypted" / "telemetry"
    (volume / "graph-api-calls").mkdir(parents=True)
    repo.mkdir()
    (repo / "telemetry").symlink_to(volume, target_is_directory=True)
    monkeypatch.setattr(ps, "REPO_ROOT", repo)
    old = volume / "graph-api-calls" / "2026-01-01.jsonl"
    old.write_text("x" * 10)
    _age(old, 40)

    plan = ps.build_plan(_rule("telemetry/graph-api-calls", pattern="*.jsonl"), repo_root=repo)
    assert [c.path for c in plan] == ["telemetry/graph-api-calls/2026-01-01.jsonl"]
    assert ps.apply_plan(plan, repo_root=repo)["deleted"] == 1
    assert not old.exists()


@pytest.mark.parametrize("errors, status", [([], "success"), (["tmp/x: denied"], "errors")])
def test_apply_records_a_status_the_security_audit_reads(scratch, monkeypatch, errors, status):
    seen: list[dict] = []
    monkeypatch.setattr(ps, "DEFAULT_RULES", _rule("tmp"))
    monkeypatch.setattr(ps, "apply_plan", lambda candidates: {"deleted": 1, "freed_bytes": 1, "freed_mib": 0.0, "errors": errors})
    monkeypatch.setattr(ps, "_emit_telemetry", seen.append)
    assert ps.main(["--apply"]) == 0
    assert seen and seen[0]["status"] == status
