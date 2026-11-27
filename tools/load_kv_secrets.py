#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import stat
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

try:
    import firm_profile
except ImportError:
    from tools import firm_profile

DEFAULT_VAULT = firm_profile.load_profile().key_vault_name
DEFAULT_MGMT_VAULT = firm_profile.management_vault_name()
MGMT_SECRETS = frozenset({"cloudflare-global-api-key", "cloudflare-api-email"})

OPT_IN_ENV = {"CLAUDE_CODE_OAUTH_TOKEN": "CASEFORGE_LOAD_CLAUDE_CODE_OAUTH_TOKEN"}


def _opted_in(env_var: str) -> bool:
    gate = OPT_IN_ENV.get(env_var)
    return gate is None or (os.environ.get(gate) or "").strip().lower() in {"1", "true", "yes", "on"}


SECRET_MAP = [
    ("microsoft-tenant-id",               "GRAPH_TENANT_ID",               True,  "Shared AAD tenant ID"),
    ("outlook-mailbox-upn",             "GRAPH_MAILBOX_UPN",             True,  "Mailbox UPN for all apps"),
    ("graph-observer-app-id",         "GRAPH_OBSERVER_CLIENT_ID",      False, "Observer fallback app client ID"),
    ("graph-observer-app-secret",     "GRAPH_OBSERVER_CLIENT_SECRET",  False, "Observer fallback app client secret"),
    ("outlook-calendar-client-id",           "GRAPH_CAL_CLIENT_ID",           True,  "Calendar app client ID"),
    ("outlook-calendar-client-secret",       "GRAPH_CAL_CLIENT_SECRET",       True,  "Calendar app client secret"),
    ("sharepoint-files-client-id",         "GRAPH_FILES_CLIENT_ID",         True,  "Files app client ID"),
    ("sharepoint-files-client-secret",     "GRAPH_FILES_CLIENT_SECRET",     True,  "Files app client secret"),
    ("outlook-mail-client-id",          "GRAPH_MAIL_CLIENT_ID",          True,  "Mail app client ID"),
    ("outlook-mail-client-secret",      "GRAPH_MAIL_CLIENT_SECRET",      True,  "Mail app client secret"),
    ("claude-code-oauth-token",       "CLAUDE_CODE_OAUTH_TOKEN",       False, "Claude CLI token for headless agentic callers"),
    ("caseforge-mail-intake-webhook-url",          "CASEFORGE_MAIL_INTAKE_WEBHOOK_URL",          False, "Mail intake public Graph webhook URL"),
    ("caseforge-mail-intake-webhook-client-state", "CASEFORGE_MAIL_INTAKE_WEBHOOK_CLIENT_STATE", False, "Mail intake Graph webhook clientState"),
    ("caseforge-mail-intake-azure-queue-connection-string", "CASEFORGE_MAIL_INTAKE_AZURE_QUEUE_CONNECTION_STRING", False, "Mail intake Azure Queue relay connection string"),
    ("caseforge-mail-intake-azure-queue-name",              "CASEFORGE_MAIL_INTAKE_AZURE_QUEUE_NAME",              False, "Mail intake Azure Queue relay queue name"),
    ("caseforge-email-print-webhook-url",          "CASEFORGE_EMAIL_PRINT_WEBHOOK_URL",          False, "Email print/archive public Graph webhook URL"),
    ("caseforge-graph-webhook-client-state",       "CASEFORGE_GRAPH_WEBHOOK_CLIENT_STATE",       False, "Email print/archive Graph webhook clientState"),
    ("caseforge-telemetry-url",                    "CASEFORGE_TELEMETRY_URL",                    False, "Fleet phone-home receiver URL (private network address)"),
    ("caseforge-telemetry-token",                  "CASEFORGE_TELEMETRY_TOKEN",                  False, "Bearer token for the fleet phone-home receiver"),
    ("caseforge-calendar-finder-webhook-url",          "CASEFORGE_CALENDAR_FINDER_WEBHOOK_URL",          False, "Calendar finder public Graph webhook URL"),
    ("caseforge-calendar-finder-webhook-client-state", "CASEFORGE_CALENDAR_FINDER_WEBHOOK_CLIENT_STATE", False, "Calendar finder Graph webhook clientState"),
    ("caseforge-chat-secrets-toml",         "CASEFORGE_CHAT_SECRETS_TOML",         False, "Chat app Streamlit auth TOML"),
    ("caseforge-qdrant-url",                "CASEFORGE_QDRANT_URL",                False, "Qdrant endpoint"),
    ("caseforge-qdrant-api-key",             "CASEFORGE_QDRANT_API_KEY",            False, "Qdrant REST/gRPC API key (required once the server enforces it)"),
    ("caseforge-qdrant-readonly-api-key",    "CASEFORGE_QDRANT_READONLY_API_KEY",    False, "Qdrant read-only API key (query-only consumers, not yet wired anywhere)"),
    ("caseforge-counsel-telegram-bot-token", "CASEFORGE_COUNSEL_TELEGRAM_BOT_TOKEN", False, "Counsel Telegram bot token"),
    ("caseforge-monitor-telegram-bot-token", "CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", False, "Monitoring Telegram bot token (secretary alerts)"),
    ("caseforge-monitor-telegram-chat-id",   "CASEFORGE_MONITOR_TELEGRAM_CHAT_ID",   False, "Telegram chat id that receives secretary alerts"),
    ("signin-names",                   "SIGNIN_NAMES",                   False, "Names to log signed-in people under: email=Name pairs separated by semicolons (tools/vergil/signin_names.py)"),
    ("box-stats-token",                "CASEFORGE_BOX_STATS_TOKEN",      False, "Bearer token for the dev box's System health stats push; accepted only by /monitor/box-stats and /monitor/box-extras"),
    ("healthchecks-ping-base",         "CASEFORGE_HEALTHCHECKS_PING_BASE",     False, "Healthchecks ping base URL (http://<host>:8000/ping/<project-ping-key>)"),
    ("healthchecks-io-ping-base",      "CASEFORGE_HEALTHCHECKS_IO_PING_BASE",  False, "Hosted healthchecks.io ping base (https://hc-ping.com/<project-ping-key>) for the external dead-man's switch"),
    ("restic-backup-password",         "CASEFORGE_RESTIC_PASSWORD",            False, "Restic backup encryption password, shared across the fleet"),
    ("caseforge-backup-age-recipient",       "CASEFORGE_BACKUP_AGE_RECIPIENT",       False, "age public key(s) (age1...) the nightly backups are encrypted to"),
    ("openrouter-api-key",             "OPENROUTER_API_KEY",             False, "OpenRouter API key for the model_backend.py openrouter backend"),
    ("openrouter-ocr-api-key",         "OPENROUTER_OCR_API_KEY",         False, "Dedicated OpenRouter key (daily cap) for OCR vision escalation in model_backend.run_vision"),
    ("anthropic-api-key",              "ANTHROPIC_API_KEY",              False, "Anthropic API key for the model_backend.py direct Claude path"),
    ("caseforge-backup-age-recipient",       "CASEFORGE_BACKUP_AGE_RECIPIENT", False, "age public key(s) the backup jobs encrypt to (not a secret; the private key is in the password manager)"),
    ("caseforge-chat-api-token",             "CASEFORGE_CHAT_API_TOKEN",             False, "Bearer token for the hub API (ndichie-hub-api.service)"),
    ("portal-export-signing-key",      "PORTAL_EXPORT_SIGNING_KEY",  False, "Ed25519 seed that signs the portal-fill answers export (hub API only)"),
    ("glitchtip-dsn-client-viewer",    "GLITCHTIP_DSN_CLIENT_VIEWER",    False, "GlitchTip DSN for the client viewer"),
    ("glitchtip-dsn-chat-web",         "GLITCHTIP_DSN_CHAT_WEB",         False, "GlitchTip DSN for the chat web app"),
    ("glitchtip-dsn-hub-api",          "GLITCHTIP_DSN_HUB_API",          False, "GlitchTip DSN for the hub API (tools/vergil/api.py)"),
    ("cloudflare-tunnel-token",                "CF_TUNNEL_TOKEN",                False, "Cloudflare Tunnel token for unattended `cloudflared service install`"),
    ("documenso-api-token",            "DOCUMENSO_API_TOKEN",            False, "Documenso API token for envelope creation (documenso_envelopes.py)"),
    ("cloudflare-api-token",           "CLOUDFLARE_API_TOKEN",           False, "Retired scoped token; use cloudflare-global-api-key + cloudflare-api-email instead"),
    ("cloudflare-global-api-key",      "CLOUDFLARE_GLOBAL_API_KEY",       False, "Cloudflare Global API Key for the deployment's account, used for every Cloudflare operation"),
    ("cloudflare-api-email",           "CLOUDFLARE_API_EMAIL",            False, "Account email paired with the global key for X-Auth-Email auth"),
    ("caseforge-clientdb-pg-url",            "CASEFORGE_CLIENTDB_PG_URL",            False, "Postgres DSN for the client database (private network)"),
    ("audit-log-client-id",            "AUDIT_LOG_CLIENT_ID",            False, "audit-log app client ID"),
    ("audit-log-client-secret",        "AUDIT_LOG_CLIENT_SECRET",        False, "audit-log app client secret"),
]


