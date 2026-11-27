
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, NamedTuple

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import matter_orders
import ops_db
from documents.order_text_case import normalise_order_text
import firm_profile
import robot_notices
from documents.draft_attendance_note_goose import (
    AttendanceNoteDraftCostRefusal,
    AttendanceNoteDraftGooseError,
    PROOFREAD_FLAGS_KEY,
    draft_body_fields,
)

log = logging.getLogger(__name__)

CREATE_AN_SCRIPT =Path(__file__).resolve().parent / "create-attendance-note.py"


class AttendanceNoteDraftError(ValueError):
    pass


class AttendanceNoteCostRefusalError(AttendanceNoteDraftError):
    pass


MIN_TIME_MINUTES = 1
MAX_TIME_MINUTES = 99 * 60 + 59


def validate_time_minutes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AttendanceNoteDraftError("time_minutes must be a whole number of minutes")
    if not MIN_TIME_MINUTES <= value <= MAX_TIME_MINUTES:
        raise AttendanceNoteDraftError(f"time_minutes must be between {MIN_TIME_MINUTES} and {MAX_TIME_MINUTES}")
    return value


def format_time_engaged(minutes: int) -> str:
    minutes = validate_time_minutes(minutes) or 0
    hours, rest = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours != 1 else ''} {rest:02d} mins" if hours else f"{rest:02d} mins"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


CALLERS: dict[str, tuple[str, str, str]] = {
    "court": ("Court", "attendance_counsel_court", "court"),
    "counsel": ("Counsel", "attendance_counsel_court", "counsel"),
    "client": ("Client", "attendance_preparation", "client"),
    "respondent": ("Opponent", "attendance_preparation", "other_side"),
    "other": ("", "attendance_preparation", "other"),
}


NOTE_KINDS = ("call", "letter_out", "letter_in", "preparation", "perusal")

CREATE_KINDS = ("call", "perusal", "preparation")

ATTENDANCE_TYPE_FOR = {"call": "Attendance", "perusal": "Perusal", "preparation": "Preparation"}

LEGACY_KINDS = ("bundle",)

LETTER_KINDS = ("letter_out", "letter_in")
TIME_KINDS = ("preparation", "perusal")
SCHEDULE_FOR = {"call": 1, "perusal": 2, "preparation": 2}

_NON_CALL: dict[str, tuple[str, str, str]] = {
    "letter_out": ("routine_letter_out", "Letter Out to {who}", "Letter out"),
    "letter_in": ("routine_letter_in", "Routine Letter In from {who}", "Letter in"),
    "preparation": ("attendance_preparation", "Preparation: letter out to {who}", "Preparation"),
    "perusal": ("attendance_preparation", "Perusal: letter in from {who}", "Perusal"),
    "bundle": ("bundle_pages", "Bundle prepared for {who}", "Bundle"),
}


def _without_party(description: str) -> str:
    return description.replace(" to {who}", "").replace(" from {who}", "")


def validate_kind(kind: str | None, *, legacy: bool = False) -> str:
    key = str(kind or "call").strip().lower() or "call"
    if key not in NOTE_KINDS and not (legacy and key in LEGACY_KINDS):
        raise AttendanceNoteDraftError(f"kind must be one of {list(NOTE_KINDS)}, got {kind!r}")
    return key


def caller_details(caller: str | None, caller_other: str | None, kind: str = "call") -> dict[str, str]:
    key = str(caller or "").strip().lower()
    if not key and str(kind or "") in (*LETTER_KINDS, *TIME_KINDS):
        non_call_category, description, word = _NON_CALL[kind]
        return {
            "caller": "",
            "billing_category": non_call_category,
            "party": "",
            "billing_description": _without_party(description),
            "attendance_type": ATTENDANCE_TYPE_FOR.get(kind, "Attendance"),
            "description": word,
            **({"schedule": SCHEDULE_FOR[kind]} if kind in SCHEDULE_FOR else {}),
        }
    if not key:
        return {}
    if key not in CALLERS:
        raise AttendanceNoteDraftError(f"caller must be one of {sorted(CALLERS)}, got {caller!r}")
    label, category, party = CALLERS[key]
    if key == "other":
        label = " ".join(str(caller_other or "").split())
        if not label:
            raise AttendanceNoteDraftError("caller_other is required when caller is 'other'")
    kind = validate_kind(kind, legacy=True)
    if kind != "call":
        non_call_category, description, word = _NON_CALL[kind]
        return {
            "caller": label,
            "billing_category": non_call_category,
            "party": party,
            "billing_description": description.format(who=label),
            "attendance_type": ATTENDANCE_TYPE_FOR.get(kind, "Attendance"),
            "description": word,
            **({"schedule": SCHEDULE_FOR[kind]} if kind in SCHEDULE_FOR else {}),
        }
    return {
        "caller": label,
        "billing_category": category,
        "party": party,
        "billing_description": f"Attendance note - Attendance with {label}",
        "attendance_type": "Attendance",
        "schedule": SCHEDULE_FOR["call"],
    }


def _row_to_dict(row: tuple) -> dict[str, Any]:
    (
        draft_id, matter_id, ticks_json, note_text, status, created_utc, committed_utc,
        an_output_path, billing_item_id, billing_deleted_utc, caller, caller_other,
        time_minutes, ready_utc, claimed_utc, attempts, last_error, note_kind, filed_unsorted, filed_folder,
        bundle_pages, billing_note,
    ) = row
    return {
        "draft_id": draft_id,
        "matter_id": matter_id,
        "ticks": json.loads(ticks_json) if ticks_json else {},
        "note_text": note_text,
        "status": status,
        "created_utc": created_utc,
        "committed_utc": committed_utc,
        "an_output_path": an_output_path,
        "billing_item_id": billing_item_id,
        "billing_deleted_utc": billing_deleted_utc,
        "caller": caller,
        "caller_other": caller_other,
        "time_minutes": time_minutes,
        "ready_utc": ready_utc,
        "claimed_utc": claimed_utc,
        "attempts": int(attempts or 0),
        "last_error": last_error,
        "kind": note_kind or "call",
        "filed_unsorted": bool(filed_unsorted),
        "filed_folder": filed_folder or "",
        "bundle_pages": bundle_pages,
        "billing_note": billing_note or "",
    }


