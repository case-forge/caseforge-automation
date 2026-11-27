#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import threading
from pathlib import Path
from typing import Any

DIR_ENV = "CASEFORGE_MAIL_REVIEW_DIR"
DEFAULT_DIR = "/mnt/encrypted-data/eval/mail-classifier"
DEFAULT_EXPIRY = "2026-11-13T12:34:00Z"
EXTEND_DAYS = (7, 30)
TEXT_LIMIT = 5000
MATTER_LIMIT = 300

_LOCK = threading.Lock()


class MailReviewError(ValueError):
    pass


class MailReviewClosed(MailReviewError):
    pass


def data_dir() -> Path:
    return Path(os.environ.get(DIR_ENV, "").strip() or DEFAULT_DIR)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: str) -> dt.datetime:
    moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def load_sheet(directory: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    with open((directory or data_dir()) / "sheet.json", encoding="utf-8") as fh:
        sheet = json.load(fh)
    return list(sheet.get("items") or []), [str(r) for r in sheet.get("routes") or []]


def latest_answers(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    path = (directory or data_dir()) / "labels.jsonl"
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
                latest[row["job_id"]] = row
            except Exception:
                continue
    return latest


def expiry(directory: Path | None = None) -> dict[str, Any]:
    path = (directory or data_dir()) / "review_state.json"
    state: dict[str, Any] = {}
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    expires = str(state.get("expires_utc") or DEFAULT_EXPIRY)
    return {"expires_utc": expires, "expired": _now() >= _parse(expires), "extensions": list(state.get("extensions") or [])}


def extend(days: int, by: str, *, directory: Path | None = None) -> dict[str, Any]:
    if days not in EXTEND_DAYS:
        raise MailReviewError("Extend by 7 or 30 days.")
    who = " ".join(str(by or "").split())[:60]
    if not who:
        raise MailReviewError("Type your name first.")
    folder = directory or data_dir()
    with _LOCK:
        current = expiry(folder)
        base = max(_parse(current["expires_utc"]), _now())
        new = _iso(base + dt.timedelta(days=days))
        state = {
            "expires_utc": new,
            "extensions": [*current["extensions"], {"days": days, "by": who, "at": _iso(_now()), "expires_utc": new}],
        }
        path = folder / "review_state.json"
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    return expiry(folder)


def _brief(item: dict[str, Any], answer: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "n": item["n"],
        "done": answer is not None,
        "route": (answer or {}).get("route", ""),
        "no_clean_answer": bool((answer or {}).get("no_clean_answer")),
    }


def overview(directory: Path | None = None) -> dict[str, Any]:
    items, routes = load_sheet(directory)
    latest = latest_answers(directory)
    rows = [_brief(it, latest.get(it["job_id"])) for it in items]
    counts = {route: 0 for route in routes}
    no_clean = 0
    for row in rows:
        if row["done"] and row["route"] in counts:
            counts[row["route"]] += 1
        elif row["done"] and row["no_clean_answer"]:
            no_clean += 1
    first = next((row["n"] for row in rows if not row["done"]), None)
    return {
        "total": len(items),
        "answered": sum(1 for row in rows if row["done"]),
        "routes": routes,
        "counts": counts,
        "no_clean_answer": no_clean,
        "first_unanswered": first,
        "items": rows,
        **expiry(directory),
    }


def _safe_link(value: Any) -> str:
    link = str(value or "")
    return link if link.startswith("https://") else ""


def item(n: int, directory: Path | None = None) -> dict[str, Any]:
    items, routes = load_sheet(directory)
    if not 1 <= int(n) <= len(items):
        raise MailReviewError("No such item.")
    it = items[int(n) - 1]
    answer = latest_answers(directory).get(it["job_id"])
    return {
        "n": it["n"],
        "total": len(items),
        "from": str(it.get("from") or ""),
        "to": str(it.get("to") or ""),
        "cc": str(it.get("cc") or ""),
        "date": str(it.get("date") or ""),
        "subject": str(it.get("subject") or ""),
        "attachments": [str(a) for a in it.get("attachments") or []],
        "text": str(it.get("text") or ""),
        "weblink": _safe_link(it.get("weblink")),
        "routes": routes,
        "answer": answer,
        **expiry(directory),
    }


def save(n: int, fields: dict[str, Any], *, directory: Path | None = None, by: str = "") -> dict[str, Any]:
    folder = directory or data_dir()
    if expiry(folder)["expired"]:
        raise MailReviewClosed("This sheet has expired and is read only. Extend it to go on.")
    items, routes = load_sheet(folder)
    if not 1 <= int(n) <= len(items):
        raise MailReviewError("No such item.")

    def g(key: str) -> str:
        return str(fields.get(key) or "").strip()[:TEXT_LIMIT]

    route = g("route") if g("route") in routes else ""
    also = g("also") if g("also") in routes else ""
    record = {
        "job_id": items[int(n) - 1]["job_id"],
        "n": int(n),
        "route": route,
        "also": also,
        "no_clean_answer": bool(fields.get("no_clean_answer")),
        "matter": g("matter")[:MATTER_LIMIT],
        "logic": g("logic"),
        "saved_utc": _now().isoformat(),
        **({"by": by.strip()[:120]} if by.strip() else {}),
    }
    if not (route or record["no_clean_answer"] or record["logic"]):
        raise MailReviewError("Choose a route, tick no clean answer, or write your logic.")
    path = folder / "labels.jsonl"
    with _LOCK:
        old_umask = os.umask(0o077)
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                fh.write(json.dumps(record) + "\n")
                fh.flush()
                fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            os.umask(old_umask)
        os.chmod(path, 0o600)
    return record



def _qc(fn, *args, **kwargs):
    from vergil import mail_qc

    try:
        return fn(*args, **kwargs)
    except mail_qc.QcError as exc:
        raise MailReviewError(str(exc)) from exc


def decide(offset: int = 0) -> dict[str, Any]:
    from vergil import mail_qc

    return _qc(mail_qc.decide_view, offset)


def decide_save(job_id: str, fields: dict[str, Any], by: str = "") -> dict[str, Any]:
    from vergil import mail_qc

    record = _qc(
        mail_qc.decide_answer,
        job_id,
        route=str(fields.get("route") or "").strip(),
        also=str(fields.get("also") or "").strip(),
        logic=str(fields.get("logic") or ""),
        by=by,
        other_text=str(fields.get("other_text") or ""),
    )
    return {"saved": True, "job_id": record["job_id"], "route": record["route"], "verdict": record["verdict"], "event_recorded": record["event_recorded"]}


def control(n: int | None = None, date: str | None = None, claimant: str | None = None, pool: str | None = None) -> dict[str, Any]:
    from vergil import mail_qc

    return _qc(mail_qc.control_view, date, n=n, claimant=claimant, pool=pool)


def control_release(job_id: str, claimant: str) -> dict[str, Any]:
    from vergil import mail_qc

    return {"released": mail_qc.release_control_claim(job_id, claimant)}


def control_save(date: str, job_id: str, fields: dict[str, Any], claimant: str | None = None) -> dict[str, Any]:
    from vergil import mail_qc

    record = _qc(
        mail_qc.control_answer,
        date,
        job_id,
        verdict=str(fields.get("verdict") or ""),
        route=str(fields.get("route") or "").strip(),
        also=str(fields.get("also") or "").strip(),
        logic=str(fields.get("logic") or ""),
        claimant=claimant,
        other_text=str(fields.get("other_text") or ""),
    )
    out = {"saved": True, "job_id": record["job_id"], "verdict": record["verdict"], "route": record["route"]}
    if record["verdict"] == "agree":
        from vergil import mail_agree_save

        out["filing"] = mail_agree_save.save(
            record["job_id"], str(record.get("applied_route") or record["route"]),
            by=str(record.get("by") or claimant or ""), note=str(record.get("logic") or ""),
        )
    return out
