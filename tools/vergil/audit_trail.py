from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

try:
    import actor_kind
except ImportError:
    from tools import actor_kind

FILE_ACTIONS = {
    "FileUploaded": "Uploaded", "FileModified": "Edited", "FileRenamed": "Renamed", "FileMoved": "Moved", "FileRecycled": "Deleted",
    "FileDeleted": "Deleted", "FileCopied": "Copied", "FileRestored": "Restored", "FolderCreated": "Created folder",
    "FolderRenamed": "Renamed folder", "FolderMoved": "Moved folder", "FolderRecycled": "Deleted folder", "FolderDeleted": "Deleted folder",
    "FolderCopied": "Copied folder", "FolderRestored": "Restored folder",
}
MAIL_ACTIONS = {
    "Create": "Created email", "Update": "Changed email", "Send": "Sent email", "SoftDelete": "Deleted email", "HardDelete": "Permanently deleted email",
    "MoveToDeletedItems": "Deleted email", "Move": "Moved email", "MailItemsAccessed": "Opened email",
}
GRAPH_ACTIONS = {
    "move": "Moved", "rename": "Renamed", "delete": "Deleted", "create_folder": "Created folder", "upload_file": "Uploaded",
    "PUT": "Uploaded", "DELETE": "Deleted", "POST": "Created", "PATCH": "Changed",
}
AUTOMATION_EDITORS = ("system:", "claude", "automatic", "case flow", "robot", "agent")
MATCH_SECONDS = 3
CRM_MATCH_SECONDS = 3
ADDRESS_WINDOW_HOURS = 6
LOG_TAIL_BYTES = 60 * 1024 * 1024


