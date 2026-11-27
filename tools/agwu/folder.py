#!/usr/bin/env python3
from __future__ import annotations

import re

import sys
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import graph_files
from clientdb_sql import find_matter_folder_locations, seed_matter_folder_location


@dataclass
class FolderResolution:
    status: str
    matter_folder_id: str = ""
    matter_folder_path: str = ""
    attendance_folder_id: str = ""
    source: str = ""
    storage_root: str = ""
    drive_id: str = ""
    reason: str = ""


_NMO_ORDERS = ("nmo", "oo", "fla")
_CAO_ORDERS = ("cao", "pso", "sio", "ca")


def attendance_group(order_type: str) -> str:
    words = set(re.findall(r"[a-z]+", str(order_type or "").lower()))
    if words & set(_NMO_ORDERS) or {"non", "molestation"} <= words or "nonmolestation" in words:
        return "nmo"
    if words & set(_CAO_ORDERS):
        return "cao"
    return ""


def _find_attendance_subfolder(matter_folder_id: str, drive_id: str, order_type: str = "") -> tuple[str, str]:
    try:
        import ops_db

        children = ops_db.list_onedrive_children(
            drive_id=drive_id, parent_item_id=matter_folder_id, item_type="folder"
        )
    except Exception:
        return "", ""
    matches = [item for item in children if "attendance" in str(item.get("name") or "").lower()]
    if not matches:
        return "", ""
    def rank(item: dict) -> int:
        name = str(item.get("name") or "")
        recognised = graph_files.folder_kind(name).kind == "attendance_notes"
        noted = bool(re.search(r"(?<![a-z])notes?(?![a-z])", name.lower()))
        return 0 if recognised and noted else 1 if recognised else 2

    matches = sorted(matches, key=rank)
    group = attendance_group(order_type)
    preference = {"nmo": _NMO_ORDERS + _CAO_ORDERS, "cao": _CAO_ORDERS + _NMO_ORDERS}.get(group, _NMO_ORDERS + _CAO_ORDERS)
    for order in preference:
        for item in matches:
            if re.search(rf"(?<![a-z]){order}(?![a-z])", str(item.get("name") or "").lower()):
                return str(item.get("item_id") or ""), str(item.get("name") or "")
    return str(matches[0].get("item_id") or ""), str(matches[0].get("name") or "")


def attendance_folders_of(matter_folder_id: str, drive_id: str) -> list[dict[str, str]]:
    import anyanwu

    return anyanwu.attendance_folders_of(matter_folder_id, drive_id)


def child_folder_named(matter_folder_id: str, drive_id: str, name: str) -> tuple[str, str]:
    import anyanwu

    return anyanwu.child_folder_named(matter_folder_id, drive_id, name)


def why_no_attendance_folder(matter_folder_id: str, drive_id: str, *, matter_folder_name: str = "") -> str:
    if not matter_folder_id:
        return "the matter has no folder record"
    try:
        import ops_db

        with ops_db.connect() as conn:
            row = conn.execute(
                "SELECT deleted_at_utc FROM onedrive_items WHERE drive_id = ? AND item_id = ?", (drive_id, matter_folder_id)
            ).fetchone()
        children = ops_db.list_onedrive_children(drive_id=drive_id, parent_item_id=matter_folder_id, item_type="folder")
    except Exception:
        return "the folder index could not be read"
    if row is None or row[0]:
        return "the folder record points at a folder that is gone from the index"
    names = sorted(str(item.get("name") or "") for item in children)
    if not names:
        return f"the case folder{' ' + repr(matter_folder_name) if matter_folder_name else ''} holds no subfolders in the index"
    return "none of its subfolders reads as an attendance notes folder (" + ", ".join(repr(n) for n in names[:8]) + ")"


def attendance_subfolder_for(matter_folder_id: str, drive_id: str, order_type: str) -> tuple[str, str]:
    return _find_attendance_subfolder(matter_folder_id, drive_id, order_type)


def _graph_live_fallback(matter_id: str) -> FolderResolution | None:
    try:
        import ops_db

        matches = ops_db.search_onedrive_items(matter_id, folders_only=True, limit=20)
        live = [
            item
            for item in matches
            if "clients live files" in str(item.get("path") or "").lower()
            and "concluded" not in str(item.get("path") or "").lower()
        ] or matches
        exact = next(
            (item for item in live if str(item.get("name") or "").lower() == matter_id.lower()),
            None,
        )
        picked = exact or (live[0] if live else None)
        if not picked:
            return None
        picked_path = str(picked.get("path") or "")
        picked_item_id = str(picked.get("item_id") or "")
        picked_drive_id = str(picked.get("drive_id") or "")
        attendance_folder_id, _ = _find_attendance_subfolder(picked_item_id, picked_drive_id)
        return FolderResolution(
            status="resolved_live",
            matter_folder_id=picked_item_id,
            matter_folder_path=picked_path,
            attendance_folder_id=attendance_folder_id,
            source="graph_live_fallback",
            storage_root=str(picked.get("root_name") or "") or ops_db.root_name_from_path(picked_path),
            drive_id=picked_drive_id,
        )
    except Exception:
        return None


