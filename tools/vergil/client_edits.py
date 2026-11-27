from __future__ import annotations

import datetime as dt
import functools
import sys
import uuid
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
import clientdb_sql

COLUMNS = (
    "edit_id", "matter_id", "field_name", "old_value", "new_value", "note",
    "edited_by", "created_at",
)

NOTE_MAX_LENGTH = 100

REQUIRED_NAME_FIELDS = frozenset({"name_first", "name_last"})

FIELD_LABELS: dict[str, str] = {
    "name_first": "First name",
    "name_middle": "Middle name",
    "name_last": "Last name",
    "client_canonical_name": "Full name (as used on documents)",
    "dob_iso": "Date of birth",
    "sex": "Sex",
    "sex_other": "Sex (other)",
    "nino_canonical": "NI number",
    "phone_primary": "Telephone",
    "email_primary": "Email",
    "address_line1": "Address line 1",
    "address_line2": "Address line 2",
    "address_line3": "Address line 3",
    "address_line4": "Address line 4",
    "address_postcode": "Postcode",
    "matter_name": "Matter name",
    "client_role": "Client role",
    "company_reference": "Company reference",
    "order_requested_text": "Application / order type",
    "legal_aid_tracker_status": "Legal aid certificate status",
    "has_c8": "C8 confidentiality order",
    "c8_phone": "C8 - telephone",
    "c8_email": "C8 - email",
    "c8_address": "C8 - address",
    "tracker_notes": "Notes",
    "order_type_tags": "Order type tags",
    "children_summary": "Children",
    "relationship_start": "Relationship start",
    "relationship_end": "Relationship end",
    "marriage_date": "Date of marriage",
    "divorce_date": "Date of divorce",
    "lived_together": "Lived together",
    "married": "Married or in a civil partnership",
    "bail_conditions": "Respondent on bail with conditions",
    "bail_end_date": "Bail conditions end",
    "crime_refs": "Police crime reference(s)",
    "concluded": "Concluded",
    "live_matter_folder": "Matter folder location",
    "court_references": "Court reference(s)",
}

FLAG_LABELS: dict[str, str] = {
    "persistent_caller": "Frequent caller",
    "persistent_caller_respondent": "Frequent caller (Opponent)",
    "transferred": "Transferred",
    "dropped_out": "Dropped out",
    "billed": "Billed",
    "flagged": "Flagged",
    "starred": "Starred",
    "ccl_filed": "CCL filed",
    "waiting_client": "Waiting for client",
    "waiting_court": "Waiting for court",
    "waiting_counsel": "Waiting for counsel",
    "private_billing": "Privately billed",
}

try:
    from onboarding.new_client_categories import PILL_LABELS as _NEW_CLIENT_PILLS
    from onboarding.new_client_categories import SOURCE_LABELS as _SOURCE_PILLS

    FLAG_LABELS.update(_NEW_CLIENT_PILLS)
    FLAG_LABELS.update(_SOURCE_PILLS)
except ImportError:
    pass

FIELD_LABELS.update({f"flag:{name}": label for name, label in FLAG_LABELS.items()})
FIELD_LABELS["order_types"] = "Order types"


_ROW_ACTION_WORDS = {"add": "added", "update": "changed", "remove": "removed"}
_ROW_KIND_NOUNS = {"party": "Other party", "child": "Child"}


def field_label(field_name: str) -> str:
    if field_name in FIELD_LABELS:
        return FIELD_LABELS[field_name]
    kind, _, rest = field_name.partition("_")
    action, _, detail = rest.partition(":")
    if kind in _ROW_KIND_NOUNS and action in _ROW_ACTION_WORDS:
        label = f"{_ROW_KIND_NOUNS[kind]} {_ROW_ACTION_WORDS[action]}"
        return f"{label}: {detail}" if detail else label
    return field_name


PORTAL_FLAG = "portal"


def _portal_matters(matter_ids: list[str]) -> set[str]:
    try:
        from onboarding.pipeline import portal_courts

        return portal_courts.portal_matters(matter_ids)
    except Exception:
        return set()

PERSONAL_FLAGS: tuple[str, ...] = ("flagged", "starred")
DRAFT_REASON = "Unfinished draft"
_USER_LIMIT = 200


def personal_user(identity: str | None) -> str:
    return " ".join(str(identity or "").split()).lower()[:_USER_LIMIT]


def is_personal_request(flag_name: str) -> bool:
    return flag_name in PERSONAL_FLAGS


def _personal_rows(conn: Any, user: str, matters: list[str] | None = None, names: list[str] | None = None) -> list[tuple[str, str]]:
    where, args = ["user_key = ?"], [user]
    if matters is not None:
        where.append(f"matter_id IN ({', '.join('?' for _ in matters)})")
        args.extend(matters)
    if names is not None:
        where.append(f"flag_name IN ({', '.join('?' for _ in names)})")
        args.extend(names)
    sql = f"SELECT matter_id, flag_name FROM user_matter_flags WHERE {' AND '.join(where)}"
    return [(str(m), str(f)) for m, f in conn.execute(sql, tuple(args)).fetchall()]


