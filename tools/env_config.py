
from __future__ import annotations

import os
import re
from pathlib import Path

try:
    import firm_profile
except ImportError:
    from tools import firm_profile

_DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".secrets" / "caseforge-env"

_LINE_RE = re.compile(
    r"""^\s*(?:export\s+)?
        (?P<key>[A-Za-z_][A-Za-z0-9_]*)
        =
        (?P<value>.*)$""",
    re.VERBOSE,
)


def _env_file_path() -> Path:
    override = os.environ.get("CASEFORGE_ENV_FILE", "").strip()
    return Path(override) if override else _DEFAULT_ENV_FILE


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _read_env_file() -> dict[str, str]:
    path = _env_file_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        values[match.group("key")] = _unquote(match.group("value"))
    return values


def get(name: str, default: str = "") -> str:
    env_value = os.environ.get(name, "")
    if env_value.strip():
        return env_value
    file_value = _read_env_file().get(name, "")
    if file_value.strip():
        return file_value
    return default


class Secret:
    __slots__ = ("_v",)
    def __init__(self, v): self._v = v
    def __str__(self):  return "***"
    def __repr__(self): return "<Secret ***>"
    def reveal(self):   return self._v



_VAULT_NAME = firm_profile.load_profile().key_vault_name
_kv_client = None
_kv_cache: dict[str, "Secret"] = {}


def _make_kv_client():
    from azure.identity import (
        AzureCliCredential,
        ChainedTokenCredential,
        EnvironmentCredential,
    )
    from azure.keyvault.secrets import SecretClient

    credential = ChainedTokenCredential(EnvironmentCredential(), AzureCliCredential())
    vault = os.environ.get("CASEFORGE_KEY_VAULT_NAME", "").strip() or _VAULT_NAME
    return SecretClient(vault_url=f"https://{vault}.vault.azure.net/", credential=credential)


def get_secret(kv_name: str, *, env_var: str | None = None) -> "Secret":
    env_name = env_var or kv_name.upper().replace("-", "_")
    from_env = get(env_name, "")
    if from_env:
        return Secret(from_env)

    if kv_name in _kv_cache:
        return _kv_cache[kv_name]

    global _kv_client
    try:
        if _kv_client is None:
            _kv_client = _make_kv_client()
        value = _kv_client.get_secret(kv_name).value or ""
    except ImportError as exc:
        raise RuntimeError(
            "azure-identity / azure-keyvault-secrets are not installed on this "
            "box -- run bootstrap.sh (they are in requirements.txt)"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"could not read '{kv_name}' from Key Vault {_VAULT_NAME}: not in "
            f"the environment, and the vault read failed. On a box with no "
            f"'az login', run tools/load_kv_secrets.py --save on a logged-in "
            f"box or complete 'az login' here. ({type(exc).__name__})"
        ) from exc
    if not value:
        raise RuntimeError(f"Key Vault secret '{kv_name}' exists but is empty")
    secret = Secret(value)
    _kv_cache[kv_name] = secret
    return secret
