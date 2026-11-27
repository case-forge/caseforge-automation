from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
import matter_orders
import clientdb_sql
from hearing_calendar import hearing_store
from vergil import sos_status, work_log

LONDON = ZoneInfo("Europe/London")

COMMON_START = ("s1", "s2", "s3")
FL401_STAGES = ("s6a", "s7a", "s8a", "s9a", "s10a")
C100_STAGES = ("s6b", "s7b", "s8b", "s9b", "s10b")
COMMON_END = ("s11",)
SIDE_BRANCHES = ("s12a", "s12b")
CLOSING = ("s13",)

ALL_STAGES: tuple[str, ...] = (
    COMMON_START + FL401_STAGES + C100_STAGES + COMMON_END + SIDE_BRANCHES + CLOSING
)

TRACKS = ("fl401", "c100", "both", "unknown")


class CaseFlowError(ValueError):
    pass



_FL401_TAGS = {"NMO", "OO"}
_C100_TAGS = {"CAO", "SIO", "PSO"}


def detect_track(order_type_tags: str | None, order_requested_text: str | None, order_rows: Iterable[str] | None = None) -> tuple[str, str]:
    resolved = matter_orders.resolve_orders(order_requested_text, order_type_tags, order_rows)
    codes = set(resolved.codes)
    if resolved.structured:
        fl401, c100 = bool(codes & _FL401_TAGS), bool(codes & _C100_TAGS)
        if fl401 or c100:
            shown = ", ".join(sorted(codes & (_FL401_TAGS | _C100_TAGS)))
            return _track_of(fl401, c100), f"Order tags {shown}"
    text = str(order_requested_text or "")
    if text.strip():
        fl401 = bool(codes & _FL401_TAGS)
        c100 = bool(codes & _C100_TAGS) or resolved.reading.children_form
        if fl401 or c100:
            return _track_of(fl401, c100), "Read from the order requested text, no order tags set"
        return "unknown", "The order requested text does not name an NMO, occupation or children order"
    return "unknown", "No order type recorded for this matter"


def _track_of(fl401: bool, c100: bool) -> str:
    if fl401 and c100:
        return "both"
    return "fl401" if fl401 else "c100"


def _track_stages(track: str) -> tuple[str, ...]:
    if track == "fl401":
        return COMMON_START + FL401_STAGES + COMMON_END + SIDE_BRANCHES + CLOSING
    if track == "c100":
        return COMMON_START + C100_STAGES + COMMON_END + SIDE_BRANCHES + CLOSING
    return ALL_STAGES



_WITHOUT_NOTICE = re.compile(r"without[\s-]*notice|ex[\s-]*parte", re.IGNORECASE)
_ON_NOTICE = re.compile(r"on[\s-]*notice|return\s+(?:date|hearing)|full\s+hearing", re.IGNORECASE)
_FHDRA = re.compile(r"\bfhdra\b|first\s+hearing", re.IGNORECASE)
_DRA = re.compile(r"\bdra\b|dispute\s+resolution\s+appointment", re.IGNORECASE)
_FINAL = re.compile(r"final\s+hearing", re.IGNORECASE)


def hearing_stage(hearing: dict[str, Any], track: str) -> str | None:
    kind = str(hearing.get("hearing_type") or "")
    final = bool(hearing.get("is_final")) or bool(_FINAL.search(kind))
    if hearing.get("notice") == "without notice" or _WITHOUT_NOTICE.search(kind):
        return "s8a"
    if _FHDRA.search(kind):
        return "s8b"
    if _DRA.search(kind):
        return "s10b"
    if hearing.get("notice") == "on notice" or _ON_NOTICE.search(kind):
        return "s10a"
    if final:
        return {"fl401": "s10a", "c100": "s10b"}.get(track)
    return None


def _day(iso: str) -> str:
    try:
        return dt.date.fromisoformat(str(iso)[:10]).strftime("%-d %b %Y")
    except ValueError:
        return str(iso)[:10]


