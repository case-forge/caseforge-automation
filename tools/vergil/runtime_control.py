from __future__ import annotations

import os
import signal
from typing import Mapping


ADMIN_USERS_ENV = "CASEFORGE_CHAT_ADMIN_USERS"


def _env_names(var: str) -> set[str]:
    return {part.strip().lower() for part in os.getenv(var, "").split(",") if part.strip()}


def env_dev_users() -> set[str]:
    return _env_names("CASEFORGE_DEV_USERS")


def env_tailnet_dev_logins() -> set[str]:
    return _env_names("CASEFORGE_TAILNET_DEV_LOGINS")


def env_admin_users() -> set[str]:
    return _env_names(ADMIN_USERS_ENV) | env_dev_users()


def is_env_admin(username: str) -> bool:
    name = str(username or "").strip().lower()
    return bool(name) and name in env_admin_users()


def is_env_dev(username: str) -> bool:
    name = str(username or "").strip().lower()
    return bool(name) and name in env_dev_users()


def is_tailnet_dev_login(login: str) -> bool:
    name = str(login or "").strip().lower()
    return bool(name) and name in env_tailnet_dev_logins()


def restart_permitted(username: str, users: Mapping) -> bool:
    if is_env_admin(username):
        return True
    roles = (users.get(username, {}) or {}).get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    return any(str(role).strip().lower() in {"admin", "supervisor"} for role in roles)


def kill_active_process(run: dict, reason: str) -> None:
    if run.get("finished"):
        return
    run["cancel_reason"] = reason
    run["cancel_requested"] = True
    run["timeout_requested"] = reason.lower().startswith("timed out")
    proc = run.get("process")
    pgid = run.get("pgid")
    try:
        if pgid:
            os.killpg(pgid, signal.SIGTERM)
        elif proc:
            proc.terminate()
    except ProcessLookupError:
        pass
    except Exception:
        pass


def ensure_graph_env_for_current_process(env: Mapping[str, str]) -> None:
    for key in (
        "GRAPH_TENANT_ID",
        "GRAPH_MAILBOX_UPN",
        "GRAPH_FILES_CLIENT_ID",
        "GRAPH_FILES_CLIENT_SECRET",
        "GRAPH_MAIL_CLIENT_ID",
        "GRAPH_MAIL_CLIENT_SECRET",
        "GRAPH_CLIENT_ID",
        "GRAPH_CLIENT_SECRET",
        "SHAREPOINT_CLIENT_FILES_SITE_ID",
    ):
        value = str(env.get(key) or "").strip()
        if value and not os.environ.get(key):
            os.environ[key] = value
