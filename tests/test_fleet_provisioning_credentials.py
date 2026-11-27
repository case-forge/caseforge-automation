from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import load_kv_secrets

FLEET_CREDENTIALS = [
    ("cloudflare-tunnel-token", "CF_TUNNEL_TOKEN"),
]


def _env_names() -> dict[str, str]:
    return {env: kv for kv, env, _required, _desc in load_kv_secrets.SECRET_MAP}


def test_fleet_credentials_are_fetchable_from_key_vault():
    mapped = _env_names()
    missing = [env for _kv, env in FLEET_CREDENTIALS if env not in mapped]
    assert not missing, (
        f"{missing} are not in load_kv_secrets.SECRET_MAP, so storing them in "
        "Key Vault has no effect. The build falls back to the interactive "
        "path without erroring."
    )


def test_fleet_credentials_use_the_expected_vault_secret_names():
    mapped = _env_names()
    for kv_name, env_name in FLEET_CREDENTIALS:
        assert mapped[env_name] == kv_name, (
            f"{env_name} maps to vault secret {mapped[env_name]!r}, not {kv_name!r}. "
            "Renaming it means the secret already in the vault stops being found."
        )


def test_fleet_credentials_are_optional_not_required():
    required = {
        env for _kv, env, is_required, _desc in load_kv_secrets.SECRET_MAP if is_required
    }
    for _kv, env in FLEET_CREDENTIALS:
        assert env not in required, f"{env} must stay optional"


def test_azure_service_principal_is_the_one_credential_that_cannot_come_from_the_vault():
    mapped = _env_names()
    for name in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"):
        assert name not in mapped, (
            f"{name} cannot be loaded from Key Vault -- it is what unlocks Key "
            "Vault. It must come from the environment or a managed identity."
        )
