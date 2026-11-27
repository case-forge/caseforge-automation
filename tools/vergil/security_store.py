from __future__ import annotations

import json
import logging
import sqlite3

import ops_db
from usage import audit_log_export as audit_export

from vergil.primitives import int_env, utc_now_iso as _utc_now_iso
from vergil.security import (
    SECURITY_ALERT_LIMIT,
    SECURITY_ALERT_LOOKBACK_HOURS,
    audit_window_since as _audit_window_since,
    security_alert_ack_path as _security_alert_ack_path,
    security_alert_db_path as _security_alert_db_path,
    security_alert_display_rows as _security_alert_display_rows,
    security_alert_kind as _security_alert_kind,
    security_alert_pattern_key as _security_alert_pattern_key,
    security_alert_pattern_path as _security_alert_pattern_path,
    security_alert_pattern_signature as _security_alert_pattern_signature,
    security_alert_row_key as _security_alert_row_key,
    security_audit_source_counts as _security_audit_source_counts,
    security_bulk_read_signal as _security_bulk_read_signal,
)

log = logging.getLogger(__name__)

SECURITY_ALERT_REPEAT_THRESHOLD = int_env("CASEFORGE_CHAT_SECURITY_REPEAT_THRESHOLD", 2, 2)
SECURITY_AUDIT_PANEL_LIMIT = int_env("CASEFORGE_CHAT_SECURITY_AUDIT_PANEL_LIMIT", 50, 1)
SECURITY_BULK_READ_THRESHOLD = int_env("CASEFORGE_CHAT_SECURITY_BULK_READ_THRESHOLD", 150, 1)


