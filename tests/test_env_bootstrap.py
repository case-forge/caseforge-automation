import os

from tools.env_bootstrap import load_repo_secrets, parse_env_file


def test_parse_env_file_reads_export_lines_without_toml(tmp_path):
    path = tmp_path / "caseforge-env"
    path.write_text(
        "\n".join(
            [
                "# generated",
                "export GRAPH_TENANT_ID='tenant-123'",
                'export GRAPH_MAILBOX_UPN="box@example.test"',
                "[cookie]",
                "name = should-not-load",
            ]
        ),
        encoding="utf-8",
    )

    values = parse_env_file(path)

    assert values == {
        "GRAPH_TENANT_ID": "tenant-123",
        "GRAPH_MAILBOX_UPN": "box@example.test",
    }


def test_load_repo_secrets_loads_missing_required_keys_without_overwriting(tmp_path, monkeypatch):
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    (secrets / "caseforge-env").write_text(
        "\n".join(
            [
                "export GRAPH_TENANT_ID='tenant-from-file'",
                "export GRAPH_MAILBOX_UPN='box@example.test'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("GRAPH_TENANT_ID", raising=False)
    monkeypatch.setenv("GRAPH_MAILBOX_UPN", "already@example.test")
    monkeypatch.delenv("CASEFORGE_ENV_FILE", raising=False)

    loaded = load_repo_secrets(
        repo_root=tmp_path,
        required_keys=("GRAPH_TENANT_ID", "GRAPH_MAILBOX_UPN"),
    )

    assert "GRAPH_TENANT_ID" in loaded
    assert os.environ["GRAPH_TENANT_ID"] == "tenant-from-file"
    assert os.environ["GRAPH_MAILBOX_UPN"] == "already@example.test"


def test_env_config_file_override_beats_repo_root(tmp_path, monkeypatch):
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    (secrets / "caseforge-env").write_text("export GRAPH_TENANT_ID='from-repo-root'\n", encoding="utf-8")
    monkeypatch.delenv("GRAPH_TENANT_ID", raising=False)
    monkeypatch.setenv("CASEFORGE_ENV_FILE", str(tmp_path / "caseforge-env-absent"))

    loaded = load_repo_secrets(repo_root=tmp_path, required_keys=("GRAPH_TENANT_ID",))

    assert loaded == []
    assert "GRAPH_TENANT_ID" not in os.environ


def test_explicit_secrets_path_still_wins_over_override(tmp_path, monkeypatch):
    named = tmp_path / "named-env"
    named.write_text("export GRAPH_TENANT_ID='from-named-file'\n", encoding="utf-8")
    monkeypatch.delenv("GRAPH_TENANT_ID", raising=False)
    monkeypatch.setenv("CASEFORGE_ENV_FILE", str(tmp_path / "caseforge-env-absent"))

    loaded = load_repo_secrets(secrets_path=named, required_keys=("GRAPH_TENANT_ID",))

    assert "GRAPH_TENANT_ID" in loaded
    assert os.environ["GRAPH_TENANT_ID"] == "from-named-file"


def test_agent_identity_uses_the_model_id_and_session_in_an_agent_session(monkeypatch):
    from tools.env_bootstrap import agent_identity

    monkeypatch.setenv("CASEFORGE_MODEL_LABEL", "Claude Code")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5[1m]")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc-123")
    assert agent_identity() == {"model_label": "claude-sonnet-5", "agent_session_id": "abc-123"}


def test_agent_identity_keeps_a_worker_label(monkeypatch):
    from tools.env_bootstrap import agent_identity

    monkeypatch.setenv("CASEFORGE_MODEL_LABEL", "calendar-finder")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert agent_identity() == {"model_label": "calendar-finder"}


def test_agent_identity_without_any_model_env_is_unchanged(monkeypatch):
    from tools.env_bootstrap import agent_identity

    monkeypatch.delenv("CASEFORGE_MODEL_LABEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert agent_identity() == {"model_label": ""}