def _sha(text: str) -> str:
    text = (text or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def _ts(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(text: Any) -> dict[str, Any]:
    try:
        data = json.loads(text or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_automation_editor(name: str) -> bool:
    lowered = (name or "").strip().lower()
    return not lowered or lowered.startswith(AUTOMATION_EDITORS) or lowered in {"automatic", "case flow"}




def _log_rows(path: Path | None, since: dt.datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path or not Path(path).is_file():
        return rows
    since_text = _iso(since)
    with open(path, "rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - LOG_TAIL_BYTES))
        if size > LOG_TAIL_BYTES:
            handle.readline()
        for raw in handle:
            if b'"remote_user": "' not in raw or b'"remote_user": ""' in raw:
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if str(row.get("ts", "")) >= since_text and row.get("remote_user"):
                rows.append(row)
    return rows


class Access:

    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        writes = [(_ts(r.get("ts", "")), r) for r in rows if r.get("method") not in (None, "GET", "HEAD", "OPTIONS")]
        self._writes = sorted(((t, r["remote_user"]) for t, r in writes if t), key=lambda x: x[0])
        self._times = [t for t, _ in self._writes]
        self._by_ip: dict[str, list[tuple[dt.datetime, str]]] = {}
        for row in rows:
            ip, when = str(row.get("client_ip") or ""), _ts(row.get("ts", ""))
            if ip and when:
                self._by_ip.setdefault(ip, []).append((when, str(row["remote_user"])))

    def person_making_a_change_at(self, when: dt.datetime) -> str:
        lo = bisect.bisect_left(self._times, when - dt.timedelta(seconds=CRM_MATCH_SECONDS))
        hi = bisect.bisect_right(self._times, when + dt.timedelta(seconds=CRM_MATCH_SECONDS))
        people = {who for _, who in self._writes[lo:hi]}
        return people.pop() if len(people) == 1 else ""

    def person_at_address(self, ip: str, when: dt.datetime) -> str:
        near = {who for seen, who in self._by_ip.get(ip, []) if abs((seen - when).total_seconds()) <= ADDRESS_WINDOW_HOURS * 3600}
        return near.pop() if len(near) == 1 else ""




def _ms_rows(conn: sqlite3.Connection, since: str, until: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in conn.execute(
        "SELECT id, created_utc, workload, operation, user_upn, user_type, app_id, client_ip, source_path, dest_path, source_name, dest_name, site_url "
        "FROM ms_audit_events WHERE created_utc >= ? AND created_utc <= ? ORDER BY created_utc DESC", (since, until)
    ):
        id_, at, workload, op, upn, utype, app, ip, src, dst, sname, dname, site = r
        if workload in ("SharePoint", "OneDrive"):
            area, action = ("folder" if op.startswith("Folder") else "file"), FILE_ACTIONS.get(op, op)
            what_from, what_to, what = (src, dst, "") if dst and dst != src else ("", "", src or sname)
            where = (src.rsplit("/", 1)[0] if src else "")
        elif workload == "Exchange":
            area, action = "mail", MAIL_ACTIONS.get(op, op)
            what_from, what_to = (src, dst) if dst else ("", "")
            what, where = (sname or "(no subject)"), (src or site)
        else:
            area, action = "admin", op.rstrip(".")
            what_from = what_to = ""
            what, where = sname, ""
        human = utype == "Regular"
        out.append({
            "id": "ms:" + id_, "at": at, "kind": actor_kind.PERSON if human else actor_kind.AUTOMATION, "who": upn if human else f"app {app[:8]}" if app else "an app",
            "area": area, "action": action, "what": what, "from": what_from, "to": what_to, "where": where, "ip": ip, "seen_by": ["microsoft"],
            "_hash": _sha(src), "_op": action, "_when": _ts(at),
        })
    return out


def _tel_file_op(payload: dict[str, Any], method: str) -> str:
    return GRAPH_ACTIONS.get(str(payload.get("graph_action") or ""), GRAPH_ACTIONS.get(method, method))


def _tel_rows(conn: sqlite3.Connection, since: str, until: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ts, method, call_type, url, label, payload_json in conn.execute(
        "SELECT timestamp, method, call_type, url, runtime_label, payload_json FROM graph_api_calls "
        "WHERE method IN ('PUT','POST','PATCH','DELETE') AND success = 1 AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC", (since, until)
    ):
        payload = _json(payload_json)
        seen.add(str(payload.get("event_id") or ""))
        row = _tel_row(ts, method, call_type, url, label, payload)
        if row:
            out.append(row)
    for payload in _fallback_events(since, until):
        if str(payload.get("event_id") or "") in seen:
            continue
        row = _tel_row(str(payload.get("timestamp") or ""), str(payload.get("method") or ""), str(payload.get("type") or ""),
                       str(payload.get("url") or ""), str(payload.get("runtime_label") or ""), payload)
        if row:
            out.append(row)
    return out


def _fallback_events(since: str, until: str) -> list[dict[str, Any]]:
    try:
        import graph_write_audit

        lines = graph_write_audit.jsonl_path().read_text(encoding="utf-8").splitlines()
    except (ImportError, OSError):
        return []
    events = [_json(line) for line in lines]
    return [e for e in events if e.get("success") and since <= str(e.get("timestamp", "")) <= until]


def _tel_row(ts: str, method: str, call_type: str, url: str, label: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if str(payload.get("phase") or "response") == "preflight":
        return None
    is_file = "file" in str(payload.get("type") or call_type or "")
    who = label or payload.get("runtime_label") or "unlabelled"
    kind = actor_kind.clean(payload.get("actor_kind")) or actor_kind.AUTOMATION
    row: dict[str, Any] = {"id": "tel:" + str(payload.get("event_id") or ts), "at": ts[:19] + "Z", "kind": kind, "who": who, "ip": "", "seen_by": ["ours"], "_when": _ts(ts)}
    if is_file:
        old, new, path = str(payload.get("old_path") or ""), str(payload.get("new_path") or ""), str(payload.get("path") or "")
        action = _tel_file_op(payload, method)
        folder = payload.get("item_kind") == "folder" or payload.get("graph_action") == "create_folder"
        row.update({
            "area": "folder" if folder else "file", "action": (action + " folder") if folder and action in ("Moved", "Renamed", "Deleted") else action,
            "what": "" if new else (path or old or str(payload.get("item_name") or "(name not recorded)")),
            "from": old if new else "", "to": new, "where": str(payload.get("parent_path") or (old.rsplit("/", 1)[0] if old else "")) or str(payload.get("parent_scope") or payload.get("path_scope") or ""),
            "_hash": str(payload.get("path_hash") or _sha(old) or _sha(path)), "_op": action,
        })
    else:
        body = payload.get("body_summary") if isinstance(payload.get("body_summary"), dict) else {}
        if str(payload.get("target_ref") or "").startswith("category") or "mastercategories" in url.lower():
            area, action = "mail", "Changed email categories"
        else:
            area, action = "mail", {"POST": "Created email", "PATCH": "Changed email", "DELETE": "Deleted email", "PUT": "Changed email"}.get(method, method)
        row.update({
            "area": area, "action": action, "what": str(body.get("subject") or payload.get("target_id") or ""), "from": "", "to": str(body.get("destination_id") or ""),
            "where": str(payload.get("mailbox") or ""), "_hash": "", "_op": action,
        })
    for key, field in (("program", "program"), ("unit", "unit"), ("caller", "caller"), ("matter_id", "matter_id"), ("item_id", "item_id"), ("host", "host")):
        if payload.get(field):
            row[key] = payload[field]
    return row


def _edit_rows(conn: sqlite3.Connection, since: str, until: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edit_id, matter_id, field, old, new, by, created in conn.execute(
        "SELECT edit_id, matter_id, field_name, old_value, new_value, edited_by, created_at FROM client_edit_history WHERE created_at >= ? AND created_at <= ? ORDER BY created_at DESC", (since, until)
    ):
        out.append({
            "id": "edit:" + str(edit_id), "at": str(created)[:19] + "Z", "kind": actor_kind.AUTOMATION if is_automation_editor(by) else actor_kind.PERSON, "who": by or "unknown",
            "area": "record", "action": f"Edited {field}", "what": "", "from": str(old or "")[:160], "to": str(new or "")[:160], "where": f"Matter {matter_id}", "ip": "", "seen_by": ["ours"],
            "_hash": "", "_op": "", "_when": _ts(created),
        })
    return out


FLOW_STARTED = "started"


def _flow_rows(conn: sqlite3.Connection, since: str, until: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        found = conn.execute(
            "SELECT event_id, matter_id, step, status, summary, by_name, mode, created_utc, instance, actor_kind FROM pipeline_events "
            "WHERE created_utc >= ? AND created_utc <= ? AND status <> ? ORDER BY created_utc DESC", (since, until, FLOW_STARTED)
        ).fetchall()
    except sqlite3.OperationalError:
        return out
    for event_id, matter_id, step, status_, summary, by, mode, created, instance, stored_kind in found:
        mid = str(matter_id or "")
        out.append({
            "id": "flow:" + str(event_id), "at": str(created)[:19] + "Z", "kind": actor_kind.for_stored(stored_kind, by), "who": by or "unknown",
            "area": "case flow", "action": f"Case flow {step}" + ("" if status_ in ("ok", "info") else f" ({status_})"), "what": str(summary or ""),
            "from": "", "to": "", "where": f"Matter {mid}" if mid else "Every client", "ip": "", "seen_by": ["ours"],
            "mode": str(mode or ""), "_hash": "", "_op": "", "_when": _ts(created),
            **({"matter_id": mid} if mid else {}), **({"instance": str(instance)} if instance else {}),
        })
    return out


def _link_rows(conn: sqlite3.Connection, since: str, until: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from onboarding.pipeline import provenance

        out += provenance.trail_rows(conn, since, until)
    except Exception:
        pass
    try:
        try:
            from vergil import activity_views
        except ImportError:
            from tools.vergil import activity_views

        out += activity_views.trail_rows(conn, since, until)
    except Exception:
        pass
    return out




def _merge(ms: list[dict[str, Any]], tel: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in ms:
        if row["_hash"]:
            index.setdefault(row["_hash"], []).append(row)
    taken: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in tel:
        match = None
        if row["_hash"] and row.get("_when"):
            for candidate in index.get(row["_hash"], []):
                if candidate["id"] in taken or not candidate.get("_when") or candidate["_op"] != row["_op"]:
                    continue
                if abs((candidate["_when"] - row["_when"]).total_seconds()) <= MATCH_SECONDS:
                    match = candidate
                    break
        if match:
            taken.add(match["id"])
            row = {**row, "seen_by": ["ours", "microsoft"], "ip": match["ip"], "from": row["from"] or match["from"], "to": row["to"] or match["to"],
                   "what": row["what"] or match["what"], "where": row["where"] or match["where"]}
        merged.append(row)
    merged.extend(r for r in ms if r["id"] not in taken)
    return merged


def collect(conn: sqlite3.Connection, *, days: int = 7, request_log: Path | None = None, now: dt.datetime | None = None) -> tuple[list[dict[str, Any]], str, str]:
    end = now or dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=max(1, min(int(days), 90)))
    since, until = _iso(start), _iso(end + dt.timedelta(minutes=1))
    rows = _merge(_ms_rows(conn, since, until), _tel_rows(conn, since, until)) + _edit_rows(conn, since, until) + _flow_rows(conn, since, until)
    rows += _link_rows(conn, since, until)

    access = Access(_log_rows(request_log, start - dt.timedelta(hours=ADDRESS_WINDOW_HOURS)))
    for row in rows:
        when = row.get("_when")
        if not when:
            continue
        if row["who"] == "hub-api":
            person = access.person_making_a_change_at(when)
            row["who"], row["kind"] = (person or "the CRM (person not recorded)"), actor_kind.PERSON
        elif row["kind"] == actor_kind.PERSON and row.get("ip"):
            row["likely_crm_user"] = access.person_at_address(row["ip"], when)
    for row in rows:
        for key in ("_hash", "_op", "_when"):
            row.pop(key, None)
    return rows, since, until


def trail(conn: sqlite3.Connection, *, kind: str = "all", days: int = 7, q: str = "", limit: int = 100, offset: int = 0,
          request_log: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    rows, since, until = collect(conn, days=days, request_log=request_log, now=now)
    counts = {k: sum(1 for r in rows if r["kind"] == k) for k in actor_kind.KINDS}
    if kind in actor_kind.KINDS:
        rows = [r for r in rows if r["kind"] == kind]
    needle = (q or "").strip().lower()
    if needle:
        rows = [r for r in rows if needle in " ".join(str(r.get(k, "")) for k in ("who", "action", "what", "from", "to", "where", "ip", "likely_crm_user", "program", "unit", "caller", "matter_id", "mode")).lower()]
    rows.sort(key=lambda r: r["at"], reverse=True)
    limit = max(1, min(int(limit), 500))
    return {"rows": rows[offset: offset + limit], "total": len(rows), "counts": counts, "since": since, "until": until, "kind": kind}
