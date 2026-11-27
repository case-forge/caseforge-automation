from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

import ops_db
from usage import audit_log_export as audit_export

from vergil.primitives import (
    REPO_ROOT,
    csv_env_set,
    env_truthy,
    int_env,
    normalise_space,
    safe_upload_name,
    utc_now_iso,
)

SESSION_DIR = Path.home() / ".caseforge-chat-sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

SECURITY_ALERT_LOOKBACK_HOURS = int_env("CASEFORGE_CHAT_SECURITY_ALERT_HOURS", 6, 1)
SECURITY_ALERT_LIMIT = int_env("CASEFORGE_CHAT_SECURITY_ALERT_LIMIT", 5, 1)
SECURITY_AUDIT_WINDOW_OPTIONS = {
    "6h": ("6 hours", 6),
    "24h": ("24 hours", 24),
    "72h": ("3 days", 72),
    "168h": ("7 days", 168),
    "720h": ("30 days", 720),
    "all": ("All local", 0),
}
SECURITY_AUDIT_PANEL_HOURS = int_env("CASEFORGE_CHAT_SECURITY_AUDIT_PANEL_HOURS", 24, 1)
SECURITY_BULK_READ_IGNORE_ACTORS = {
    item.strip().lower()
    for item in os.getenv("CASEFORGE_CHAT_SECURITY_BULK_READ_IGNORE_ACTORS", "graph-index-cron").split(",")
    if item.strip()
}


def security_notifications_enabled(username: str | None, guest: bool) -> bool:
    if guest or not username or not env_truthy("CASEFORGE_CHAT_SECURITY_NOTIFICATIONS"):
        return False
    notify_users = csv_env_set("CASEFORGE_CHAT_SECURITY_NOTIFY_USERS")
    if not notify_users:
        return False
    return "*" in notify_users or username.lower() in notify_users


def security_alert_db_path() -> Path:
    override = os.getenv("CASEFORGE_CHAT_SECURITY_AUDIT_DB", "").strip()
    if override:
        return Path(override)
    return ops_db.resolve_ops_db_path()


def security_alert_ack_path(username: str) -> Path:
    return SESSION_DIR / f"{safe_upload_name(username or 'user')}.security-alerts.json"


def security_alert_pattern_path(username: str) -> Path:
    return SESSION_DIR / f"{safe_upload_name(username or 'user')}.security-alert-patterns.json"


def security_alert_row_key(row: dict[str, str]) -> str:
    return f"{row.get('CreationTime', '')}|{row.get('LocalEventId', '')}"


def security_alert_pattern_signature(row: dict[str, str]) -> dict[str, str]:
    actor = str(row.get("UserId") or "").split("/", 1)[0]
    result = re.sub(r"\b\d+\b", "#", normalise_space(str(row.get("ResultStatus") or "")))
    return {
        "risk": str(row.get("RiskLevel") or "").lower(),
        "operation": normalise_space(str(row.get("Operation") or "")),
        "workload": normalise_space(str(row.get("Workload") or "")),
        "result": result[:180],
        "source": normalise_space(str(row.get("EvidenceSource") or "")),
        "actor": normalise_space(actor),
        "record_type": normalise_space(str(row.get("RecordType") or "")),
        "change_area": normalise_space(str(row.get("ChangeArea") or "")),
        "change_action": normalise_space(str(row.get("ChangeAction") or "")),
    }


