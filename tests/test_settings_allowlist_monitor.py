import json

from tools.monitoring import settings_allowlist_monitor as m


def test_classify_arbitrary_exec():
    for entry in [
        "Bash(python3 *)",
        "Bash(python *)",
        "Bash(bash *)",
        "Bash(python -c ' *)",
        "Bash(source .secrets/caseforge-env && python3 *)",
        "Bash(pip install *)",
        "Bash(npx *)",
    ]:
        assert "arbitrary_exec" in m.classify_entry(entry), entry


def test_classify_destructive():
    for entry in [
        "Bash(git *)",
        "Bash(git push *)",
        "Bash(gh api *)",
        "Bash(gh repo *)",
        "Bash(curl *)",
        "Bash(find *)",
        "Bash(chmod +x *)",
    ]:
        assert "destructive" in m.classify_entry(entry), entry


def test_classify_secret_exposure():
    assert "secret_exposure" in m.classify_entry("Bash(env)")
    assert "secret_exposure" in m.classify_entry("Read(//root/.cloudflared/**)")
    assert "secret_exposure" in m.classify_entry("Read(//root/.ssh/**)")


def test_classify_safe_entries_unflagged():
    for entry in [
        "Bash(git add tools/*)",
        "Bash(git commit*)",
        "Bash(gh pr *)",
        "Bash(python tools/foo.py --no-server)",
        "Bash(curl -s http://localhost:8501/health)",
        "Bash(source .secrets/caseforge-env*)",
        "Read(//tmp/**)",
        "Read(//root/.claude/**)",
        "WebSearch",
    ]:
        assert m.classify_entry(entry) == set(), entry


def test_severity_thresholds():
    assert m.severity_for(5, set())[0] == "green"
    assert m.severity_for(30, set(), amber_count=25, red_count=50)[0] == "amber"
    assert m.severity_for(60, set(), amber_count=25, red_count=50)[0] == "red"
    assert m.severity_for(3, {"destructive"})[0] == "amber"
    assert m.severity_for(3, {"arbitrary_exec"})[0] == "red"
    assert m.severity_for(3, {"secret_exposure"})[0] == "red"


def _write(path, allow):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"allow": allow}}), encoding="utf-8")


def test_scan_file_clean_vs_risky(tmp_path):
    clean = tmp_path / "clean" / ".claude" / "settings.local.json"
    _write(clean, ["Bash(git commit*)", "Read(//tmp/**)"])
    assert m.scan_file(clean).severity == "green"

    risky = tmp_path / "risky" / ".claude" / "settings.local.json"
    _write(risky, ["Bash(python3 *)", "Bash(curl *)", "Bash(env)"])
    rep = m.scan_file(risky)
    assert rep.severity == "red"
    assert "arbitrary_exec" in rep.risky


def test_scan_file_malformed_is_amber(tmp_path):
    bad = tmp_path / ".claude" / "settings.local.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{ not json", encoding="utf-8")
    assert m.scan_file(bad).severity == "amber"


def test_find_and_evaluate_rolls_up(tmp_path):
    _write(tmp_path / ".claude" / "settings.local.json", ["Bash(git commit*)"])
    _write(
        tmp_path / "wt" / ".claude" / "settings.local.json",
        ["Bash(bash *)"],
    )
    files = m.find_settings_files(tmp_path)
    assert len(files) == 2
    result = m.evaluate(tmp_path)
    assert result["severity"] == "red"
    assert len(result["files"]) == 2


def test_discovers_multiple_agents_repo_only(tmp_path):
    _write(tmp_path / ".claude" / "settings.json", ["Bash(git status)"])
    _write(tmp_path / ".claude" / "settings.local.json", ["Bash(git commit*)"])
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "settings.json").write_text(
        json.dumps({"autoAccept": True, "coreTools": ["ShellTool"]}), encoding="utf-8"
    )
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text(
        'approval_policy = "never"\n', encoding="utf-8"
    )
    found = {agent for agent, _p, _fmt in m.discover_configs(tmp_path)}
    assert {"claude", "gemini", "codex"} <= found
    result = m.evaluate(tmp_path)
    assert result["severity"] == "red"
    agents = {f["agent"]: f for f in result["files"]}
    assert "safety_bypass" in agents["gemini"]["risky"]
    assert agents["codex"]["flags"]