def _label(hearing: dict[str, Any]) -> str:
    kind = ", ".join(part for part in (str(hearing.get("hearing_type") or "").strip(), str(hearing.get("notice") or "")) if part)
    return f"{_day(hearing['hearing_date'])} ({kind})" if kind else _day(hearing["hearing_date"])


def hearing_evidence(hearings: list[dict[str, Any]], track: str, today: dt.date) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in sorted(hearings, key=lambda h: str(h["hearing_date"])):
        if row.get("review_state") != "ok" or row.get("status") != "scheduled":
            continue
        stage = hearing_stage(row, track)
        if stage is None:
            continue
        held = str(row["hearing_date"])[:10] < today.isoformat()
        if held:
            out[stage] = {
                "state": "done",
                "evidence": f"Hearing on {_label(row)}: the date has passed and it was not vacated or cancelled",
            }
        elif stage not in out or out[stage]["state"] != "done":
            out.setdefault(stage, {"state": "upcoming", "evidence": f"Hearing listed for {_label(row)}"})
    return out



_DRAFT = re.compile(r"\bdraft\d*\b", re.IGNORECASE)
_CCL = re.compile(
    r"opening[\s_-]*client[\s_-]*care|client[\s_-]*care[\s_-]*letter|\bccl\b|opening[\s_-]*letter", re.IGNORECASE
)
_FL401_FILE = re.compile(r"\bfl401\b", re.IGNORECASE)
_C100_FILE = re.compile(r"\bc100\b", re.IGNORECASE)
_ISSUED = re.compile(r"\bissued\b", re.IGNORECASE)
_LAA = re.compile(r"\blaa\b|legal[\s_-]*aid|notice[\s_-]*of[\s_-]*issue", re.IGNORECASE)
_SEALED = re.compile(r"\bsealed\b", re.IGNORECASE)
_ENFORCEMENT = re.compile(r"\bd89\b|committal|breach", re.IGNORECASE)


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", " ", name)


def _first(files: list[str], *patterns: re.Pattern[str], allow_draft: bool, exclude: re.Pattern[str] | None = None) -> str | None:
    for name in files:
        text = _norm(name)
        if not allow_draft and _DRAFT.search(text):
            continue
        if exclude is not None and exclude.search(text):
            continue
        if all(p.search(text) for p in patterns):
            return name
    return None


def file_evidence(files: list[str], track: str) -> dict[str, str]:
    def note(name: str, what: str) -> str:
        return f"{what}: file named '{name[:80]}' in the matter folder (name only, contents not read)"

    found: dict[str, str] = {}
    hit = _first(files, _CCL, allow_draft=False)
    if hit:
        found["s3"] = note(hit, "Client care letter")
    if track in ("fl401", "both", "unknown"):
        hit = _first(files, _FL401_FILE, allow_draft=True)
        if hit:
            found["s6a"] = note(hit, "FL401 application")
        hit = _first(files, _FL401_FILE, _ISSUED, allow_draft=False, exclude=_LAA)
        if hit:
            found["s7a"] = note(hit, "Application marked issued")
        hit = _first(files, re.compile(r"statement[\s_-]*of[\s_-]*service", re.IGNORECASE), allow_draft=False)
        if hit and sos_status._is_sos_filename(hit):
            found["s9a"] = note(hit, "Statement of Service")
    if track in ("c100", "both", "unknown"):
        hit = _first(files, _C100_FILE, allow_draft=True)
        if hit:
            found["s6b"] = note(hit, "C100 application")
        hit = _first(files, _C100_FILE, _ISSUED, allow_draft=False, exclude=_LAA)
        if hit:
            found["s7b"] = note(hit, "Application marked issued")
    hit = _first(files, _SEALED, allow_draft=False, exclude=_LAA)
    if hit:
        found["s11"] = note(hit, "Sealed order")
    hit = _first(files, _ENFORCEMENT, allow_draft=False)
    if hit:
        found["s12a"] = note(hit, "Enforcement paperwork")
    return found