_SDK_CLIENTS: dict = {}
_SDK_CREDENTIAL = None


def _sdk_client(vault: str):
    global _SDK_CREDENTIAL
    if vault not in _SDK_CLIENTS:
        from azure.identity import (
            AzureCliCredential,
            ChainedTokenCredential,
            EnvironmentCredential,
        )
        from azure.keyvault.secrets import SecretClient

        if _SDK_CREDENTIAL is None:
            _SDK_CREDENTIAL = ChainedTokenCredential(EnvironmentCredential(), AzureCliCredential())
        _SDK_CLIENTS[vault] = SecretClient(vault_url=f"https://{vault}.vault.azure.net/", credential=_SDK_CREDENTIAL)
    return _SDK_CLIENTS[vault]


def _fetch_secret_sdk(vault: str, name: str) -> tuple[str, Optional[str], Optional[str]]:
    from azure.core.exceptions import ResourceNotFoundError

    try:
        value = _sdk_client(vault).get_secret(name).value
        return name, value.strip() if value else None, None
    except ResourceNotFoundError:
        return name, None, "not_found"
    except Exception as exc:
        return name, None, f"{type(exc).__name__}: {exc}"


def _fetch_secret_cli(vault: str, name: str) -> tuple[str, Optional[str], Optional[str]]:
    result = subprocess.run(
        ["az", "keyvault", "secret", "show",
         "--vault-name", vault, "--name", name,
         "--only-show-errors", "-o", "json"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "SecretNotFound" in stderr or "does not exist" in stderr.lower():
            return name, None, "not_found"
        return name, None, stderr or f"exit code {result.returncode}"
    try:
        payload = json.loads(result.stdout)
        value = payload.get("value", "")
        return name, value.strip() if value else None, None
    except json.JSONDecodeError as exc:
        return name, None, f"JSON parse error: {exc}"


CACHE_TTL_DEFAULT_SECONDS = 3600
CACHE_DIR = Path("/run/caseforge-kv")


def _cache_ttl_seconds() -> int:
    raw = os.environ.get("CASEFORGE_KV_CACHE_TTL_SECONDS", "").strip()
    try:
        return max(0, int(raw)) if raw else CACHE_TTL_DEFAULT_SECONDS
    except ValueError:
        return CACHE_TTL_DEFAULT_SECONDS


def _cache_dir_trusted(directory: Path) -> bool:
    try:
        info = os.lstat(directory)
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not (info.st_mode & 0o022)


def _ensure_shared_cache_dir(directory: Path) -> None:
    if os.getuid() != 0:
        return
    try:
        os.lstat(directory)
        return
    except FileNotFoundError:
        pass
    except OSError:
        return
    try:
        os.mkdir(directory, 0o700)
    except OSError:
        pass


def _cache_path(vault: str) -> Optional[Path]:
    safe_vault = "".join(c for c in vault if c.isalnum() or c in "-_")
    name = f"caseforge-kv-cache-{os.getuid()}-{safe_vault}.json"
    _ensure_shared_cache_dir(CACHE_DIR)
    if _cache_dir_trusted(CACHE_DIR) and os.access(CACHE_DIR, os.W_OK):
        return CACHE_DIR / name
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    if xdg and _cache_dir_trusted(Path(xdg)) and os.access(xdg, os.W_OK):
        return Path(xdg) / name
    return None


def _read_cache(vault: str) -> Optional[dict[str, Optional[str]]]:
    ttl = _cache_ttl_seconds()
    path = _cache_path(vault)
    if not ttl or path is None:
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or (info.st_mode & 0o177) or not stat.S_ISREG(info.st_mode):
            return None
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(payload, dict) or payload.get("vault") != vault:
        return None
    fetched = payload.get("fetched_at")
    values = payload.get("secrets")
    if not isinstance(fetched, (int, float)) or not isinstance(values, dict):
        return None
    if not 0 <= time.time() - fetched < ttl:
        return None
    if set(values) != {row[0] for row in SECRET_MAP}:
        return None
    return {str(k): (v if isinstance(v, str) else None) for k, v in values.items()}


def _write_cache(vault: str, secrets: dict[str, Optional[str]]) -> None:
    if not _cache_ttl_seconds():
        return
    path = _cache_path(vault)
    if path is None:
        return
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".caseforge-kv-cache-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"vault": vault, "fetched_at": time.time(), "secrets": secrets}, handle)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    except OSError:
        pass


LAST_FETCH_ERRORS: list[str] = []


def vault_for(name: str, vault: str, mgmt_vault: Optional[str]) -> str:
    return mgmt_vault if mgmt_vault and name in MGMT_SECRETS else vault


def fetch_all_secrets(vault: str, *, use_cache: bool = False,
                      mgmt_vault: Optional[str] = None) -> dict[str, Optional[str]]:
    if mgmt_vault is None:
        mgmt_vault = DEFAULT_MGMT_VAULT
    if mgmt_vault == vault:
        mgmt_vault = ""
    cache_key = f"{vault}+{mgmt_vault}" if mgmt_vault else vault
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached
    all_names = [row[0] for row in SECRET_MAP]
    results: dict[str, Optional[str]] = {}
    errors: list[str] = []
    LAST_FETCH_ERRORS.clear()

    try:
        import azure.keyvault.secrets
        fetch_one = _fetch_secret_sdk
        try:
            _sdk_client(vault)
        except Exception as exc:
            print(f"[load_kv_secrets] SDK credential unavailable ({type(exc).__name__}); "
                  f"falling back to az CLI", file=sys.stderr)
            fetch_one = _fetch_secret_cli
    except ImportError:
        fetch_one = _fetch_secret_cli

    def _record(name: str, value: Optional[str], error: Optional[str]) -> None:
        if error and error != "not_found":
            errors.append(f"  {name}: {error}")
            LAST_FETCH_ERRORS.append(name)
        results[name] = None if error else value

    retry: list[str] = []

    def _first_try(name: str, value: Optional[str], error: Optional[str]) -> None:
        if error and error != "not_found":
            retry.append(name)
        else:
            _record(name, value, error)

    if all_names:
        _first_try(*fetch_one(vault_for(all_names[0], vault, mgmt_vault), all_names[0]))
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_one, vault_for(name, vault, mgmt_vault), name) for name in all_names[1:]]
        for future in as_completed(futures):
            _first_try(*future.result())
    for name in retry:
        _record(*fetch_one(vault_for(name, vault, mgmt_vault), name))

    if errors:
        print("[load_kv_secrets] WARNING: Some secrets could not be fetched:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
    elif use_cache:
        _write_cache(cache_key, results)

    return results


def _check_claude_oauth_token(value: str) -> Optional[str]:
    if "#" in value:
        return ("contains '#', so this is the OAuth authorization code from the "
                "browser callback, not the token; paste the code into "
                "`claude setup-token` and store what it prints")
    if not value.startswith("sk-ant-oat01-"):
        return "does not start with 'sk-ant-oat01-'"
    if len(value) < 40:
        return f"implausibly short for a token ({len(value)} chars)"
    if any(c.isspace() for c in value):
        return "contains whitespace"
    return None


SECRET_VALIDATORS: dict[str, Callable[[str], Optional[str]]] = {
    "claude-code-oauth-token": _check_claude_oauth_token,
}


def validate_secret(kv_name: str, value: str) -> Optional[str]:
    validator = SECRET_VALIDATORS.get(kv_name)
    if validator is None:
        return None
    try:
        return validator(value)
    except Exception:
        return None


def build_env_map(secrets: dict[str, Optional[str]]) -> dict[str, str]:
    env: dict[str, str] = {}
    missing_required: list[str] = []
    rejected: list[str] = []

    for kv_name, env_var, required, _ in SECRET_MAP:
        if not _opted_in(env_var):
            continue
        value = secrets.get(kv_name)
        if value:
            value = value.strip()
        if value:
            defect = validate_secret(kv_name, value)
            if defect:
                rejected.append(f"{kv_name} → {env_var}: {defect}")
                if required:
                    missing_required.append(f"{kv_name} → {env_var} (malformed: {defect})")
                continue
            env[env_var] = value
        elif required:
            missing_required.append(f"{kv_name} → {env_var}")

    if rejected:
        print(
            "[load_kv_secrets] WARNING: Secrets present but malformed — NOT exported:",
            file=sys.stderr,
        )
        for r in rejected:
            print(f"  {r}", file=sys.stderr)

    if missing_required:
        print("[load_kv_secrets] ERROR: Required secrets missing:", file=sys.stderr)
        for m in missing_required:
            print(f"  {m}", file=sys.stderr)
        sys.exit(1)

    return env


def print_shell_export(env: dict[str, str]) -> None:
    if sys.stdout.isatty():
        print(
            "[load_kv_secrets] REFUSING: stdout is a terminal, so this would print "
            "live secrets straight to your screen. Use:\n"
            '  eval "$(python tools/load_kv_secrets.py --shell)"   (one command, nothing displayed)\n'
            "  python tools/load_kv_secrets.py exec -- <command>   (safer -- never prints anything)\n"
            "  python tools/load_kv_secrets.py --list-keys         (just checking what's loaded)",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        "[load_kv_secrets] DANGER: the lines below are live secrets in plaintext. "
        "Only ever consume this via eval \"$(...)\" in the same command -- never "
        "pipe to head/cat/tee/less, never save to a file you'll read back, never "
        "run standalone to \"check it worked\". Need one command run with these "
        "secrets? Use `exec --` instead -- it never prints anything.",
        file=sys.stderr,
    )
    for var, value in sorted(env.items()):
        safe = value.replace("'", "'\\''")
        print(f"export {var}='{safe}'")


def _shape(value: str) -> str:
    if not value:
        return "empty"
    classes = []
    if any(c.isalpha() for c in value):
        classes.append("alpha")
    if any(c.isdigit() for c in value):
        classes.append("digit")
    if any(not c.isalnum() for c in value):
        classes.append("symbol")
    return f"{len(value)} chars, {'+'.join(classes) or 'none'}"


def print_key_list(env: dict[str, str]) -> None:
    if not env:
        print("[load_kv_secrets] no secrets loaded")
        return
    width = max(len(k) for k in env)
    for key in sorted(env):
        print(f"{key.ljust(width)}  {_shape(env[key])}")


def print_summary(env: dict[str, str]) -> None:
    apps = []
    if env.get("GRAPH_OBSERVER_CLIENT_ID"):
        apps.append("OBSERVER")
    if env.get("GRAPH_CAL_CLIENT_ID"):
        apps.append("CAL")
    if env.get("GRAPH_FILES_CLIENT_ID"):
        apps.append("FILES")
    if env.get("GRAPH_MAIL_CLIENT_ID"):
        apps.append("MAIL")

    mail_intake_loaded = bool(env.get("CASEFORGE_MAIL_INTAKE_WEBHOOK_URL") and env.get("CASEFORGE_MAIL_INTAKE_WEBHOOK_CLIENT_STATE"))
    mail_intake_azure_queue_loaded = bool(env.get("CASEFORGE_MAIL_INTAKE_AZURE_QUEUE_CONNECTION_STRING") and env.get("CASEFORGE_MAIL_INTAKE_AZURE_QUEUE_NAME"))
    email_print_loaded = bool(env.get("CASEFORGE_EMAIL_PRINT_WEBHOOK_URL") and env.get("CASEFORGE_GRAPH_WEBHOOK_CLIENT_STATE"))
    calendar_finder_loaded = bool(env.get("CASEFORGE_CALENDAR_FINDER_WEBHOOK_URL") and env.get("CASEFORGE_CALENDAR_FINDER_WEBHOOK_CLIENT_STATE"))
    print(f"[load_kv_secrets] Graph apps loaded: {', '.join(apps)}")
    if mail_intake_loaded:
        print("[load_kv_secrets] Mail intake webhook settings loaded.")
    if mail_intake_azure_queue_loaded:
        print("[load_kv_secrets] Mail intake Azure Queue relay settings loaded.")
    if email_print_loaded:
        print("[load_kv_secrets] Email print/archive webhook settings loaded.")
    if calendar_finder_loaded:
        print("[load_kv_secrets] Calendar finder webhook settings loaded.")
    if env.get("GRAPH_TENANT_ID"):
        print(f"[load_kv_secrets] Tenant: {env['GRAPH_TENANT_ID']}")
    if env.get("GRAPH_MAILBOX_UPN"):
        print(f"[load_kv_secrets] Mailbox: {env['GRAPH_MAILBOX_UPN']}")
    print(
        "[load_kv_secrets] Nothing was exported to this process's environment "
        "(gh#260) -- a bare call only fetches and reports. Use --shell (eval "
        "into a shell), --save (write .secrets/caseforge-env), or exec -- CMD "
        "(inject into a subprocess) to actually get these values into an "
        "environment."
    )


def _save_env_file(env: dict[str, str]) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    secrets_dir = repo_root / ".secrets"
    secrets_dir.mkdir(mode=0o700, exist_ok=True)
    secrets_dir.chmod(0o700)

    azure_cli_dir = secrets_dir / "azure-cli"
    if azure_cli_dir.exists():
        azure_cli_dir.chmod(0o700)

    streamlit_dir = repo_root / "tools" / "caseforge-chat" / ".streamlit"
    if streamlit_dir.exists():
        streamlit_dir.chmod(0o700)

    env_file = secrets_dir / "caseforge-env"
    lines = ["# CaseForge secrets — generated by load_kv_secrets.py --save\n",
             "# Refresh: eval \"$(python3 tools/load_kv_secrets.py --shell --save)\"\n",
             "# Do not commit — gitignored via .secrets/\n\n"]
    for var, value in sorted(env.items()):
        safe = value.replace("'", "'\\''")
        lines.append(f"export {var}='{safe}'\n")
    env_file.write_text("".join(lines), encoding="utf-8")
    env_file.chmod(0o600)
    print(f"[load_kv_secrets] Secrets saved to {env_file} (chmod 600)", file=sys.stderr)


VAULT_CREDENTIAL_VARS = ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID")
KEEP_SP_ENV = "KV_EXEC_KEEP_SP"


def run_exec_mode(vault: str, cmd: list[str], only: Optional[list[str]] = None,
                  mgmt_vault: Optional[str] = None) -> int:
    if not cmd:
        print("[load_kv_secrets] ERROR: exec mode needs a command after '--', "
              "e.g. `load_kv_secrets.py exec -- rclone sync ...`",
              file=sys.stderr)
        return 2
    if only is not None:
        by_name = {**{row[0]: row[1] for row in SECRET_MAP}, **{row[1]: row[1] for row in SECRET_MAP}}
        unknown = [name for name in only if name not in by_name]
        if unknown or not only:
            print("[load_kv_secrets] ERROR: --only names are not secret env vars: "
                  + (", ".join(unknown) or "(empty list)"), file=sys.stderr)
            return 2
        only = [by_name[name] for name in only]
    secrets = fetch_all_secrets(vault, use_cache=True, mgmt_vault=mgmt_vault)
    if LAST_FETCH_ERRORS:
        print("[load_kv_secrets] ERROR: not starting the command: secrets failed to fetch: "
              + ", ".join(LAST_FETCH_ERRORS), file=sys.stderr)
        return 1
    env = build_env_map(secrets)
    if only is not None:
        env = {name: value for name, value in env.items() if name in only}
    child_env = {**os.environ, **env}
    if only is not None:
        for name in {row[1] for row in SECRET_MAP} - set(only):
            child_env.pop(name, None)
    if os.environ.get(KEEP_SP_ENV, "").strip() != "1":
        for name in VAULT_CREDENTIAL_VARS:
            child_env.pop(name, None)
    try:
        os.execvpe(cmd[0], cmd, child_env)
    except FileNotFoundError:
        print(f"[load_kv_secrets] ERROR: command not found: {cmd[0]}", file=sys.stderr)
        return 127
    except OSError as exc:
        print(f"[load_kv_secrets] ERROR: exec failed: {exc}", file=sys.stderr)
        return 126


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load Graph suite credentials from Azure Key Vault."
    )
    parser.add_argument("--vault", default=DEFAULT_VAULT,
                        help=f"Key Vault name (default: this box's CASEFORGE_KEY_VAULT, else the firm profile's "
                             f"key_vault_name; here {DEFAULT_VAULT})")
    parser.add_argument("--mgmt-vault", default=DEFAULT_MGMT_VAULT,
                        help="Management vault the administrative secrets (MGMT_SECRETS) are read from "
                             f"(default: this box's CASEFORGE_KEY_VAULT_MGMT; here {DEFAULT_MGMT_VAULT or 'none'}). "
                             "Empty: read them from --vault")
    parser.add_argument("--shell", action="store_true",
                        help="DANGER: prints live secrets in plaintext, for eval \"$(...)\" only -- "
                             "never pipe/display/save-and-read this output. Prefer `exec --` or "
                             "--list-keys, which cannot leak a value.")
    parser.add_argument("--list-keys", action="store_true",
                        help="List loaded env var names + a length/shape summary, no values ever "
                             "-- the safe way to check what's available")
    parser.add_argument("--save", action="store_true",
                        help="Save secrets to .secrets/caseforge-env (chmod 600) for unattended cron use")

    subparsers = parser.add_subparsers(dest="mode")
    exec_parser = subparsers.add_parser(
        "exec",
        help="Run a command with secrets injected only into its own environment, never printed",
    )
    exec_parser.add_argument("--only", default=None, metavar="NAME,NAME",
                              help="Pass the child ONLY these secrets (vault or env var names, comma separated)")
    exec_parser.add_argument("cmd", nargs=argparse.REMAINDER,
                              help="Command to run, e.g. -- rclone sync ...")

    args = parser.parse_args()

    try:
        import azure.keyvault.secrets
    except ImportError:
        if subprocess.run(["which", "az"], capture_output=True, timeout=10).returncode != 0:
            print("[load_kv_secrets] ERROR: neither the Azure SDK "
                  "(azure-keyvault-secrets) nor the az CLI is available. "
                  "Run bootstrap.sh, or install either.", file=sys.stderr)
            sys.exit(1)

    if args.mode == "exec":
        cmd = args.cmd
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        only = [n.strip() for n in args.only.split(",") if n.strip()] if args.only is not None else None
        sys.exit(run_exec_mode(args.vault, cmd, only, mgmt_vault=args.mgmt_vault))

    secrets = fetch_all_secrets(args.vault, mgmt_vault=args.mgmt_vault)
    env = build_env_map(secrets)

    if args.save:
        _save_env_file(env)

    if args.list_keys:
        print_key_list(env)
    elif args.shell:
        print_shell_export(env)
    elif not args.save:
        print_summary(env)


if __name__ == "__main__":
    main()
