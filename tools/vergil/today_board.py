#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
from onboarding import pipeline as pl
from vergil import board_overrides

LONDON = ZoneInfo("Europe/London")
LIMIT = 50
log = logging.getLogger(__name__)

NEW_CLIENT_STEPS = ("record", "folder", "statement")
NEW_CLIENT_MAX_DAYS = 3
STEP_5_MAX_AGE_DAYS = 7
PERSON_ONLY_STEPS = ("amend", "ws_sign", "court_email")
_CHASER_SUBJECT = re.compile(r"(update requested|not received)\s*$", re.I)
STEP_TILES = tuple(
    (key, pl.step_number(key), f"{pl.step_ref(key).capitalize()} ({what})")
    for key, what in (
        ("email", "email first Witness Statement draft"),
        ("amend", "email amended Witness Statement draft"),
        ("ws_sign", "email approved Witness Statement draft"),
        ("court_pack", "check and sign applications and draft orders"),
        ("court_email", "email applications to court"),
    )
)
TITLES = {
    **{f"step_{number}": title for _key, number, title in STEP_TILES},
    "reminders": "Court chasers waiting to be sent",
    "drafts": "Other drafts waiting for you",
    "waiting_client": "Waiting for client",
    "waiting_court": "Waiting for court",
    "waiting_counsel": "Waiting for counsel",
}
ORDER = tuple(TITLES)




def _drafts() -> list[dict[str, Any]]:
    from vergil import mailbox_drafts

    return list(mailbox_drafts.list_drafts().get("items") or [])


def _intake(db_path: Any) -> list[dict[str, Any]]:
    from vergil import intake_tray

    return list(intake_tray.list_recent(db_path=db_path).get("items") or [])


def _names(matter_ids: list[str]) -> dict[str, str]:
    import clientdb_sql

    return {mid: str(row.get("canonical_name") or "") for mid, row in clientdb_sql._matter_summaries(matter_ids).items()}


def _hidden(db_path: Any) -> set[str]:
    from onboarding import client_removal

    return client_removal.hidden_ids(db_path)


def _seen_views(matter_ids: list[str], db_path: Any) -> list[tuple[str, str, dict[str, Any], str]]:
    if not matter_ids:
        return []
    from onboarding import pipeline as pl

    out = []
    with ops_db.connect(db_path) as conn:
        for start in range(0, len(matter_ids), 400):
            chunk = matter_ids[start : start + 400]
            marks = ", ".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT matter_id, step, view_json, checked_utc FROM pipeline_step_seen WHERE matter_id IN ({marks})", tuple(chunk)
            ).fetchall()
            for mid, step, view_json, checked in rows:
                try:
                    view = json.loads(view_json)
                except ValueError:
                    continue
                if pl.whole_view(view, str(step)) and str(step) not in pl.LEGACY_FOLDER_STEPS:
                    out.append((str(mid), str(step), view, str(checked or "")))
    return out


def _caseflow_clients(db_path: Any) -> list[dict[str, Any]]:
    from vergil import case_board

    return list(case_board.board(db_path=db_path).get("items") or [])


def _portal_court(matter_id: str) -> str:
    from onboarding.pipeline import portal_courts

    try:
        return portal_courts.portal_court(portal_courts.recorded_court(matter_id))
    except Exception:
        return ""


def _portal_url() -> str:
    from onboarding.pipeline import portal_courts

    return str(portal_courts.PORTAL_LOGIN_URL)


def _pit_stops(db_path: Any) -> dict[str, str]:
    from onboarding.pipeline import waiting
    from vergil import client_edits

    rows = client_edits.list_matters_with_flags(list(waiting.FLAGS.values()), db_path=db_path)
    closed = _closed_matter_ids(list(rows))
    return {mid: state for mid, flags in rows.items() if mid not in closed and (state := waiting.state_of_flags({f: True for f in flags}))}


