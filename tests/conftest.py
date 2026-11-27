import ipaddress
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))


def snapshot_process_state():
    env = dict(os.environ)
    cwd = os.getcwd()
    modules = dict(sys.modules)

    def restore() -> None:
        _restore_process_state(env, cwd, modules)

    return restore


@pytest.fixture(autouse=True)
def _process_state_restored():
    restore = snapshot_process_state()
    yield
    restore()


@pytest.fixture(autouse=True)
def _graph_cooldown_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEFORGE_GRAPH_COOLDOWN_FILE", str(tmp_path / "graph-429-cooldown"))


@pytest.fixture(autouse=True)
def _statement_on_file_is_case_flows_own(request, monkeypatch):
    module = sys.modules.get("onboarding.pipeline.step_statement")
    if module is not None and not request.node.get_closest_marker("real_statement_provenance"):
        monkeypatch.setattr(module, "made_by_case_flow", lambda ctx, files: True)


def _restore_process_state(env, cwd, modules) -> None:
    for key in [k for k in os.environ if k not in env]:
        os.environ.pop(key, None)
    for key, value in env.items():
        if os.environ.get(key) != value:
            os.environ[key] = value
    try:
        if os.getcwd() != cwd:
            os.chdir(cwd)
    except OSError:
        os.chdir(cwd)
    replaced_roots = {name.split(".")[0] for name, module in modules.items() if sys.modules.get(name) is not module}
    if replaced_roots:
        for name in [n for n in sys.modules if n not in modules and n.split(".")[0] in replaced_roots]:
            sys.modules.pop(name, None)
        for name, module in modules.items():
            if sys.modules.get(name) is not module:
                sys.modules[name] = module


_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})
_real_getaddrinfo = socket.getaddrinfo


def _resolvable_in_tests(host) -> bool:
    if host is None:
        return True
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "replace")
    name = str(host).strip().rstrip(".").lower()
    if name in _LOOPBACK_NAMES or name.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return False
    return True


def _test_getaddrinfo(host, *args, **kwargs):
    if not _resolvable_in_tests(host):
        raise socket.gaierror(socket.EAI_NONAME, f"DNS lookup of {host!r} blocked in tests (gh#305)")
    return _real_getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _test_getaddrinfo

os.environ["CASEFORGE_SQLITE_SYNCHRONOUS_OFF"] = "1"

for _vault_var in ("CASEFORGE_KEY_VAULT", "CASEFORGE_KEY_VAULT_MGMT"):
    os.environ.pop(_vault_var, None)
import flags_env as _flags_env

os.environ[_flags_env.FLAGS_FILE_ENV] = os.path.join(tempfile.gettempdir(), "flags-absent-in-tests.env")

os.environ["CASEFORGE_SOT_SIGNATURE_FETCH"] = "0"
os.environ["CASEFORGE_SOT_SIGNATURE_CACHE"] = os.path.join(tempfile.gettempdir(), "sot-signature-absent-in-tests.pdf")
os.environ.pop("CASEFORGE_SOT_SIGNATURE_FILE", None)


@pytest.fixture(scope="session")
def _tool_doc_cache_path(tmp_path_factory):
    return tmp_path_factory.mktemp("tool-doc-cache") / "tool-doc-cache.json"