_COLUMNS = (
    "draft_id, matter_id, ticks_json, note_text, status, created_utc, committed_utc, "
    "an_output_path, billing_item_id, billing_deleted_utc, caller, caller_other, "
    "time_minutes, ready_utc, claimed_utc, attempts, last_error, note_kind, filed_unsorted, filed_folder, "
    "bundle_pages, billing_note"
)


def save_pending(
    *,
    matter_id: str,
    ticks: dict[str, bool] | None = None,
    note_text: str,
    caller: str | None = None,
    caller_other: str | None = None,
    time_minutes: int | None = None,
    queue: bool = False,
    kind: str = "call",
    doc_kind: str | None = None,
    doc_other: str | None = None,
    pages: int | None = None,
    attendance_folder: str | None = None,
    allow_unknown_time: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = str(matter_id or "").strip()
    if not matter:
        raise AttendanceNoteDraftError("matter_id is required")
    kind = validate_kind(kind)
    details = caller_details(caller, caller_other, kind)
    time_minutes = validate_time_minutes(time_minutes)
    if kind in LETTER_KINDS:
        raise AttendanceNoteDraftError("a letter has no note of its own: make a Perusal (letter in) or Preparation (letter out) note")
    if kind in TIME_KINDS:
        from billing import letter_notes

        try:
            letter_notes.validate_meta(doc_kind, pages)
        except Exception as exc:
            raise AttendanceNoteDraftError(str(exc)) from exc
        if time_minutes is not None or pages:
            time_minutes = min(letter_notes.note_minutes(pages, time_minutes, db_path=db_path), MAX_TIME_MINUTES) or None
        if time_minutes is None and not allow_unknown_time:
            raise AttendanceNoteDraftError("say the time spent or the number of pages")
    draft_id = uuid.uuid4().hex
    now = _now()
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO an_drafts (draft_id, matter_id, ticks_json, note_text, status, created_utc, "
            "caller, caller_other, time_minutes, ready_utc, attempts, note_kind) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, 0, ?)",
            (
                draft_id, matter, json.dumps(ticks or {}), str(note_text or ""), now,
                str(caller or "").strip().lower() or None,
                str(caller_other or "").strip() or None if details else None,
                time_minutes, now if queue else None,
                None if kind == "call" else kind,
            ),
        )
        conn.commit()
    if kind in TIME_KINDS:
        from billing import letter_notes

        try:
            letter_notes.set_meta(draft_id, doc_kind, pages, db_path=db_path)
            if doc_kind == "other":
                letter_notes.set_doc_other(draft_id, doc_other, db_path=db_path)
        except Exception as exc:
            raise AttendanceNoteDraftError(str(exc)) from exc
    if attendance_folder:
        from billing import letter_notes

        letter_notes.set_folder(draft_id, attendance_folder, db_path=db_path)
    return {"draft_id": draft_id, "matter_id": matter, "status": "pending", "created_utc": now}


def get(draft_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with ops_db.connect(db_path) as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM an_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def cancel(draft_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    existing = get(draft_id, db_path=db_path)
    if existing is None:
        raise AttendanceNoteDraftError(f"no such draft: {draft_id}")
    if existing["status"] == "draft":
        return existing
    if existing["status"] != "pending":
        raise AttendanceNoteDraftError(f"draft {draft_id} is already {existing['status']}, cannot cancel")
    with ops_db.connect(db_path) as conn:
        conn.execute("UPDATE an_drafts SET status = 'draft' WHERE draft_id = ?", (draft_id,))
        conn.commit()
    return get(draft_id, db_path=db_path)


def mark_committed(
    draft_id: str,
    *,
    an_output_path: str,
    billing_item_id: str | None = None,
    filed_unsorted: bool = False,
    filed_folder: str = "",
    bundle_pages: int | None = None,
    billing_note: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    existing = get(draft_id, db_path=db_path)
    if existing is None:
        raise AttendanceNoteDraftError(f"no such draft: {draft_id}")
    if existing["status"] != "pending":
        raise AttendanceNoteDraftError(f"draft {draft_id} is {existing['status']}, expected pending")
    now = _now()
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "UPDATE an_drafts SET status = 'committed', committed_utc = ?, an_output_path = ?, "
            "billing_item_id = ?, filed_unsorted = ?, filed_folder = ?, bundle_pages = ?, billing_note = ? "
            "WHERE draft_id = ?",
            (
                now, an_output_path, billing_item_id, 1 if filed_unsorted else 0, filed_folder,
                bundle_pages, billing_note or None, draft_id,
            ),
        )
        conn.commit()
    return get(draft_id, db_path=db_path)


def delete_billing(draft_id: str, *, by: str = "", db_path: str | Path | None = None) -> dict[str, Any]:
    existing = get(draft_id, db_path=db_path)
    if existing is None:
        raise AttendanceNoteDraftError(f"no such draft: {draft_id}")
    if existing["billing_deleted_utc"]:
        return existing
    if existing["status"] != "committed":
        raise AttendanceNoteDraftError(f"draft {draft_id} is {existing['status']}, expected committed")
    if not existing["billing_item_id"]:
        raise AttendanceNoteDraftError(f"draft {draft_id} has no billing_item_id to reverse")

    import billing.billing_items as billing_items

    billing_items.remove_item(existing["billing_item_id"], by=by, db_path=db_path)
    now = _now()
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "UPDATE an_drafts SET billing_deleted_utc = ? WHERE draft_id = ?",
            (now, draft_id),
        )
        conn.commit()
    return get(draft_id, db_path=db_path)


def restore_billing_item(item_id: str, *, by: str = "", db_path: str | Path | None = None) -> dict[str, Any]:
    import billing.billing_items as billing_items

    item = billing_items.get_item(item_id, db_path=db_path)
    if item is None:
        raise AttendanceNoteDraftError(f"no such billing item: {item_id}")
    if item["removed_utc"]:
        billing_items.restore_item(item["item_id"], by=by, db_path=db_path)
        with ops_db.connect(db_path) as conn:
            conn.execute(
                "UPDATE an_drafts SET billing_deleted_utc = NULL WHERE billing_item_id = ?",
                (item["item_id"],),
            )
            conn.commit()
    return billing_items.get_item(item["item_id"], db_path=db_path)


def list_ready_to_commit(*, older_than_seconds: int = 60, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=older_than_seconds)).isoformat().replace(
        "+00:00", "Z"
    )
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM an_drafts WHERE status = 'pending' "
            "AND (created_utc <= ? OR ready_utc IS NOT NULL)",
            (cutoff,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


DEFAULT_UNSORTED_FOLDER = "Unsorted Attendance Notes"
UNSORTED_BOOK = firm_profile.load_profile().unsorted_attendance_book
DEFAULT_UNSORTED_PATH = f"{firm_profile.load_profile().library_root}/{DEFAULT_UNSORTED_FOLDER}"
LEGACY_UNSORTED_PATH = f"{firm_profile.load_profile().library_root}/{UNSORTED_BOOK}"
_CACHE_SECONDS = 60.0
_unsorted_cache: dict[str, tuple[float, tuple[str, str]]] = {}


class UnsortedTarget(NamedTuple):

    drive_id: str
    folder_id: str
    name: str
    wanted: str
    fell_back: bool


def unsorted_path() -> str:
    import app_settings

    return app_settings.get_setting("unsorted_notes_folder") or DEFAULT_UNSORTED_PATH


def _folder_ids(graph_files, path: str, token: str) -> tuple[str, str]:
    graph_path = graph_files.normalise_onedrive_path(path)
    drive = graph_files.drive_id_for(graph_path, token)
    item = graph_files.graph_json(graph_files.item_url(drive, graph_path.relative_path), token)
    return drive, str(item["id"])


def unsorted_name() -> str:
    return unsorted_path().rsplit("/", 1)[-1]


def _is_missing(exc: BaseException) -> bool:
    return getattr(exc, "code", None) == 404 or "HTTP Error 404" in str(exc)


def _find(graph_files, path: str, token: str) -> tuple[str, str] | None:
    import time

    hit = _unsorted_cache.get(path)
    if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    try:
        found = _folder_ids(graph_files, path, token)
    except Exception as exc:
        if _is_missing(exc):
            _unsorted_cache.pop(path, None)
            return None
        raise
    _unsorted_cache[path] = (time.monotonic(), found)
    return found


def resolve_unsorted() -> UnsortedTarget:
    import graph_files

    wanted_path = unsorted_path()
    wanted = wanted_path.rstrip("/").rsplit("/", 1)[-1]
    try:
        token = graph_files.token()
        found = _find(graph_files, wanted_path, token)
        if found:
            return UnsortedTarget(*found, wanted, wanted, False)
        fell_back = wanted_path.rstrip("/").lower() != DEFAULT_UNSORTED_PATH.lower()
        found = _find(graph_files, DEFAULT_UNSORTED_PATH, token) if fell_back else None
        if not found:
            parent = DEFAULT_UNSORTED_PATH.rsplit("/", 1)[0]
            try:
                graph_files.create_folder(parent, DEFAULT_UNSORTED_FOLDER, token)
            except Exception:
                pass
            _unsorted_cache.pop(DEFAULT_UNSORTED_PATH, None)
            found = _find(graph_files, DEFAULT_UNSORTED_PATH, token)
        if not found:
            raise AttendanceNoteDraftError(f"the {DEFAULT_UNSORTED_FOLDER} folder could not be found or made")
        return UnsortedTarget(*found, DEFAULT_UNSORTED_FOLDER, wanted, fell_back)
    except AttendanceNoteDraftError:
        raise
    except Exception as exc:
        raise AttendanceNoteDraftError(f"the {wanted} folder could not be read") from exc


def unsorted_folder() -> tuple[str, str]:
    target = resolve_unsorted()
    return target.drive_id, target.folder_id


_DOB_SUFFIX_RE = re.compile(r"\s*\((?:DOB|D\.O\.B\.?|born)[^)]*\)\s*$", re.IGNORECASE)


def clean_client_name(name: str) -> str:
    return _DOB_SUFFIX_RE.sub("", " ".join(str(name or "").split())).strip()


def folder_choice_for_file(matter_id: str, file_name: str, *, db_path: str | Path | None = None) -> str:
    from urllib.parse import unquote

    from billing import letter_notes

    name = str(file_name or "").strip().casefold()
    if not name:
        return ""
    try:
        with ops_db.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT d.draft_id, d.an_output_path FROM an_drafts d JOIN an_letter_meta m ON m.draft_id = d.draft_id "
                "WHERE d.matter_id = ? AND d.status = 'committed' AND m.attendance_folder IS NOT NULL AND m.attendance_folder != ''",
                (str(matter_id),),
            ).fetchall()
    except Exception:
        return ""
    for draft_id, output in rows:
        if unquote(str(output or "")).casefold().rsplit("/", 1)[-1] == name:
            return letter_notes.get_folder(str(draft_id), db_path=db_path)
    return ""


def attendance_folder_ids(folder: Any, order_text: str, custom_folder: str = "") -> tuple[str, str]:
    import agwu

    if folder is None or getattr(folder, "status", "not_found") == "not_found" or not getattr(folder, "attendance_folder_id", ""):
        return "", ""
    drive_id, folder_id = str(folder.drive_id or ""), str(folder.attendance_folder_id)
    if custom_folder:
        try:
            named, _ = agwu.folder.child_folder_named(folder.matter_folder_id, folder.drive_id, custom_folder)
        except Exception:
            named = ""
        return (drive_id, named) if named else ("", "")
    try:
        by_order, _ = agwu.folder.attendance_subfolder_for(folder.matter_folder_id, folder.drive_id, order_text)
    except Exception:
        by_order = ""
    return drive_id, by_order or folder_id


def order_text_of(row: dict[str, Any]) -> str:
    resolved = matter_orders.resolve_row(row, load_rows=True)
    return ",".join(resolved.codes) if resolved.structured else str(row.get("order_requested_text") or "")


def _matter_label(row: dict[str, Any]) -> str:
    resolved = matter_orders.resolve_row(row, load_rows=True)
    if resolved.structured:
        return ",".join(resolved.codes)
    return str(normalise_order_text(row.get("order_requested_text")) or "").strip()


def _why_no_attendance_folder(folder: Any) -> str:
    import agwu

    try:
        return agwu.folder.why_no_attendance_folder(
            str(getattr(folder, "matter_folder_id", "") or ""), str(getattr(folder, "drive_id", "") or ""),
            matter_folder_name=str(getattr(folder, "matter_folder_path", "") or "").rsplit("/", 1)[-1],
        )
    except Exception:
        return ""


def _ensure_group_folder(folder: Any, group: str, client_name: str) -> tuple[str, str] | None:
    matter_folder_id = str(getattr(folder, "matter_folder_id", "") or "")
    parent = str(getattr(folder, "matter_folder_path", "") or "")
    drive_id = str(getattr(folder, "drive_id", "") or "")
    if not matter_folder_id or not parent:
        return None
    try:
        import agwu
        import graph_files

        if any(f.get("code") == group for f in agwu.folder.attendance_folders_of(matter_folder_id, drive_id)):
            return None
        surname = (client_name.split() or [""])[-1].upper()
        item = graph_files.create_folder(parent, f"Attendance-Notes-({group})-{surname}", graph_files.token())
    except Exception:
        return None
    new_id = str(item.get("id") or "")
    return (drive_id, new_id) if new_id else None


def _resolve_matter_context(matter_id: str, folder_choice: str = "") -> dict[str, Any]:
    import clientdb_sql
    import agwu

    row = clientdb_sql.get_client_by_matter_id(matter_id)
    if not row:
        raise AttendanceNoteDraftError(f"matter {matter_id} not found on record")
    client_name = clean_client_name(str(row.get("client_name") or row.get("name") or ""))
    if not client_name:
        raise AttendanceNoteDraftError(f"matter {matter_id} has no client_name on file")

    phone = ""
    try:
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT p.phone_digits FROM dbo.matters m "
                "LEFT JOIN dbo.people p ON p.person_id = m.primary_person_id "
                "WHERE m.matter_id = ?",
                (matter_id,),
            )
            phone_row = cursor.fetchone()
            phone = str(phone_row[0] or "").strip() if phone_row else ""
    except Exception:
        pass

    folder = agwu.resolve_folder(
        matter_id,
        allow_live_fallback=True,
        caller="attendance_note_drafts.commit_draft",
        live_search_hint=client_name,
    )
    from billing import letter_notes

    choice = letter_notes.clean_folder(folder_choice)
    custom = choice if letter_notes.is_custom_folder(choice) else ""
    made = _ensure_group_folder(folder, choice, client_name) if choice in ("FLA", "CA") else None
    if made:
        drive_id, folder_id = made
    else:
        drive_id, folder_id = attendance_folder_ids(folder, choice or order_text_of(row), custom_folder=custom)
    fallback = not folder_id
    unsorted = None
    unsorted_reason = _why_no_attendance_folder(folder) if fallback else ""
    if fallback:
        try:
            unsorted = resolve_unsorted()
        except AttendanceNoteDraftError as exc:
            raise AttendanceNoteDraftError(
                f"matter {matter_id} has no live attendance-note folder yet, and {exc}"
            ) from exc
        drive_id, folder_id = unsorted.drive_id, unsorted.folder_id

    return {
        "fallback": fallback,
        "unsorted_name": unsorted.name if unsorted else "",
        "unsorted_wanted": unsorted.wanted if unsorted and unsorted.fell_back else "",
        "unsorted_reason": unsorted_reason,
        "matter_id": str(matter_id),
        "client_name": client_name,
        "surname": client_name.split()[-1] if client_name.split() else client_name,
        "internal_ref": str(row.get("company_reference") or row.get("case_reference") or "").strip(),
        "phone": phone,
        "matter": _matter_label(row),
        "matter_folder_path": "" if fallback else str(getattr(folder, "matter_folder_path", "") or ""),
        "destination_drive_id": drive_id,
        "destination_folder_id": folder_id,
    }



