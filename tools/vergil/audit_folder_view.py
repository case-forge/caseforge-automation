from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

try:
    import actor_kind
    import firm_profile
    import ops_db
    from vergil import audit_trail
except ImportError:
    from tools import actor_kind, firm_profile, ops_db
    from tools.vergil import audit_trail

_PROFILE = firm_profile.load_profile()
BOOK = _PROFILE.protective_orders_book
LIBRARY_ROOT = _PROFILE.library_root

CREATING = frozenset({"Uploaded", "Created folder", "Copied", "Copied folder", "Restored", "Restored folder"})
MOVING = frozenset({"Moved", "Renamed", "Moved folder", "Renamed folder"})
REMOVING = frozenset({"Deleted", "Deleted folder"})
EDITING = frozenset({"Edited"})
MAX_ITEMS = 5000
CACHE_SECONDS = 60
STALE_SECONDS = 600

_cache_lock = threading.Lock()
_cache: dict[tuple[int, str], tuple[float, tuple[list[dict[str, Any]], str, str]]] = {}
_refreshing: set[tuple[int, str]] = set()
_rows_memo: tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str | None, str | None, str | None]]] | None = None


def rel(path: str, book: str = BOOK) -> str | None:
    parts = [p for p in ops_db.normalise_graph_path(path).split("/") if p]
    for i, part in enumerate(parts):
        if part.casefold() == book.casefold():
            return "/".join(parts[i + 1:])
    return None


def _first(path: str) -> str:
    return path.split("/", 1)[0]


def _key(path: str) -> str:
    return path.casefold()


def _inside(path: str | None, client: str) -> bool:
    return bool(path) and "/" in path and _first(path).casefold() == client.casefold()


def _cached_collect(conn: sqlite3.Connection, days: int, request_log: Path | None, now: dt.datetime | None) -> tuple[list[dict[str, Any]], str, str]:
    if now is not None:
        return audit_trail.collect(conn, days=days, request_log=request_log, now=now)
    key = (days, str(request_log or ""))
    with _cache_lock:
        hit = _cache.get(key)
        age = time.monotonic() - hit[0] if hit else None
        if hit and age < CACHE_SECONDS:
            return hit[1]
        if hit and age < STALE_SECONDS:
            if key not in _refreshing:
                _refreshing.add(key)
                threading.Thread(target=_refresh, args=(key, days, request_log), name="audit-folder-refresh", daemon=True).start()
            return hit[1]
    result = audit_trail.collect(conn, days=days, request_log=request_log)
    with _cache_lock:
        _cache.clear()
        _cache[key] = (time.monotonic(), result)
    return result


def _refresh(key: tuple[int, str], days: int, request_log: Path | None) -> None:
    try:
        with ops_db.connect() as conn:
            result = audit_trail.collect(conn, days=days, request_log=request_log)
        with _cache_lock:
            _cache.clear()
            _cache[key] = (time.monotonic(), result)
    except Exception:
        pass
    finally:
        with _cache_lock:
            _refreshing.discard(key)


INDEX_LAG = dt.timedelta(minutes=30)


def _latest(conn: sqlite3.Connection, sql: str) -> str:
    try:
        row = conn.execute(sql).fetchone()
    except sqlite3.OperationalError:
        return ""
    return str(row[0]) if row and row[0] else ""


def _event(row: dict[str, Any], frm: str | None, to: str | None, client: str) -> dict[str, Any]:
    ev: dict[str, Any] = {"at": row["at"], "kind": row.get("kind") or "", "who": row["who"], "action": row["action"], "seen_by": row.get("seen_by", [])}
    for name, path in (("from", frm), ("to", to)):
        if path:
            inside = _first(path).casefold() == client.casefold()
            ev[name] = path.split("/", 1)[1] if inside and "/" in path else path
            if not inside:
                ev[f"{name}_outside"] = True
    for field in ("program", "unit"):
        if row.get(field):
            ev[field] = row[field]
    return ev


def _file_rows(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str | None, str | None, str | None]]:
    global _rows_memo
    memo = _rows_memo
    if memo is not None and memo[0] is rows:
        return memo[1]
    out = []
    for row in sorted((r for r in rows if r.get("area") in ("file", "folder")), key=lambda r: r["at"]):
        frm, to, what = (rel(row.get(k) or "") for k in ("from", "to", "what"))
        if frm is None and to is None and what is None:
            continue
        out.append((row, frm, to, what))
    _rows_memo = (rows, out)
    return out


