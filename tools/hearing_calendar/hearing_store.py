#!/usr/bin/env python3

from __future__ import annotations

import logging
import datetime as dt
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql
import firm_profile
from hearing_calendar import bank_holidays, hearing_dates

LONDON = ZoneInfo("Europe/London")
ICS_UID_DOMAIN = firm_profile.load_profile().hostnames["crm"]
MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0024_matter_hearings.sql"
COLUMNS_MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0025_matter_hearings_counsel_chambers.sql"
VACATE_MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0045_matter_hearings_vacate_request.sql"
SPAN_MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0047_matter_hearings_multi_day.sql"
SPAN_COLUMNS = ("hearing_end_date", "hearing_dates")
NOTICE_MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0060_matter_hearings_notice.sql"
NOTICE_COLUMNS = ("notice", "not_before_date")
NOTICES = ("", "on notice", "without notice")
VACATE_COLUMNS = ("vacate_kind", "replaced_by_hearing_id", "request_state", "request_reason")
LATE_COLUMNS = ("counsel", "chambers")
DURATION_STATED_COLUMN = "duration_stated"
_ADD_DURATION_STATED = "ALTER TABLE matter_hearings ADD COLUMN IF NOT EXISTS duration_stated INTEGER NOT NULL DEFAULT 1"
_ADD_DURATION_STATED_SQLITE = "ALTER TABLE matter_hearings ADD COLUMN duration_stated INTEGER NOT NULL DEFAULT 1"
_BACKFILL_DURATION_STATED = (
    "UPDATE matter_hearings SET duration_stated = 0 "
    "WHERE source_kind IN ('email', 'outlook_import') AND duration_minutes = 60 AND human_edited = 0"
)

STATUSES = ("scheduled", "vacated")
LEGACY_STATUSES = {"cancelled": "vacated"}
VACATE_KINDS = ("moved", "no_longer_acting", "court_vacated", "other")
REQUEST_STATES = ("", "vacation_requested", "hybrid_requested")
REVIEW_STATES = ("ok", "needs_review", "dismissed")
SOURCE_KINDS = ("email", "ics", "invite", "manual", "outlook_import")
MODES = ("", "in person", "video", "telephone", "hybrid")
COURT_OPEN_MINUTES = 9 * 60
COURT_CLOSE_MINUTES = 17 * 60
CASE_REF_RE = re.compile(r"\b([A-Z]{1,3}\d{2}[A-Z]\d{5})\b", re.ASCII)

EDITABLE_FIELDS = (
    "case_ref", "matter_id", "hearing_date", "hearing_time", "duration_minutes",
    "hearing_type", "order_types", "is_final", "court", "mode", "join_url",
    "applicant", "respondent", "counsel", "chambers", "notes",
    "hearing_end_date", "hearing_dates", "notice", "not_before_date",
)
DERIVED_FIELDS = ("duration_stated",)
AUTOMATION_FIELDS = (
    "hearing_time", "duration_minutes", "hearing_type", "order_types", "is_final",
    "court", "mode", "join_url", "applicant", "respondent",
    "hearing_end_date", "hearing_dates", "notice", "not_before_date",
)
_TEXT_LIMITS = {
    "hearing_type": 120, "order_types": 60, "court": 240, "join_url": 500,
    "applicant": 200, "respondent": 200, "counsel": 200, "chambers": 200, "notes": 4000, "case_ref": 30,
    "source_subject": 500, "source_web_link": 900, "source_message_id": 400,
    "review_reason": 600,
}
_ROW_COLUMNS = (
    "hearing_id", "hearing_uid", "matter_id", "case_ref", "hearing_date", "hearing_time",
    "duration_minutes", "duration_stated", "hearing_type", "order_types", "is_final", "court", "mode",
    "join_url", "applicant", "respondent", "counsel", "chambers", "status", "review_state",
    "review_reason", "confidence", "source_kind", "source_message_id", "source_subject",
    "source_received_utc", "source_web_link", "notes", "human_edited",
    "created_utc", "updated_utc", "updated_by",
    "vacate_kind", "replaced_by_hearing_id", "request_state", "request_reason",
    "hearing_end_date", "hearing_dates", "notice", "not_before_date",
)


class HearingError(ValueError):
    pass



def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def london_today() -> dt.date:
    return dt.datetime.now(LONDON).date()


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", _CONTROL_RE.sub(" ", str(value or "").replace("\xa0", " "))).strip()[:limit]