_PARTY_TO_CALLER = {"client": "client", "court": "court", "counsel": "counsel", "other_side": "respondent"}


def _caller_for_party(party: str) -> tuple[str, str | None]:
    key = str(party or "").strip()
    if key in _PARTY_TO_CALLER:
        return _PARTY_TO_CALLER[key], None
    from billing import billing_items

    return "other", billing_items.party_labels().get(key, "Others")


def _pages_text(pages: int | None) -> str:
    return f"{int(pages)} page{'s' if int(pages) != 1 else ''}" if pages else "page count not known"


def time_note_text(direction: str, label: str, pages: int | None, doc_label: str = "", *, doc_other: str | None = None, db_path: str | Path | None = None) -> str:
    from billing import letter_notes

    word = "Perusal of" if direction == "in" else "Preparation of"
    what = f"{doc_label} " if doc_label and doc_label != "letter" else ""
    prep = "from" if direction == "in" else "to"
    who = f" {prep} {label}" if label else ""
    tbc = "" if letter_notes.note_minutes(pages, db_path=db_path) else " Time to be confirmed once the page count is known."
    typed = letter_notes.clean_doc_other(doc_other)
    if typed:
        return f"{word} the {typed}{who}.{tbc}"
    return f"{word} the {what}letter {direction}{who}.{tbc}"