def resolve_folder(
    matter_id: str,
    *,
    allow_live_fallback: bool = False,
    caller: str = "",
    live_search_hint: str = "",
) -> FolderResolution:
    mid = str(matter_id or "").strip()
    if not mid:
        resolution = FolderResolution(status="not_found")
        from agwu.telemetry import log_folder_resolution

        log_folder_resolution(mid, resolution, caller=caller)
        return resolution

    rows = find_matter_folder_locations(matter_id=mid, limit=1)
    recorded_path = ""
    if not rows:
        recorded_path = seed_matter_folder_location(mid)
        if recorded_path:
            rows = find_matter_folder_locations(matter_id=mid, limit=1)
    if rows:
        row = rows[0]
        cached_matter_folder_id = str(row.get("matter_folder_id") or "")
        cached_drive_id = str(row.get("drive_id") or "")
        attendance_folder_id = str(row.get("attendance_folder_id") or "")
        if not attendance_folder_id and cached_matter_folder_id:
            attendance_folder_id, _ = _find_attendance_subfolder(cached_matter_folder_id, cached_drive_id)
        resolution = FolderResolution(
            status="cached",
            matter_folder_id=cached_matter_folder_id,
            matter_folder_path=str(row.get("matter_folder_path") or ""),
            attendance_folder_id=attendance_folder_id,
            source="ops_db_cache",
            storage_root=str(row.get("storage_root") or ""),
            drive_id=cached_drive_id,
        )
        from agwu.telemetry import log_folder_resolution

        log_folder_resolution(mid, resolution, caller=caller)
        return resolution

    if allow_live_fallback:
        search_key = str(live_search_hint or "").strip() or mid
        live = _graph_live_fallback(search_key)
        if live is not None:
            from agwu.telemetry import log_folder_resolution

            log_folder_resolution(mid, live, caller=caller)
            return live

    resolution = FolderResolution(status="not_found")
    if recorded_path:
        resolution.matter_folder_path = recorded_path
        resolution.source = "matters.live_matter_folder"
        resolution.reason = "the matter records a folder, but it is not in the folder index (moved, renamed or not yet indexed)"
    from agwu.telemetry import log_folder_resolution

    log_folder_resolution(mid, resolution, caller=caller)
    return resolution




@dataclass
class Relocation:

    status: str
    path: str = ""
    item_id: str = ""
    drive_id: str = ""
    how: str = ""
    reason: str = ""


def _path_of_item(item: dict) -> str:
    import graph_files

    parent = str((item.get("parentReference") or {}).get("path") or "")
    relative = parent.split("root:", 1)[1] if "root:" in parent else ""
    return "/".join(p for p in (graph_files.DEFAULT_ONEDRIVE_ROOT_NAME, relative.strip("/"), str(item.get("name") or "")) if p)


def relocate_missing_folder(
    matter_id: str,
    missing_path: str,
    *,
    access_token: str | None = None,
    graph_json=None,
    update_cache: bool = True,
) -> Relocation:
    import urllib.parse

    import graph_files

    mid = str(matter_id or "").strip()
    try:
        call = graph_json or graph_files.graph_json
        access_token = access_token or graph_files.token()
        gp = graph_files.normalise_onedrive_path(missing_path)
        drive_id = graph_files.drive_id_for(gp, access_token)
        base = f"{graph_files.GRAPH}/drives"
        cached = (find_matter_folder_locations(matter_id=mid, limit=1) or [{}])[0] if mid else {}
        item_id = str(cached.get("matter_folder_id") or "")
        cached_drive = str(cached.get("drive_id") or "") or drive_id
        found: dict | None = None
        how = ""
        if item_id:
            try:
                item = call(f"{base}/{cached_drive}/items/{item_id}?$select=id,name,parentReference,folder,deleted", access_token)
                if item.get("folder") is not None and not item.get("deleted"):
                    found, how = item, "item_id"
            except Exception as exc:
                if "404" not in str(exc):
                    raise
        if found is None:
            name = gp.relative_path.rstrip("/").rsplit("/", 1)[-1]
            if name:
                query = urllib.parse.quote(name.replace("'", "''"), safe="")
                payload = call(f"{base}/{drive_id}/root/search(q='{query}')?$top=200", access_token)
                hits = [
                    i for i in payload.get("value", [])
                    if i.get("folder") is not None and not i.get("deleted") and str(i.get("name") or "").lower() == name.lower()
                ]
                if hits:
                    found, how = hits[0], "name_search" if len(hits) == 1 else "name_search_ambiguous"
    except Exception as exc:
        return Relocation(status="unknown", reason=f"the re-check failed ({type(exc).__name__})")
    if found is None:
        return Relocation(status="missing", reason="not found by item id or by name")
    new_path = _path_of_item(found)
    found_drive = str((found.get("parentReference") or {}).get("driveId") or drive_id)
    result = Relocation(status="found", path=new_path, item_id=str(found.get("id") or ""), drive_id=found_drive, how=how)
    if update_cache and mid and how != "name_search_ambiguous":
        import ops_db

        ops_db.upsert_matter_onedrive_root(
            matter_id=mid, folder_item_id=result.item_id, drive_id=found_drive, folder_path=new_path,
            source="agwu_relocated",
        )
    return result