@pytest.fixture(autouse=True)
def _no_live_model_calls(monkeypatch, tmp_path, _tool_doc_cache_path):
    monkeypatch.setenv("CASEFORGE_CHAT_ENABLE_SMALL_MODEL", "0")
    monkeypatch.setenv("CASEFORGE_CHAT_ALLOW_API_FALLBACK", "0")
    monkeypatch.setenv("CASEFORGE_OPS_DB", str(tmp_path / "caseforge-ops-test.sqlite3"))
    monkeypatch.setenv("CASEFORGE_ENV_FILE", str(tmp_path / "caseforge-env-absent"))
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(tmp_path / "caseforge-sql-test.sqlite"))
    monkeypatch.setenv("CASEFORGE_TELEMETRY_DB", str(tmp_path / "caseforge-telemetry-test.sqlite3"))
    monkeypatch.setenv("CASEFORGE_TELEMETRY_ROOT", str(tmp_path / "telemetry"))
    monkeypatch.setenv("CASEFORGE_HUB_API_REQUEST_LOG_EXPECTED", "0")
    monkeypatch.setenv("CASEFORGE_AGENT_PIN_STATE_PATH", str(tmp_path / "agent-cwd-pin.json"))
    monkeypatch.setenv("CASEFORGE_TOOL_DOC_CACHE", str(_tool_doc_cache_path))
    absent_luks_paths = tmp_path / "luks-paths-absent.env"
    monkeypatch.setenv("CASEFORGE_LUKS_PATHS_FILE", str(absent_luks_paths))
    for _ops_db_name in ("ops_db", "tools.ops_db"):
        _ops_db_module = sys.modules.get(_ops_db_name)
        if _ops_db_module is not None and hasattr(_ops_db_module, "LUKS_PATHS_ENV_FILE"):
            monkeypatch.setattr(_ops_db_module, "LUKS_PATHS_ENV_FILE", absent_luks_paths)
    for _graph_var in (
        "GRAPH_TENANT_ID", "GRAPH_MAIL_CLIENT_ID", "GRAPH_CLIENT_ID",
        "GRAPH_MAIL_CLIENT_SECRET", "GRAPH_CLIENT_SECRET", "GRAPH_MAILBOX_UPN",
    ):
        monkeypatch.delenv(_graph_var, raising=False)
    for _db_var in ("CASEFORGE_CLIENTDB_PG_URL", "AZURE_SQL_CONNECTION_STRING"):
        monkeypatch.delenv(_db_var, raising=False)
    for _git_var in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE", "GIT_PREFIX",
    ):
        monkeypatch.delenv(_git_var, raising=False)
    for _glitchtip_var in (
        "GLITCHTIP_DSN_CLIENT_VIEWER", "GLITCHTIP_DSN_CHAT_WEB", "GLITCHTIP_DSN_HUB_API",
    ):
        monkeypatch.delenv(_glitchtip_var, raising=False)
    monkeypatch.delenv("CASEFORGE_HEALTHCHECKS_PING_BASE", raising=False)


_SECRET_ENV_SHAPE = re.compile(r"(_KEY|_TOKEN|_SECRET|_PASSWORD|_DSN|_PG_URL|_CONNECTION_STRING)$")


@pytest.fixture(autouse=True)
def _no_secret_shaped_env(monkeypatch):
    for name in [n for n in os.environ if _SECRET_ENV_SHAPE.search(n.upper())]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_real_wait_between_model_retries(monkeypatch):
    module = sys.modules.get("documents.model_proofread")
    if module is not None:
        monkeypatch.setattr(module, "RUNNER_PAUSE_S", 0.0)