def queue_time_note(
    *, direction: str, matter_id: str, party: str, pages: int | None, note_item_id: str,
    item_date: str = "", doc_kind: str | None = None, doc_other: str | None = None, pair_key: str = "", db_path: str | Path | None = None,
) -> str:
    from billing import billing_items, letter_notes

    label = billing_items.party_labels().get(party, "Others") if party else ""
    caller, other = _caller_for_party(party) if party else ("", None)
    doc_label = letter_notes.DOC_KINDS.get(str(doc_kind or ""), "")
    text = time_note_text(direction, label, pages, doc_label, doc_other=doc_other if doc_kind == "other" else None, db_path=db_path)
    row = save_pending(
        matter_id=matter_id, note_text=text, caller=caller, caller_other=other, queue=True,
        kind="perusal" if direction == "in" else "preparation", doc_kind=doc_kind, doc_other=doc_other, pages=pages,
        allow_unknown_time=True, db_path=db_path,
    )
    letter_notes.set_links(row["draft_id"], note_item_id=note_item_id, pair_key=pair_key or None, auto_activity=text, db_path=db_path)
    return row["draft_id"]


def queue_letter_notes(
    *, matter_id: str, direction: str, party: str, dedupe_key: str, pages: int | None, item_date: str,
    letter_item_id: str = "", note_item_id: str, doc_kind: str | None = None, db_path: str | Path | None = None,
) -> dict[str, str]:
    from billing import letter_notes

    if direction not in ("in", "out"):
        raise AttendanceNoteDraftError(f"direction must be 'in' or 'out', got {direction!r}")
    pair_key = f"pair:{dedupe_key}"[:64]
    if letter_notes.drafts_for_pair_key(pair_key, db_path=db_path):
        return {}
    time_id = queue_time_note(
        direction=direction, matter_id=matter_id, party=party, pages=pages, note_item_id=note_item_id,
        item_date=item_date, doc_kind=doc_kind, pair_key=pair_key, db_path=db_path,
    )
    return {"time_draft_id": time_id}


