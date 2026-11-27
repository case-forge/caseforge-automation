from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from products.ikoro import obligation_aging as obligation_aging_lib

from vergil.primitives import csv_env_set, env_truthy
from vergil.user_state import SESSION_DIR, safe_upload_name

DEFAULT_HUB_API_URL = "http://127.0.0.1:8771"


def monitor_ack_path(username: str) -> Path:
    return SESSION_DIR / f"{safe_upload_name(username or 'user')}.monitor-acks.json"


def load_monitor_acks(username: str) -> set[str]:
    try:
        payload = json.loads(monitor_ack_path(username).read_text(encoding="utf-8"))
        return set(payload) if isinstance(payload, list) else set()
    except Exception:
        return set()


def load_monitor_obligations() -> tuple[list[dict], str]:
    try:
        import clientdb_sql

        rows = clientdb_sql.list_open_obligation_rows()
    except Exception as exc:
        return [], str(exc)
    try:
        now = dt.datetime.now(dt.timezone.utc)
        return obligation_aging_lib.compute_obligations(rows, now=now), ""
    except Exception as exc:
        return [], str(exc)


def monitor_enabled(username: str | None, guest: bool) -> bool:
    if guest or not username:
        return False
    if not env_truthy("CASEFORGE_MONITOR_ENABLED", True):
        return False
    users = csv_env_set("CASEFORGE_MONITOR_USERS")
    if users:
        return "*" in users or username.lower() in users
    return True


def monitor_ob_key(ob: dict) -> str:
    return f"{ob.get('matter_id')}|{ob.get('obligation')}|{ob.get('urgency')}"


def write_monitor_acks(username: str, keys: set[str]) -> None:
    try:
        path = monitor_ack_path(username)
        path.parent.mkdir(parents=True, exist_ok=True)
        from atomic_json import atomic_write_json
        atomic_write_json(path, sorted(keys)[-500:], indent=None)
    except Exception:
        pass


def monitor_urgency_style(urgency: str) -> tuple[str, str]:
    return {
        "red": ("#7f1d1d", ":material/error:"),
        "amber": ("#92400e", ":material/warning:"),
        "green": ("#14532d", ":material/schedule:"),
    }.get(urgency, ("#374151", ":material/info:"))


def monitor_action_prompt(ob: dict) -> str:
    ref = str(ob.get("matter_ref") or "")
    obligation = str(ob.get("obligation") or "")
    prompts = {
        "send_to_client": f"Draft the client cover email sending the order for matter {ref}.",
        "book_counsel": f"Help me book counsel for the upcoming hearing on matter {ref}; prepare the counsel availability request.",
        "arrange_service": f"Prepare the process-server service step for matter {ref}.",
        "prepare_bundle": f"Start the hearing bundle preparation for matter {ref}.",
    }
    return prompts.get(obligation, f"What is the next step for matter {ref}?")


def fetch_intern_audit_recent(limit: int = 10, *, timeout: float = 5.0) -> tuple[list[dict], str]:
    token = os.getenv("CASEFORGE_CHAT_API_TOKEN", "").strip()
    if not token:
        return [], "intern audit unavailable"
    base_url = (os.getenv("CASEFORGE_HUB_API_URL", "").strip() or DEFAULT_HUB_API_URL).rstrip("/")
    url = f"{base_url}/retrieval/audit?limit={int(limit)}"
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return [], "intern audit unavailable"
    entries = payload.get("entries")
    return (list(entries) if isinstance(entries, list) else []), ""