def test_global_paths_not_scanned(tmp_path):
    (tmp_path / "stray.json").write_text(json.dumps({"permissions": {"allow": ["*"]}}), encoding="utf-8")
    assert m.discover_configs(tmp_path) == []


def test_wildcard_all_entry_is_arbitrary_exec():
    assert "arbitrary_exec" in m.classify_entry("*")
    assert "arbitrary_exec" in m.classify_entry("Bash(*)")
    assert "arbitrary_exec" in m.classify_entry("ShellTool")




def _repo(tmp_path):
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_a_grant_for_a_missing_repo_path_is_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / "tools").mkdir()
    assert m.classify_stale_paths("Bash(python3 tools/gone.py:*)", root) == {"stale_path"}


def test_a_grant_for_an_existing_path_is_not_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools" / "real.py").write_text("", encoding="utf-8")
    assert m.classify_stale_paths("Bash(python3 tools/real.py:*)", root) == set()


def test_a_deleted_scratch_venv_grant_is_flagged(tmp_path):
    root = _repo(tmp_path)
    entry = "Bash(tmp/headroom-test/venv/bin/pip install*)"
    assert m.classify_stale_paths(entry, root) == {"stale_path"}


def test_a_glob_grant_is_never_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / "tools").mkdir()
    for entry in (
        "Bash(python3 tools/*.py*)",
        "Bash(python3 $CLAUDE_PROJECT_DIR/tools/*.py*)",
        "Bash(grep *)",
    ):
        assert m.classify_stale_paths(entry, root) == set(), entry


def test_system_and_non_repo_paths_are_not_judged(tmp_path):
    root = _repo(tmp_path)
    for entry in (
        "Bash(/usr/bin/systemctl status *)",
        "Bash(some/other/project/script.sh)",
        "Read(//root/.claude/**)",
    ):
        assert m.classify_stale_paths(entry, root) == set(), entry


def test_entries_with_no_path_at_all_are_ignored(tmp_path):
    root = _repo(tmp_path)
    for entry in ("Bash(ls)", "WebSearch", "Skill(code-review)", "Bash(date*)"):
        assert m.classify_stale_paths(entry, root) == set(), entry


def test_a_domain_grant_is_not_mistaken_for_a_path(tmp_path):
    root = _repo(tmp_path)
    assert m.classify_stale_paths("WebFetch(domain:www.docuseal.com)", root) == set()


def test_stale_path_is_amber_not_red():
    sev, msg = m.severity_for(3, {"stale_path"})
    assert sev == "amber"
    assert "no longer exist" in msg


def test_stale_path_does_not_outrank_a_real_breach():
    sev, _ = m.severity_for(3, {"stale_path", "arbitrary_exec"})
    assert sev == "red"


def test_scan_config_reports_stale_grants_end_to_end(tmp_path):
    root = _repo(tmp_path)
    (root / ".claude").mkdir()
    path = root / ".claude" / "settings.json"
    path.write_text(
        json.dumps({"permissions": {"allow": ["Bash(python3 tools/vanished.py:*)"]}}),
        encoding="utf-8",
    )
    (root / "tools").mkdir()

    report = m.scan_config("claude", path, "claude_json")
    assert report.severity == "amber"
    assert report.risky["stale_path"] == ["Bash(python3 tools/vanished.py:*)"]


def test_the_live_configs_are_clean(tmp_path):
    del tmp_path
    import subprocess

    tracked = set(subprocess.run(["git", "ls-files"], cwd=m.REPO_ROOT, capture_output=True, text=True, check=True, timeout=60).stdout.split("\n"))
    result = m.evaluate()
    offenders = [f for f in result["files"] if f["severity"] != "green" and f["path"] in tracked]
    assert not offenders, f"agent configs are no longer clean: {offenders}"


def test_count_thresholds_leave_room_for_the_repos_real_needs():
    assert m.DEFAULT_AMBER_COUNT >= 35
    assert m.DEFAULT_RED_COUNT > m.DEFAULT_AMBER_COUNT