def _record_letter_ledger(draft_id: str, kind: str, matter_id: str, client_name: str, note_item_id: str, item: dict[str, Any], db_path: str | Path | None) -> None:
    try:
        from billing import billing_items

        direction = "in" if kind == "perusal" else "out"
        letter = billing_items.record_correspondence_item(
            matter_id=matter_id, item_date=str(item.get("date") or ""), direction=direction,
            party=str(item.get("party") or ""), dedupe_key=f"an:{draft_id}", client_name=client_name, db_path=db_path,
        )
        if letter:
            billing_items.link_items(letter["item_id"], note_item_id, db_path=db_path)
    except Exception:
        logging.getLogger(__name__).warning("routine letter line not recorded for draft %s", draft_id, exc_info=True)


def _adopt_document_url(item_id: str, output_path: str, db_path: str | Path | None) -> None:
    if not item_id or not output_path.startswith("http"):
        return
    try:
        import billing.billing_items as billing_items

        if (billing_items.get_item(item_id, db_path=db_path) or {}).get("document_url"):
            return

        billing_items.set_document_url(item_id, output_path, db_path=db_path)
    except Exception:
        log.warning("billing line not linked to its note (%s)", item_id, exc_info=True)


def commit_draft(
    draft_id: str, *, time_minutes: int | None = None, db_path: str | Path | None = None
) -> dict[str, Any]:
    from billing import letter_notes

    time_minutes = validate_time_minutes(time_minutes)
    draft = get(draft_id, db_path=db_path)
    if draft is None:
        raise AttendanceNoteDraftError(f"no such draft: {draft_id}")
    if draft["status"] != "pending":
        raise AttendanceNoteDraftError(f"draft {draft_id} is {draft['status']}, expected pending")

    chosen_folder = letter_notes.get_folder(draft_id, db_path=db_path)
    context = _resolve_matter_context(draft["matter_id"], chosen_folder) if chosen_folder else _resolve_matter_context(draft["matter_id"])
    kind = draft.get("kind") or "call"
    links = letter_notes.get_links(draft_id, db_path=db_path)
    meta = letter_notes.get_meta(draft_id, db_path=db_path)
    party = caller_details(draft.get("caller"), draft.get("caller_other"), kind).get("caller", "")
    if links["auto_activity"]:
        body_fields = {"activity": links["auto_activity"], "to_do": ""}
    else:
        try:
            body_fields = draft_body_fields(
                ticks=draft["ticks"], note_text=draft["note_text"],
                **({"kind": kind} if kind != "call" else {}), **({"party": party} if party else {}),
            )
        except AttendanceNoteDraftCostRefusal as exc:
            raise AttendanceNoteCostRefusalError(f"could not draft AN body: the model provider refused for cost/credit: {exc}") from exc
        except AttendanceNoteDraftGooseError as exc:
            raise AttendanceNoteDraftError(f"could not draft AN body: {exc}") from exc

    proofread_flags = str(body_fields.pop(PROOFREAD_FLAGS_KEY, "") or "")
    fallback = bool(context.pop("fallback", False))
    context.pop("matter_folder_path", None)
    unsorted_reason = str(context.pop("unsorted_reason", "") or "")
    adopt_id = links["note_item_id"] if kind in TIME_KINDS else ""
    details = caller_details(draft.get("caller"), draft.get("caller_other"), kind)
    if kind in TIME_KINDS and not adopt_id:
        pages = meta["pages"]
        if time_minutes is not None:
            time_minutes = min(letter_notes.note_minutes(minutes=time_minutes), MAX_TIME_MINUTES)
        facts = []
        if pages:
            facts.append(_pages_text(pages))
        if time_minutes is not None:
            facts.append(format_time_engaged(time_minutes))
        if facts:
            details["billing_description"] = f"{details.get('billing_description', '')} ({', '.join(facts)})"
    item = {
        "date": dt.datetime.now().strftime("%d.%m.%y"),
        "caller": "Client",
        **context,
        **body_fields,
        **details,
        **({"time": format_time_engaged(time_minutes)} if time_minutes is not None else {}),
        **({"time": time_engaged_for_pages(meta["pages"], time_minutes, db_path=db_path)} if adopt_id else {}),
        **({"skip_billing": True} if adopt_id else {}),
        "billing_work_id": f"an-draft:{draft_id}",
    }
    result = subprocess.run(
        [sys.executable, str(CREATE_AN_SCRIPT), "--payload-json", json.dumps({"items": [item]})],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise AttendanceNoteDraftError(f"create-attendance-note.py failed (exit {result.returncode}): {result.stderr[-500:]}")
    try:
        created = json.loads(result.stdout).get("created", [])
    except json.JSONDecodeError as exc:
        raise AttendanceNoteDraftError(f"create-attendance-note.py returned unparseable output: {result.stdout[:300]!r}") from exc
    if not created or created[0].get("error"):
        error = created[0].get("error") if created else "no result returned"
        raise AttendanceNoteDraftError(f"AN upload failed: {error}")

    output_path = str(created[0].get("webUrl") or created[0].get("id") or created[0].get("filename") or "")
    billing_item_id = adopt_id or created[0].get("billing_item_id") or None
    committed = mark_committed(
        draft_id,
        an_output_path=output_path,
        billing_item_id=billing_item_id,
        filed_unsorted=fallback,
        filed_folder=folder_label(created[0].get("parentReference")),
        db_path=db_path,
    )
    robot_notices.resolve(f"an:{draft_id}", db_path=db_path)
    if proofread_flags:
        _notice(
            "attendance_note_proofread",
            "Attendance note: some sentences were left as typed",
            f"The proofread would have changed the words of some sentences, so they were filed exactly as typed: {proofread_flags[:300]}. "
            "Read the note and correct it by hand if it needs it.",
            matter_id=str(context["matter_id"]),
            client_name=str(context["client_name"]),
            dedupe_key=f"an-proofread:{draft_id}",
            db_path=db_path,
        )
    if adopt_id:
        _adopt_document_url(adopt_id, output_path, db_path)
    if kind in TIME_KINDS and not adopt_id and billing_item_id:
        _record_letter_ledger(draft_id, kind, str(context["matter_id"]), str(context["client_name"]), billing_item_id, item, db_path)
    if fallback:
        wanted = str(context.get("unsorted_wanted") or "")
        _notice(
            "attendance_note_unsorted",
            "Attendance note filed to Unsorted",
            f"{context['client_name']} has no attendance-notes folder that could be found"
            + (f" ({unsorted_reason})" if unsorted_reason else "")
            + f", so the note is in '{context.get('unsorted_name') or unsorted_name()}'. "
            + (f"The folder chosen for unsorted notes, '{wanted}', could not be found, so the default folder was used. " if wanted else "")
            + "It moves into the client's folder by itself once there is one.",
            matter_id=str(context["matter_id"]),
            client_name=str(context["client_name"]),
            dedupe_key=f"an-unsorted:{context['matter_id']}:{dt.datetime.now(dt.timezone.utc):%Y-%m-%d}",
            db_path=db_path,
        )
        from vergil import auto_flags

        auto_flags.raise_flag(str(context["matter_id"]), auto_flags.UNSORTED_AN_REASON, db_path=db_path)
    return committed


def time_engaged_for_pages(pages: int | None, time_minutes: int | None = None, *, db_path: str | Path | None = None) -> str:
    from billing import letter_notes

    minutes = letter_notes.note_minutes(pages, time_minutes, db_path=db_path)
    if not minutes:
        return "To be confirmed (page count not known)"
    return format_time_engaged(min(minutes, MAX_TIME_MINUTES))


def _notice(kind: str, title: str, detail: str, *, matter_id: str, client_name: str, dedupe_key: str, db_path: Any) -> None:
    try:
        robot_notices.add(kind, title, detail, matter_id=matter_id, client_name=client_name, dedupe_key=dedupe_key, db_path=db_path)
    except Exception as exc:
        log.error("robot notice not written (%s)", type(exc).__name__)


def _client_name_for(matter_id: str) -> str:
    try:
        import clientdb_sql

        row = clientdb_sql.get_client_by_matter_id(matter_id) or {}
        return str(row.get("client_name") or row.get("name") or "").strip()
    except Exception:
        return ""


def create_and_commit(
    *,
    matter_id: str,
    caller: str,
    caller_other: str | None = None,
    note_text: str,
    time_minutes: int | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not str(caller or "").strip():
        raise AttendanceNoteDraftError("caller is required")
    if not str(note_text or "").strip():
        raise AttendanceNoteDraftError("note_text is required")
    time_minutes = validate_time_minutes(time_minutes)
    row = save_pending(
        matter_id=matter_id, note_text=note_text, caller=caller, caller_other=caller_other, db_path=db_path
    )
    try:
        return commit_draft(row["draft_id"], time_minutes=time_minutes, db_path=db_path)
    except Exception:
        try:
            cancel(row["draft_id"], db_path=db_path)
        except Exception:
            pass
        raise



CLAIM_STALE_SECONDS = 10 * 60
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 30

WAITING_FOR_KEY = "Waiting for the AI service's credit. This note files itself once it is topped up or the limit resets."
KEY_RECHECK_SECONDS = 15 * 60
KEY_MIN_REMAINING = 0.5
_KEY_CACHE_SECONDS = 5 * 60
_key_checked: tuple[float, bool] | None = None

_KNOWN_SAFE_ERRORS = (
    "has no live attendance-note folder yet",
    "not found on record",
    "has no client_name on file",
)


def _iso(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def plain_error(exc: BaseException) -> str:
    message = str(exc)
    for known in _KNOWN_SAFE_ERRORS:
        if known in message:
            return message[:200]
    if "could not draft AN body" in message:
        return "The note could not be written up just now."
    if isinstance(exc, AttendanceNoteDraftError):
        return "The note could not be filed to SharePoint just now."
    return "Something went wrong filing the note."


def claim(draft_id: str, *, db_path: str | Path | None = None, now: dt.datetime | None = None) -> bool:
    current = now or dt.datetime.now(dt.timezone.utc)
    stale_before = _iso(current - dt.timedelta(seconds=CLAIM_STALE_SECONDS))
    with ops_db.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE an_drafts SET claimed_utc = ?, attempts = COALESCE(attempts, 0) + 1 "
            "WHERE draft_id = ? AND status = 'pending' AND ready_utc IS NOT NULL AND ready_utc <= ? "
            "AND COALESCE(attempts, 0) < ? AND (claimed_utc IS NULL OR claimed_utc < ?)",
            (_iso(current), draft_id, _iso(current), MAX_ATTEMPTS, stale_before),
        )
        conn.commit()
        return cursor.rowcount == 1


def release_failed(
    draft_id: str, error: str, *, db_path: str | Path | None = None, now: dt.datetime | None = None
) -> None:
    current = now or dt.datetime.now(dt.timezone.utc)
    with ops_db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(attempts, 0) FROM an_drafts WHERE draft_id = ? AND status = 'pending'", (draft_id,)
        ).fetchone()
        if row is None:
            return
        next_due = _iso(current + dt.timedelta(seconds=RETRY_BACKOFF_SECONDS * max(1, int(row[0]))))
        conn.execute(
            "UPDATE an_drafts SET claimed_utc = NULL, last_error = ?, ready_utc = ? "
            "WHERE draft_id = ? AND status = 'pending'",
            (str(error)[:300], next_due, draft_id),
        )
        conn.commit()


def key_has_room(*, now: float | None = None) -> bool:
    global _key_checked
    import time

    moment = time.monotonic() if now is None else now
    if _key_checked and moment - _key_checked[0] < _KEY_CACHE_SECONDS:
        return _key_checked[1]
    try:
        from monitoring import openrouter_spend

        spend = openrouter_spend.fetch_spend()
        credit = float(spend.get("total_credits") or 0) - float(spend.get("total_usage") or 0)
        remaining = spend.get("key_limit_remaining")
        room = credit >= KEY_MIN_REMAINING and (remaining is None or float(remaining) >= KEY_MIN_REMAINING)
    except Exception:
        room = True
    _key_checked = (moment, room)
    return room


def release_waiting_for_key(
    draft_id: str, *, db_path: str | Path | None = None, now: dt.datetime | None = None
) -> None:
    current = now or dt.datetime.now(dt.timezone.utc)
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "UPDATE an_drafts SET claimed_utc = NULL, attempts = MAX(COALESCE(attempts, 0) - 1, 0), last_error = ?, "
            "ready_utc = ? WHERE draft_id = ? AND status = 'pending'",
            (WAITING_FOR_KEY, _iso(current + dt.timedelta(seconds=KEY_RECHECK_SECONDS)), draft_id),
        )
        conn.commit()