def clients(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names: dict[str, str] = {}
    prefix = f"{LIBRARY_ROOT}/{BOOK}/"
    try:
        for (path,) in conn.execute("SELECT path FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'folder' AND path LIKE ? ESCAPE '\\'", (_like(prefix) + "%",)):
            below = path[len(prefix):]
            if below and "/" not in below:
                names[_key(below)] = below
    except sqlite3.OperationalError:
        pass
    stats: dict[str, dict[str, Any]] = {}
    for row, frm, to, what in _file_rows(rows):
        if row["action"] in EDITING:
            continue
        place = to or what
        if not place or "/" not in place:
            continue
        client = _first(place)
        names.setdefault(_key(client), client)
        entry = stats.setdefault(_key(client), {"person": 0, "agent": 0, "automation": 0, "unrecorded": 0, "last_at": ""})
        entry[row.get("kind") or "unrecorded"] += 1
        entry["last_at"] = max(entry["last_at"], row["at"])
    flagged: dict[str, int] = {}
    for flag in _open_flags(conn):
        names.setdefault(_key(flag["client"]), flag["client"])
        flagged[_key(flag["client"])] = flagged.get(_key(flag["client"]), 0) + 1
    out = [{"name": name, **stats.get(k, {"person": 0, "agent": 0, "automation": 0, "unrecorded": 0, "last_at": ""}), "flagged": flagged.get(k, 0)} for k, name in names.items()]
    out.sort(key=lambda c: c["name"].casefold())
    out.sort(key=lambda c: c["last_at"], reverse=True)
    return out


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _index(conn: sqlite3.Connection, client: str) -> dict[str, dict[str, Any]]:
    base = f"{LIBRARY_ROOT}/{BOOK}/"
    out: dict[str, dict[str, Any]] = {}
    try:
        found = conn.execute(
            "SELECT path, name, item_type, modified_utc, size_bytes, item_id FROM onedrive_items WHERE deleted_at_utc IS NULL AND path LIKE ? ESCAPE '\\' ORDER BY path COLLATE NOCASE",
            (_like(f"{base}{client}/") + "%",),
        ).fetchall()
    except sqlite3.OperationalError:
        return out
    for path, name, kind, modified, size, item_id in found:
        below = path[len(base):]
        if _inside(below, client):
            out[_key(below)] = {"path": below, "name": name, "type": kind, "modified": modified or "", "size": size, "item_id": item_id}
    return out


def _open_flags(conn: sqlite3.Connection, client: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT client, item_key, path, item_type, flagged_by, flagged_at, note, kind FROM audit_folder_flags WHERE book = ? AND cleared_at IS NULL"
    args: list[Any] = [BOOK]
    if client is not None:
        sql += " AND client = ? COLLATE NOCASE"
        args.append(client)
    if kind is not None:
        sql += " AND kind = ?"
        args.append(kind)
    try:
        found = conn.execute(sql + " ORDER BY flag_id", args).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"client": c, "item_key": k, "path": p, "type": t, "by": by, "at": at, "note": n or "", "kind": kd or actor_kind.PERSON} for c, k, p, t, by, at, n, kd in found]


def _flag_view(flag: dict[str, Any]) -> dict[str, str]:
    return {"by": flag["by"], "at": flag["at"], "note": flag["note"]}


def _attach_flags(items: list[dict[str, Any]], flags: list[dict[str, Any]], client: str) -> None:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for f in flags:
        by_key.setdefault(f["item_key"], []).append(f)
    used: set[str] = set()
    for item in items:
        keys = [k for k in (item.get("item_id") or "", "path:" + _key(f"{client}/{item['path']}")) if k in by_key]
        item.pop("item_id", None)
        item["flags"] = {f["kind"]: _flag_view(f) for k in keys for f in by_key[k]}
        used.update(keys)
    for key, group in by_key.items():
        if key in used:
            continue
        first = group[0]
        below = first["path"]
        items.append({"path": below, "name": below.rsplit("/", 1)[-1], "type": first["type"], "modified": "", "size": None, "indexed": False, "removed": True,
                      "created": None, "placed": None, "edits": 0, "last_edit": None, "flags": {f["kind"]: _flag_view(f) for f in group}, "flag_gone": True})


def item_key(conn: sqlite3.Connection, client: str, path: str, item_type: str) -> tuple[str, str, str]:
    parts = [p for p in str(path).replace("\\", "/").split("/") if p]
    if not client or "/" in client or not parts or any(p in (".", "..") for p in parts):
        raise ValueError("path must be an item inside a client folder")
    below = "/".join(parts)
    row = conn.execute(
        "SELECT item_id, item_type FROM onedrive_items WHERE deleted_at_utc IS NULL AND path = ? COLLATE NOCASE LIMIT 1", (f"{LIBRARY_ROOT}/{BOOK}/{client}/{below}",)
    ).fetchone()
    return (row[0] if row else "path:" + _key(f"{client}/{below}")), (row[1] if row else item_type), below