def _folder_and_files(matter_id: str) -> tuple[str, list[str]]:
    import agwu

    folder = agwu.resolve_folder(matter_id, allow_live_fallback=False, caller="case_flow")
    path = str(folder.matter_folder_path or "").rstrip("/")
    if not path:
        return "", []
    like = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
    with ops_db.connect() as conn:
        rows = conn.execute(
            "SELECT name FROM onedrive_items WHERE item_type = 'file' AND deleted_at_utc IS NULL "
            "AND path LIKE ? ESCAPE '\\' LIMIT 5000",
            (like,),
        ).fetchall()
    return path, [str(r[0]) for r in rows]



def _matter_row(matter_id: str) -> dict[str, Any] | None:
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        names = [d[0] for d in cursor.description]
    return dict(zip(names, tuple(row)))


def _hearings(matter_id: str) -> list[dict[str, Any]]:
    if not matter_id.isdigit():
        return []
    return hearing_store.list_hearings("1990-01-01", "2100-12-31", matter_id=int(matter_id))



def _concluded(row: dict[str, Any], folder_path: str) -> str | None:
    closed = str(row.get("closed_at") or "").strip()
    if closed:
        return f"Closed on {_day(closed)} (closed date recorded in the client database)"
    if str(row.get("closed_notes") or "").strip():
        return None
    parts = [p.lower() for p in folder_path.split("/") if p]
    if any("concluded" in p or "close files" in p for p in parts):
        return "The matter folder is filed under Concluded or Close Files"
    return None