def _closed_matter_ids(matter_ids: list[str]) -> set[str]:
    ids = [int(m) for m in matter_ids if str(m).isdigit()]
    if not ids:
        return set()
    try:
        import clientdb_sql

        marks = ", ".join("?" for _ in ids)
        with clientdb_sql.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT matter_id FROM dbo.matters WHERE closed_at IS NOT NULL AND matter_id IN ({marks})", tuple(ids))
            return {str(row[0]) for row in cur.fetchall()}
    except Exception:
        return set()


def _step_waits_on_person(view: dict[str, Any], mode: str) -> bool:
    from onboarding import pipeline as pl

    if view.get("status") in ("done", pl.NOT_NEEDED):
        return False
    return pl.with_actor(view, mode).get("actor") == pl.ACTOR_YOU


def _step_label(step: str) -> str:
    from onboarding import pipeline as pl

    return next((label for key, label, _module in pl.STEPS if key == step), step)


def _https(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith("https://") else ""


def _link_for(step: str, view: dict[str, Any] | None, portal: str) -> dict[str, str]:
    if step == "court_email" and portal:
        return {"kind": "portal", "label": f"Open the court's online portal ({portal})", "url": _portal_url()}
    links = [l for l in (view or {}).get("links") or [] if isinstance(l, dict) and _https(l.get("url"))]
    if step == "court_pack":
        pick = next((l for l in links if "prelim" in str(l.get("label") or "").lower()), None) or next(
            (l for l in links if "folder" in str(l.get("label") or "").lower()), None
        )
        return {"kind": "folder", "label": str(pick.get("label") or "Open the folder"), "url": _https(pick["url"])} if pick else {}
    pick = next((l for l in links if "draft" in str(l.get("label") or "").lower() or "outlook" in str(l.get("label") or "").lower()), None)
    return {"kind": "draft", "label": str(pick.get("label") or "Open the draft"), "url": _https(pick["url"])} if pick else {}


def _tile_rows(db_path: Any, hidden: set[str]) -> dict[str, list[dict[str, Any]]]:
    from onboarding import pipeline as pl

    keys = [key for key, _n, _t in STEP_TILES]
    clients = [c for c in _caseflow_clients(db_path) if str(c.get("matter_id") or "") not in hidden and not c.get("waiting")]
    mids = [str(c["matter_id"]) for c in clients]
    seen = {(mid, step): (view, checked) for mid, step, view, checked in _seen_views(mids, db_path)}
    modes = pl.effective_modes(mids, db_path=db_path) if mids else {}
    out: dict[str, list[dict[str, Any]]] = {key: [] for key in keys}
    for client in clients:
        mid = str(client["matter_id"])
        mode = modes.get(mid, "manual")
        step = str(client.get("step") or "")
        amend = seen.get((mid, "amend"))
        if amend and _step_waits_on_person(amend[0], mode):
            step = "amend"
        if step in NEW_CLIENT_STEPS:
            step = "email"
        while step in keys[:-1] and (seen.get((mid, step)) or ({}, ""))[0].get("status") in ("not_needed", "done"):
            step = keys[keys.index(step) + 1]
        if step not in out:
            continue
        view, checked = seen.get((mid, step), (None, ""))
        yours = bool(view) and _step_waits_on_person(view, mode)
        age = client.get("age_days")
        new = age is not None and int(age) <= NEW_CLIENT_MAX_DAYS
        if step in PERSON_ONLY_STEPS:
            keep = yours and (step != "ws_sign" or age is None or int(age) <= STEP_5_MAX_AGE_DAYS)
        elif step == "court_pack":
            keep = yours or (view or {}).get("status") == "todo"
        else:
            keep = False
        place = step if keep else ("email" if new else "")
        if not place:
            continue
        portal = _portal_court(mid) if place == "court_email" else ""
        done = len(client.get("done_steps") or [])
        out[place].append(
            {
                "matter_id": mid,
                "client_name": str(client.get("client_name") or ""),
                "step": place,
                "state": "yours" if yours else "flow",
                "line": str((view or {}).get("summary") or client.get("pending") or "")[:240],
                "link": _link_for(place, view, portal) if place == step else {},
                "at_step": {
                    "current": _step_label(str(client.get("step") or step)),
                    "days": client.get("days"),
                    "quiet": bool(client.get("quiet")),
                },
                "checked_utc": checked,
            }
        )
    for rows in out.values():
        rows.sort(key=lambda r: (r["state"] != "yours", -(r["at_step"]["days"] or 0), r["client_name"]))
    return out




def _section(key: str, build: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    try:
        items = build()
        return {"key": key, "title": TITLES[key], "count": len(items), "items": items[:LIMIT], "error": False}
    except Exception as exc:
        log.warning("today board section %s failed: %s", key, type(exc).__name__)
        return {"key": key, "title": TITLES[key], "count": 0, "items": [], "error": True}


def board(*, now: dt.datetime | None = None, db_path: Any = None) -> dict[str, Any]:
    moment = (now or dt.datetime.now(dt.timezone.utc)).astimezone(LONDON)
    today, tomorrow = moment.date(), moment.date() + dt.timedelta(days=1)
    hidden = _hidden(db_path)

    def visible(matter_id: Any) -> bool:
        return str(matter_id or "").strip() not in hidden

    name_cache: dict[str, str] = {}

    def names_for(ids: Iterable[Any]) -> dict[str, str]:
        wanted = [str(i) for i in ids if str(i or "").strip() and str(i) not in name_cache]
        if wanted:
            try:
                name_cache.update(_names(wanted))
            except Exception as exc:
                log.warning("today board names failed: %s", type(exc).__name__)
        return name_cache

    def draft_rows() -> list[dict[str, Any]]:
        rows = [d for d in _drafts() if visible(d["matter_id"]) or not d.get("matter_id")]
        return [
            {
                "matter_id": str(d.get("matter_id") or ""),
                "client_name": str(d.get("client_name") or ""),
                "subject": str(d.get("subject") or ""),
                "created_utc": str(d.get("created_utc") or ""),
                "scheduled_utc": str(d.get("scheduled_utc") or ""),
                "human_touched": bool(d.get("scheduled_utc")),
                "web_link": _https(d.get("web_link")),
            }
            for d in rows
        ]

    cache: dict[str, Any] = {}

    def new_intakes(taken: set[str]) -> list[dict[str, Any]]:
        try:
            stopped = set(_pit_stops(db_path))
            cutoff = (moment.astimezone(dt.timezone.utc) - dt.timedelta(days=NEW_CLIENT_MAX_DAYS)).isoformat().replace("+00:00", "Z")
            fresh = [
                i for i in _intake(db_path)
                if str(i.get("matter_id") or "") not in hidden and str(i.get("matter_id") or "") not in taken
                and str(i.get("matter_id") or "") not in stopped and str(i.get("created_utc") or "") >= cutoff
            ]
        except Exception as exc:
            log.warning("today board intake failed: %s", type(exc).__name__)
            return []
        return [
            {
                "matter_id": str(i.get("matter_id") or ""),
                "client_name": str(i.get("client_name") or ""),
                "step": "email",
                "state": "flow",
                "line": "New client.",
                "link": {},
                "at_step": {"current": _step_label("record"), "days": None, "quiet": False},
                "checked_utc": str(i.get("created_utc") or ""),
            }
            for i in fresh
        ]

    def tiles() -> dict[str, list[dict[str, Any]]]:
        if "tiles" not in cache:
            rows = _tile_rows(db_path, hidden)
            cache["tiles"] = {k: [r for r in v if visible(r["matter_id"])] for k, v in rows.items()}
            taken = {str(r["matter_id"]) for v in cache["tiles"].values() for r in v}
            cache["tiles"]["email"] = cache["tiles"].get("email", []) + new_intakes(taken)
        return cache["tiles"]

    def unheld_drafts() -> list[dict[str, Any]]:
        held_links = {r["link"]["url"] for rows in tiles().values() for r in rows if r.get("link", {}).get("kind") == "draft"}
        return [d for d in draft_rows() if not (d["web_link"] and d["web_link"] in held_links)]

    def reminders() -> list[dict[str, Any]]:
        return [d for d in unheld_drafts() if _CHASER_SUBJECT.search(d["subject"])]

    def drafts() -> list[dict[str, Any]]:
        return [d for d in unheld_drafts() if not _CHASER_SUBJECT.search(d["subject"])]

    def tile_builder(step_key: str) -> Callable[[], list[dict[str, Any]]]:
        return lambda: tiles().get(step_key, [])

    def pit_stops(state: str) -> Callable[[], list[dict[str, Any]]]:
        def build() -> list[dict[str, Any]]:
            from onboarding.pipeline import waiting as pit

            states = _pit_stops(db_path)
            mids = [mid for mid in sorted(states) if visible(mid) and states[mid] == state]
            names = names_for(mids)
            return sorted(
                ({"matter_id": mid, "client_name": names.get(mid, ""), "state": state, "label": pit.label(state)} for mid in mids),
                key=lambda r: r["client_name"],
            )

        return build

    builders = {
        "reminders": reminders, "drafts": drafts,
        "waiting_client": pit_stops("client"), "waiting_court": pit_stops("court"), "waiting_counsel": pit_stops("counsel"),
    }
    builders.update({f"step_{number}": tile_builder(key) for key, number, _title in STEP_TILES})
    sections = [_section(key, builders[key]) for key in ORDER]
    return {
        "today": today.isoformat(),
        "tomorrow": tomorrow.isoformat(),
        "sections": sections,
        "not_tracked": ["Court replies overdue are not tracked yet (gh#343)."],
    }


def _text(result: dict[str, Any], section: str = "") -> str:
    lines = [f"Today board, {result['today']}"]
    for sec in result["sections"]:
        if section and sec["key"] != section:
            continue
        lines.append(f"\n{sec['title']}: {sec['count']}" + (f"  [error: {sec['error']}]" if sec.get("error") else ""))
        for item in sec["items"]:
            lines.append("  " + " · ".join(str(v) for k, v in item.items() if v not in ("", None) and k not in ("web_link", "link", "progress"))[:240])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="vergil.today_board", description="Read the Today board, or correct a wrong hearing marker.")
    sub = parser.add_subparsers(dest="command", required=True)
    read = sub.add_parser("read", help="print the board")
    read.add_argument("--section", choices=ORDER, default="")
    read.add_argument("--json", action="store_true")
    over = sub.add_parser("override", help="correct a hearing line (shown on the board with your reason)")
    over.add_argument("hearing_id")
    over.add_argument("field", choices=board_overrides.FIELDS)
    over.add_argument("value", choices=("yes", "no"))
    over.add_argument("--reason", required=True)
    over.add_argument("--by", required=True)
    over.add_argument("--matter", default="")
    over.add_argument("--days", type=int, default=board_overrides.DEFAULT_DAYS)
    sub.add_parser("overrides", help="list the active corrections")
    clear = sub.add_parser("clear", help="remove a correction so the line reads from the evidence again")
    clear.add_argument("--id", default="")
    clear.add_argument("--hearing", default="")
    args = parser.parse_args(argv)
    if args.command == "read":
        result = board()
        if args.section:
            result = {**result, "sections": [s for s in result["sections"] if s["key"] == args.section]}
        print(json.dumps(result, indent=2, default=str) if args.json else _text(result, args.section))
    elif args.command == "override":
        override_id = board_overrides.add(args.hearing_id, args.field, args.value == "yes", args.reason, args.by, matter_id=args.matter, days=args.days)
        print(f"override {override_id} recorded: hearing {args.hearing_id} {args.field} = {args.value}")
    elif args.command == "overrides":
        for (hearing, field), fix in sorted(board_overrides.active().items()):
            print(f"{fix['id']}  hearing {hearing} {field} = {'yes' if fix['value'] else 'no'}  by {fix['by']}  until {fix['expires_utc']}  {fix['reason']}")
    else:
        try:
            print(f"removed {board_overrides.remove(args.id, hearing_id=args.hearing)}")
        except ValueError as exc:
            parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