def create_queued(
    *,
    matter_id: str,
    caller: str,
    caller_other: str | None = None,
    note_text: str,
    time_minutes: int | None = None,
    kind: str = "call",
    doc_kind: str | None = None,
    doc_other: str | None = None,
    pages: int | None = None,
    attendance_folder: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not str(caller or "").strip() and str(kind or "") not in TIME_KINDS:
        raise AttendanceNoteDraftError("the party is required")
    if not str(note_text or "").strip():
        raise AttendanceNoteDraftError("note_text is required")
    row = save_pending(
        matter_id=matter_id, note_text=note_text, caller=caller, caller_other=caller_other,
        time_minutes=time_minutes, queue=True, kind=kind, doc_kind=doc_kind, doc_other=doc_other, pages=pages,
        attendance_folder=attendance_folder, db_path=db_path,
    )
    return {"draft_id": row["draft_id"], "matter_id": row["matter_id"], "status": "pending"}


def commit_queued(draft_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    if not claim(draft_id, db_path=db_path):
        return None
    try:
        draft = get(draft_id, db_path=db_path)
        if draft is None:
            return None
        commit_draft(draft_id, time_minutes=draft.get("time_minutes"), db_path=db_path)
    except AttendanceNoteCostRefusalError:
        log.warning("attendance note waiting for the AI key")
        release_waiting_for_key(draft_id, db_path=db_path)
    except Exception as exc:
        log.error("attendance note filing failed (%s)", type(exc).__name__)
        release_failed(draft_id, plain_error(exc), db_path=db_path)
        _notice_if_given_up(draft_id, db_path=db_path)
    return status_of(draft_id, db_path=db_path)


def _day_label(created_utc: str) -> str:
    try:
        return dt.datetime.fromisoformat(str(created_utc).replace("Z", "+00:00")).strftime("%-d %b")
    except ValueError:
        return "an earlier day"


def _notice_if_given_up(draft_id: str, *, db_path: str | Path | None = None) -> None:
    view = status_of(draft_id, db_path=db_path)
    if not view or view["state"] != "failed":
        return
    _notice(
        "attendance_note_failed",
        "Attendance note not filed",
        f"Note of {_day_label(view['created_utc'])}. {view['error'] or 'The note could not be filed.'} "
        "The note is saved: open the client's Attendance notes tab, then Edit or Try again.",
        matter_id=str(view["matter_id"]),
        client_name=_client_name_for(str(view["matter_id"])),
        dedupe_key=f"an:{draft_id}",
        db_path=db_path,
    )


def start_background_commit(draft_id: str, *, db_path: str | Path | None = None) -> threading.Thread:
    thread = threading.Thread(
        target=commit_queued, args=(draft_id,), kwargs={"db_path": db_path},
        name=f"an-commit-{draft_id[:8]}", daemon=True,
    )
    thread.start()
    return thread


def list_queued(*, db_path: str | Path | None = None, now: dt.datetime | None = None) -> list[str]:
    current = now or dt.datetime.now(dt.timezone.utc)
    stale_before = _iso(current - dt.timedelta(seconds=CLAIM_STALE_SECONDS))
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT draft_id, last_error FROM an_drafts WHERE status = 'pending' AND ready_utc IS NOT NULL "
            "AND ready_utc <= ? AND COALESCE(attempts, 0) < ? AND (claimed_utc IS NULL OR claimed_utc < ?) "
            "ORDER BY ready_utc",
            (_iso(current), MAX_ATTEMPTS, stale_before),
        ).fetchall()
    room = key_has_room() if any(row[1] == WAITING_FOR_KEY for row in rows) else True
    return [row[0] for row in rows if room or row[1] != WAITING_FOR_KEY]


def sweep_queued(*, db_path: str | Path | None = None) -> int:
    tried = 0
    for draft_id in list_queued(db_path=db_path):
        if commit_queued(draft_id, db_path=db_path) is not None:
            tried += 1
    notify_failed(db_path=db_path)
    return tried


def notify_failed(*, db_path: str | Path | None = None) -> int:
    raised = 0
    try:
        stale_before = _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=CLAIM_STALE_SECONDS))
        with ops_db.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT draft_id FROM an_drafts WHERE status = 'pending' AND ready_utc IS NOT NULL "
                "AND COALESCE(attempts, 0) >= ? AND (claimed_utc IS NULL OR claimed_utc < ?)",
                (MAX_ATTEMPTS, stale_before),
            ).fetchall()
        for (draft_id,) in rows:
            if robot_notices.ever_raised(f"an:{draft_id}", db_path=db_path):
                continue
            _notice_if_given_up(draft_id, db_path=db_path)
            raised += 1
    except Exception as exc:
        log.error("failed-note notices not written (%s)", type(exc).__name__)
    return raised