_LINKS: dict[tuple[str, str], str] = {}


def share_link(conn: sqlite3.Connection, client: str, path: str) -> str:
    parts = [p for p in str(path).replace("\\", "/").split("/") if p]
    if not client or "/" in client or not parts or any(p in (".", "..") for p in parts):
        raise ValueError("path must be an item inside a client folder")
    row = conn.execute(
        "SELECT drive_id, item_id, name FROM onedrive_items WHERE deleted_at_utc IS NULL AND path = ? COLLATE NOCASE LIMIT 1",
        (f"{LIBRARY_ROOT}/{BOOK}/{client}/{'/'.join(parts)}",),
    ).fetchone()
    if not row:
        raise LookupError("not in the index")
    drive_id, item_id, name = row
    cached = _LINKS.get((drive_id, item_id))
    if cached:
        return cached
    import graph_files

    url = str(graph_files.create_link_by_ids(drive_id, item_id, item_name=name).get("webUrl") or "")
    if not url:
        raise RuntimeError("no link from Graph")
    _LINKS[(drive_id, item_id)] = url
    return url


def set_flag(conn: sqlite3.Connection, *, client: str, path: str, item_type: str, flagged: bool, by: str, kind: str = actor_kind.PERSON, note: str = "",
             now: dt.datetime | None = None, commit: bool = True) -> dict[str, Any]:
    if kind not in actor_kind.KINDS:
        raise ValueError("kind must be person, agent or automation")
    key, found_type, below = item_key(conn, client, path, item_type)
    path_key = "path:" + _key(f"{client}/{below}")
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if flagged:
        open_now = conn.execute("SELECT 1 FROM audit_folder_flags WHERE book = ? AND kind = ? AND item_key IN (?, ?) AND cleared_at IS NULL", (BOOK, kind, key, path_key)).fetchone()
        if not open_now:
            conn.execute(
                "INSERT INTO audit_folder_flags (book, client, item_key, path, item_type, flagged_by, flagged_at, note, kind) VALUES (?,?,?,?,?,?,?,?,?)",
                (BOOK, client, key, below, found_type, by, stamp, (note or "").strip()[:300], kind),
            )
    else:
        conn.execute("UPDATE audit_folder_flags SET cleared_by = ?, cleared_at = ? WHERE book = ? AND kind = ? AND item_key IN (?, ?) AND cleared_at IS NULL", (by, stamp, BOOK, kind, key, path_key))
    if commit:
        conn.commit()
    return {"flagged": flagged, "path": below, "client": client, "kind": kind}


def clear_kind(conn: sqlite3.Connection, *, kind: str, by: str, keep_keys: frozenset[str] = frozenset(), client: str | None = None, now: dt.datetime | None = None) -> int:
    if kind not in actor_kind.KINDS:
        raise ValueError("kind must be person, agent or automation")
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cleared = 0
    for flag in _open_flags(conn, client=client, kind=kind):
        if flag["item_key"] in keep_keys:
            continue
        cleared += conn.execute(
            "UPDATE audit_folder_flags SET cleared_by = ?, cleared_at = ? WHERE book = ? AND kind = ? AND item_key = ? AND cleared_at IS NULL", (by, stamp, BOOK, kind, flag["item_key"])
        ).rowcount
    conn.commit()
    return cleared