def load_security_alert_pattern_store(username: str) -> dict[str, object]:
    try:
        payload = json.loads(_security_alert_pattern_path(username).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def record_security_alert_patterns(username: str, rows: list[dict[str, str]]) -> dict[str, object]:
    store = load_security_alert_pattern_store(username)
    patterns = store.setdefault("patterns", {})
    if not isinstance(patterns, dict):
        patterns = {}
        store["patterns"] = patterns
    for row in rows:
        pattern_key = _security_alert_pattern_key(row)
        row_key = _security_alert_row_key(row)
        record = patterns.setdefault(
            pattern_key,
            {
                "count": 0,
                "first_seen": str(row.get("CreationTime") or ""),
                "last_seen": "",
                "row_keys": [],
                "signature": _security_alert_pattern_signature(row),
            },
        )
        if not isinstance(record, dict):
            continue
        row_keys = record.setdefault("row_keys", [])
        if not isinstance(row_keys, list):
            row_keys = []
            record["row_keys"] = row_keys
        if row_key and row_key not in row_keys:
            row_keys.append(row_key)
            del row_keys[:-50]
            record["count"] = int(record.get("count") or 0) + 1
        record["last_seen"] = str(row.get("CreationTime") or _utc_now_iso())
        record["signature"] = _security_alert_pattern_signature(row)
    store["updated_at"] = _utc_now_iso()
    try:
        path = _security_alert_pattern_path(username)
        path.parent.mkdir(parents=True, exist_ok=True)
        from atomic_json import atomic_write_json
        atomic_write_json(path, store)
    except Exception:
        pass
    return store


def security_alert_deterministic_explanation(
    username: str,
    rows: list[dict[str, str]],
) -> dict[str, object]:
    store = record_security_alert_patterns(username, rows)
    patterns = store.get("patterns") if isinstance(store, dict) else {}
    patterns = patterns if isinstance(patterns, dict) else {}
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(_security_alert_pattern_key(row), []).append(row)
    if not grouped:
        return {"text": "No high-risk local telemetry rows are currently pending.", "is_repeat": False, "count": 0}
    pattern_key, pattern_rows = max(
        grouped.items(),
        key=lambda item: (
            int((patterns.get(item[0]) or {}).get("count") or 0) if isinstance(patterns.get(item[0]), dict) else 0,
            len(item[1]),
        ),
    )
    newest = pattern_rows[0]
    record = patterns.get(pattern_key) if isinstance(patterns.get(pattern_key), dict) else {}
    count = int(record.get("count") or len(pattern_rows))
    title, meaning, next_step = _security_alert_kind(newest)
    repeat = count >= SECURITY_ALERT_REPEAT_THRESHOLD
    display = _security_alert_display_rows(pattern_rows[:1])[0]
    prefix = "Known repeated alert pattern" if repeat else "First-seen or low-frequency alert pattern"
    text = (
        f"**{prefix}: {title}**\n\n"
        f"{meaning}\n\n"
        f"Seen {count} time{'s' if count != 1 else ''}. Latest: {display.get('Time') or 'unknown time'}; "
        f"operation: `{display.get('Operation') or 'unknown'}`; workload: `{display.get('Workload') or 'unknown'}`; "
        f"result: `{display.get('Result') or 'unknown'}`; source: `{display.get('Source') or 'unknown'}`.\n\n"
        f"Next check: {next_step}"
    )
    return {
        "text": text,
        "is_repeat": repeat,
        "count": count,
        "pattern_key": pattern_key,
        "title": title,
    }


def is_routine_local_alert(row: dict[str, str]) -> bool:
    checker = getattr(audit_export, "is_routine_local_alert", None)
    if callable(checker):
        return bool(checker(row))

    actor_name = str(row.get("UserId") or "").split("/", 1)[0]
    key = (
        str(row.get("EvidenceSource") or ""),
        actor_name,
        str(row.get("Operation") or ""),
        str(row.get("Workload") or ""),
        str(row.get("ResultStatus") or ""),
    )
    return key in {
        ("local.graph_api_calls", "caseforge-startup", "GraphPATCH", "ExchangeCalendar", "Succeeded"),
        ("local.graph_api_calls", "caseforge-startup", "GraphPATCH", "GraphSubscription", "Succeeded"),
        ("local.runtime_activation_events", "graph-index-cron", "graph_index_refresh", "VALAutomation", "success"),
    }


def load_security_alert_ack(username: str) -> str:
    try:
        payload = json.loads(_security_alert_ack_path(username).read_text(encoding="utf-8"))
        return str(payload.get("latest_alert_key") or "")
    except Exception:
        return ""


def load_security_alert_rows() -> tuple[list[dict[str, str]], str]:
    try:
        db_path = _security_alert_db_path()
    except ops_db.OpsDbNotConfiguredError:
        return [], "Security audit DB not configured."
    if not db_path.exists():
        log.warning("security audit DB not found: %s", db_path)
        return [], "Security audit DB not found."
    since = audit_export.default_since(SECURITY_ALERT_LOOKBACK_HOURS)
    until = ""
    query_limit = max(SECURITY_ALERT_LIMIT * 8, SECURITY_BULK_READ_THRESHOLD + 50, 200)
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows: list[dict[str, str]] = []
            rows.extend(audit_export.graph_rows(conn, since, until, query_limit))
            rows.extend(audit_export.runtime_rows(conn, since, until, query_limit))
            high_rows = [
                row for row in audit_export.filter_rows(rows, "high", "")
                if not is_routine_local_alert(row)
            ]
            bulk_signal = _security_bulk_read_signal(conn, since, until, SECURITY_BULK_READ_THRESHOLD)
            if bulk_signal:
                high_rows.append(bulk_signal)
    except sqlite3.Error as exc:
        log.warning("security audit query failed: %s", exc)
        return [], "Security audit query failed."
    high_rows = sorted(high_rows, key=_security_alert_row_key, reverse=True)
    return high_rows[:SECURITY_ALERT_LIMIT], ""


def load_security_audit_rows(
    risk: str = "all",
    *,
    window_key: str = "24h",
    limit: int | None = None,
    contains: str = "",
) -> tuple[list[dict[str, str]], str, dict[str, int]]:
    try:
        db_path = _security_alert_db_path()
    except ops_db.OpsDbNotConfiguredError:
        return [], "Security audit DB not configured.", {}
    if not db_path.exists():
        log.warning("security audit DB not found: %s", db_path)
        return [], "Security audit DB not found.", {}
    since = _audit_window_since(window_key)
    until = ""
    row_limit = max(1, int(limit or SECURITY_AUDIT_PANEL_LIMIT))
    query_limit = max(row_limit * 6, SECURITY_BULK_READ_THRESHOLD + 50, 500)
    try:
        with sqlite3.connect(str(db_path)) as conn:
            counts = _security_audit_source_counts(conn, since, until)
            rows: list[dict[str, str]] = []
            rows.extend(audit_export.graph_rows(conn, since, until, query_limit))
            rows.extend(audit_export.runtime_rows(conn, since, until, query_limit))
            bulk_signal = _security_bulk_read_signal(conn, since, until, SECURITY_BULK_READ_THRESHOLD)
            if bulk_signal:
                rows.append(bulk_signal)
    except sqlite3.Error as exc:
        log.warning("security audit query failed: %s", exc)
        return [], "Security audit query failed.", {}
    rows = audit_export.filter_rows(rows, risk, contains)
    return rows[:row_limit], "", counts


def load_security_change_rows(
    risk: str = "all",
    *,
    window_key: str = "24h",
    limit: int | None = None,
    contains: str = "",
) -> tuple[list[dict[str, str]], str, dict[str, int]]:
    try:
        db_path = _security_alert_db_path()
    except ops_db.OpsDbNotConfiguredError:
        return [], "Security audit DB not configured.", {}
    if not db_path.exists():
        log.warning("security audit DB not found: %s", db_path)
        return [], "Security audit DB not found.", {}
    since = _audit_window_since(window_key)
    until = ""
    row_limit = max(1, int(limit or SECURITY_AUDIT_PANEL_LIMIT))
    try:
        with sqlite3.connect(str(db_path)) as conn:
            counts = _security_audit_source_counts(conn, since, until)
            change_loader = getattr(audit_export, "graph_change_rows", None)
            if callable(change_loader):
                rows = change_loader(conn, since, until, row_limit * 4)
            else:
                rows = fallback_graph_change_rows(conn, since, until, row_limit * 4)
    except (sqlite3.Error, AttributeError) as exc:
        log.warning("security change query failed: %s", exc)
        return [], "Security change query failed.", {}
    rows = audit_export.filter_rows(rows, risk, contains)
    return rows[:row_limit], "", counts


def fallback_graph_change_rows(conn: sqlite3.Connection, since: str, until: str, limit: int) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    fetch_limit = max(limit * 12, 500)
    for row in audit_export.graph_rows(conn, since, until, fetch_limit):
        operation = str(row.get("Operation") or "")
        if not any(method in operation.upper() for method in ("POST", "PUT", "PATCH", "DELETE")):
            continue
        if "preflight" in operation.lower():
            continue
        workload = str(row.get("Workload") or "")
        if not (workload.startswith("SharePoint/OneDrive") or workload == "Exchange"):
            continue
        enriched = dict(row)
        enriched.update(
            {
                "ChangeArea": "OneDrive" if workload.startswith("SharePoint/OneDrive") else "Email",
                "ChangeAction": operation,
                "ChangeItem": str(row.get("SourceFileName") or row.get("DestinationFileName") or "redacted"),
                "ChangeLocation": str(row.get("SiteUrl") or ""),
                "ChangeDetail": "Derived from local Graph telemetry fallback.",
            }
        )
        output.append(enriched)
        if len(output) >= limit:
            break
    return output