def retry(draft_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    existing = get(draft_id, db_path=db_path)
    if existing is None:
        raise AttendanceNoteDraftError(f"no such draft: {draft_id}")
    if existing["status"] == "committed":
        raise AttendanceNoteDraftError("that attendance note has already been filed")
    if existing["status"] != "pending" or not existing["ready_utc"]:
        raise AttendanceNoteDraftError("that attendance note cannot be retried")
    if _claim_is_live(existing.get("claimed_utc")):
        raise AttendanceNoteDraftError("that attendance note is being filed right now; try again in a minute")
    stale_before = _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=CLAIM_STALE_SECONDS))
    with ops_db.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE an_drafts SET attempts = 0, claimed_utc = NULL, last_error = NULL, ready_utc = ? "
            "WHERE draft_id = ? AND status = 'pending' AND (claimed_utc IS NULL OR claimed_utc < ?)",
            (_now(), draft_id, stale_before),
        )
        conn.commit()
        if cursor.rowcount != 1:
            raise AttendanceNoteDraftError("that attendance note is being filed right now; try again in a minute")
    robot_notices.resolve(f"an:{draft_id}", db_path=db_path)
    return status_of(draft_id, db_path=db_path)


def take_for_edit(draft_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    existing = get(draft_id, db_path=db_path)
    if existing is None:
        raise AttendanceNoteDraftError(f"no such draft: {draft_id}")
    if existing["status"] == "committed":
        raise AttendanceNoteDraftError("that attendance note has already been filed")
    if existing["status"] != "pending" or not existing["ready_utc"]:
        raise AttendanceNoteDraftError("that attendance note cannot be edited")
    if _claim_is_live(existing.get("claimed_utc")):
        raise AttendanceNoteDraftError("that attendance note is being filed right now; try again in a minute")
    stale_before = _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=CLAIM_STALE_SECONDS))
    with ops_db.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE an_drafts SET status = 'draft', claimed_utc = NULL WHERE draft_id = ? AND status = 'pending' "
            "AND (claimed_utc IS NULL OR claimed_utc < ?)",
            (draft_id, stale_before),
        )
        conn.commit()
        if cursor.rowcount != 1:
            raise AttendanceNoteDraftError("that attendance note is being filed right now; try again in a minute")
    robot_notices.resolve(f"an:{draft_id}", db_path=db_path)
    return {
        "draft_id": draft_id,
        "matter_id": existing["matter_id"],
        "caller": existing.get("caller") or "",
        "caller_other": existing.get("caller_other") or "",
        "note_text": existing["note_text"],
        "time_minutes": existing.get("time_minutes"),
        "kind": existing.get("kind") or "call",
        "pages": (_pages_of(draft_id, db_path=db_path) if (existing.get("kind") or "call") in TIME_KINDS else None),
    }