def security_alert_pattern_key(row: dict[str, str]) -> str:
    payload = json.dumps(security_alert_pattern_signature(row), sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def security_alert_kind(row: dict[str, str]) -> tuple[str, str, str]:
    operation = str(row.get("Operation") or "")
    workload = str(row.get("Workload") or "")
    result = str(row.get("ResultStatus") or "")
    source = str(row.get("EvidenceSource") or "")
    text = f"{operation} {workload} {result} {source}".lower()
    if operation == "BulkGraphReadVolume":
        return (
            "High OneDrive read volume",
            "This is a review signal from local telemetry showing unusually heavy Graph file-read activity. It is not proof of exfiltration by itself.",
            "Check whether the graph indexer, a known audit, or an approved worker was running at the same time. If not, open Audit and review the actor/runtime and time window.",
        )
    if "blocked" in text:
        return (
            "Blocked Graph operation",
            "A local guardrail or preflight blocked a Graph operation. That is high risk because the attempted action touched live Microsoft 365 data, but the block usually means the safeguard worked.",
            "Check the actor/runtime and operation. If it matches an expected blocked safety check, acknowledge it; otherwise inspect the related job before retrying anything.",
        )
    if any(word in text for word in ("delete", "deleted", "purge", "remove", "removed")):
        return (
            "Potential deletion/removal action",
            "The telemetry describes a delete, purge, remove, or similar action. This deserves human review because live mailbox, OneDrive, or local data could be affected.",
            "Confirm the action was explicitly authorised, verify the destination/source, and do not retry until the audit row matches an approved workflow.",
        )
    if any(word in text for word in ("patch", "put", "post", "move", "rename", "write", "upload")):
        return (
            "Write/change operation",
            "The telemetry describes a write or change operation against a live system. That can be routine, but it should be checked when marked high risk.",
            "Check whether it came from the expected worker and matter. If the actor or timing is unexpected, treat it as unresolved until reviewed.",
        )
    if "runtime_activation_events" in source:
        return (
            "Local runtime high-risk event",
            "A local automation runtime reported a high-risk command or metric. This is about local tool behaviour, not a Purview tenant alert.",
            "Review the command label, files written, and task context in the local audit panel. Do not expose raw secrets or raw payloads while reviewing.",
        )
    return (
        "Unknown high-risk telemetry pattern",
        "This high-risk row does not match a known deterministic class yet. It still has enough redacted fields to identify the operation type and actor without using raw paths or secrets.",
        "Use Audit for the redacted source row, compare actor/time with expected jobs, and use Ask AI only if the deterministic summary is not enough.",
    )


def write_security_alert_ack(username: str, latest_key: str) -> None:
    path = security_alert_ack_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "latest_alert_key": latest_key,
                "acknowledged_at": utc_now_iso(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def security_bulk_read_signal(
    conn: sqlite3.Connection,
    since: str,
    until: str,
    threshold: int,
) -> dict[str, str] | None:
    ignored_actors = tuple(sorted(SECURITY_BULK_READ_IGNORE_ACTORS))
    ignored_clause = ""
    ignored_params: tuple[str, ...] = ()
    if ignored_actors:
        ignored_clause = "AND lower(COALESCE(runtime_label, '')) NOT IN ({})".format(
            ",".join("?" for _ in ignored_actors)
        )
        ignored_params = ignored_actors
    query = """
        SELECT COUNT(*), MAX(timestamp)
        FROM graph_api_calls
        WHERE method = 'GET'
          AND (? = '' OR timestamp >= ?)
          AND (? = '' OR timestamp <= ?)
          {ignored_clause}
          AND (
              call_type = 'graph-file-http-call'
              OR lower(url) LIKE '%/drive%'
              OR lower(url) LIKE '%/drives/%'
          )
    """.format(ignored_clause=ignored_clause)
    count, latest = conn.execute(query, (since, since, until, until, *ignored_params)).fetchone()
    count = int(count or 0)
    if count < threshold:
        return None
    latest_time = audit_export.parse_time(str(latest or "")) or utc_now_iso()
    return {
        "CreationTime": latest_time,
        "RecordType": "local_security_signal",
        "Workload": "SharePoint/OneDrive",
        "Operation": "BulkGraphReadVolume",
        "UserId": "local-runtime",
        "ClientIP": "local-runtime",
        "ObjectId": "redacted",
        "SiteUrl": "",
        "SourceFileName": "",
        "SourceRelativeUrl": "",
        "DestinationFileName": "",
        "DestinationRelativeUrl": "",
        "ResultStatus": f"{count} Graph file read calls in {SECURITY_ALERT_LOOKBACK_HOURS}h",
        "RiskLevel": "review",
        "EvidenceSource": "local.graph_api_calls.aggregate",
        "LocalEventId": f"bulk-graph-read-{latest_time}-{count}",
        "AuditData": audit_export.compact_json(
            {
                "count": count,
                "threshold": threshold,
                "since": since,
                "until": until,
                "note": "High read volume is a review signal, not proof of exfiltration.",
            }
        ),
    }


def audit_window_since(window_key: str) -> str:
    _label, hours = SECURITY_AUDIT_WINDOW_OPTIONS.get(
        str(window_key or "24h"),
        SECURITY_AUDIT_WINDOW_OPTIONS.get("24h", ("24 hours", SECURITY_AUDIT_PANEL_HOURS)),
    )
    if int(hours or 0) <= 0:
        return ""
    return audit_export.default_since(int(hours))


def audit_window_label(window_key: str) -> str:
    label, _hours = SECURITY_AUDIT_WINDOW_OPTIONS.get(
        str(window_key or "24h"),
        SECURITY_AUDIT_WINDOW_OPTIONS.get("24h", ("24 hours", SECURITY_AUDIT_PANEL_HOURS)),
    )
    return label


def security_audit_source_counts(conn: sqlite3.Connection, since: str, until: str) -> dict[str, int]:
    params = (since, since, until, until)
    graph_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM graph_api_calls
        WHERE (? = '' OR timestamp >= ?)
          AND (? = '' OR timestamp <= ?)
        """,
        params,
    ).fetchone()[0]
    runtime_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM runtime_activation_events
        WHERE (? = '' OR timestamp >= ?)
          AND (? = '' OR timestamp <= ?)
        """,
        params,
    ).fetchone()[0]
    return {"graph": int(graph_count or 0), "runtime": int(runtime_count or 0)}


def security_alert_display_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    display_rows = []
    for row in rows[:SECURITY_ALERT_LIMIT]:
        display_rows.append(
            {
                "Time": str(row.get("CreationTime") or "")[:19].replace("T", " "),
                "Risk": str(row.get("RiskLevel") or ""),
                "Operation": str(row.get("Operation") or ""),
                "Workload": str(row.get("Workload") or ""),
                "Result": str(row.get("ResultStatus") or ""),
                "Source": str(row.get("EvidenceSource") or ""),
                "Local ID": str(row.get("LocalEventId") or "")[:12],
            }
        )
    return display_rows


def security_alert_explain_prompt(rows: list[dict[str, str]]) -> str:
    safe_rows = security_alert_display_rows(rows)
    return (
        "Explain these redacted CaseForge local telemetry alerts in plain English for a caseworker. "
        "Say what the event likely means, whether it looks routine, blocked, or genuinely risky, "
        "and what to check next. Do not ask for raw telemetry, secrets, file paths, tokens, or passwords. "
        "Use only this redacted table:\n\n"
        f"{json.dumps(safe_rows, ensure_ascii=False, indent=2)}"
    )


def security_audit_display_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                "Time": str(row.get("CreationTime") or "")[:19].replace("T", " "),
                "Risk": str(row.get("RiskLevel") or ""),
                "Workload": str(row.get("Workload") or ""),
                "Operation": str(row.get("Operation") or ""),
                "Result": str(row.get("ResultStatus") or ""),
                "Actor": str(row.get("UserId") or ""),
                "Source": str(row.get("EvidenceSource") or ""),
                "Local ID": str(row.get("LocalEventId") or "")[:16],
            }
        )
    return display_rows


def security_change_display_rows(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    display_rows = []
    for row in rows[:limit]:
        display_rows.append(
            {
                "Time": str(row.get("CreationTime") or "")[:19].replace("T", " "),
                "Area": str(row.get("ChangeArea") or ""),
                "Action": str(row.get("ChangeAction") or ""),
                "Item": str(row.get("ChangeItem") or ""),
                "Location": str(row.get("ChangeLocation") or ""),
                "Result": str(row.get("ResultStatus") or ""),
                "Actor": str(row.get("UserId") or ""),
                "Local ID": str(row.get("LocalEventId") or "")[:16],
                "Detail": str(row.get("ChangeDetail") or ""),
            }
        )
    return display_rows
