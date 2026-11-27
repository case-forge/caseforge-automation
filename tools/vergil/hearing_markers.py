#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
from vergil import board_overrides

log = logging.getLogger(__name__)


def _bundles_done(matter_ids: list[str], db_path: Any) -> set[tuple[str, str]]:
    if not matter_ids:
        return set()
    from onboarding.pipeline import OUTSIDE_EVENT
    from onboarding.pipeline import step_bundle

    done = set()
    with ops_db.connect(db_path) as conn:
        for start in range(0, len(matter_ids), 400):
            chunk = matter_ids[start : start + 400]
            marks = ", ".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT matter_id, instance FROM pipeline_events WHERE step = ? AND status IN ('ok', ?) AND matter_id IN ({marks})",
                (step_bundle.STEP, OUTSIDE_EVENT, *chunk),
            ).fetchall()
            done.update((str(r[0]), str(r[1] or "")) for r in rows)
    return done


def _bundles_in_folders(hearings: list[tuple[str, str, str]], db_path: Any) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    if not hearings:
        return found
    with ops_db.connect(db_path) as conn:
        for matter_id, hearing_id, hearing_date in hearings:
            try:
                day = dt.date.fromisoformat(str(hearing_date)[:10])
            except ValueError:
                continue
            root = conn.execute(
                "SELECT r.drive_id, r.folder_item_id, i.path FROM matter_onedrive_roots r JOIN onedrive_items i "
                "ON i.drive_id = COALESCE(r.drive_id, '') AND i.item_id = r.folder_item_id "
                "WHERE r.matter_id = ? AND COALESCE(r.folder_item_id, '') <> '' AND i.deleted_at_utc IS NULL LIMIT 1",
                (str(matter_id),),
            ).fetchone()
            if not root:
                continue
            drive_id, root_id, root_path = root
            import graph_files

            folder = next(
                (
                    (row[0],)
                    for row in conn.execute(
                        "SELECT item_id, name FROM onedrive_items WHERE drive_id = ? AND parent_item_id = ? "
                        "AND item_type = 'folder' AND deleted_at_utc IS NULL",
                        (drive_id, root_id),
                    ).fetchall()
                    if (kind := graph_files.folder_kind(str(row[1] or ""))).kind == "hearing" and kind.date == day
                ),
                None,
            )
            if not folder:
                continue
            made = conn.execute(
                "SELECT 1 FROM onedrive_items WHERE drive_id = ? AND parent_item_id = ? AND item_type = 'file' AND deleted_at_utc IS NULL "
                "AND lower(name) LIKE 'bundle%' AND lower(name) LIKE '%.pdf' LIMIT 1",
                (drive_id, folder[0]),
            ).fetchone()
            if not made:
                continue
            below = root_path.rstrip("/")
            sent = conn.execute(
                "SELECT 1 FROM onedrive_items INDEXED BY ux_onedrive_items_path WHERE path COLLATE NOCASE >= ? AND path COLLATE NOCASE < ? "
                "AND drive_id = ? AND item_type = 'file' AND deleted_at_utc IS NULL "
                "AND lower(name) LIKE '%[out]%' AND lower(name) LIKE '%bundle%' LIMIT 1",
                (below + "/", below + "0", drive_id),
            ).fetchone()
            if sent:
                found.add((str(matter_id), f"hearing:{hearing_id}"))
    return found


def annotate(rows: list[dict[str, Any]], *, db_path: Any = None, today: str = "") -> list[dict[str, Any]]:
    today = today or dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("Europe/London")).date().isoformat()
    todo = [
        h for h in rows
        if h.get("matter_id") is not None and str(h.get("status") or "scheduled") == "scheduled" and str(h.get("hearing_date") or "")[:10] >= today
    ]
    if not todo:
        return rows
    try:
        mids = sorted({str(h["matter_id"]) for h in todo})
        logged = _bundles_done(mids, db_path)
        in_folders = _bundles_in_folders([(str(h["matter_id"]), str(h.get("hearing_id")), str(h.get("hearing_date") or "")) for h in todo], db_path)
    except Exception as exc:
        log.warning("hearing markers failed: %s", type(exc).__name__)
        return rows
    try:
        corrections = board_overrides.active(db_path=db_path)
    except Exception as exc:
        log.warning("hearing marker overrides failed: %s", type(exc).__name__)
        corrections = {}
    for h in todo:
        key = (str(h["matter_id"]), f"hearing:{h.get('hearing_id')}")
        bundle_done = key in logged or key in in_folders
        h["bundle_why"] = (
            "Case flow's bundle step ran or was marked done" if key in logged
            else "the hearing folder holds a bundle and a sent bundle email is filed" if key in in_folders
            else "no bundle step logged and no bundle plus sent email found in the folders"
        )
        counsel_booked = bool(str(h.get("counsel") or "").strip())
        overridden: dict[str, Any] = {}
        for field, current in (("bundle_done", bundle_done), ("counsel_booked", counsel_booked)):
            fix = corrections.get((str(h.get("hearing_id")), field))
            if fix:
                overridden[field] = {"was": current, "now": fix["value"], "reason": fix["reason"], "by": fix["by"], "id": fix["id"]}
                if field == "bundle_done":
                    bundle_done = fix["value"]
                else:
                    counsel_booked = fix["value"]
        h["bundle_done"] = bundle_done
        h["counsel_booked"] = counsel_booked
        if overridden:
            h["overridden"] = overridden
    return rows