@pytest.fixture(autouse=True)
def _model_overrides_isolated(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("CASEFORGE_MODEL_OVERRIDES_FILE", str(tmp_path_factory.mktemp("model-overrides") / "model-role-overrides.json"))


_RSA_KEYS: dict = {}


def _rsa_key(name: str = "team"):
    if name not in _RSA_KEYS:
        from cryptography.hazmat.primitives.asymmetric import rsa

        _RSA_KEYS[name] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _RSA_KEYS[name]


@pytest.fixture
def access_jwt(monkeypatch):
    import time

    import jwt as pyjwt

    from vergil import access_identity

    team, aud_ok = "team.example.test", "test-aud"
    monkeypatch.setenv(access_identity.TEAM_DOMAIN_ENV, team)
    monkeypatch.setenv(access_identity.AUD_ENV, aud_ok)
    monkeypatch.setattr(access_identity, "signing_key", lambda assertion, t: _rsa_key("team").public_key())

    def make(email: str, *, aud: str = aud_ok, exp_in: int = 600, forged: bool = False) -> str:
        now = int(time.time())
        claims = {"email": email, "aud": [aud], "iss": f"https://{team}", "iat": now - 5, "exp": now + exp_in}
        return pyjwt.encode(claims, _rsa_key("other" if forged else "team"), algorithm="RS256")

    return make


@pytest.fixture(autouse=True)
def _ccl_switch_on(monkeypatch, tmp_path_factory):
    path = tmp_path_factory.mktemp("ccl-switch") / "ccl-switch.json"
    path.write_text('{"on": true}\n', encoding="utf-8")
    monkeypatch.setenv("CCL_SWITCH_PATH", str(path))


@pytest.fixture(autouse=True)
def _mid_letter_switch_on(monkeypatch, tmp_path_factory):
    path = tmp_path_factory.mktemp("mid-letter-switch") / "mid-letter-switch.json"
    path.write_text('{"on": true}\n', encoding="utf-8")
    monkeypatch.setenv("MID_LETTER_SWITCH_PATH", str(path))


@pytest.fixture(autouse=True)
def _email_filing_released(monkeypatch, tmp_path_factory):
    path = tmp_path_factory.mktemp("email-filing-hold") / "email-filing-hold.json"
    path.write_text('{"held": false}', encoding="utf-8")
    monkeypatch.setenv("CASEFORGE_EMAIL_FILING_HOLD_PATH", str(path))


@pytest.fixture(autouse=True)
def _no_live_worktree_janitor(monkeypatch):
    for name in ("monitoring.ops_supervisor", "tools.monitoring.ops_supervisor"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "_worktree_janitor_metrics"):
            monkeypatch.setattr(mod, "_worktree_janitor_metrics", lambda **_kw: {"available": False})


@pytest.fixture(autouse=True)
def _portal_press_bills_nothing(monkeypatch):
    try:
        from onboarding.pipeline import portal_billing
    except Exception:
        return
    monkeypatch.setattr(portal_billing, "bill_press", lambda ctx, **kw: "")


@pytest.fixture(autouse=True)
def _documenso_envelope_record(monkeypatch, tmp_path_factory):
    path = tmp_path_factory.mktemp("documenso-envelopes") / "documenso-envelopes.json"
    monkeypatch.setenv("DOCUMENSO_ENVELOPES_STATE", str(path))


@pytest.fixture(autouse=True)
def _fresh_client_rows_cache():
    try:
        from vergil import client_rows
    except Exception:
        yield
        return
    client_rows.clear()
    yield
    client_rows.clear()


@pytest.fixture
def fallback_root_in_a_live_book(monkeypatch):
    import importlib

    stand_in_book = "fallback-book"
    for module_name, attr in (
        ("agents.documenso_webhook_worker", "AI_EXP_PARENT"),
        ("agents.ccl_pipeline", "AI_EXP_ROOT"),
        ("matter_fact_extraction", "AI_EXP_ROOT"),
        ("matter_incidents_extraction", "AI_EXP_ROOT"),
        ("onboarding.pipeline.step_ccl", "AI_EXP_BOOK"),
    ):
        for prefix in ("", "tools."):
            try:
                module = importlib.import_module(prefix + module_name)
            except Exception:
                continue
            value = getattr(module, attr, None)
            if isinstance(value, str):
                monkeypatch.setattr(module, attr, re.sub(r"[^/]*AI-EXP", stand_in_book, value, count=1))


@pytest.fixture(autouse=True)
def _folder_guard_makes_no_graph_calls(monkeypatch):
    monkeypatch.setenv("CASEFORGE_FOLDER_GUARD", "off")


@pytest.fixture(autouse=True)
def _no_documenso_database_in_tests(monkeypatch):
    monkeypatch.setenv("DOCUMENSO_DB_SCAN", "0")


@pytest.fixture(autouse=True)
def _alert_routing_off(monkeypatch):
    monkeypatch.setenv("CASEFORGE_ALERT_ROUTING", "none")


@pytest.fixture(autouse=True)
def _kv_fetch_errors_cleared():
    kv = sys.modules.get("load_kv_secrets")
    if kv is not None:
        kv.LAST_FETCH_ERRORS.clear()


@pytest.fixture(autouse=True)
def _no_leaked_secret_fetch_errors():
    module = sys.modules.get("load_kv_secrets")
    if module is not None and getattr(module, "LAST_FETCH_ERRORS", None):
        module.LAST_FETCH_ERRORS = []
    yield
    module = sys.modules.get("load_kv_secrets")
    if module is not None and getattr(module, "LAST_FETCH_ERRORS", None):
        module.LAST_FETCH_ERRORS = []
