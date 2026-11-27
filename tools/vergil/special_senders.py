from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from mail_intake.routing_overrides import _BARE_SUFFIXES, _DOMAIN_RE
from vergil import branding_logo

SETTING_KEY = "special_senders"
MAX_SENDERS, MAX_NAME, MAX_DOMAINS, MAX_AUDIT = 12, 40, 10, 50
MAX_MARK_LETTERS = 3
MIN_CONTRAST = 1.5
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is not None:
        return data_dir
    import app_settings

    return app_settings.data_dir()


def _stored(db_path: Any = None) -> dict[str, Any]:
    try:
        import ops_db

        with ops_db.connect(db_path) as conn:
            row = conn.execute("SELECT value FROM pipeline_settings WHERE key = ?", (SETTING_KEY,)).fetchone()
        data = json.loads(row[0]) if row else None
    except Exception:
        return {"senders": [], "_audit": []}
    if not isinstance(data, dict):
        return {"senders": [], "_audit": []}
    senders = [s for s in data.get("senders") or [] if isinstance(s, dict) and s.get("id") and s.get("name")]
    audit = [a for a in data.get("_audit") or [] if isinstance(a, dict)][-MAX_AUDIT:]
    return {"senders": senders, "_audit": audit}


def _public(sender: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    logo = str(sender.get("logo") or "")
    if logo and not branding_logo.read(logo, data_dir):
        logo = ""
    return {
        "id": str(sender["id"]),
        "name": str(sender["name"]),
        "domains": [str(d) for d in sender.get("domains") or []],
        "new_clients": bool(sender.get("new_clients")),
        "logo": logo,
        "mark": sender.get("mark") if isinstance(sender.get("mark"), dict) else None,
    }


def view(*, db_path: Any = None, data_dir: Path | None = None) -> dict[str, Any]:
    folder = _data_dir(data_dir)
    return {"items": [_public(s, folder) for s in _stored(db_path)["senders"]]}


def audit_trail(*, db_path: Any = None) -> list[dict[str, str]]:
    return [{k: str(v) for k, v in row.items()} for row in _stored(db_path)["_audit"]]


def _clean_domain(raw: Any) -> str:
    if not isinstance(raw, str):
        raise ValueError("each domain must be text")
    domain = raw.strip().lower().lstrip("@")
    if domain.startswith("www."):
        domain = domain[4:]
    if not _DOMAIN_RE.match(domain) or domain in _BARE_SUFFIXES:
        raise ValueError(f"'{raw.strip()[:60]}' is not a domain that names one sender (for example chambers.example)")
    return domain


def _luminance(colour: str) -> float:
    channels = []
    for i in (1, 3, 5):
        v = int(colour[i : i + 2], 16) / 255
        channels.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _clean_mark(raw: Any) -> dict[str, Any] | None:
    if raw in (None, {}):
        return None
    if not isinstance(raw, dict):
        raise ValueError("the made logo must be letters and colours")
    text = str(raw.get("text") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,%d}" % MAX_MARK_LETTERS, text):
        raise ValueError(f"a made logo is one to {MAX_MARK_LETTERS} letters or digits")
    colours = raw.get("colours")
    background = str(raw.get("background") or "")
    if not isinstance(colours, list) or len(colours) != len(text) or not all(isinstance(c, str) and _HEX.match(c) for c in colours):
        raise ValueError("every letter needs a colour (for example #1e7a34)")
    if not _HEX.match(background):
        raise ValueError("the background needs a colour (for example #d4d4d4)")
    colours = [c.lower() for c in colours]
    background = background.lower()
    for letter, colour in zip(text, colours):
        if _contrast(colour, background) < MIN_CONTRAST:
            raise ValueError(f"the letter {letter} would be too hard to see on that background; choose a different colour")
    return {"text": text, "colours": colours, "background": background}


def _clean_sender(raw: Any, known: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("each special sender must be an object")
    name = " ".join(str(raw.get("name") or "").split())
    if not name:
        raise ValueError("every special sender needs a name")
    if len(name) > MAX_NAME:
        raise ValueError(f"'{name[:20]}...' is longer than {MAX_NAME} characters")
    domains: list[str] = []
    for entry in raw.get("domains") or []:
        clean = _clean_domain(entry)
        if clean not in domains:
            domains.append(clean)
    if len(domains) > MAX_DOMAINS:
        raise ValueError(f"'{name}' has more than {MAX_DOMAINS} domains")
    new_clients = bool(raw.get("new_clients"))
    if not domains and not new_clients:
        raise ValueError(f"'{name}' needs a domain, or the new-clients switch, so there is something to recognise it by")
    sender_id = str(raw.get("id") or "")
    if sender_id and sender_id not in known:
        raise ValueError("that special sender no longer exists; reload the page")
    mark = _clean_mark(raw.get("mark"))
    return {
        "id": sender_id or f"ss_{uuid.uuid4().hex[:10]}",
        "name": name,
        "domains": domains,
        "new_clients": new_clients,
        "logo": "" if mark else str((known.get(sender_id) or {}).get("logo") or ""),
        "mark": mark,
    }


def _write(senders: list[dict[str, Any]], audit: list[dict[str, Any]], who: str, summary: str, db_path: Any) -> None:
    import ops_db

    stamp = ops_db.utc_now_z()
    name = str(who or "").strip()[:80] or "unknown"
    trail = (audit + [{"who": name, "at": stamp, "summary": summary}])[-MAX_AUDIT:]
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO pipeline_settings (key, value, updated_by, updated_utc) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, updated_utc = excluded.updated_utc",
            (SETTING_KEY, json.dumps({"senders": senders, "_audit": trail}, sort_keys=True), name, stamp),
        )
        conn.commit()


def save(senders: Any, who: str, *, db_path: Any = None, data_dir: Path | None = None) -> dict[str, Any]:
    if not isinstance(senders, list):
        raise ValueError("send a list of special senders")
    if len(senders) > MAX_SENDERS:
        raise ValueError(f"at most {MAX_SENDERS} special senders")
    current = _stored(db_path)
    known = {str(s["id"]): s for s in current["senders"]}
    cleaned = [_clean_sender(raw, known) for raw in senders]
    names = [c["name"].lower() for c in cleaned]
    if len(set(names)) != len(names):
        raise ValueError("two special senders have the same name")
    _write(cleaned, current["_audit"], who, f"{len(cleaned)} special sender(s): {', '.join(c['name'] for c in cleaned)[:200]}", db_path)
    return view(db_path=db_path, data_dir=data_dir)


def set_logo(sender_id: str, data: bytes, who: str, *, db_path: Any = None, data_dir: Path | None = None) -> str:
    current = _stored(db_path)
    target = next((s for s in current["senders"] if str(s["id"]) == str(sender_id)), None)
    if target is None:
        raise ValueError("no such special sender")
    kind, clean = branding_logo.prepare(data)
    digest = branding_logo.store(kind, clean, _data_dir(data_dir))
    target["logo"] = digest
    target["mark"] = None
    _write(current["senders"], current["_audit"], who, f"logo set for {target['name']}", db_path)
    return digest


def clear_logo(sender_id: str, who: str, *, db_path: Any = None) -> None:
    current = _stored(db_path)
    target = next((s for s in current["senders"] if str(s["id"]) == str(sender_id)), None)
    if target is None:
        raise ValueError("no such special sender")
    if target.get("logo"):
        target["logo"] = ""
        _write(current["senders"], current["_audit"], who, f"logo removed for {target['name']}", db_path)


def logo(sender_id: str, *, db_path: Any = None, data_dir: Path | None = None) -> tuple[bytes, str] | None:
    target = next((s for s in _stored(db_path)["senders"] if str(s["id"]) == str(sender_id)), None)
    digest = str((target or {}).get("logo") or "")
    return branding_logo.read(digest, _data_dir(data_dir)) if digest else None
