
from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from scanned_docs.intake_facts import filename_date, filename_surname

LONDON = ZoneInfo("Europe/London")

DATE_SOURCES = ("filename", "uploaded", "modified", "unknown")


class ScansFolderUnreadable(Exception):
    pass


def scanned_docs_path() -> str:
    from scanned_docs import scan_setting

    return scan_setting.scanned_docs_path()


def _london_date(stamp: Any) -> str:
    text = str(stamp or "").strip()
    if not text:
        return ""
    try:
        when = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(LONDON).date().isoformat()


def scan_date(name: str, uploaded: Any = "", modified: Any = "") -> tuple[str, str]:
    from_upload = _london_date(uploaded)
    from_change = _london_date(modified)
    when = from_upload or from_change
    from_name = filename_date(name, dt.date.fromisoformat(when) if when else None)
    if from_name:
        return from_name, "filename"
    if from_upload:
        return from_upload, "uploaded"
    if from_change:
        return from_change, "modified"
    return "", "unknown"


def _content_hash(item: dict[str, Any]) -> str:
    if not int(item.get("size") or 0):
        return ""
    file_facet = item.get("file") if isinstance(item.get("file"), dict) else {}
    hashes = file_facet.get("hashes") if isinstance(file_facet.get("hashes"), dict) else {}
    for kind in ("quickXorHash", "sha256Hash", "sha1Hash"):
        value = str(hashes.get(kind) or "").strip()
        if value:
            return f"{kind}:{value}"
    return ""


def build_table(folder: str, items: list[Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_hash: dict[str, list[int]] = {}
    folders = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("folder"), dict):
            folders += 1
            continue
        name = str(item.get("name") or "").strip()
        uploaded = str(item.get("createdDateTime") or "").strip()
        modified = str(item.get("lastModifiedDateTime") or "").strip()
        date, source = scan_date(name, uploaded, modified)
        content = _content_hash(item)
        if content:
            by_hash.setdefault(content, []).append(len(rows))
        rows.append({
            "id": str(item.get("id") or "").strip(),
            "name": name,
            "scan_date": date,
            "date_source": source,
            "uploaded_utc": uploaded,
            "modified_utc": modified,
            "pages": None,
            "possible_client": filename_surname(name) or "",
            "folder": folder,
            "web_url": str(item.get("webUrl") or "").strip(),
            "size_bytes": int(item.get("size") or 0),
            "content_hash": content,
            "same_contents_as": [],
        })
    for indexes in by_hash.values():
        if len(indexes) < 2:
            continue
        for i in indexes:
            rows[i]["same_contents_as"] = [rows[j]["name"] for j in indexes if j != i]
    rows.sort(key=lambda r: r["name"].lower())
    rows.sort(key=lambda r: (r["scan_date"], r["uploaded_utc"]), reverse=True)
    return {
        "folder": folder,
        "readable": True,
        "total": len(rows),
        "folders_not_listed": folders,
        "read_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "rows": rows,
    }


def unreadable(folder: str) -> dict[str, Any]:
    table = build_table(folder, [])
    table["readable"] = False
    return table


def list_scans(path: str = "") -> dict[str, Any]:
    import graph_files

    folder = path.strip() or scanned_docs_path()
    try:
        listing = graph_files.list_children(folder)
    except Exception as exc:
        raise ScansFolderUnreadable(type(exc).__name__) from exc
    return build_table(folder, list(listing.get("value") or []))
