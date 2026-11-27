
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scanned_docs.intake_facts import DEFAULT_SCANNED_DOCS_PATH, filename_surname

SETTING_KEY = "scanned_docs_path"
MAX_PATH_CHARS = 200
STATE_PATH = Path(__file__).resolve().parents[2] / "telemetry" / "scanned-docs-monitor" / "state.json"


class ScannedFolderError(ValueError):
    pass


class ScannedCacheUnavailable(Exception):
    pass


def clean_path(value: Any) -> str:
    text = str(value or "").strip().strip("/")
    if not text:
        raise ScannedFolderError("the folder path is empty")
    if len(text) > MAX_PATH_CHARS:
        raise ScannedFolderError(f"the folder path is longer than {MAX_PATH_CHARS} characters")
    if "\\" in text or any(ord(ch) < 32 for ch in text):
        raise ScannedFolderError("the folder path uses forward slashes and no control characters")
    parts = text.split("/")
    if any(not part.strip() or part.strip() in (".", "..") for part in parts):
        raise ScannedFolderError("the folder path has an empty or relative part")
    return "/".join(part.strip() for part in parts)


def stored_path(*, db_path: Any = None) -> str:
    try:
        import ops_db

        with ops_db.connect(db_path) as conn:
            row = conn.execute("SELECT value FROM pipeline_settings WHERE key = ?", (SETTING_KEY,)).fetchone()
        return clean_path(row[0]) if row else ""
    except Exception:
        return ""


def scanned_docs_path(*, db_path: Any = None) -> str:
    import app_settings

    return app_settings.get_setting("scanned_docs_folder", db_path=db_path) or DEFAULT_SCANNED_DOCS_PATH


def set_scanned_docs_path(value: Any, by: str = "", *, db_path: Any = None) -> str:
    import ops_db

    blank = not str(value or "").strip().strip("/")
    path = "" if blank else clean_path(value)
    with ops_db.connect(db_path) as conn:
        if blank:
            conn.execute("DELETE FROM pipeline_settings WHERE key = ?", (SETTING_KEY,))
        else:
            conn.execute(
                "INSERT INTO pipeline_settings (key, value, updated_by, updated_utc) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, updated_utc = excluded.updated_utc",
                (SETTING_KEY, path, str(by or "").strip()[:80], ops_db.utc_now_z()),
            )
        conn.commit()
    import app_settings

    app_settings.invalidate()
    return scanned_docs_path(db_path=db_path)


def cached_waiting(*, state_path: Path | None = None, db_path: Any = None) -> dict[str, Any]:
    from scanned_docs.scan_rows import scan_date

    path = scanned_docs_path(db_path=db_path)
    try:
        state = json.loads((state_path or STATE_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ScannedCacheUnavailable("no saved listing") from exc
    items = state.get("items") if isinstance(state, dict) else None
    if not isinstance(items, dict) or str(state.get("path") or "").strip("/") != path:
        raise ScannedCacheUnavailable("the saved listing is of another folder")
    files = []
    for item in items.values():
        if not isinstance(item, dict) or item.get("kind") != "file":
            continue
        name = str(item.get("name") or "")
        date, source = scan_date(name, item.get("createdDateTime"), item.get("lastModifiedDateTime"))
        files.append({
            "id": str(item.get("id") or ""),
            "name": name,
            "scan_date": date,
            "date_source": source,
            "possible_client": filename_surname(name) or "",
            "web_url": str(item.get("webUrl") or ""),
        })
    files.sort(key=lambda f: (f["scan_date"] == "", f["scan_date"], f["name"]), reverse=False)
    return {"path": path, "checked_utc": str(state.get("last_run_utc") or ""), "files": files}