def _clean_multiline(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub(" ", text.replace("\t", " "))
    return "\n".join(re.sub(r" +", " ", line).strip() for line in text.split("\n")).strip()[:limit]


_DRA_LONG = (
    (re.compile(r"\bfirst\s+hearing\s+dispute\s+resolution\s+appointment\b", re.I), "FHDRA"),
    (re.compile(r"\bfinal\s+dispute\s+resolution\s+appointment\b", re.I), "FDRA"),
    (re.compile(r"\bdispute\s+resolution\s+appointment\b", re.I), "DRA"),
)
_SHORT_THEN_REPEAT = re.compile(r"\b(FHDRA|FDRA)\b(?:\s+(?:hearing|appointment))*\s*\(\s*\1\s*\)", re.I)
_SHORT_THEN_WORD = re.compile(r"\b(FHDRA|FDRA)\b(?:\s+(?:hearing|appointment))+", re.I)


def short_hearing_type(value: Any) -> str:
    text = _clean(value, _TEXT_LIMITS["hearing_type"] * 3)
    for pattern, short in _DRA_LONG:
        text = pattern.sub(short, text)
    text = _SHORT_THEN_REPEAT.sub(lambda m: m.group(1).upper(), text)
    text = _SHORT_THEN_WORD.sub(lambda m: m.group(1).upper(), text)
    return text[: _TEXT_LIMITS["hearing_type"]].strip()


_WITHOUT_NOTICE_WORDS = re.compile(r"\(?\b(?:without[- ]notice|w/o\s+notice|ex[- ]parte)\b\)?", re.IGNORECASE)
_ON_NOTICE_WORDS = re.compile(r"\(?\bon[- ]notice\b\)?", re.IGNORECASE)
_BARE_WORDS = {"hearing"}


def split_notice(value: Any) -> tuple[str, str]:
    text = _clean(value, 200)
    notice = ""
    for found, pattern in (("without notice", _WITHOUT_NOTICE_WORDS), ("on notice", _ON_NOTICE_WORDS)):
        if pattern.search(text):
            notice = notice or found
            text = pattern.sub(" ", text)
    if not notice:
        return text, ""
    text = re.sub(r"\s+", " ", text).strip(" -–:,/")
    if text.lower() in _BARE_WORDS:
        text = ""
    return (text[:1].upper() + text[1:]) if text else "", notice


def normalise_case_ref(value: Any) -> str:
    match = CASE_REF_RE.search(str(value or "").upper().replace(" ", ""))
    return match.group(1) if match else ""


def _valid_date(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise HearingError(f"hearing_date must be an ISO date (YYYY-MM-DD), got {text!r}") from exc


def _valid_dates(value: Any) -> str:
    parts = value if isinstance(value, (list, tuple, set)) else str(value or "").split(",")
    days = sorted({_valid_date(p) for p in (str(x).strip() for x in parts) if p})
    return ",".join(days)


def _span_fields(values: dict[str, Any], start: str) -> dict[str, Any]:
    out = dict(values)
    listed = [d for d in str(out.get("hearing_dates") or "").split(",") if d]
    end = str(out.get("hearing_end_date") or "")
    if listed:
        listed = sorted({start, *listed})
        end = listed[-1] if not end or end < listed[-1] else end
    if end and end < start:
        raise HearingError("hearing_end_date cannot be before hearing_date")
    if end and (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days >= 45:
        raise HearingError("a hearing cannot span more than 45 days")
    if end == start:
        end, listed = "", []
    if listed and len(listed) == (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1:
        listed = []
    if "hearing_end_date" in out or end:
        out["hearing_end_date"] = end
    if "hearing_dates" in out or listed:
        out["hearing_dates"] = ",".join(listed)
    return out


def _valid_time(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match or not (0 <= int(match.group(1)) <= 23 and 0 <= int(match.group(2)) <= 59):
        raise HearingError(f"hearing_time must be HH:MM, got {text!r}")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _time_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def normalise_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw in fields.items():
        if key == "case_ref":
            text = str(raw or "").strip()
            out[key] = normalise_case_ref(text) if text else ""
            if text and not out[key]:
                raise HearingError(f"case_ref {text!r} is not a court case number")
        elif key == "matter_id":
            out[key] = int(raw) if str(raw or "").strip() else None
        elif key == "hearing_date":
            out[key] = _valid_date(raw)
        elif key == "hearing_end_date":
            out[key] = _valid_date(raw) if str(raw or "").strip() else ""
        elif key == "hearing_dates":
            out[key] = _valid_dates(raw)
        elif key == "notice":
            notice = _clean(raw, 40).lower().replace("-", " ")
            if notice not in NOTICES:
                raise HearingError(f"notice must be one of {list(NOTICES)}, got {notice!r}")
            out[key] = notice
        elif key == "not_before_date":
            out[key] = _valid_date(raw) if str(raw or "").strip() else ""
        elif key == "hearing_time":
            out[key] = _valid_time(raw)
        elif key == "duration_minutes":
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                out[key] = 60
                derived_stated = 0
            else:
                try:
                    minutes = int(raw)
                except (TypeError, ValueError) as exc:
                    raise HearingError("duration_minutes must be a whole number") from exc
                out[key] = max(15, min(minutes, 480))
                derived_stated = 1
            if "duration_stated" not in fields:
                out["duration_stated"] = derived_stated
        elif key == "duration_stated":
            out[key] = 1 if raw in (True, 1, "1", "true", "True", "yes") else 0
        elif key == "is_final":
            out[key] = 1 if raw in (True, 1, "1", "true", "True", "yes") else 0
        elif key == "mode":
            mode = _clean(raw, 40).lower()
            if mode not in MODES:
                raise HearingError(f"mode must be one of {list(MODES)}, got {mode!r}")
            out[key] = mode
        elif key == "order_types":
            codes = [c for c in re.split(r"[^A-Za-z]+", str(raw or "").upper()) if c in {"NMO", "OO", "PSO", "CAO", "SIO"}]
            out[key] = "/".join(dict.fromkeys(codes))
        elif key == "hearing_type":
            out[key], found = split_notice(short_hearing_type(raw))
            if found and not fields.get("notice"):
                out["notice"] = found
        elif key == "notes":
            out[key] = _clean_multiline(raw, _TEXT_LIMITS["notes"])
        elif key in _TEXT_LIMITS:
            out[key] = _clean(raw, _TEXT_LIMITS[key])
        else:
            raise HearingError(f"unknown hearing field {key!r}")
    return out


def sanity_issues(hearing_date: str, hearing_time: str | None) -> list[str]:
    issues: list[str] = []
    date = dt.date.fromisoformat(hearing_date)
    if date.weekday() >= 5:
        issues.append("date falls on a weekend; courts do not sit then")
    holiday = bank_holidays.name_on(date)
    if holiday:
        issues.append(f"date is a bank holiday ({holiday}); check the notice with the court")
    if hearing_time is not None:
        minutes = _time_minutes(hearing_time)
        if not COURT_OPEN_MINUTES <= minutes <= COURT_CLOSE_MINUTES:
            issues.append("time is outside court hours (09:00-17:00)")
        if minutes % 5:
            issues.append("time is not on a five-minute boundary, so it may be a message timestamp")
    return issues



_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS matter_hearings (
    hearing_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hearing_uid TEXT NOT NULL,
    matter_id INTEGER NULL,
    case_ref TEXT NOT NULL DEFAULT '',
    hearing_date TEXT NOT NULL,
    hearing_time TEXT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 60,
    duration_stated INTEGER NOT NULL DEFAULT 1,
    hearing_type TEXT NOT NULL DEFAULT '',
    order_types TEXT NOT NULL DEFAULT '',
    is_final INTEGER NOT NULL DEFAULT 0,
    court TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT '',
    join_url TEXT NOT NULL DEFAULT '',
    applicant TEXT NOT NULL DEFAULT '',
    respondent TEXT NOT NULL DEFAULT '',
    counsel TEXT NOT NULL DEFAULT '',
    chambers TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'scheduled',
    review_state TEXT NOT NULL DEFAULT 'ok',
    review_reason TEXT NOT NULL DEFAULT '',
    confidence REAL NULL,
    source_kind TEXT NOT NULL DEFAULT 'manual',
    source_message_id TEXT NOT NULL DEFAULT '',
    source_subject TEXT NOT NULL DEFAULT '',
    source_received_utc TEXT NOT NULL DEFAULT '',
    source_web_link TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    human_edited INTEGER NOT NULL DEFAULT 0,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    vacate_kind TEXT NOT NULL DEFAULT '',
    replaced_by_hearing_id INTEGER NULL,
    request_state TEXT NOT NULL DEFAULT '',
    request_reason TEXT NOT NULL DEFAULT '',
    hearing_end_date TEXT NOT NULL DEFAULT '',
    hearing_dates TEXT NOT NULL DEFAULT '',
    notice TEXT NOT NULL DEFAULT '',
    not_before_date TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_matter_hearings_uid ON matter_hearings (hearing_uid);
CREATE UNIQUE INDEX IF NOT EXISTS ux_matter_hearings_case_date_live ON matter_hearings (case_ref, hearing_date) WHERE case_ref <> '' AND status = 'scheduled';
CREATE INDEX IF NOT EXISTS ix_matter_hearings_date ON matter_hearings (hearing_date);
CREATE TABLE IF NOT EXISTS matter_hearing_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hearing_id INTEGER NOT NULL,
    at_utc TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT NOT NULL DEFAULT '',
    after_json TEXT NOT NULL DEFAULT '',
    source_message_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_matter_hearing_events_hearing ON matter_hearing_events (hearing_id, at_utc);
CREATE TABLE IF NOT EXISTS matter_hearing_leads (
    lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_message_id TEXT NOT NULL,
    source_subject TEXT NOT NULL DEFAULT '',
    source_received_utc TEXT NOT NULL DEFAULT '',
    source_web_link TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'open',
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_matter_hearing_leads_message ON matter_hearing_leads (source_message_id);
"""


def _pg_statements(path: Path) -> list[str]:
    text = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    text = re.sub(r"\s+--[^\n]*", "", text)
    return [stmt.strip() for stmt in text.split(";") if stmt.strip()]


def _pg_ddl_statements() -> list[str]:
    return _pg_statements(MIGRATION_PATH)


def _pg_column_statements() -> list[str]:
    return _pg_statements(COLUMNS_MIGRATION_PATH)


_ensured_backends: set[str] = set()


def ensure_tables(conn) -> None:
    key = f"{'sqlite:' + clientdb_sql._sqlite_path() if clientdb_sql._using_sqlite() else 'pg'}"
    if key in _ensured_backends:
        return
    cursor = conn.cursor()
    if clientdb_sql._using_sqlite():
        cursor.execute("PRAGMA table_info(matter_hearings)")
        have = {row[1] for row in cursor.fetchall()}
        if have and "request_state" not in have:
            for column, ddl in (("vacate_kind", "TEXT NOT NULL DEFAULT ''"), ("replaced_by_hearing_id", "INTEGER NULL"), ("request_state", "TEXT NOT NULL DEFAULT ''"), ("request_reason", "TEXT NOT NULL DEFAULT ''")):
                cursor.execute(f"ALTER TABLE matter_hearings ADD COLUMN {column} {ddl}")
            cursor.execute("UPDATE matter_hearings SET status = 'vacated', vacate_kind = 'cancelled' WHERE status = 'cancelled'")
            cursor.execute("DROP INDEX IF EXISTS ux_matter_hearings_case_date")
        for stmt in [s.strip() for s in _SQLITE_DDL.split(";") if s.strip()]:
            cursor.execute(stmt)
        cursor.execute("PRAGMA table_info(matter_hearings)")
        have = {row[1] for row in cursor.fetchall()}
        for column in LATE_COLUMNS:
            if column not in have:
                cursor.execute(f"ALTER TABLE matter_hearings ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        for column in (*SPAN_COLUMNS, *NOTICE_COLUMNS):
            if column not in have:
                cursor.execute(f"ALTER TABLE matter_hearings ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        if DURATION_STATED_COLUMN not in have:
            cursor.execute(_ADD_DURATION_STATED_SQLITE)
            cursor.execute(_BACKFILL_DURATION_STATED)
    else:
        for stmt in _pg_ddl_statements():
            cursor.execute(stmt)
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'matter_hearings' "
            "AND column_name IN ('counsel', 'chambers', 'duration_stated', 'request_state', 'hearing_end_date', 'notice')"
        )
        have = {row[0] for row in cursor.fetchall()}
        if not set(LATE_COLUMNS) <= have:
            for stmt in _pg_column_statements():
                cursor.execute(stmt)
        if "request_state" not in have:
            for stmt in _pg_statements(VACATE_MIGRATION_PATH):
                cursor.execute(stmt)
        if "hearing_end_date" not in have:
            for stmt in _pg_statements(SPAN_MIGRATION_PATH):
                cursor.execute(stmt)
        if "notice" not in have:
            for stmt in _pg_statements(NOTICE_MIGRATION_PATH):
                cursor.execute(stmt)
        if DURATION_STATED_COLUMN not in have:
            cursor.execute("LOCK TABLE matter_hearings IN ACCESS EXCLUSIVE MODE")
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'matter_hearings' "
                "AND column_name = 'duration_stated'"
            )
            if not cursor.fetchall():
                cursor.execute(_ADD_DURATION_STATED)
                cursor.execute(_BACKFILL_DURATION_STATED)
    _ensure_matter_day_index(cursor)
    _ensured_backends.add(key)


def _ensure_matter_day_index(cursor) -> None:
    cursor.execute(
        "SELECT 1 FROM matter_hearings WHERE case_ref = '' AND status = 'scheduled' AND matter_id IS NOT NULL "
        "GROUP BY matter_id, hearing_date HAVING COUNT(*) > 1 LIMIT 1"
    )
    if cursor.fetchall():
        logging.getLogger(__name__).error("ux_matter_hearings_matter_date_live not built: duplicate live hearings exist for a matter and day")
        return
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_matter_hearings_matter_date_live ON matter_hearings (matter_id, hearing_date) "
        "WHERE case_ref = '' AND status = 'scheduled' AND matter_id IS NOT NULL"
    )


def _rows(cursor) -> list[dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _select_hearings(where: str, params: tuple, *, order: str = "hearing_date, COALESCE(hearing_time, '99:99'), hearing_id", limit: int = 2000) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 5000))
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(_ROW_COLUMNS)} FROM matter_hearings {where} ORDER BY {order} LIMIT {limit}",
            params,
        )
        rows = _rows(cursor)
    return _decorate(rows)


def _confirmers(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    try:
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT hearing_id, actor FROM matter_hearing_events WHERE hearing_id IN ({', '.join('?' for _ in ids)}) ORDER BY at_utc, event_id",
                tuple(ids),
            )
            events = cursor.fetchall()
    except Exception:
        return {}
    named: dict[int, str] = {}
    for hearing_id, actor in events:
        if is_signed_in_person(str(actor or "")):
            named[int(hearing_id)] = _clean(actor, 200)
    return named


def _decorate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names: dict[int, str] = {}
    ids = sorted({int(r["matter_id"]) for r in rows if r.get("matter_id") is not None})
    if ids:
        try:
            with clientdb_sql.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT matter_id, canonical_name FROM matters WHERE matter_id IN ({', '.join('?' for _ in ids)})",
                    tuple(ids),
                )
                names = {int(r[0]): _clean(r[1], 200) for r in cursor.fetchall()}
        except Exception:
            names = {}
    links = _replacement_links(rows)
    confirmers = _confirmers([int(r["hearing_id"]) for r in rows if r.get("human_edited")])
    for row in rows:
        row["confirmed_by"] = confirmers.get(int(row["hearing_id"]), "")
        row["vacate_kind"] = row.get("vacate_kind") or ""
        row["request_state"] = row.get("request_state") or ""
        row["request_reason"] = row.get("request_reason") or ""
        row["replaced_by"] = links["by"].get(int(row["hearing_id"]))
        row["replaces_hearing_id"] = links["from"].get(int(row["hearing_id"]))
        row["is_final"] = bool(row.get("is_final"))
        row["human_edited"] = bool(row.get("human_edited"))
        row["duration_minutes"] = int(row.get("duration_minutes") or 60)
        row["duration_stated"] = bool(1 if row.get("duration_stated") is None else row["duration_stated"])
        row["hearing_date"] = str(row["hearing_date"])[:10]
        row["hearing_end_date"] = str(row.get("hearing_end_date") or "")[:10]
        row["hearing_dates"] = str(row.get("hearing_dates") or "")
        row["notice"] = row.get("notice") or ""
        row["not_before_date"] = str(row.get("not_before_date") or "")[:10]
        row["multi_day"] = hearing_dates.is_multi_day(row)
        row["hearing_label"] = hearing_dates.hearing_label(row)
        row["counsel"] = row.get("counsel") or ""
        row["chambers"] = row.get("chambers") or ""
        row["counsel_booked"] = bool(row["counsel"].strip())
        row["client_name"] = names.get(int(row["matter_id"])) if row.get("matter_id") is not None else None
    return rows


def _replacement_links(rows: list[dict[str, Any]]) -> dict[str, dict[int, Any]]:
    out: dict[str, dict[int, Any]] = {"by": {}, "from": {}}
    ids = sorted({int(r["hearing_id"]) for r in rows})
    targets = sorted({int(r["replaced_by_hearing_id"]) for r in rows if r.get("replaced_by_hearing_id") is not None})
    try:
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            if targets:
                cursor.execute(
                    f"SELECT hearing_id, hearing_date, hearing_time FROM matter_hearings WHERE hearing_id IN ({', '.join('?' for _ in targets)})",
                    tuple(targets),
                )
                found = {int(r[0]): {"hearing_id": int(r[0]), "hearing_date": str(r[1])[:10], "hearing_time": r[2]} for r in cursor.fetchall()}
                for row in rows:
                    target = row.get("replaced_by_hearing_id")
                    if target is not None and int(target) in found:
                        out["by"][int(row["hearing_id"])] = found[int(target)]
            if ids:
                cursor.execute(
                    f"SELECT hearing_id, replaced_by_hearing_id FROM matter_hearings WHERE replaced_by_hearing_id IN ({', '.join('?' for _ in ids)})",
                    tuple(ids),
                )
                for old_id, new_id in cursor.fetchall():
                    out["from"][int(new_id)] = int(old_id)
    except Exception:
        return {"by": {}, "from": {}}
    return out


def _log(cursor, hearing_id: int, actor: str, action: str, before: Any, after: Any, source_message_id: str = "") -> None:
    cursor.execute(
        "INSERT INTO matter_hearing_events (hearing_id, at_utc, actor, action, before_json, after_json, source_message_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            hearing_id, utc_now_z(), _clean(actor, 200) or "system", action,
            json.dumps(before, sort_keys=True, default=str) if before is not None else "",
            json.dumps(after, sort_keys=True, default=str) if after is not None else "",
            _clean(source_message_id, 400),
        ),
    )



def get_hearing(hearing_id: int) -> dict[str, Any] | None:
    rows = _select_hearings("WHERE hearing_id = ?", (int(hearing_id),), limit=1)
    return rows[0] if rows else None


def list_hearings(
    date_from: str, date_to: str, *, matter_id: int | None = None, include_dismissed: bool = False,
) -> list[dict[str, Any]]:
    where = "WHERE hearing_date >= ? AND hearing_date <= ?"
    params: list[Any] = [_valid_date(date_from), _valid_date(date_to)]
    if matter_id is not None:
        where += " AND matter_id = ?"
        params.append(int(matter_id))
    if not include_dismissed:
        where += " AND review_state <> 'dismissed'"
    return _select_hearings(where, tuple(params))


def unlinked_hearings(date_from: str = "") -> list[dict[str, Any]]:
    where = "WHERE matter_id IS NULL AND review_state <> 'dismissed' AND status = 'scheduled'"
    params: tuple = ()
    if date_from:
        where += " AND hearing_date >= ?"
        params = (_valid_date(date_from),)
    return _select_hearings(where, params)


def review_queue(*, include_past: bool = False, today: str | None = None) -> list[dict[str, Any]]:
    if include_past:
        return _select_hearings("WHERE review_state = 'needs_review'", ())
    day = today or london_today().isoformat()
    return _select_hearings("WHERE review_state = 'needs_review' AND substr(CAST(hearing_date AS TEXT), 1, 10) >= ?", (day,))


def count_needs_review(today: str | None = None) -> int:
    day = today or dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat()
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM matter_hearings WHERE review_state = 'needs_review' AND substr(CAST(hearing_date AS TEXT), 1, 10) >= ?",
            (day,),
        )
        return int(cursor.fetchone()[0])


def history(hearing_id: int) -> list[dict[str, Any]]:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT event_id, hearing_id, at_utc, actor, action, before_json, after_json, source_message_id "
            "FROM matter_hearing_events WHERE hearing_id = ? ORDER BY at_utc DESC, event_id DESC LIMIT 200",
            (int(hearing_id),),
        )
        rows = _rows(cursor)
    for row in rows:
        row["at"] = row.pop("at_utc")
        row["before"] = json.loads(row.pop("before_json") or "null")
        row["after"] = json.loads(row.pop("after_json") or "null")
    return rows


_LIVE_FIRST = "CASE WHEN status = 'scheduled' THEN 0 ELSE 1 END, hearing_id"


def find_by_identity(case_ref: str = "", matter_id: int | None = None, hearing_date: str = "") -> dict[str, Any] | None:
    if not hearing_date:
        return None
    if case_ref:
        rows = _select_hearings("WHERE case_ref = ? AND hearing_date = ?", (case_ref, hearing_date), order=_LIVE_FIRST, limit=1)
        return rows[0] if rows else None
    if matter_id is not None:
        rows = _select_hearings("WHERE matter_id = ? AND hearing_date = ?", (int(matter_id), hearing_date), order=_LIVE_FIRST, limit=1)
        if rows:
            return rows[0]
    return None



def _insert(cursor, values: dict[str, Any]) -> int:
    uid = uuid.uuid4().hex
    now = utc_now_z()
    row = {
        "hearing_uid": uid, "matter_id": None, "case_ref": "", "hearing_time": None,
        "duration_minutes": 60, "duration_stated": 0, "hearing_type": "", "order_types": "", "is_final": 0,
        "court": "", "mode": "", "join_url": "", "applicant": "", "respondent": "",
        "counsel": "", "chambers": "", "status": "scheduled", "review_state": "ok", "review_reason": "", "confidence": None,
        "source_kind": "manual", "source_message_id": "", "source_subject": "",
        "source_received_utc": "", "source_web_link": "", "notes": "", "human_edited": 0,
        "created_utc": now, "updated_utc": now, "updated_by": "",
        "vacate_kind": "", "replaced_by_hearing_id": None, "request_state": "", "request_reason": "",
        "hearing_end_date": "", "hearing_dates": "", "notice": "", "not_before_date": "",
        **values,
    }
    columns = [c for c in _ROW_COLUMNS if c != "hearing_id"]
    cursor.execute(
        f"INSERT INTO matter_hearings ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        tuple(row[c] for c in columns),
    )
    cursor.execute("SELECT hearing_id FROM matter_hearings WHERE hearing_uid = ?", (uid,))
    return int(cursor.fetchone()[0])


def _current(cursor, hearing_id: int, *, lock: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock and not clientdb_sql._using_sqlite() else ""
    cursor.execute(f"SELECT {', '.join(_ROW_COLUMNS)} FROM matter_hearings WHERE hearing_id = ?{suffix}", (hearing_id,))
    rows = _rows(cursor)
    if not rows:
        raise HearingError(f"hearing {hearing_id} not found")
    return rows[0]


def _is_conflict(exc: Exception) -> bool:
    return any(word in type(exc).__name__ for word in ("Unique", "Integrity"))


def _find_locked(cursor, case_ref: str, matter_id: int | None, hearing_date: str) -> dict[str, Any] | None:
    suffix = " FOR UPDATE" if not clientdb_sql._using_sqlite() else ""
    if case_ref:
        where, params = "case_ref = ? AND hearing_date = ?", (case_ref, hearing_date)
    elif matter_id is not None:
        where, params = "matter_id = ? AND hearing_date = ?", (int(matter_id), hearing_date)
    else:
        return None
    cursor.execute(f"SELECT {', '.join(_ROW_COLUMNS)} FROM matter_hearings WHERE {where} ORDER BY {_LIVE_FIRST} LIMIT 1{suffix}", params)
    rows = _rows(cursor)
    return rows[0] if rows else None


def _apply(
    cursor, hearing_id: int, changes: dict[str, Any], actor: str, action: str, before: dict[str, Any], source_message_id: str = "",
    *, source: dict[str, Any] | None = None,
) -> None:
    if not changes:
        return
    changes = {**changes, "updated_utc": utc_now_z(), "updated_by": _clean(actor, 200)}
    cursor.execute(
        f"UPDATE matter_hearings SET {', '.join(f'{k} = ?' for k in changes)} WHERE hearing_id = ?",
        (*changes.values(), hearing_id),
    )
    after = {k: v for k, v in changes.items() if k not in ("updated_utc", "updated_by")}
    if source:
        after["source"] = source
    _log(cursor, hearing_id, actor, action, {k: before.get(k) for k in changes if k not in ("updated_utc", "updated_by")}, after, source_message_id)


def _human_flag(actor: str) -> dict[str, int]:
    return {"human_edited": 1} if is_signed_in_person(actor) else {}


def _firm_workers() -> set[str]:
    try:
        import firm_profile

        return {str(w).strip().lower() for w in firm_profile.load_profile().workers}
    except Exception:
        return set()


def is_signed_in_person(actor: str) -> bool:
    name = _clean(actor, 200)
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", name):
        return True
    return name.lower() in _firm_workers()


def actor_kind(actor: str) -> str:
    if is_signed_in_person(actor):
        return "person"
    return "assistant" if re.match(r"\s*(claude|assistant|ai|tailnet)\b", str(actor or ""), re.I) else "system"


def create_hearing(fields: dict[str, Any], *, actor: str) -> dict[str, Any]:
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    values = normalise_fields({k: v for k, v in fields.items() if k in EDITABLE_FIELDS})
    if "hearing_date" not in values:
        raise HearingError("hearing_date is required")
    values = _span_fields(values, values["hearing_date"])
    if not values.get("case_ref") and values.get("matter_id") is None:
        raise HearingError("a case number or a matter is required")
    clash = find_by_identity(values.get("case_ref", ""), values.get("matter_id"), values["hearing_date"])
    if clash and clash["status"] == "scheduled":
        raise HearingError("this case already has a hearing on that date; edit it instead")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        hearing_id = _insert(cursor, {**values, "human_edited": int(is_signed_in_person(actor)), "source_kind": "manual" if is_signed_in_person(actor) else actor_kind(actor), "updated_by": actor})
        _log(cursor, hearing_id, actor, "created", None, {"duration_stated": 0, **values})
    return get_hearing(hearing_id)


def update_hearing(hearing_id: int, edits: dict[str, Any], *, actor: str) -> dict[str, Any]:
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    unknown = set(edits) - set(EDITABLE_FIELDS)
    if unknown:
        raise HearingError(f"cannot edit {sorted(unknown)}")
    values = normalise_fields(edits)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id))
        if any(k in values for k in (*SPAN_COLUMNS, "hearing_date")):
            start = values.get("hearing_date") or str(before["hearing_date"])[:10]
            merged = _span_fields({"hearing_end_date": before.get("hearing_end_date") or "", "hearing_dates": before.get("hearing_dates") or "", **values}, start)
            values = {**values, **{k: merged[k] for k in SPAN_COLUMNS if k in merged}}
        changes = {k: v for k, v in values.items() if before.get(k) != v}
        if changes:
            if values.get("counsel") and before["review_state"] == "needs_review":
                changes.update({"review_state": "ok", "review_reason": ""})
            try:
                _apply(cursor, int(hearing_id), {**changes, **_human_flag(actor)}, actor, "updated", before)
            except Exception as exc:
                if _is_conflict(exc):
                    raise HearingError("another hearing already exists for that case number on that date") from exc
                raise
    return get_hearing(int(hearing_id))


REPLY_ACTOR = "Case flow (counsel accepted)"


def _counsel_events(cursor, hearing_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        "SELECT at_utc, actor, after_json FROM matter_hearing_events WHERE hearing_id = ? ORDER BY at_utc DESC, event_id DESC",
        (hearing_id,),
    )
    out = []
    for row in _rows(cursor):
        after = json.loads(row["after_json"] or "null")
        if isinstance(after, dict) and any(str(after.get(k) or "").strip() for k in ("counsel", "chambers")):
            out.append({"at": str(row["at_utc"]), "actor": str(row["actor"]), "after": after})
    return out


def record_counsel_from_reply(
    hearing_id: int, *, counsel: str = "", chambers: str = "", reply_utc: str, evidence: list[str] | None = None,
) -> dict[str, Any]:
    values = normalise_fields({k: v for k, v in {"counsel": counsel, "chambers": chambers}.items() if str(v or "").strip()})
    reply_utc = _clean(reply_utc, 40)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id), lock=True)
        events = _counsel_events(cursor, int(hearing_id))
        human = max((e["at"] for e in events if e["actor"] != REPLY_ACTOR), default="")
        last_reply = max((str((e["after"].get("source") or {}).get("reply_utc") or "") for e in events if e["actor"] == REPLY_ACTOR), default="")
        changes: dict[str, Any] = {}
        replaced: dict[str, str] = {}
        for key, value in values.items():
            old = str(before.get(key) or "").strip()
            if not value or old == value:
                continue
            if old and (human >= reply_utc or (last_reply and last_reply >= reply_utc)):
                continue
            changes[key] = value
            if old:
                replaced[key] = old
        if changes.get("counsel") and before.get("review_state") == "needs_review":
            changes.update({"review_state": "ok", "review_reason": ""})
        lines = [_clean(e, 200) for e in (evidence or []) if e.split(":", 1)[0] in changes]
        lines += [f"{key}: replaced {old}" for key, old in replaced.items()]
        source = {"reply_utc": reply_utc, "evidence": lines, **({"replaced": replaced} if replaced else {})}
        _apply(cursor, int(hearing_id), changes, REPLY_ACTOR, "updated", before, source=source)
    return {"hearing": get_hearing(int(hearing_id)), "recorded": sorted(k for k in changes if k in values), "replaced": replaced}


def set_status(hearing_id: int, status: str, *, actor: str, note: str = "") -> dict[str, Any]:
    status = LEGACY_STATUSES.get(status, status)
    if status not in STATUSES:
        raise HearingError(f"status must be one of {list(STATUSES)}")
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id), lock=True)
        if before["status"] != status:
            changes: dict[str, Any] = {"status": status, **_human_flag(actor), "request_state": "", "request_reason": ""}
            if status == "vacated":
                changes["vacate_kind"] = before.get("vacate_kind") or "other"
            else:
                changes.update({"vacate_kind": "", "replaced_by_hearing_id": None})
            if note:
                changes["notes"] = _clean_multiline(f"{before.get('notes', '')}\n{note}", 4000)
            try:
                _apply(cursor, int(hearing_id), changes, actor, "status", before)
            except Exception as exc:
                if _is_conflict(exc):
                    raise HearingError("another hearing is already listed for that case number on that date; vacate or edit it first") from exc
                raise
    return get_hearing(int(hearing_id))


_CARRIED_FIELDS = (
    "case_ref", "matter_id", "duration_minutes", "hearing_type", "order_types", "is_final", "court",
    "mode", "join_url", "applicant", "respondent", "counsel", "chambers",
)


def _when(row: dict[str, Any]) -> str:
    return f"{row['hearing_date']} {row.get('hearing_time') or '(no time)'}"


def _note_line(existing: str, line: str) -> str:
    return _clean_multiline(f"{existing}\n{line}" if existing else line, 4000)


def vacate_hearing(
    hearing_id: int, kind: str, *, actor: str, reason: str = "", replacement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in VACATE_KINDS:
        raise HearingError(f"kind must be one of {list(VACATE_KINDS)}")
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    reason = _clean_multiline(reason, 600)
    if kind != "moved" and replacement:
        raise HearingError("only a moved hearing has a replacement")
    new_values: dict[str, Any] = {}
    if kind == "moved":
        if not replacement or not replacement.get("hearing_date"):
            raise HearingError("a moved hearing needs its new date")
        new_values = normalise_fields({k: v for k, v in replacement.items() if k in EDITABLE_FIELDS})
    new_id: int | None = None
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        old = _current(cursor, int(hearing_id), lock=True)
        if old["status"] == "vacated" and not (kind == "moved" and old.get("replaced_by_hearing_id") is None):
            raise HearingError("this hearing is already vacated")
        line = {
            "moved": "Vacated: moved by the court.",
            "no_longer_acting": "Vacated: no longer acting for the client.",
            "court_vacated": "Vacated: the court agreed to vacate it.",
            "other": "Vacated.",
        }[kind]
        if reason:
            line += f" Reason: {reason}"
        vacated = {"status": "vacated", "vacate_kind": kind, **_human_flag(actor), "request_state": "", "request_reason": ""}
        try:
            if kind != "moved":
                _apply(cursor, int(hearing_id), {**vacated, "notes": _note_line(old.get("notes", ""), line)}, actor, "status", old)
            else:
                fresh: dict[str, Any] = {k: old[k] for k in _CARRIED_FIELDS}
                fresh.update(new_values)
                fresh.setdefault("hearing_date", old["hearing_date"])
                if "hearing_time" not in new_values:
                    fresh["hearing_time"] = None
                if _when(fresh) == _when(old):
                    raise HearingError("the new date and time are the same as this hearing's; nothing has moved")
                if old["status"] == "scheduled":
                    _apply(cursor, int(hearing_id), {**vacated, "notes": _note_line(old.get("notes", ""), line)}, actor, "status", old)
                clash = _find_locked(cursor, fresh.get("case_ref", ""), fresh.get("matter_id"), fresh["hearing_date"])
                if clash and clash["status"] == "scheduled":
                    raise HearingError("this case already has a hearing on that date; edit it instead")
                notes = _note_line("", f"Moved from {_when(old)}." + (f" Reason: {reason}" if reason else ""))
                stated = 1 if "duration_minutes" in new_values else int(old.get("duration_stated") or 0)
                new_id = _insert(cursor, {**fresh, **_human_flag(actor), "source_kind": "manual" if is_signed_in_person(actor) else actor_kind(actor), "updated_by": actor, "duration_stated": stated, "notes": notes})
                _log(cursor, new_id, actor, "created", None, {"moved_from": int(hearing_id), "hearing_date": fresh["hearing_date"], "hearing_time": fresh["hearing_time"]})
                after = _current(cursor, int(hearing_id))
                _apply(cursor, int(hearing_id), {"replaced_by_hearing_id": new_id, "notes": _note_line(after.get("notes", ""), f"Moved to {_when(fresh)}.")}, actor, "moved", after)
        except HearingError:
            raise
        except Exception as exc:
            if _is_conflict(exc):
                raise HearingError("this case already has a hearing on that date; edit it instead") from exc
            raise
    return {"hearing": get_hearing(int(hearing_id)), "replacement": get_hearing(new_id) if new_id else None}


def request_from_court(hearing_id: int, request_state: str, *, actor: str, reason: str = "") -> dict[str, Any]:
    if request_state not in REQUEST_STATES or not request_state:
        raise HearingError(f"request_state must be one of {[r for r in REQUEST_STATES if r]}")
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id), lock=True)
        if before["status"] != "scheduled":
            raise HearingError("only a live hearing can have a request made about it")
        _apply(cursor, int(hearing_id), {"request_state": request_state, "request_reason": _clean_multiline(reason, 2000), **_human_flag(actor)}, actor, "request", before)
    return get_hearing(int(hearing_id))


def court_decision(hearing_id: int, agreed: bool, *, actor: str) -> dict[str, Any]:
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id), lock=True)
        state = before.get("request_state") or ""
        if not state:
            raise HearingError("no request is waiting for the court's answer on this hearing")
        asked = before.get("request_reason") or ""
        cleared = {"request_state": "", "request_reason": ""}
        if not agreed:
            changes: dict[str, Any] = {**cleared, "notes": _note_line(before.get("notes", ""), "The court refused the request.")}
        elif state == "vacation_requested":
            changes = {**cleared, "status": "vacated", "vacate_kind": "court_vacated", "notes": _note_line(before.get("notes", ""), "Vacated: the court agreed to vacate it.")}
        else:
            changes = {**cleared, "mode": "hybrid", "notes": _note_line(before.get("notes", ""), "The court agreed to a hybrid or remote hearing.")}
        _ = asked
        _apply(cursor, int(hearing_id), {**changes, **_human_flag(actor)}, actor, "request", before)
    return get_hearing(int(hearing_id))


def resolve_review(hearing_id: int, action: str, *, actor: str, edits: dict[str, Any] | None = None) -> dict[str, Any]:
    if action not in ("confirm", "dismiss"):
        raise HearingError("action must be 'confirm' or 'dismiss'")
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    unknown = set(edits or {}) - set(EDITABLE_FIELDS)
    if unknown:
        raise HearingError(f"cannot edit {sorted(unknown)}")
    values = normalise_fields(edits or {})
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id))
        changes = {k: v for k, v in values.items() if before.get(k) != v}
        changes["review_state"] = "ok" if action == "confirm" else "dismissed"
        changes["review_reason"] = ""
        changes.update(_human_flag(actor))
        try:
            _apply(cursor, int(hearing_id), changes, actor, "review", before)
        except Exception as exc:
            if _is_conflict(exc):
                raise HearingError("another hearing already exists for that case number on that date") from exc
            raise
    return get_hearing(int(hearing_id))


def note_review_reason(hearing_id: int, reason: str, *, actor: str) -> dict[str, Any]:
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor is required")
    text = _clean_multiline(reason, 600)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id))
        if before["review_state"] == "needs_review" and text and before.get("review_reason") != text:
            _apply(cursor, int(hearing_id), {"review_reason": text}, actor, "review_note", before)
    return get_hearing(int(hearing_id))


def tidy_review(hearing_id: int, remaining_reason: str, *, actor: str) -> dict[str, Any]:
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor is required")
    text = _clean_multiline(remaining_reason, 600)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id))
        if before["review_state"] != "needs_review" or before.get("human_edited") or (before.get("review_reason") or "") == text:
            return get_hearing(int(hearing_id))
        changes = {"review_reason": text} if text else {"review_state": "ok", "review_reason": ""}
        _apply(cursor, int(hearing_id), changes, actor, "review_tidy", before)
    return get_hearing(int(hearing_id))


def link_matter(hearing_id: int, matter_id: int, *, actor: str) -> dict[str, Any]:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id))
        if before.get("matter_id") != int(matter_id):
            _apply(cursor, int(hearing_id), {"matter_id": int(matter_id)}, actor, "updated", before)
    return get_hearing(int(hearing_id))


AUTO_LINK_ACTOR = "system:auto-link"


def unlink_hearing(hearing_id: int, *, actor: str) -> dict[str, Any]:
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id), lock=True)
        if before.get("matter_id") is not None:
            _apply(cursor, int(hearing_id), {"matter_id": None}, actor, "unlinked", before)
    return get_hearing(int(hearing_id))


def _was_unlinked(cursor, hearing_id: int) -> bool:
    cursor.execute("SELECT 1 FROM matter_hearing_events WHERE hearing_id = ? AND action = 'unlinked' LIMIT 1", (int(hearing_id),))
    return cursor.fetchone() is not None


def _auto_link_choice(row: dict[str, Any], suggestions: list[dict[str, Any]], party_names: Callable[[int], list[str] | None]) -> int | None:
    if len({s["matter_id"] for s in suggestions}) != 1:
        return None
    pick = suggestions[0]
    wanted = _name_words(row.get("applicant"))
    if pick.get("exact"):
        matched = str(pick.get("matched_on") or "")
        same_case = _compact(matched) != "" and _compact(matched) == _compact(row.get("case_ref"))
        full_name = len(wanted) >= 2 and _name_words(matched) == wanted
        return int(pick["matter_id"]) if same_case or full_name else None
    if len(wanted) < 2:
        return None
    have: set[str] = set()
    for name in party_names(int(pick["matter_id"])) or []:
        have |= _name_words(name)
    return int(pick["matter_id"]) if wanted <= have else None


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _name_words(name: Any) -> set[str]:
    return {w for w in re.split(r"[^a-z]+", str(name or "").lower()) if len(w) > 1}


def _matter_of_the_case(row: dict[str, Any]) -> int | None:
    case_ref = str(row.get("case_ref") or "")
    if not case_ref:
        return None
    owners = _case_ref_owners(case_ref)
    if owners and len(owners) == 1:
        return next(iter(owners))
    if owners:
        return None
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT matter_id FROM matter_hearings WHERE case_ref = ? AND matter_id IS NOT NULL", (case_ref,))
        linked = {int(r[0]) for r in cursor.fetchall()}
    return next(iter(linked)) if len(linked) == 1 else None


def auto_link(hearing_id: int, *, suggester: Callable[..., list[dict[str, Any]]] | None = None,
              party_names: Callable[[int], list[str] | None] | None = None) -> int | None:
    row = get_hearing(int(hearing_id))
    if row is None or row.get("matter_id") is not None:
        return None
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        if _was_unlinked(conn.cursor(), int(hearing_id)):
            return None
    try:
        matter_id = _matter_of_the_case(row)
        if matter_id is not None:
            link_matter(int(hearing_id), matter_id, actor=AUTO_LINK_ACTOR)
            return matter_id
    except Exception:
        pass
    try:
        suggestions = (suggester or suggest_matters)(int(hearing_id))
        if party_names is None:
            from calendar_finder.matter_link import _matter_party_names as party_names
        matter_id = _auto_link_choice(row, suggestions, party_names)
    except Exception:
        return None
    if matter_id is None:
        return None
    link_matter(int(hearing_id), matter_id, actor=AUTO_LINK_ACTOR)
    return matter_id


def auto_link_all(limit: int = 500) -> int:
    rows = _select_hearings("WHERE matter_id IS NULL AND review_state <> 'dismissed'", (), limit=limit)
    return sum(1 for r in rows if auto_link(int(r["hearing_id"])) is not None)


_CASE_REF_TYPES = {"F": "court_family", "P": "court_children"}


def _matter_known(cursor, matter_id: int) -> bool | None:
    try:
        cursor.execute("SELECT 1 FROM matters WHERE matter_id = ?", (int(matter_id),))
        return cursor.fetchone() is not None
    except Exception:
        return None


def _case_ref_owners(case_ref: str) -> set[int] | None:
    try:
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT matter_id FROM matter_references WHERE ref_type IN ('court_family', 'court_children') AND ref_value_normalised = ?",
                (case_ref,),
            )
            return {int(r[0]) for r in cursor.fetchall()}
    except Exception:
        return None


def link_hearing_to_matter(hearing_id: int, matter_id: int, *, actor: str) -> dict[str, Any]:
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    matter_id = int(matter_id)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        if _matter_known(cursor, matter_id) is False:
            raise HearingError(f"matter {matter_id} does not exist")
        before = _current(cursor, int(hearing_id), lock=True)
    case_ref = before["case_ref"]
    ref_type = _CASE_REF_TYPES.get(case_ref[len(case_ref) - 6 : len(case_ref) - 5]) if case_ref else None
    owners = _case_ref_owners(case_ref) if (case_ref and ref_type) else None
    conflict = bool(owners) and owners != {matter_id}
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        current = _current(cursor, int(hearing_id), lock=True)
        if current.get("matter_id") != matter_id:
            _apply(cursor, int(hearing_id), {"matter_id": matter_id}, actor, "updated", current)
        if case_ref and not conflict:
            cursor.execute("SELECT hearing_id FROM matter_hearings WHERE case_ref = ? AND matter_id IS NULL", (case_ref,))
            for (other_id,) in cursor.fetchall():
                _apply(cursor, int(other_id), {"matter_id": matter_id}, actor, "updated", _current(cursor, int(other_id), lock=True))
    reference = "skipped"
    if ref_type:
        if conflict:
            reference = "conflict"
        elif owners:
            reference = "exists"
        else:
            try:
                with clientdb_sql.get_connection() as conn:
                    cursor = conn.cursor()
                    now = utc_now_z()
                    cursor.execute(
                        "INSERT INTO matter_references (matter_id, ref_type, ref_value, ref_value_normalised, source, notes, is_primary, created_utc, updated_utc) "
                        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                        (matter_id, ref_type, case_ref, case_ref, "hearing_calendar_link", f"Linked by {actor} from the hearing calendar", now, now),
                    )
                reference = "recorded"
            except Exception:
                reference = "failed"
    return {"hearing": get_hearing(int(hearing_id)), "reference": reference}


def suggest_matters(hearing_id: int, *, limit: int = 5) -> list[dict[str, Any]]:
    row = get_hearing(int(hearing_id))
    if row is None:
        raise HearingError(f"hearing {hearing_id} not found")
    from agwu import resolve_client

    seen: dict[int, dict[str, Any]] = {}
    for query in (row["applicant"], row["respondent"], row["case_ref"]):
        if not str(query or "").strip():
            continue
        result = resolve_client(str(query), limit=limit, caller="hearing_store.suggest_matters")
        for cand in result.matches:
            data = cand.row or {}
            matter = data.get("matter_id")
            if matter is None or int(matter) in seen:
                continue
            seen[int(matter)] = {
                "matter_id": int(matter),
                "client_name": _clean(data.get("client_name") or data.get("canonical_name") or "", 200),
                "matched_on": _clean(query, 120),
                "exact": "exact_search" in (cand.match_sources or []),
            }
    return list(seen.values())[: max(1, min(int(limit), 10))]


def _newer(incoming_received: str, existing_received: str) -> bool:
    if not existing_received:
        return True
    if not incoming_received:
        return False
    return incoming_received >= existing_received


def upsert_from_source(
    fields: dict[str, Any],
    *,
    source_kind: str,
    source_message_id: str,
    source_subject: str = "",
    source_received_utc: str = "",
    source_web_link: str = "",
    confidence: float | None = None,
    matter_id: int | None = None,
    actor: str = "system:calendar-finder",
    review_reason: str = "",
) -> dict[str, Any]:
    if source_kind not in SOURCE_KINDS:
        raise HearingError(f"source_kind must be one of {list(SOURCE_KINDS)}")
    values = normalise_fields({k: v for k, v in fields.items() if (k in EDITABLE_FIELDS or k in DERIVED_FIELDS) and k != "matter_id"})
    if "hearing_date" not in values:
        raise HearingError("hearing_date is required")
    if dt.date.fromisoformat(values["hearing_date"]).weekday() >= 5:
        return _refuse_weekend(values["hearing_date"], source_message_id, source_subject, source_received_utc, source_web_link, actor)
    values = _span_fields(values, values["hearing_date"])
    if not values.get("case_ref") and matter_id is None:
        return {"action": "ignored", "hearing": None, "issues": ["no case number or matter to attach the hearing to"]}
    for attempt in (1, 2):
        try:
            return _upsert_once(
                values, source_kind=source_kind, source_message_id=source_message_id, source_subject=source_subject,
                source_received_utc=source_received_utc, source_web_link=source_web_link, confidence=confidence,
                matter_id=matter_id, actor=actor, review_reason=_clean(review_reason, 400),
            )
        except Exception as exc:
            if attempt == 1 and _is_conflict(exc):
                continue
            raise
    raise HearingError("could not record the hearing")


def _refuse_weekend(hearing_date: str, source_message_id: str, source_subject: str, source_received_utc: str, source_web_link: str, actor: str) -> dict[str, Any]:
    reason = f"BUG: a weekend date ({hearing_date}) was read as a hearing and was not recorded; check the notice and the reader"
    if _clean(source_message_id, 400):
        record_lead(source_message_id=source_message_id, source_subject=source_subject, source_received_utc=source_received_utc,
                    source_web_link=source_web_link, reason=reason, actor=actor)
    return {"action": "ignored", "hearing": None, "issues": [reason]}


def _upsert_once(values, *, source_kind, source_message_id, source_subject, source_received_utc, source_web_link,
                 confidence, matter_id, actor, review_reason) -> dict[str, Any]:
    case_ref = values.get("case_ref", "")
    issues = sanity_issues(values["hearing_date"], values.get("hearing_time"))
    if review_reason:
        issues = [*issues, review_reason]
    provenance = {
        "source_kind": source_kind,
        "source_message_id": _clean(source_message_id, 400),
        "source_subject": _clean(source_subject, 500),
        "source_received_utc": _clean(source_received_utc, 80),
        "source_web_link": _clean(source_web_link, 900),
        "confidence": confidence,
    }
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        existing = _find_locked(cursor, case_ref, matter_id, values["hearing_date"])
        if existing is None:
            row = {**values, **provenance, "matter_id": matter_id, "updated_by": actor}
            if issues:
                row["review_state"] = "needs_review"
                row["review_reason"] = _clean("; ".join(issues), 600)
            hearing_id = _insert(cursor, row)
            _log(cursor, hearing_id, actor, "created", None, {**values, "review_reason": row.get("review_reason", "")}, source_message_id)
            action = "created"
        else:
            hearing_id = int(existing["hearing_id"])
            before = _current(cursor, hearing_id, lock=True)
            changes: dict[str, Any] = {}
            newer = _newer(provenance["source_received_utc"], before["source_received_utc"])
            if not newer and provenance["source_message_id"] and provenance["source_message_id"] == before.get("source_message_id"):
                newer = True
            disagreements: list[str] = []
            unsure: list[str] = []
            for key in AUTOMATION_FIELDS:
                if key not in values:
                    continue
                incoming, current = values[key], before.get(key)
                if key == "duration_minutes":
                    if not values.get("duration_stated", 1):
                        continue
                    current_stated = bool(1 if before.get("duration_stated") is None else before["duration_stated"])
                    if incoming == current and current_stated:
                        continue
                    blank = not current_stated
                else:
                    if incoming in (None, "", 0) or incoming == current:
                        continue
                    blank = current in (None, "", 0)
                if before["human_edited"] and not blank:
                    disagreements.append(key)
                elif review_reason and not blank:
                    unsure.append(key)
                elif blank and (newer or not before["human_edited"]):
                    changes[key] = incoming
                elif not blank and newer:
                    changes[key] = incoming
                if key == "duration_minutes" and key in changes:
                    changes["duration_stated"] = 1
            if matter_id is not None and before.get("matter_id") is None:
                changes["matter_id"] = matter_id
            substantive = bool(changes) or bool(disagreements) or bool(unsure)
            if newer and provenance["source_message_id"] and not (review_reason and unsure and not changes):
                changes.update({k: v for k, v in provenance.items() if v not in (None, "")})
            changes = {k: v for k, v in changes.items() if before.get(k) != v}

            merged_time = changes.get("hearing_time", before.get("hearing_time"))
            merged_issues = sanity_issues(before["hearing_date"], merged_time)
            if disagreements:
                changes["review_state"] = "needs_review"
                changes["review_reason"] = _clean(
                    f"a newer message disagrees with a manual edit ({', '.join(sorted(disagreements))}); check the source", 600
                )
            elif review_reason and substantive:
                what = f" (proposes a different {', '.join(sorted(unsure))})" if unsure else ""
                changes["review_state"] = "needs_review"
                changes["review_reason"] = _clean(f"{review_reason}{what}", 600)
            elif before["status"] != "scheduled" and newer and changes:
                changes["review_state"] = "needs_review"
                changes["review_reason"] = "a newer message lists a hearing that was vacated or cancelled"
            elif not before["human_edited"]:
                if merged_issues and before["review_state"] == "ok":
                    changes["review_state"] = "needs_review"
                    changes["review_reason"] = _clean("; ".join(merged_issues), 600)
                elif not merged_issues and not review_reason and before["review_state"] == "needs_review":
                    changes["review_state"] = "ok"
                    changes["review_reason"] = ""
            changes = {k: v for k, v in changes.items() if before.get(k) != v}
            if changes:
                _apply(cursor, hearing_id, changes, actor, "updated" if (disagreements or unsure) else "source", before, source_message_id)
                action = "updated"
            else:
                action = "unchanged"
    return {"action": action, "hearing": get_hearing(hearing_id), "issues": issues}


def apply_vacated(
    *, case_ref: str = "", matter_id: int | None = None, hearing_date: str = "",
    source_message_id: str = "", source_received_utc: str = "", actor: str = "system:calendar-finder",
) -> dict[str, Any]:
    case_ref = normalise_case_ref(case_ref)
    date = _valid_date(hearing_date) if hearing_date else ""
    existing = find_by_identity(case_ref, matter_id, date)
    if existing is None:
        return {"action": "no_match", "hearing": None}
    if existing["status"] == "vacated":
        return {"action": "unchanged", "hearing": existing}
    if existing["human_edited"]:
        flag_review(int(existing["hearing_id"]), "a message says this hearing was vacated; confirm before changing a hearing a person has handled", source_message_id=source_message_id, actor=actor)
        return {"action": "unchanged", "hearing": get_hearing(int(existing["hearing_id"]))}
    if not _newer(source_received_utc, existing["source_received_utc"]):
        return {"action": "unchanged", "hearing": existing}
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(existing["hearing_id"]))
        _apply(cursor, int(existing["hearing_id"]), {"status": "vacated", "vacate_kind": "court_vacated", "request_state": "", "request_reason": "", "source_message_id": _clean(source_message_id, 400), "source_received_utc": _clean(source_received_utc, 80)}, actor, "status", before, source_message_id)
    return {"action": "vacated", "hearing": get_hearing(int(existing["hearing_id"]))}


def flag_review(hearing_id: int, reason: str, *, source_message_id: str = "", actor: str = "system:calendar-finder") -> None:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(hearing_id))
        if before["review_state"] != "needs_review" or before["review_reason"] != _clean(reason, 600):
            _apply(cursor, int(hearing_id), {"review_state": "needs_review", "review_reason": _clean(reason, 600)}, actor, "review", before, source_message_id)


def note_not_before(case_ref: str, not_before: str, *, source_message_id: str = "", actor: str = "system:calendar-finder") -> dict[str, Any] | None:
    case = normalise_case_ref(case_ref)
    try:
        date = _valid_date(not_before) if str(not_before or "").strip() else ""
    except HearingError:
        return None
    if not case or not date:
        return None
    rows = _select_hearings("WHERE case_ref = ?", (case,), order="hearing_date DESC, hearing_id DESC", limit=1)
    if not rows:
        return None
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        before = _current(cursor, int(rows[0]["hearing_id"]))
        if str(before.get("not_before_date") or "") != date:
            _apply(cursor, int(before["hearing_id"]), {"not_before_date": date}, actor, "updated", before, source_message_id)
    return get_hearing(int(rows[0]["hearing_id"]))




def unbacked_read_reason(hearing_date: str, hearing_time: str = "", case_ref: str = "") -> str:
    try:
        when = dt.date.fromisoformat(str(hearing_date)[:10]).strftime("%-d %b %Y")
    except ValueError:
        when = str(hearing_date)
    when += f" at {str(hearing_time)[:5]}" if hearing_time else ""
    case = f" (case {case_ref})" if case_ref else ""
    return f"the reader thinks this email gives a hearing on {when}{case}, but no sentence in it states one; check it and add the hearing if it is one"


_LEAD_COLUMNS = ("lead_id", "source_message_id", "source_subject", "source_received_utc", "source_web_link", "reason", "state", "created_utc", "updated_utc", "updated_by")


def record_lead(*, source_message_id: str, source_subject: str = "", source_received_utc: str = "", source_web_link: str = "", reason: str, actor: str = "system:calendar-finder") -> dict[str, Any]:
    message_id = _clean(source_message_id, 400)
    if not message_id:
        raise HearingError("source_message_id is required")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(f"SELECT {', '.join(_LEAD_COLUMNS)} FROM matter_hearing_leads WHERE source_message_id = ?", (message_id,))
        rows = _rows(cursor)
        if rows:
            return {"action": "exists", "lead": rows[0]}
        now = utc_now_z()
        cursor.execute(
            "INSERT INTO matter_hearing_leads (source_message_id, source_subject, source_received_utc, source_web_link, reason, state, created_utc, updated_utc, updated_by) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)",
            (message_id, _clean(source_subject, 500), _clean(source_received_utc, 80), _clean(source_web_link, 900), _clean(reason, 400), now, now, _clean(actor, 200)),
        )
        cursor.execute(f"SELECT {', '.join(_LEAD_COLUMNS)} FROM matter_hearing_leads WHERE source_message_id = ?", (message_id,))
        return {"action": "created", "lead": _rows(cursor)[0]}


def list_leads(state: str = "open") -> list[dict[str, Any]]:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(_LEAD_COLUMNS)} FROM matter_hearing_leads WHERE state = ? ORDER BY created_utc DESC, lead_id DESC LIMIT 500",
            (state,),
        )
        return _rows(cursor)


def count_open_leads() -> int:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM matter_hearing_leads WHERE state = 'open'")
        return int(cursor.fetchone()[0])


def resolve_lead(lead_id: int, action: str, *, actor: str) -> dict[str, Any]:
    if action not in ("done", "dismissed"):
        raise HearingError("action must be 'done' or 'dismissed'")
    actor = _clean(actor, 200)
    if not actor:
        raise HearingError("actor (your name) is required")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT lead_id FROM matter_hearing_leads WHERE lead_id = ?", (int(lead_id),))
        if cursor.fetchone() is None:
            raise HearingError(f"lead {lead_id} not found")
        cursor.execute("UPDATE matter_hearing_leads SET state = ?, updated_utc = ?, updated_by = ? WHERE lead_id = ?", (action, utc_now_z(), actor, int(lead_id)))
        cursor.execute(f"SELECT {', '.join(_LEAD_COLUMNS)} FROM matter_hearing_leads WHERE lead_id = ?", (int(lead_id),))
        return _rows(cursor)[0]



def _ics_escape(text: str) -> str:
    text = _CONTROL_RE.sub(" ", str(text).replace("\r\n", "\n").replace("\r", "\n"))
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line: str) -> list[str]:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    out: list[str] = []
    current = b""
    for char in line:
        piece = char.encode("utf-8")
        limit = 75 if not out else 74
        if len(current) + len(piece) > limit:
            out.append(current.decode("utf-8"))
            current = b""
        current += piece
    out.append(current.decode("utf-8"))
    return [out[0]] + [" " + part for part in out[1:]]


def render_ics(rows: Iterable[dict[str, Any]], *, calendar_name: str = "CaseForge hearings") -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CaseForge//CaseForge hearings//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_escape(calendar_name)}"]
    for row in rows:
        if row.get("review_state") == "dismissed":
            continue
        date = dt.date.fromisoformat(str(row["hearing_date"])[:10])
        label = row.get("order_types") or row.get("hearing_type") or "Hearing"
        parties = " v ".join(p for p in (row.get("applicant"), row.get("respondent")) if p) or row.get("client_name") or ""
        summary = " | ".join(p for p in (label + (" (final)" if row.get("is_final") and "final" not in label.lower() else ""), row.get("case_ref"), parties) if p)
        if row.get("status") != "scheduled":
            summary += f" ({row['status']})"
        if row.get("review_state") == "needs_review":
            summary += " [to check]"
        lines += ["BEGIN:VEVENT", f"UID:hearing-{row['hearing_uid']}@{ICS_UID_DOMAIN}", f"DTSTAMP:{stamp}"]
        time = row.get("hearing_time")
        if time:
            start = dt.datetime.combine(date, dt.time(int(time[:2]), int(time[3:5])), tzinfo=LONDON).astimezone(dt.timezone.utc)
            end = start + dt.timedelta(minutes=int(row.get("duration_minutes") or 60))
            lines += [f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{date.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(date + dt.timedelta(days=1)).strftime('%Y%m%d')}"]
        lines.append(f"SUMMARY:{_ics_escape(summary)}")
        location = row.get("court") or ""
        if row.get("mode"):
            location = f"{location} ({row['mode']})" if location else row["mode"]
        if location:
            lines.append(f"LOCATION:{_ics_escape(location)}")
        description = [
            f"Case number: {row['case_ref']}" if row.get("case_ref") else "",
            row.get("counsel") and f"Counsel: {row['counsel']}",
            row.get("chambers") and f"Chambers: {row['chambers']}",
            row.get("join_url") and f"Join: {row['join_url']}",
            row.get("notes"),
        ]
        body = "\n".join(str(d) for d in description if d)
        if body:
            lines.append(f"DESCRIPTION:{_ics_escape(body)}")
        lines += [f"STATUS:{'CANCELLED' if row.get('status') != 'scheduled' else 'CONFIRMED'}", "CATEGORIES:Hearing", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _ics_fold(line)) + "\r\n"
