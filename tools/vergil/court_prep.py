from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

COLUMNS = ("court_informed", "client_informed", "papers_sent", "opponent_served", "counsel_booked", "bundle_sent", "brief_sent")
WINDOW_DAYS = 14
KNOWN_BUT_UNDATED = "yes"


def london_today() -> dt.date:
    from zoneinfo import ZoneInfo

    return dt.datetime.now(ZoneInfo("Europe/London")).date()


def _in_window(h: dict[str, Any], today: dt.date, days: int) -> bool:
    day = str(h.get("hearing_date") or "")[:10]
    return bool(day) and today.isoformat() <= day <= (today + dt.timedelta(days=days)).isoformat()


def clean_hearings(hearings: Iterable[dict[str, Any]], today: dt.date, days: int = WINDOW_DAYS) -> list[dict[str, Any]]:
    return [
        h
        for h in hearings
        if str(h.get("matter_id") or "").strip()
        and _in_window(h, today, days)
        and str(h.get("status") or "scheduled") == "scheduled"
        and str(h.get("review_state") or "ok") == "ok"
    ]


def one_per_sitting(hearings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for h in hearings:
        key = (str(h.get("matter_id") or ""), str(h.get("hearing_date") or "")[:10], str(h.get("hearing_time") or ""))
        if key not in best:
            best[key] = h
            order.append(key)
            continue
        def richness(row: dict[str, Any]) -> tuple[int, int, int]:
            return (bool(str(row.get("hearing_type") or "").strip()), bool(str(row.get("court") or "").strip()), -int(row.get("hearing_id") or 0))
        if richness(h) > richness(best[key]):
            best[key] = h
    return [best[k] for k in order]


def _date_words(day: str) -> tuple[str, ...]:
    try:
        d = dt.date.fromisoformat(day)
    except ValueError:
        return ()
    suffix = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    month = d.strftime("%B")
    return (f"{d.day:02d}.{d.month:02d}.{d.year}", f"{d.day}.{d.month}.{d.year}", f"{d.day:02d}.{d.month:02d}.{d.year % 100:02d}", f"{d.day}{suffix} {month} {d.year}", f"{d.day} {month} {d.year}")


def accepted_counsel_at(hearing: dict[str, Any], replies: Iterable[dict[str, Any]]) -> str:
    words = _date_words(str(hearing.get("hearing_date") or "")[:10])
    if not words:
        return ""
    about = [r for r in replies if any(w in str(r.get("subject") or "") for w in words)]
    ordered = sorted(about, key=lambda r: str(r.get("created_utc") or ""))
    standing: dict[str, str] = {}
    for r in ordered:
        who = str(r.get("sender_domain") or "").lower()
        if r.get("kind") == "counsel_accepted":
            standing[who] = str(r.get("created_utc") or "")
        elif r.get("kind") == "counsel_rejected":
            standing.pop(who, None)
    return min(standing.values()) if standing else ""


def _counsel_replies(matter_id: str) -> list[dict[str, Any]]:
    try:
        from vergil import attention_store

        return [r for r in attention_store.list_for_matter(matter_id, limit=200) if r.get("kind") in ("counsel_accepted", "counsel_rejected")]
    except Exception:
        return []


def counsel_booked_at(hearing: dict[str, Any], history: Callable[[int], list[dict[str, Any]]] | None) -> str:
    if not str(hearing.get("counsel") or "").strip():
        return ""
    if history is not None:
        try:
            entries = history(int(hearing["hearing_id"]))
        except Exception:
            entries = []
        times = [
            str(e.get("at") or "")
            for e in entries
            if isinstance(e.get("after"), dict) and str(e["after"].get("counsel") or "").strip() and not str((e.get("before") or {}).get("counsel") or "").strip()
        ]
        times = [t for t in times if t]
        if times:
            return min(times)
    return KNOWN_BUT_UNDATED


def board(
    *,
    today: dt.date | None = None,
    hearings: Iterable[dict[str, Any]] | None = None,
    names: dict[str, str] | None = None,
    history: Callable[[int], list[dict[str, Any]]] | None = None,
    marks: Callable[[list[int]], dict[int, dict[str, str]]] | None = None,
    counsel_replies: Callable[[str], list[dict[str, Any]]] | None = None,
    db_path: Any = None,
) -> dict[str, Any]:
    today = today or london_today()
    if hearings is None:
        from hearing_calendar import hearing_store

        hearings = hearing_store.list_hearings(today.isoformat(), (today + dt.timedelta(days=WINDOW_DAYS)).isoformat())
        history = history or hearing_store.history
    hearings = list(hearings)
    if names is None:
        from onboarding.pipeline import milestones

        names = {str(m["matter_id"]): str(m.get("client_name") or "") for m in milestones.open_matters()}
    if marks is None:
        from onboarding.pipeline import court_prep_marks

        def marks(ids: list[int]) -> dict[int, dict[str, str]]:
            return court_prep_marks.stored(ids, db_path=db_path)

    shown = one_per_sitting(h for h in clean_hearings(hearings, today) if str(h["matter_id"]) in names)
    counsel_replies = counsel_replies or _counsel_replies
    in_review = sum(
        1
        for h in hearings
        if str(h.get("matter_id") or "").strip() and _in_window(h, today, WINDOW_DAYS) and str(h.get("status") or "scheduled") == "scheduled" and str(h.get("review_state") or "ok") == "needs_review"
    )
    sends = marks([int(h["hearing_id"]) for h in shown])
    items = []
    for h in shown:
        hid = int(h["hearing_id"])
        got = sends.get(hid, {})
        milestones_ = {col: got.get(col, "") for col in COLUMNS}
        milestones_["counsel_booked"] = counsel_booked_at(h, history) or accepted_counsel_at(h, counsel_replies(str(h["matter_id"])))
        items.append(
            {
                "matter_id": str(h["matter_id"]),
                "client_name": names[str(h["matter_id"])],
                "hearing_id": hid,
                "hearing_date": str(h.get("hearing_date") or "")[:10],
                "hearing_time": str(h.get("hearing_time") or ""),
                "hearing_type": str(h.get("hearing_type") or ""),
                "notice": str(h.get("notice") or ""),
                "court": str(h.get("court") or ""),
                "is_final": bool(h.get("is_final")),
                "milestones": milestones_,
            }
        )
    items.sort(key=lambda i: (i["hearing_date"], i["hearing_time"] or "99:99", i["client_name"].lower(), i["hearing_id"]))
    return {"items": items, "in_review": in_review}
