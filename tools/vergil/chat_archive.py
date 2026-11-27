from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from vergil_chat import vergil_chat_ai_helpers as ai_helpers
from london_time import london_today
from vergil.model_provider import provider_session_ids
from vergil.user_state import archive_dir


def generate_title(messages: list) -> str:
    try:
        suggested = ai_helpers.suggest_chat_title(messages)
        title = str(suggested.get("title") or "").strip()
        if title:
            return title[:80]
    except Exception:
        pass
    for m in messages:
        if m.get("role") == "user" and m.get("content", "").strip():
            t = m["content"].strip().replace("\n", " ")
            return t[:45] + ("…" if len(t) > 45 else "")
    return f"Chat {london_today().strftime('%d %b %Y')}"


def normalise_message_for_hash(message: dict) -> dict:
    tools = []
    for tool in message.get("tools", []) or []:
        if isinstance(tool, dict):
            tools.append(
                {
                    "name": str(tool.get("name", "")),
                    "detail": str(tool.get("detail", "")),
                    "type": str(tool.get("type", "")),
                }
            )
    return {
        "role": str(message.get("role", "")),
        "content": str(message.get("content", "")).strip(),
        "tools": tools,
        "model": str(message.get("model", "")),
        "terminal_state": str(message.get("terminal_state", "")),
    }


def content_hash(messages: list) -> str:
    normalised = [normalise_message_for_hash(m) for m in messages if isinstance(m, dict)]
    blob = json.dumps(normalised, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def latest_archive_for_user(username: str) -> dict | None:
    files = sorted(archive_dir(username).glob("*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def archived_session_with_hash(username: str, content_hash_value: str) -> dict | None:
    if not content_hash_value:
        return None
    for path in sorted(archive_dir(username).glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(data.get("content_hash") or "") == content_hash_value:
            return data
    return None


def archive_messages(username: str, messages: list, provider_state: dict | None = None) -> dict:
    if not messages:
        return {"status": "skipped", "reason": "empty", "id": ""}
    hash_value = content_hash(messages)
    duplicate = archived_session_with_hash(username, hash_value)
    if duplicate:
        return {"status": "skipped", "reason": "duplicate", "id": str(duplicate.get("id", ""))}
    now = dt.datetime.utcnow()
    sid = f"{now.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:4]}"
    session_ids = provider_session_ids(provider_state)
    payload = {
        "id": sid,
        "title": generate_title(messages),
        "created_utc": now.isoformat() + "Z",
        "updated_utc": now.isoformat() + "Z",
        "message_count": len(messages),
        "content_hash": hash_value,
        "messages": messages,
        "provider_session_ids": session_ids,
        "claude_session_id": session_ids.get("claude", ""),
    }
    (archive_dir(username) / f"{sid}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"status": "saved", "id": sid, "title": payload["title"]}


def run_archive_job(job: dict) -> None:
    try:
        result = archive_messages(job["username"], job["messages"], job.get("provider_state"))
        job["queue"].put({"ok": True, **result})
    except Exception as exc:
        job["queue"].put({"ok": False, "status": "failed", "error": str(exc)})


def list_archived_sessions(username: str) -> list[dict]:
    d = archive_dir(username)
    sessions: list[dict] = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", f.stem),
                "updated_utc": data.get("updated_utc", ""),
                "message_count": data.get("message_count", 0),
                "starred": bool(data.get("starred", False)),
            })
        except Exception:
            pass
    sessions.sort(key=lambda s: (0 if s["starred"] else 1))
    return sessions[:30]


def delete_archived_session(username: str, session_id: str) -> None:
    (archive_dir(username) / f"{session_id}.json").unlink(missing_ok=True)


def rename_archived_session(username: str, session_id: str, new_title: str) -> None:
    path = archive_dir(username) / f"{session_id}.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["title"] = new_title.strip()[:80]
        from atomic_json import atomic_write_json
        atomic_write_json(path, data)
    except Exception:
        pass


def star_archived_session(username: str, session_id: str, starred: bool) -> None:
    path = archive_dir(username) / f"{session_id}.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["starred"] = starred
        from atomic_json import atomic_write_json
        atomic_write_json(path, data)
    except Exception:
        pass


def export_chat_markdown(messages: list, include_debug: bool = False) -> str:
    now = dt.datetime.now(ZoneInfo("Europe/London"))
    lines = [f"# CaseForge Chat - {now.strftime('%A %d %B %Y, %H:%M')}", ""]
    for msg in messages:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if role == "user":
            lines += ["---", "", "**You**", "", content, ""]
        elif role == "assistant":
            model_label = msg.get("model", "CaseForge")
            header = f"**CaseForge** *({model_label})*" if model_label else "**CaseForge**"
            lines += ["---", "", header, ""]
            if include_debug:
                for tc in msg.get("tools", []):
                    name = tc.get("name", "tool")
                    detail = tc.get("detail", "")
                    lines.append(f"`Debug: {name}{': ' + detail if detail else ''}`")
            if content:
                lines.append(content)
            if msg.get("error"):
                lines.append(f"\n> ⚠ {msg['error']}")
            lines.append("")
    return "\n".join(lines)