class ClientEditError(ValueError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _clean(value: Any, *, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_multiline(value: Any) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def _named_in_change_log(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with clientdb_sql.acting_as(f"{_clean(kwargs.get('edited_by'), limit=150)} via CRM"):
            return func(*args, **kwargs)
    return wrapper


def _clean_sex_edit(matter: str, field_name: str, value: str) -> str:
    import field_shapes

    try:
        if field_name == "sex":
            return field_shapes.clean_sex_pair(value)[0]
        current = str(clientdb_sql.get_editable_field(matter, "sex") or "")
        return field_shapes.clean_sex_pair(current, value)[1]
    except ValueError as exc:
        raise ClientEditError(str(exc)) from exc


@_named_in_change_log
def record_edit(
    *,
    matter_id: str,
    field_name: str,
    new_value: str,
    note: str = "",
    edited_by: str,
    closed_at: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        raise ClientEditError("matter_id is required")
    by = _clean(edited_by, limit=200)
    if not by:
        raise ClientEditError("edited_by (your name) is required")

    if field_name == "concluded":
        value = _clean(new_value, limit=8)
        if value not in ("1", "0"):
            raise ClientEditError("new_value for concluded must be '1' or '0'")
        was_closed = clientdb_sql.is_matter_closed(matter)
        old_value = "1" if was_closed else "0"
        if value == "1":
            clientdb_sql.close_matter(
                matter, closed_by=by, notes=_clean(note, limit=NOTE_MAX_LENGTH), closed_at=closed_at
            )
        else:
            clientdb_sql.reopen_matter(matter, reopened_by=by, notes=_clean(note, limit=NOTE_MAX_LENGTH))
    elif field_name == "court_references":
        try:
            old_value = "\n".join(clientdb_sql.get_court_references(matter))
            wanted = clientdb_sql.set_court_references(matter, str(new_value or "")[:500].splitlines())
        except ValueError as exc:
            raise ClientEditError(str(exc)) from exc
        value = "\n".join(wanted)
    else:
        if field_name not in clientdb_sql.EDITABLE_FIELDS:
            raise ClientEditError(
                f"unknown field_name {field_name!r}; expected one of "
                f"{tuple(clientdb_sql.EDITABLE_FIELDS)}, 'concluded' or 'court_references'"
            )
        if field_name in clientdb_sql.BOOLEAN_EDITABLE_FIELDS:
            max_len = 8
        elif field_name in clientdb_sql.LONG_TEXT_EDITABLE_FIELDS:
            max_len = clientdb_sql.LONG_TEXT_MAX_LENGTH
        else:
            max_len = 500
        if field_name in clientdb_sql.LONG_TEXT_EDITABLE_FIELDS:
            value = _clean_multiline(new_value)
        else:
            value = " ".join(str(new_value or "").split())
        if len(value) > max_len:
            raise ClientEditError(f"{field_name} is {len(value)} characters; the most it takes is {max_len}")
        if not value and field_name in clientdb_sql.NOT_NULL_EDITABLE_FIELDS:
            raise ClientEditError(f"{field_name} cannot be blank")
        if not value and field_name in REQUIRED_NAME_FIELDS:
            raise ClientEditError(f"{FIELD_LABELS[field_name]} is needed and cannot be left blank")
        if field_name in clientdb_sql.BOOLEAN_EDITABLE_FIELDS and value not in ("1", "0"):
            raise ClientEditError(f"new_value for {field_name} must be '1' or '0'")
        if field_name == "dob_iso" and value:
            import field_shapes

            value = field_shapes.parse_dob(value)
            if not value:
                raise ClientEditError("That date of birth is not a date. Write it day, month, year.")
        if field_name in ("sex", "sex_other"):
            value = _clean_sex_edit(matter, field_name, value)

        old_value = clientdb_sql.get_editable_field(matter, field_name)
        try:
            clientdb_sql.update_editable_field(matter, field_name, value or None)
        except ValueError as exc:
            raise ClientEditError(str(exc)) from exc
        if field_name in ("name_first", "name_last"):
            _sync_document_name(matter)
        if field_name == "company_reference":
            clientdb_sql.mirror_company_reference(matter, value or None)

    now = utc_now()
    row = {
        "edit_id": uuid.uuid4().hex,
        "matter_id": matter,
        "field_name": field_name,
        "old_value": old_value,
        "new_value": value,
        "note": _clean(note, limit=NOTE_MAX_LENGTH),
        "edited_by": by,
        "created_at": now,
    }
    _append_history(row, db_path)
    if field_name in clientdb_sql.C8_FIELD_FLAGS or field_name == "has_c8":
        _sync_c8_flags(matter, field_name, value, by, db_path)
    if field_name == "sex" and value != "Other" and clientdb_sql.get_editable_field(matter, "sex_other"):
        record_edit(matter_id=matter, field_name="sex_other", new_value="", note=note, edited_by=by, db_path=db_path)
    return row


ORDER_TYPES_FIELD = "order_types"


def order_type_codes(matter_id: str) -> list[str]:
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT order_type_code FROM matter_order_types WHERE matter_id = ?", (int(matter_id),))
        return sorted({str(r[0] or "").strip().upper() for r in cur.fetchall()} - {""})


@_named_in_change_log
def add_order_types(
    *,
    matter_id: str,
    codes: list[str],
    source_text: str = "",
    note: str = "",
    edited_by: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter or not matter.isdigit():
        raise ClientEditError("matter_id is required")
    by = _clean(edited_by, limit=200)
    if not by:
        raise ClientEditError("edited_by (your name) is required")
    wanted = sorted({str(c).strip().upper() for c in codes if str(c).strip()})
    if not wanted:
        raise ClientEditError("at least one order code is required")
    held = order_type_codes(matter)
    missing = [c for c in wanted if c not in held]
    if not missing:
        return {"matter_id": matter, "added": []}
    now = utc_now()
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        for code in missing:
            cur.execute(
                "INSERT INTO matter_order_types (matter_id, order_type_code, source_text, created_utc, updated_utc) "
                "VALUES (?, ?, ?, ?, ?)",
                (int(matter), code, _clean(source_text, limit=500) or None, now, now),
            )
    _append_history({
        "edit_id": uuid.uuid4().hex, "matter_id": matter, "field_name": ORDER_TYPES_FIELD,
        "old_value": ",".join(held), "new_value": ",".join(sorted(set(held) | set(missing))),
        "note": _clean(note, limit=NOTE_MAX_LENGTH), "edited_by": by, "created_at": now,
    }, db_path)
    return {"matter_id": matter, "added": missing}


@_named_in_change_log
def replace_order_types(
    *,
    matter_id: str,
    codes: list[str],
    source_text: str = "",
    note: str = "",
    edited_by: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter or not matter.isdigit():
        raise ClientEditError("matter_id is required")
    by = _clean(edited_by, limit=200)
    if not by:
        raise ClientEditError("edited_by (your name) is required")
    wanted = sorted({str(c).strip().upper() for c in codes if str(c).strip()})
    if not wanted:
        raise ClientEditError("at least one order code is required")
    held = order_type_codes(matter)
    extra = [c for c in held if c not in wanted]
    missing = [c for c in wanted if c not in held]
    if not extra and not missing:
        return {"matter_id": matter, "added": [], "removed": []}
    now = utc_now()
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        for code in extra:
            cur.execute("DELETE FROM matter_order_types WHERE matter_id = ? AND UPPER(TRIM(order_type_code)) = ?", (int(matter), code))
        for code in missing:
            cur.execute(
                "INSERT INTO matter_order_types (matter_id, order_type_code, source_text, created_utc, updated_utc) "
                "VALUES (?, ?, ?, ?, ?)",
                (int(matter), code, _clean(source_text, limit=500) or None, now, now),
            )
    _append_history({
        "edit_id": uuid.uuid4().hex, "matter_id": matter, "field_name": ORDER_TYPES_FIELD,
        "old_value": ",".join(held), "new_value": ",".join(wanted),
        "note": _clean(note, limit=NOTE_MAX_LENGTH), "edited_by": by, "created_at": now,
    }, db_path)
    return {"matter_id": matter, "added": missing, "removed": extra}


FOLDER_REF_TYPE = "matter_folder"


@_named_in_change_log
def record_folder_move(
    *,
    matter_id: str,
    old_path: str,
    new_path: str,
    edited_by: str,
    note: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    old = _clean(old_path, limit=500)
    new = _clean(new_path, limit=500)
    by = _clean(edited_by, limit=200)
    if not matter or not new or not by:
        raise ClientEditError("matter_id, new_path and edited_by are required")
    if old.lower() == new.lower():
        return {"matter_id": matter, "applied": False, "reason": "unchanged"}
    now = utc_now()
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.matters SET live_matter_folder = ?, updated_utc = ? "
            "WHERE matter_id = ? AND COALESCE(live_matter_folder, '') = ?",
            (new, now, matter, old),
        )
        if getattr(cur, "rowcount", 1) == 0:
            return {"matter_id": matter, "applied": False, "reason": "record changed meanwhile"}
        cur.execute(
            "UPDATE matter_references SET is_primary = 0, updated_utc = ? "
            "WHERE matter_id = ? AND ref_type = ? AND ref_value_normalised <> ?",
            (now, matter, FOLDER_REF_TYPE, new.upper()),
        )
        for value, primary, text in ((old, 0, "Previous location"), (new, 1, "Found by re-search")):
            if not value:
                continue
            cur.execute(
                "SELECT reference_id FROM matter_references WHERE matter_id = ? AND ref_type = ? AND ref_value_normalised = ?",
                (matter, FOLDER_REF_TYPE, value.upper()),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO matter_references (matter_id, ref_type, ref_value, ref_value_normalised, source, notes,"
                    " is_primary, created_utc, updated_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (matter, FOLDER_REF_TYPE, value, value.upper(), by[:200], text, primary, now, now),
                )
            elif primary:
                cur.execute(
                    "UPDATE matter_references SET is_primary = 1, updated_utc = ? WHERE reference_id = ?", (now, row[0])
                )
    _append_history(
        {
            "edit_id": uuid.uuid4().hex, "matter_id": matter, "field_name": "live_matter_folder",
            "old_value": old, "new_value": new,
            "note": _clean(note or "Folder found at a new location", limit=NOTE_MAX_LENGTH),
            "edited_by": by, "created_at": now,
        },
        db_path,
    )
    return {"matter_id": matter, "applied": True, "old": old, "new": new}


def _sync_document_name(matter: str) -> None:
    first = (clientdb_sql.get_editable_field(matter, "name_first") or "").strip()
    last = (clientdb_sql.get_editable_field(matter, "name_last") or "").strip()
    if first and last:
        clientdb_sql.update_editable_field(matter, "client_canonical_name", f"{first} {last}")


def _append_history(row: dict[str, Any], db_path: str | Path | None) -> None:
    with ops_db.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO client_edit_history ({', '.join(COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in COLUMNS)})",
            tuple(row[col] for col in COLUMNS),
        )


def _set_flag_and_log(matter: str, field_name: str, new: str, by: str, note: str, db_path) -> None:
    old = clientdb_sql.get_editable_field(matter, field_name)
    if (old or "0") == new:
        return
    clientdb_sql.update_editable_field(matter, field_name, new)
    _append_history({
        "edit_id": uuid.uuid4().hex, "matter_id": matter, "field_name": field_name,
        "old_value": old or "0", "new_value": new, "note": note, "edited_by": by, "created_at": utc_now(),
    }, db_path)


def _sync_c8_flags(matter: str, field_name: str, value: str, by: str, db_path) -> None:
    note = "kept in step with the C8 flags"
    if field_name == "has_c8":
        current = [(clientdb_sql.get_editable_field(matter, f) or "0") for f in clientdb_sql.C8_FIELD_FLAGS]
        if value == "1" and "1" not in current:
            for flag in clientdb_sql.C8_FIELD_FLAGS:
                _set_flag_and_log(matter, flag, "1", by, note, db_path)
        elif value == "0":
            for flag in clientdb_sql.C8_FIELD_FLAGS:
                _set_flag_and_log(matter, flag, "0", by, note, db_path)
        return
    any_set = any((clientdb_sql.get_editable_field(matter, f) or "0") == "1" for f in clientdb_sql.C8_FIELD_FLAGS)
    _set_flag_and_log(matter, "has_c8", "1" if any_set else "0", by, note, db_path)


def _party_snapshot(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    bits = [str(row.get("role") or ""), str(row.get("display_name") or "")]
    if row.get("dob_iso"):
        bits.append(f"DOB {row['dob_iso']}")
    if row.get("sex"):
        bits.append(f"Sex {row['sex']}" + (f" ({row['sex_other']})" if row.get("sex_other") else ""))
    if row.get("address_text"):
        bits.append(str(row["address_text"]))
    return " - ".join(b for b in bits if b)


def record_party_edit(
    *,
    matter_id: str,
    action: str,
    party_id: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    note: str = "",
    edited_by: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        raise ClientEditError("matter_id is required")
    by = _clean(edited_by, limit=200)
    if not by:
        raise ClientEditError("edited_by (your name) is required")
    if action not in ("add", "update", "remove"):
        raise ClientEditError(f"unknown action {action!r}; expected 'add', 'update', or 'remove'")

    role = (after or before or {}).get("role") or ""
    field_name = f"party_{action}:{_clean(str(role), limit=60)}" if role else f"party_{action}"

    now = utc_now()
    row = {
        "edit_id": uuid.uuid4().hex,
        "matter_id": matter,
        "field_name": _clean(field_name, limit=100),
        "old_value": _party_snapshot(before),
        "new_value": _party_snapshot(after),
        "note": _clean(note, limit=NOTE_MAX_LENGTH),
        "edited_by": by,
        "created_at": now,
    }
    with ops_db.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO client_edit_history ({', '.join(COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in COLUMNS)})",
            tuple(row[col] for col in COLUMNS),
        )
    return row


def _require_editor(edited_by: str) -> None:
    if not _clean(edited_by, limit=200):
        raise ClientEditError("edited_by (your name) is required")


@_named_in_change_log
def add_party(
    *, matter_id: str, fields: dict[str, Any], note: str = "", edited_by: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    _require_editor(edited_by)
    party = clientdb_sql.add_party(matter_id, fields)
    record_party_edit(
        matter_id=matter_id, action="add", party_id=str(party.get("party_id") or ""),
        after=party, note=note, edited_by=edited_by, db_path=db_path,
    )
    return party


@_named_in_change_log
def update_party(
    *, matter_id: str, party_id: str, fields: dict[str, Any], note: str = "", edited_by: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    _require_editor(edited_by)
    existing = next((p for p in clientdb_sql.list_parties(matter_id) if str(p.get("party_id")) == str(party_id)), None)
    if existing is None:
        raise ClientEditError(f"party {party_id!r} is not a party of matter {matter_id!r}")
    party = clientdb_sql.update_party(party_id, fields)
    record_party_edit(
        matter_id=matter_id, action="update", party_id=str(party_id),
        before=existing, after=party, note=note, edited_by=edited_by, db_path=db_path,
    )
    return party


@_named_in_change_log
def remove_party(
    *, matter_id: str, party_id: str, note: str = "", edited_by: str,
    db_path: str | Path | None = None,
) -> None:
    _require_editor(edited_by)
    existing = next((p for p in clientdb_sql.list_parties(matter_id) if str(p.get("party_id")) == str(party_id)), None)
    if existing is None:
        raise ClientEditError(f"party {party_id!r} is not a party of matter {matter_id!r}")
    clientdb_sql.delete_party(party_id)
    record_party_edit(
        matter_id=matter_id, action="remove", party_id=str(party_id),
        before=existing, note=note, edited_by=edited_by, db_path=db_path,
    )


def _child_snapshot(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    bits = [str(row.get("child_name") or "")]
    if row.get("dob_iso"):
        bits.append(f"DOB {row['dob_iso']}")
    return " - ".join(b for b in bits if b)


def _children_summary_text(rows: list[dict[str, Any]]) -> str:
    parts = []
    for row in rows:
        piece = str(row.get("child_name") or "Child")
        dob = str(row.get("dob_iso") or "")
        if dob:
            piece += f" ({dob})"
        parts.append(piece)
    return "; ".join(parts)


def _record_child_edit(
    *, matter_id: str, action: str, before: dict[str, Any] | None, after: dict[str, Any] | None,
    note: str, edited_by: str, db_path: str | Path | None,
) -> None:
    name = str((after or before or {}).get("child_name") or "")
    _append_history({
        "edit_id": uuid.uuid4().hex,
        "matter_id": _clean(matter_id, limit=128),
        "field_name": _clean(f"child_{action}:{name}" if name else f"child_{action}", limit=100),
        "old_value": _child_snapshot(before),
        "new_value": _child_snapshot(after),
        "note": _clean(note, limit=NOTE_MAX_LENGTH),
        "edited_by": _clean(edited_by, limit=200),
        "created_at": utc_now(),
    }, db_path)


def _children_summary_unchanged_by_hand(matter_id: str, previous: str) -> bool:
    current = " ".join(str(clientdb_sql.get_editable_field(matter_id, "children_summary") or "").split()).lower()
    return not current or current == " ".join(previous.split()).lower()


def _rebuild_children_summary(matter_id: str, edited_by: str, db_path: str | Path | None, *, previous: str) -> None:
    try:
        if not _children_summary_unchanged_by_hand(matter_id, previous):
            return
        record_edit(
            matter_id=matter_id, field_name="children_summary",
            new_value=_children_summary_text(clientdb_sql.list_children(matter_id)),
            note="rebuilt from the children list", edited_by=edited_by, db_path=db_path,
        )
    except Exception as exc:
        print(f"children_summary for matter {matter_id} was not rebuilt: {exc}", file=sys.stderr)


def _existing_child(matter_id: str, child_id: str) -> dict[str, Any]:
    existing = next((c for c in clientdb_sql.list_children(matter_id) if str(c.get("child_id")) == str(child_id)), None)
    if existing is None:
        raise ClientEditError(f"child {child_id!r} is not a child of matter {matter_id!r}")
    return existing


@_named_in_change_log
def add_child(
    *, matter_id: str, fields: dict[str, Any], note: str = "", edited_by: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    _require_editor(edited_by)
    previous = _children_summary_text(clientdb_sql.list_children(matter_id))
    child = clientdb_sql.add_child(matter_id, fields)
    _record_child_edit(matter_id=matter_id, action="add", before=None, after=child, note=note, edited_by=edited_by, db_path=db_path)
    _rebuild_children_summary(matter_id, edited_by, db_path, previous=previous)
    return child


@_named_in_change_log
def update_child(
    *, matter_id: str, child_id: str, fields: dict[str, Any], note: str = "", edited_by: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    _require_editor(edited_by)
    existing = _existing_child(matter_id, child_id)
    previous = _children_summary_text(clientdb_sql.list_children(matter_id))
    child = clientdb_sql.update_child(child_id, fields)
    _record_child_edit(matter_id=matter_id, action="update", before=existing, after=child, note=note, edited_by=edited_by, db_path=db_path)
    _rebuild_children_summary(matter_id, edited_by, db_path, previous=previous)
    return child


@_named_in_change_log
def remove_child(
    *, matter_id: str, child_id: str, note: str = "", edited_by: str,
    db_path: str | Path | None = None,
) -> None:
    _require_editor(edited_by)
    existing = _existing_child(matter_id, child_id)
    previous = _children_summary_text(clientdb_sql.list_children(matter_id))
    clientdb_sql.delete_child(child_id)
    _record_child_edit(matter_id=matter_id, action="remove", before=existing, after=None, note=note, edited_by=edited_by, db_path=db_path)
    _rebuild_children_summary(matter_id, edited_by, db_path, previous=previous)


def list_edits(
    matter_id: str,
    *,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return []
    top = max(1, min(int(limit or 50), 200))
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM client_edit_history "
            "WHERE matter_id = ? ORDER BY created_at DESC LIMIT ?",
            (matter, top),
        ).fetchall()
    return [dict(zip(COLUMNS, row)) for row in rows]


def _is_automation(edited_by: str) -> bool:
    name = (edited_by or "").strip().lower()
    return name in {"case flow", "robot"} or name.startswith("system:")


def cleared_by_person(matter_id: str, field_name: str, *, db_path: str | Path | None = None) -> bool:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return False
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        row = conn.execute(
            "SELECT new_value, edited_by FROM client_edit_history WHERE matter_id = ? AND field_name = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (matter, field_name),
        ).fetchone()
    return bool(row) and str(row[0]).strip() == "0" and not _is_automation(str(row[1]))


def list_flags(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, bool]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return {}
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            "SELECT flag_name, is_set FROM matter_flags WHERE matter_id = ?",
            (matter,),
        ).fetchall()
    flags = {name: bool(is_set) for name, is_set in rows}
    if matter in _portal_matters([matter]):
        flags[PORTAL_FLAG] = True
    return flags


def list_flags_for_matters(
    matter_ids: list[str], *, user: str | None = None, db_path: str | Path | None = None
) -> dict[str, dict[str, bool]]:
    matters = list(dict.fromkeys(m for m in (_clean(mid, limit=128) for mid in matter_ids) if m))
    result: dict[str, dict[str, bool]] = {matter: {} for matter in matters}
    if not matters:
        return result
    placeholders = ", ".join("?" for _ in matters)
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT matter_id, flag_name, is_set FROM matter_flags WHERE matter_id IN ({placeholders})",
            tuple(matters),
        ).fetchall()
        mine = _personal_rows(conn, personal_user(user), matters) if personal_user(user) else []
    for matter_id, flag_name, is_set in rows:
        result[matter_id][flag_name] = bool(is_set)
    for matter_id, flag_name in mine:
        result[matter_id][flag_name] = True
    for matter_id in _portal_matters(matters):
        result[matter_id][PORTAL_FLAG] = True
    return result


def list_flag_rows(flag_names: list[str], *, db_path: str | Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    names = [name for name in dict.fromkeys(flag_names) if name in FLAG_LABELS]
    if not names:
        return {}
    placeholders = ", ".join("?" for _ in names)
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT matter_id, flag_name, is_set, set_by, reason FROM matter_flags WHERE flag_name IN ({placeholders})",
            tuple(names),
        ).fetchall()
    return {(m, f): {"is_set": bool(i), "set_by": by or "", "reason": reason or ""} for m, f, i, by, reason in rows}


def list_flag_reasons(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, str]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return {}
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            "SELECT flag_name, reason FROM matter_flags WHERE matter_id = ? AND is_set = 1 AND reason IS NOT NULL AND reason != ''",
            (matter,),
        ).fetchall()
    return {name: reason for name, reason in rows}


def list_flags_and_reasons(
    matter_id: str, *, user: str | None = None, db_path: str | Path | None = None
) -> tuple[dict[str, bool], dict[str, str]]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return {}, {}
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            "SELECT flag_name, is_set, reason FROM matter_flags WHERE matter_id = ?",
            (matter,),
        ).fetchall()
        mine = _personal_rows(conn, personal_user(user), [matter]) if personal_user(user) else []
    flags = {name: bool(is_set) for name, is_set, _reason in rows}
    for _matter, name in mine:
        flags[name] = True
    reasons = {name: reason for name, is_set, reason in rows if is_set == 1 and reason is not None and reason != ""}
    if matter in _portal_matters([matter]):
        flags[PORTAL_FLAG] = True
    return flags, reasons


def list_reasons_by_matter(flag_name: str, *, db_path: str | Path | None = None) -> dict[str, str]:
    if flag_name not in FLAG_LABELS:
        return {}
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            "SELECT matter_id, reason FROM matter_flags WHERE flag_name = ? AND is_set = 1 AND reason IS NOT NULL AND reason != ''",
            (flag_name,),
        ).fetchall()
    return {matter_id: reason for matter_id, reason in rows}


def list_matters_with_flags(
    flag_names: list[str], *, user: str | None = None, db_path: str | Path | None = None
) -> dict[str, list[str]]:
    names = [name for name in flag_names if name in FLAG_LABELS]
    if not names:
        return {}
    placeholders = ", ".join("?" for _ in names)
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT matter_id, flag_name FROM matter_flags WHERE is_set = 1 AND flag_name IN ({placeholders})",
            tuple(names),
        ).fetchall()
        who = personal_user(user)
        mine = _personal_rows(conn, who, names=names) if who else []
    result: dict[str, list[str]] = {}
    for matter_id, flag_name in [*rows, *mine]:
        if flag_name not in result.setdefault(matter_id, []):
            result[matter_id].append(flag_name)
    return result


def count_matters_with_flags(
    flag_names: list[str], *, user: str | None = None, db_path: str | Path | None = None
) -> dict[str, int]:
    names = [name for name in dict.fromkeys(flag_names) if name in FLAG_LABELS]
    if not names:
        return {}
    placeholders = ", ".join("?" for _ in names)
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        who = personal_user(user)
        if who:
            rows = conn.execute(
                f"SELECT flag_name, COUNT(DISTINCT matter_id) FROM ("
                f"SELECT matter_id, flag_name FROM matter_flags WHERE is_set = 1 AND flag_name IN ({placeholders}) "
                f"UNION SELECT matter_id, flag_name FROM user_matter_flags WHERE user_key = ? AND flag_name IN ({placeholders})"
                f") GROUP BY flag_name",
                (*names, who, *names),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT flag_name, COUNT(DISTINCT matter_id) FROM matter_flags "
                f"WHERE is_set = 1 AND flag_name IN ({placeholders}) GROUP BY flag_name",
                tuple(names),
            ).fetchall()
    counts = {name: 0 for name in names}
    counts.update({flag_name: count for flag_name, count in rows})
    return counts


def set_personal_flag(
    *,
    user: str,
    matter_id: str,
    flag_name: str,
    is_set: bool,
    reason: str = "",
    only_if_reason: str = "",
    scope: str = "personal",
    set_by: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    who = personal_user(user)
    if not matter:
        raise ClientEditError("matter_id is required")
    if flag_name not in PERSONAL_FLAGS:
        raise ClientEditError(f"{flag_name!r} is not a personal flag; expected one of {PERSONAL_FLAGS}")
    if scope not in ("personal", "shared"):
        raise ClientEditError("scope must be personal or shared")
    if not who:
        raise ClientEditError("a signed-in identity is required for a personal flag")
    now = utc_now()
    text = _clean(reason, limit=200) if flag_name == "flagged" else ""
    only_if = _clean(only_if_reason, limit=200)
    clear_shared = False
    with ops_db.connect(db_path) as conn:
        if is_set:
            held = conn.execute(
                "SELECT 1 FROM user_matter_flags WHERE user_key = ? AND matter_id = ? AND flag_name = ?", (who, matter, flag_name)
            ).fetchone()
            if not (held and text == DRAFT_REASON):
                conn.execute(
                    "INSERT INTO user_matter_flags (user_key, matter_id, flag_name, set_at, reason) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(user_key, matter_id, flag_name) DO UPDATE SET reason = excluded.reason",
                    (who, matter, flag_name, now, text or None),
                )
        elif scope == "shared":
            clear_shared = True
        elif only_if:
            conn.execute(
                "DELETE FROM user_matter_flags WHERE user_key = ? AND matter_id = ? AND flag_name = ? AND reason = ?",
                (who, matter, flag_name, only_if),
            )
        else:
            conn.execute("DELETE FROM user_matter_flags WHERE user_key = ? AND matter_id = ? AND flag_name = ?", (who, matter, flag_name))
            clear_shared = flag_name == "starred"
        if clear_shared:
            shared = conn.execute(
                "SELECT is_set FROM matter_flags WHERE matter_id = ? AND flag_name = ?", (matter, flag_name)
            ).fetchone()
            clear_shared = bool(shared and shared[0])
    if clear_shared:
        set_flag(matter_id=matter, flag_name=flag_name, is_set=False, set_by=set_by or who, db_path=db_path)
    return {"matter_id": matter, "flag_name": flag_name, "is_set": bool(is_set), "set_at": now}


def personal_state(matter_id: str, user: str | None, *, db_path: str | Path | None = None) -> tuple[dict[str, bool], dict[str, str]]:
    matter, who = _clean(matter_id, limit=128), personal_user(user)
    if not matter or not who:
        return {}, {}
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT flag_name, reason FROM user_matter_flags WHERE user_key = ? AND matter_id = ?", (who, matter)
        ).fetchall()
    return {name: True for name, _reason in rows}, {name: reason for name, reason in rows if reason}


def list_personal_matters(user: str | None, flag_name: str, *, db_path: str | Path | None = None) -> set[str]:
    who = personal_user(user)
    if not who or flag_name not in PERSONAL_FLAGS:
        return set()
    with ops_db.connect(db_path) as conn:
        return {str(m) for (m,) in conn.execute("SELECT matter_id FROM user_matter_flags WHERE user_key = ? AND flag_name = ?", (who, flag_name)).fetchall()}


def list_personal_reasons(user: str | None, flag_name: str, *, db_path: str | Path | None = None) -> dict[str, str]:
    who = personal_user(user)
    if not who or flag_name not in PERSONAL_FLAGS:
        return {}
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT matter_id, reason FROM user_matter_flags WHERE user_key = ? AND flag_name = ? AND reason IS NOT NULL AND reason != ''",
            (who, flag_name),
        ).fetchall()
    return {str(m): str(r) for m, r in rows}


def set_flag(
    *,
    matter_id: str,
    flag_name: str,
    is_set: bool,
    set_by: str,
    reason: str = "",
    only_if_reason: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        raise ClientEditError("matter_id is required")
    if flag_name not in FLAG_LABELS:
        raise ClientEditError(f"unknown flag_name {flag_name!r}; expected one of {tuple(FLAG_LABELS)}")
    by = _clean(set_by, limit=200)
    if not by:
        raise ClientEditError("set_by (your name) is required")

    reason = _clean(reason, limit=200)
    only_if_reason = _clean(only_if_reason, limit=200)
    now = utc_now()
    with ops_db.connect(db_path) as conn:
        previous = conn.execute(
            "SELECT is_set, reason FROM matter_flags WHERE matter_id = ? AND flag_name = ?",
            (matter, flag_name),
        ).fetchone()
        was_set = bool(previous[0]) if previous else False
        current_reason = (previous[1] or "") if previous else ""
        if reason and is_set and was_set:
            return {"matter_id": matter, "flag_name": flag_name, "is_set": True, "set_by": by, "set_at": now, "unchanged": True}
        if only_if_reason and not is_set and (not was_set or current_reason != only_if_reason):
            return {"matter_id": matter, "flag_name": flag_name, "is_set": was_set, "set_by": by, "set_at": now, "unchanged": True}
        conn.execute(
            "INSERT INTO matter_flags (matter_id, flag_name, is_set, set_by, set_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(matter_id, flag_name) DO UPDATE SET "
            "is_set = excluded.is_set, set_by = excluded.set_by, set_at = excluded.set_at, reason = excluded.reason",
            (matter, flag_name, 1 if is_set else 0, by, now, reason if is_set and reason else None),
        )
        conn.execute(
            f"INSERT INTO client_edit_history ({', '.join(COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in COLUMNS)})",
            (
                uuid.uuid4().hex, matter, f"flag:{flag_name}",
                "Yes" if was_set else "No", "Yes" if is_set else "No",
                "", by, now,
            ),
        )
    return {"matter_id": matter, "flag_name": flag_name, "is_set": bool(is_set), "set_by": by, "set_at": now}


FIELD_REVIEW_COLUMNS = (
    "review_id", "matter_id", "client_name", "field_name", "field_label",
    "value_snapshot", "note", "flagged_by", "flagged_at", "resolved_by", "resolved_at",
)


def _row_to_field_review(row: tuple) -> dict[str, Any]:
    return dict(zip(FIELD_REVIEW_COLUMNS, row))


def flag_field_for_review(
    *,
    matter_id: str,
    client_name: str,
    field_name: str,
    field_label: str,
    value_snapshot: str,
    flagged_by: str,
    note: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    field = _clean(field_name, limit=200)
    if not matter:
        raise ClientEditError("matter_id is required")
    if not field:
        raise ClientEditError("field_name is required")
    by = _clean(flagged_by, limit=200)
    if not by:
        raise ClientEditError("flagged_by (your name) is required")

    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        existing = conn.execute(
            "SELECT " + ", ".join(FIELD_REVIEW_COLUMNS) + " FROM field_review_flags "
            "WHERE matter_id = ? AND field_name = ? AND resolved_at IS NULL",
            (matter, field),
        ).fetchone()
        if existing:
            return _row_to_field_review(existing)

        now = utc_now()
        review_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO field_review_flags "
            "(review_id, matter_id, client_name, field_name, field_label, value_snapshot, "
            "note, flagged_by, flagged_at, resolved_by, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
            (
                review_id, matter, _clean(client_name, limit=200), field,
                _clean(field_label, limit=200) or field, _clean(value_snapshot, limit=500),
                _clean(note, limit=500), by, now,
            ),
        )
    return {
        "review_id": review_id, "matter_id": matter, "client_name": _clean(client_name, limit=200),
        "field_name": field, "field_label": _clean(field_label, limit=200) or field,
        "value_snapshot": _clean(value_snapshot, limit=500), "note": _clean(note, limit=500),
        "flagged_by": by, "flagged_at": now, "resolved_by": None, "resolved_at": None,
    }


def resolve_field_review(
    *, review_id: str, resolved_by: str, db_path: str | Path | None = None
) -> dict[str, Any]:
    rid = _clean(review_id, limit=64)
    if not rid:
        raise ClientEditError("review_id is required")
    by = _clean(resolved_by, limit=200)
    if not by:
        raise ClientEditError("resolved_by (your name) is required")

    now = utc_now()
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        existing = conn.execute(
            "SELECT " + ", ".join(FIELD_REVIEW_COLUMNS) + " FROM field_review_flags WHERE review_id = ?",
            (rid,),
        ).fetchone()
        if not existing:
            raise ClientEditError(f"no review flag with review_id {rid!r}")
        conn.execute(
            "UPDATE field_review_flags SET resolved_by = ?, resolved_at = ? WHERE review_id = ?",
            (by, now, rid),
        )
    row = _row_to_field_review(existing)
    row["resolved_by"] = by
    row["resolved_at"] = now
    return row


def list_open_review_flags_for_matters(
    matter_ids: list[str], *, db_path: str | Path | None = None
) -> dict[str, list[dict[str, Any]]]:
    matters = list(dict.fromkeys(m for m in (_clean(mid, limit=128) for mid in matter_ids) if m))
    result: dict[str, list[dict[str, Any]]] = {}
    if not matters:
        return result
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        for start in range(0, len(matters), 500):
            chunk = matters[start : start + 500]
            rows = conn.execute(
                "SELECT " + ", ".join(FIELD_REVIEW_COLUMNS) + " FROM field_review_flags "
                f"WHERE matter_id IN ({', '.join('?' for _ in chunk)}) AND resolved_at IS NULL ORDER BY flagged_at DESC",
                tuple(chunk),
            ).fetchall()
            for row in rows:
                flag = _row_to_field_review(row)
                result.setdefault(str(flag["matter_id"]), []).append(flag)
    return result


def list_matters_with_open_review(*, db_path: str | Path | None = None) -> list[str]:
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            "SELECT DISTINCT matter_id FROM field_review_flags WHERE resolved_at IS NULL"
        ).fetchall()
    return [row[0] for row in rows]