def tree(conn: sqlite3.Connection, rows: list[dict[str, Any]], client: str) -> dict[str, Any]:
    history: dict[str, list[dict[str, Any]]] = {}
    shown: dict[str, str] = {}
    kinds: dict[str, str] = {}
    gone: dict[str, dict[str, Any]] = {}

    def rekey(old: str, new: str, folder: bool) -> None:
        moves = {_key(old): _key(new)}
        if folder:
            moves.update({k: _key(new) + k[len(_key(old)):] for k in list(history) if k.startswith(_key(old) + "/")})
        for k_old, k_new in moves.items():
            if k_old in history:
                history[k_new] = history.pop(k_old) + history.get(k_new, [])
            shown.pop(k_old, None)
            if k_old in kinds:
                kinds[k_new] = kinds.pop(k_old)

    for row, frm, to, what in _file_rows(rows):
        action, folder = row["action"], row.get("area") == "folder"
        ev = _event(row, frm, to, client)
        if action in MOVING and frm and to:
            src, dst = _inside(frm, client), _inside(to, client)
            if src and dst:
                rekey(frm, to, folder)
            elif src:
                history.pop(_key(frm), None)
                shown.pop(_key(frm), None)
                gone[_key(frm)] = {"path": frm, "type": "folder" if folder else "file", "event": ev, "moved_to": ev.get("to", ""), "to_outside": ev.get("to_outside", False)}
            if dst:
                history.setdefault(_key(to), []).append(ev)
                shown[_key(to)] = to
                kinds[_key(to)] = "folder" if folder else "file"
                gone.pop(_key(to), None)
        elif action in CREATING:
            place = to or what
            if _inside(place, client):
                history.setdefault(_key(place), []).append(ev)
                shown[_key(place)] = place
                kinds[_key(place)] = "folder" if folder else "file"
                gone.pop(_key(place), None)
        elif action in REMOVING:
            place = what or frm
            if _inside(place, client):
                history.pop(_key(place), None)
                shown.pop(_key(place), None)
                gone[_key(place)] = {"path": place, "type": "folder" if folder else "file", "event": ev, "moved_to": "", "to_outside": False}
        elif action in EDITING:
            place = what or to
            if _inside(place, client):
                history.setdefault(_key(place), []).append(ev)
                shown.setdefault(_key(place), place)

    indexed = _index(conn, client)
    seen = audit_trail._ts(_latest(conn, "SELECT MAX(last_seen_utc) FROM onedrive_items"))
    items: list[dict[str, Any]] = []
    for key, info in indexed.items():
        items.append({**info, "indexed": True, "removed": False, **_summarise(history.get(key, []))})
    for key, path in shown.items():
        evs = history.get(key, [])
        if key in indexed or not any(e["action"] in CREATING or e["action"] in MOVING for e in evs):
            continue
        last = audit_trail._ts(evs[-1]["at"])
        if seen and last and last < seen - INDEX_LAG:
            items.append({"path": path, "name": path.rsplit("/", 1)[-1], "type": kinds.get(key, "file"), "modified": "", "size": None, "indexed": False, "removed": True,
                          "unseen": True, "removed_by": None, "moved_to": "", "to_outside": False, **_summarise(evs)})
            continue
        items.append({"path": path, "name": path.rsplit("/", 1)[-1], "type": kinds.get(key, "file"), "modified": "", "size": None, "indexed": False, "removed": False, **_summarise(evs)})
    for key, info in gone.items():
        if key in indexed:
            continue
        items.append({"path": info["path"], "name": info["path"].rsplit("/", 1)[-1], "type": info["type"], "modified": "", "size": None, "indexed": False, "removed": True,
                      "removed_by": info["event"], "moved_to": info["moved_to"], "to_outside": info["to_outside"], "created": None, "placed": None, "edits": 0, "last_edit": None})
    for i in items:
        i["path"] = i["path"].split("/", 1)[1]
    _attach_flags(items, _open_flags(conn, client), client)
    items.sort(key=lambda i: i["path"].casefold())

    live = [i for i in items if not i.get("removed")]
    summary = {"person": 0, "agent": 0, "automation": 0, "unrecorded": 0, "removed": len(items) - len(live), "flagged": sum(1 for i in items if i.get("flags")),
               "flags_by_kind": {k: sum(1 for i in items if k in i.get("flags", {})) for k in actor_kind.KINDS}}
    for i in live:
        maker = i.get("placed") or i.get("created")
        summary[(maker or {}).get("kind") or "unrecorded"] += 1
    truncated = len(items) > MAX_ITEMS
    return {"name": client, "items": items[:MAX_ITEMS], "truncated": truncated, "summary": summary}


def _summarise(events: list[dict[str, Any]]) -> dict[str, Any]:
    created = next((e for e in events if e["action"] in CREATING), None)
    placed = next((e for e in reversed(events) if e["action"] in MOVING), None)
    edits = [e for e in events if e["action"] in EDITING]
    return {"created": created, "placed": placed, "edits": len(edits), "last_edit": edits[-1] if edits else None}


def folder_view(conn: sqlite3.Connection, *, folder: str = "", days: int = 90, request_log: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    days = max(1, min(int(days), 90))
    rows, since, until = _cached_collect(conn, days, request_log, now)
    out: dict[str, Any] = {
        "book": BOOK, "days": days, "since": since, "until": until, "clients": clients(conn, rows), "folder": None,
        "microsoft_through": _latest(conn, "SELECT MAX(created_utc) FROM ms_audit_events"),
        "index_through": _latest(conn, "SELECT MAX(last_seen_utc) FROM onedrive_items"),
    }
    name = (folder or "").strip().strip("/")
    if name and "/" not in name:
        known = {_key(c["name"]): c["name"] for c in out["clients"]}
        if _key(name) in known:
            out["folder"] = tree(conn, rows, known[_key(name)])
    return out