def _pages_of(draft_id: str, *, db_path: str | Path | None = None) -> int | None:
    from billing import letter_notes

    return letter_notes.get_meta(draft_id, db_path=db_path)["pages"]


def _claim_is_live(claimed_utc: str | None) -> bool:
    if not claimed_utc:
        return False
    return claimed_utc >= _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=CLAIM_STALE_SECONDS))


def clear_unsorted_notices(matter_id: str, *, db_path: str | Path | None = None) -> int:
    closed = 0
    try:
        from vergil import auto_flags

        for notice in robot_notices.open_for(str(matter_id), auto_flags.UNSORTED_AN_KIND, db_path=db_path):
            closed += robot_notices.resolve(str(notice.get("dedupe_key") or ""), db_path=db_path)
        if not robot_notices.open_for(str(matter_id), auto_flags.UNSORTED_AN_KIND, db_path=db_path):
            auto_flags.clear_flag(str(matter_id), auto_flags.UNSORTED_AN_REASON, db_path=db_path)
    except Exception as exc:
        log.error("unsorted notices not cleared (%s)", type(exc).__name__)
    return closed


def mark_moved_out_of_unsorted(matter_id: str, filed_folder: str, *, db_path: str | Path | None = None) -> str:
    try:
        with ops_db.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT draft_id FROM an_drafts WHERE matter_id = ? AND status = 'committed' AND filed_unsorted = 1",
                (str(matter_id),),
            ).fetchall()
            if len(rows) != 1:
                return ""
            draft_id = str(rows[0][0])
            conn.execute(
                "UPDATE an_drafts SET filed_unsorted = 0, filed_folder = ? WHERE draft_id = ?", (filed_folder, draft_id)
            )
            conn.commit()
        clear_unsorted_notices(matter_id, db_path=db_path)
        return draft_id
    except Exception as exc:
        log.error("moved note not recorded (%s)", type(exc).__name__)
        return ""


def folder_label(parent_reference: Any) -> str:
    path = str((parent_reference or {}).get("path") or "") if isinstance(parent_reference, dict) else ""
    parts = [p for p in path.split("root:", 1)[-1].split("/") if p]
    return " / ".join(parts[-3:])


def _status_view(row: dict[str, Any]) -> dict[str, Any]:
    if row["status"] == "committed":
        state = "filed"
    elif row["status"] == "draft":
        state = "failed"
    elif row["attempts"] >= MAX_ATTEMPTS and not _claim_is_live(row.get("claimed_utc")):
        state = "failed"
    else:
        state = "filing"
    path = str(row.get("an_output_path") or "")
    error = row.get("last_error") or None
    if state == "failed" and not error:
        error = "This note was cancelled." if row["status"] == "draft" else "The note could not be filed."
    if state == "filed":
        error = None
    return {
        "draft_id": row["draft_id"],
        "matter_id": row["matter_id"],
        "state": state,
        "an_url": path if path.startswith("http") else None,
        "unsorted": state == "filed" and bool(row.get("filed_unsorted")),
        "filed_folder": row.get("filed_folder") or "",
        "billing_item_id": row.get("billing_item_id") or None,
        "billing_removed": bool(row.get("billing_deleted_utc")),
        "error": error,
        "created_utc": row["created_utc"],
        "kind": row.get("kind") or "call",
        "bundle_pages": row.get("bundle_pages") if state == "filed" else None,
        "billing_note": (row.get("billing_note") or "") if state == "filed" else "",
    }


def status_of(draft_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    row = get(draft_id, db_path=db_path)
    return _status_view(row) if row else None


def list_recent(matter_id: str, *, hours: int = 48, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    cutoff = _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours))
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM an_drafts WHERE matter_id = ? AND ready_utc IS NOT NULL AND status != 'draft' "
            "AND (created_utc >= ? OR status = 'pending') ORDER BY created_utc DESC",
            (str(matter_id), cutoff),
        ).fetchall()
    views = [_status_view(_row_to_dict(row)) for row in rows]
    return [v for v in views if v["created_utc"] >= cutoff or v["state"] == "failed"]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="File queued attendance notes")
    parser.add_argument("command", choices=["sweep"])
    parser.parse_args(argv)
    print(json.dumps({"tried": sweep_queued()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