def case_flow(
    matter_id: str,
    *,
    today: dt.date | None = None,
    matter_row: Callable[[str], dict[str, Any] | None] | None = None,
    hearings: Callable[[str], list[dict[str, Any]]] | None = None,
    folder_files: Callable[[str], tuple[str, list[str]]] | None = None,
    work_summary: Callable[[str], dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    matter_row = matter_row or _matter_row
    hearings = hearings or _hearings
    folder_files = folder_files or _folder_and_files
    work_summary = work_summary or work_log.work_summary
    matter = str(matter_id or "").strip()
    if not matter:
        raise CaseFlowError("matter_id is required")
    row = matter_row(matter)
    if row is None:
        raise CaseFlowError(f"matter {matter} not found on record")
    today = today or dt.datetime.now(LONDON).date()

    track, track_reason = detect_track(row.get("order_type_tags"), row.get("order_requested_text"), matter_orders.load_structured(matter)[1])
    on_track = _track_stages(track)

    try:
        folder_path, files = folder_files(matter)
    except Exception:
        folder_path, files = "", []
    have_files = bool(files)

    done: dict[str, str] = {
        "s1": "Matter record exists in the client database",
        "s2": "Client record exists in the client database",
    }
    upcoming_evidence: dict[str, str] = {}

    for stage, text in file_evidence(files, track).items():
        done.setdefault(stage, text)

    work = work_summary(matter) or {}
    opening = work.get("opening_letter")
    if opening and opening.get("status") == "completed":
        done["s3"] = f"Client care letter recorded in the work log on {_day(str(opening.get('latest')))}"
    application = work.get("fl401")
    if application and application.get("status") == "completed" and track in ("fl401", "both", "unknown"):
        done["s6a"] = f"FL401 application recorded in the work log on {_day(str(application.get('latest')))}"
    service = work.get("statement_of_service")
    if service and service.get("status") == "completed" and track in ("fl401", "both", "unknown"):
        done["s9a"] = f"Statement of Service recorded in the work log on {_day(str(service.get('latest')))}"

    for stage, info in hearing_evidence(hearings(matter), track, today).items():
        if info["state"] == "done":
            done[stage] = info["evidence"]
        else:
            upcoming_evidence[stage] = info["evidence"]

    concluded = _concluded(row, folder_path)
    if concluded:
        done["s13"] = concluded

    main_line = [s for s in on_track if s not in SIDE_BRANCHES]
    single_track = track in ("fl401", "c100")
    frontier = max((main_line.index(s) for s in main_line if s in done), default=-1)

    stages: list[dict[str, str]] = []
    for stage in on_track:
        if stage in done:
            state, evidence = "done", done[stage]
        elif stage in SIDE_BRANCHES:
            state, evidence = "unknown", "No record either way; this only applies if the order is breached or subsisting"
        elif not single_track:
            state = "unknown"
            evidence = upcoming_evidence.get(stage) or "The track is not settled, so this stage cannot be placed"
        elif stage in upcoming_evidence:
            state, evidence = "upcoming", upcoming_evidence[stage]
        elif main_line.index(stage) < frontier:
            state, evidence = "unknown", "No record found, though a later stage is shown done"
        else:
            state, evidence = "upcoming", "No record yet"
        stages.append({"id": stage, "state": state, "evidence": evidence})

    suggested = None
    if single_track:
        suggested = next(
            (s["id"] for s in stages if s["id"] in main_line and main_line.index(s["id"]) > frontier and s["state"] == "upcoming"),
            None,
        )
    else:
        suggested = next((s for s in COMMON_START if s not in done), None)

    manual = get_manual_stage(matter)
    if not have_files:
        for entry in stages:
            if entry["id"] in ("s3", "s6a", "s6b", "s7a", "s7b", "s9a", "s11") and entry["state"] != "done":
                entry["evidence"] += "; no cached folder listing for this matter"

    return {
        "matter_id": matter,
        "track": track,
        "track_reason": track_reason,
        "stages": stages,
        "suggested_stage": suggested,
        "manual_stage": manual["stage"] if manual else None,
        "manual_stage_set_by": manual["set_by"] if manual else None,
        "manual_stage_set_utc": manual["set_utc"] if manual else None,
    }


def require_matter(matter_id: str) -> None:
    matter = str(matter_id or "").strip()
    if not matter:
        raise CaseFlowError("matter_id is required")
    if _matter_row(matter) is None:
        raise CaseFlowError(f"matter {matter} not found on record")



def get_manual_stage(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, str] | None:
    with ops_db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT stage, set_by, set_utc FROM matter_case_stage WHERE matter_id = ?", (str(matter_id),)
        ).fetchone()
    return {"stage": row[0], "set_by": row[1], "set_utc": row[2]} if row else None


def set_manual_stage(
    *, matter_id: str, stage: str | None, set_by: str, db_path: str | Path | None = None
) -> dict[str, str | None]:
    matter = str(matter_id or "").strip()
    if not matter:
        raise CaseFlowError("matter_id is required")
    who = " ".join(str(set_by or "").split())[:128]
    if not who:
        raise CaseFlowError("set_by is required")
    if stage is not None and stage not in ALL_STAGES:
        raise CaseFlowError(f"unknown stage {stage!r}; expected one of {list(ALL_STAGES)}")
    now = ops_db.utc_now_z()
    with ops_db.connect(db_path) as conn:
        old = conn.execute("SELECT stage FROM matter_case_stage WHERE matter_id = ?", (matter,)).fetchone()
        old_stage = old[0] if old else None
        if stage is None:
            conn.execute("DELETE FROM matter_case_stage WHERE matter_id = ?", (matter,))
        else:
            conn.execute(
                "INSERT INTO matter_case_stage (matter_id, stage, set_by, set_utc) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(matter_id) DO UPDATE SET stage = excluded.stage, "
                "set_by = excluded.set_by, set_utc = excluded.set_utc",
                (matter, stage, who, now),
            )
        conn.execute(
            "INSERT INTO matter_case_stage_events (matter_id, at_utc, actor, old_stage, new_stage) "
            "VALUES (?, ?, ?, ?, ?)",
            (matter, now, who, old_stage, stage),
        )
        conn.commit()
    return {"matter_id": matter, "stage": stage, "set_by": who if stage else None, "set_utc": now if stage else None}
