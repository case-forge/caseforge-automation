#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import email
import email.policy
import fcntl
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any, Iterable

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from mail_blocked_reasons import blocked_reason_label, veto_kind
from mail_intake import destinations

DIR_ENV = "CASEFORGE_MAIL_REVIEW_DIR"
DEFAULT_DIR = "/mnt/encrypted-data/eval/mail-classifier"
DB_ENV = "CASEFORGE_MAIL_QC_DB"
CAPTURE_ENV = "CASEFORGE_MAIL_QC_CAPTURE_ROOT"


def _int_setting(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "").strip() or default))
    except ValueError:
        return default


def _float_setting(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


REVIEW_PER_DAY = _int_setting("CASEFORGE_MAIL_QC_REVIEW_PER_DAY", 8)
CONTROL_PER_DAY = _int_setting("CASEFORGE_MAIL_QC_CONTROL_PER_DAY", 4)
MIN_VETO_UNRESOLVED = _int_setting("CASEFORGE_MAIL_QC_MIN_VETO_UNRESOLVED", 2)
MIN_MODEL_OVERRODE = _int_setting("CASEFORGE_MAIL_QC_MIN_MODEL_OVERRODE", 2)
LOW_CONF = _float_setting("CASEFORGE_MAIL_QC_LOW_CONF", 0.6)
CONTROL_MIN_CONF = _float_setting("CASEFORGE_MAIL_QC_CONTROL_MIN_CONF", 0.85)
POOL_DAYS = _int_setting("CASEFORGE_MAIL_QC_POOL_DAYS", 30)

INTERNAL_MAIL_REASONS = frozenset({"internal_firm_mail_no_action"})
POOL_REVIEW = "review"
POOL_CONTROL = "control"
POOL_DECIDE = "decide"

STRATUM_VETO = "veto"
STRATUM_UNRESOLVED = "unresolved"
STRATUM_MODEL_OVERRODE = "model_overrode_rules"
STRATUM_OTHER = "other"

UNDECIDED_ROUTES = frozenset({"Review"})
FALLBACK_ROUTES = destinations.DESTINATIONS

TEXT_LIMIT = 5000
BODY_LIMIT = 20000
_LOCK = threading.Lock()
_AGREE = "agree"


class QcError(ValueError):
    pass



def data_dir() -> Path:
    return Path(os.environ.get(DIR_ENV, "").strip() or DEFAULT_DIR)


def qc_dir(directory: Path | None = None) -> Path:
    return (directory or data_dir()) / "qc"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_moment(value: Any) -> dt.datetime | None:
    try:
        moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def seed_for(date: str, pool: str) -> int:
    return int(hashlib.sha256(f"{date}|{pool}".encode()).hexdigest(), 16)


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def is_undecided(route: str) -> bool:
    return route in UNDECIDED_ROUTES or not route


def verdict_for(applied_route: str, route: str, no_clean_answer: bool) -> str:
    if no_clean_answer or not route:
        return "no_clean_answer"
    if is_undecided(applied_route):
        return "undecided"
    return _AGREE if destinations.same_destination(route, applied_route) else "disagree"


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def stratum_of(rec: dict[str, Any]) -> str:
    source = str(rec.get("route_source") or "")
    applied = str(rec.get("applied_route") or "")
    conf = rec.get("applied_conf")
    if rec.get("veto") or source.startswith("deterministic_ai"):
        return STRATUM_VETO
    if is_undecided(applied) or "unsorted" in applied.lower() or (conf is not None and conf < LOW_CONF):
        return STRATUM_UNRESOLVED
    if source.startswith("ai") and rec.get("model_route") and rec["model_route"] != rec.get("rules_route"):
        return STRATUM_MODEL_OVERRODE
    return STRATUM_OTHER



def _db_path() -> Path:
    override = os.environ.get(DB_ENV, "").strip()
    if override:
        return Path(override)
    from vergil.background_jobs import agent_queue_module

    return agent_queue_module().resolve_db_path()


def _record_from_state(job_id: str, status: str, created: str, state: dict[str, Any]) -> dict[str, Any]:
    routing = state.get("routing") or {}
    applied = routing.get("applied_route") or state.get("deterministic") or {}
    initial = routing.get("initial_deterministic") or state.get("deterministic") or {}
    ai = state.get("ai") if isinstance(state.get("ai"), dict) else {}
    ai_ok = bool(ai) and not ai.get("model_unavailable") and ai.get("reason") != "ai_failed"
    reasons = [str(r) for r in (applied.get("reasons") or [])]
    reco = state.get("recommendation") or {}
    capture = state.get("raw_capture") or {}
    return {
        "job_id": job_id,
        "status": status,
        "created_utc": created,
        "applied_route": str(applied.get("route") or ""),
        "applied_conf": _float(applied.get("confidence")),
        "route_source": str(routing.get("route_source") or ""),
        "other_text": str(routing.get("other_text") or ""),
        "model_route": str(ai.get("route") or "") if ai_ok else "",
        "model_conf": _float(ai.get("confidence")) if ai_ok else None,
        "rules_route": str(initial.get("route") or ""),
        "veto": veto_kind(reasons),
        "review_reason": str(reco.get("manual_review_reason") or ""),
        "processed_reason": str(reco.get("processed_reason") or ""),
        "action": str(reco.get("action") or ""),
        "eml_path": str(capture.get("eml_path") or ""),
        "json_path": str(capture.get("json_path") or ""),
    }


def load_candidates(db_path: Path | None = None, *, now: dt.datetime | None = None, days: int | None = None) -> list[dict[str, Any]]:
    path = db_path or _db_path()
    if not Path(path).exists():
        raise FileNotFoundError(str(path))
    since = _iso((now or _now()) - dt.timedelta(days=POOL_DAYS if days is None else days))
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        rows = conn.execute(
            "SELECT job_id, status, created_utc, state_json FROM agent_jobs "
            "WHERE job_type = 'mail-intake' AND status IN ('blocked', 'done') AND created_utc >= ? ORDER BY created_utc, job_id",
            (since,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for job_id, status, created, state_json in rows:
        try:
            state = json.loads(state_json or "{}")
        except ValueError:
            continue
        if isinstance(state, dict) and state.get("routing"):
            out.append(_record_from_state(str(job_id), str(status), str(created or ""), state))
    return out


def human_resolved_ids(db_path: Path | None = None) -> set[str]:
    path = db_path or _db_path()
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        return {str(r[0]) for r in conn.execute("SELECT job_id FROM agent_job_events WHERE event_type = 'human_resolved'")}
    except sqlite3.Error:
        return set()
    finally:
        conn.close()


def needs_decision(rec: dict[str, Any]) -> bool:
    if rec["status"] != "blocked":
        return False
    if stratum_of(rec) in (STRATUM_VETO, STRATUM_UNRESOLVED):
        return True
    return rec.get("review_reason") in ("route_uncertain", "counsel_relationship_uncertain")


def split_pools(candidates: Iterable[dict[str, Any]], reviewed: set[str]) -> dict[str, list[dict[str, Any]]]:
    pools: dict[str, list[dict[str, Any]]] = {POOL_DECIDE: [], POOL_REVIEW: [], POOL_CONTROL: []}
    for rec in sorted(candidates, key=lambda r: (r["created_utc"], r["job_id"])):
        if rec["job_id"] in reviewed or rec.get("processed_reason") in INTERNAL_MAIL_REASONS:
            continue
        stratum = stratum_of(rec)
        rec = {**rec, "stratum": stratum}
        if needs_decision(rec):
            pools[POOL_DECIDE].append(rec)
        elif stratum != STRATUM_OTHER and not is_undecided(rec["applied_route"]):
            pools[POOL_REVIEW].append(rec)
        elif (
            stratum == STRATUM_OTHER
            and rec["status"] == "done"
            and rec["applied_conf"] is not None
            and rec["applied_conf"] >= CONTROL_MIN_CONF
        ):
            pools[POOL_CONTROL].append(rec)
    return pools


def draw(date: str, pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    review = sorted(pools.get(POOL_REVIEW, []), key=lambda r: r["job_id"])
    random.Random(seed_for(date, POOL_REVIEW)).shuffle(review)
    chosen: list[dict[str, Any]] = []
    taken: set[str] = set()

    def take(rows: Iterable[dict[str, Any]], limit: int) -> None:
        for rec in rows:
            if limit <= 0 or len(chosen) >= REVIEW_PER_DAY:
                return
            if rec["job_id"] not in taken:
                taken.add(rec["job_id"])
                chosen.append(rec)
                limit -= 1

    take([r for r in review if r["stratum"] in (STRATUM_VETO, STRATUM_UNRESOLVED)], MIN_VETO_UNRESOLVED)
    take([r for r in review if r["stratum"] == STRATUM_MODEL_OVERRODE], MIN_MODEL_OVERRODE)
    take(review, REVIEW_PER_DAY)
    control = sorted(pools.get(POOL_CONTROL, []), key=lambda r: r["job_id"])
    random.Random(seed_for(date, POOL_CONTROL)).shuffle(control)
    batch = [{**r, "pool": POOL_REVIEW} for r in chosen] + [{**r, "pool": POOL_CONTROL} for r in control[:CONTROL_PER_DAY]]
    batch.sort(key=lambda r: r["job_id"])
    random.Random(seed_for(date, "batch")).shuffle(batch)
    return batch



def _capture_root() -> Path:
    override = os.environ.get(CAPTURE_ENV, "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "artifacts" / "mail-intake" / "raw-capture"


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


_TAGS = re.compile(r"<[^>]*>")


def read_email(rec: dict[str, Any]) -> dict[str, Any]:
    blank = {"from": "", "to": "", "cc": "", "date": "", "subject": "(email not available)", "attachments": [], "text": "", "weblink": ""}
    root = _capture_root()
    eml = Path(rec.get("eml_path") or "")
    if not rec.get("eml_path") or not eml.is_file() or not _under(eml, root):
        return blank
    try:
        msg = email.message_from_bytes(eml.read_bytes(), policy=email.policy.default)
        body = msg.get_body(preferencelist=("plain", "html"))
        text = body.get_content() if body is not None else ""
        if body is not None and body.get_content_type() == "text/html":
            text = re.sub(r"\s*\n\s*\n+", "\n\n", _TAGS.sub(" ", str(text)))
        names = [str(p.get_filename() or "") for p in msg.iter_attachments()]
        out = {
            "from": str(msg.get("From") or ""), "to": str(msg.get("To") or ""), "cc": str(msg.get("Cc") or ""),
            "date": str(msg.get("Date") or ""), "subject": str(msg.get("Subject") or ""),
            "attachments": [n for n in names if n], "text": str(text)[:BODY_LIMIT], "weblink": "",
        }
    except Exception:
        return blank
    sidecar = Path(rec.get("json_path") or "")
    if rec.get("json_path") and sidecar.is_file() and _under(sidecar, root):
        try:
            link = str((json.loads(sidecar.read_text(encoding="utf-8")).get("message") or {}).get("webLink") or "")
            out["weblink"] = link if link.startswith("https://") else ""
        except Exception:
            pass
    return out


def build_item(rec: dict[str, Any], n: int) -> dict[str, Any]:
    return {
        "n": n,
        "job_id": rec["job_id"],
        **read_email(rec),
        "pool": rec.get("pool", ""),
        "applied_route": rec["applied_route"],
        "applied_destination": destinations.destination_label(rec["applied_route"]),
        "applied_other_text": str(rec.get("other_text") or destinations.destination_for_route(rec["applied_route"])[1]),
        "route_source": rec["route_source"],
        "stratum": rec.get("stratum") or stratum_of(rec),
        "model_route": rec["model_route"],
        "model_conf": rec["model_conf"],
        "rules_route": rec["rules_route"],
        "reason": blocked_reason_label(rec.get("review_reason")),
        "created_utc": rec["created_utc"],
    }



def latest_labels(directory: Path | None = None) -> dict[str, dict[str, Any]]:
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


def gold_labels(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    return {job: row for job, row in latest_labels(directory).items() if row.get("route")}


def _append_label(directory: Path, record: dict[str, Any]) -> None:
    path = directory / "labels.jsonl"
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


def _label_record(
    item: dict[str, Any], *, route: str, also: str, no_clean: bool, logic: str, date: str, pool: str, by: str = "",
    other_text: str = "",
) -> dict[str, Any]:
    typed = destinations.clean_other_text(other_text) if route == destinations.OTHER else ""
    return {
        **({"other_text": typed} if typed else {}),
        "job_id": item["job_id"],
        "n": int(item.get("n") or 0),
        "route": route,
        "also": also,
        "no_clean_answer": bool(no_clean),
        "matter": "",
        "logic": logic.strip()[:TEXT_LIMIT],
        "saved_utc": _now().isoformat(),
        "qc_date": date,
        "pool": pool,
        "verdict": verdict_for(item["applied_route"], route, no_clean),
        "applied_route": item["applied_route"],
        "route_source": item["route_source"],
        "model_route": item["model_route"],
        "model_conf": item["model_conf"],
        "rules_route": item["rules_route"],
        **({"by": by.strip()[:120]} if by.strip() else {}),
    }


def sheet_routes(directory: Path | None = None) -> list[str]:
    return list(destinations.DESTINATIONS)



def today_utc() -> str:
    return _now().date().isoformat()


def _check_date(date: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        raise QcError("That is not a date.")
    return date


def day_path(date: str, directory: Path | None = None) -> Path:
    return qc_dir(directory) / f"{_check_date(date)}.json"


def _write_private(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    old_umask = os.umask(0o077)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1)
    finally:
        os.umask(old_umask)
    os.replace(tmp, path)


def reviewed_ids(directory: Path | None = None) -> set[str]:
    return set(latest_labels(directory))


def ensure_day(date: str, *, directory: Path | None = None, db_path: Path | None = None) -> dict[str, Any]:
    folder = directory or data_dir()
    path = day_path(date, folder)
    with _LOCK:
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        reviewed = reviewed_ids(folder) | human_resolved_ids(db_path)
        pools = split_pools(load_candidates(db_path), reviewed)
        batch = draw(date, pools)
        sizes = {name: len(rows) for name, rows in pools.items()}
        payload = {
            "date": date,
            "generated_utc": _iso(_now()),
            "settings": {"review_per_day": REVIEW_PER_DAY, "control_per_day": CONTROL_PER_DAY},
            "pool_sizes": sizes,
            "routes": sheet_routes(folder),
            "items": [build_item(rec, i + 1) for i, rec in enumerate(batch)],
        }
        _write_private(path, payload)
        return payload


def _brief(item: dict[str, Any], labels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = labels.get(item["job_id"])
    return {"n": item["n"], "done": row is not None, "verdict": (row or {}).get("verdict", "")}


CLAIM_MINUTES = 30


def _claims_path(directory: Path) -> Path:
    return qc_dir(directory) / "claims.json"


def _read_claims(directory: Path) -> dict[str, dict[str, str]]:
    try:
        with open(_claims_path(directory), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _live_claims(directory: Path, now: dt.datetime) -> dict[str, dict[str, str]]:
    live: dict[str, dict[str, str]] = {}
    for job, row in _read_claims(directory).items():
        if row.get("answered_by"):
            live[job] = row
            continue
        until = parse_moment(row.get("until"))
        if until is not None and until > now and row.get("by"):
            live[job] = row
    return live


def _held_by_other(row: dict[str, str] | None, who: str) -> bool:
    if not row:
        return False
    holder = row.get("answered_by") or row.get("by") or ""
    return bool(holder) and holder != who


def _write_claims(directory: Path, claims: dict[str, dict[str, str]]) -> None:
    _write_private(_claims_path(directory), claims)


def release_control_claim(job_id: str, who: str, *, directory: Path | None = None) -> bool:
    folder = directory or data_dir()
    with _LOCK:
        claims = _read_claims(folder)
        row = claims.get(job_id)
        if not row or row.get("answered_by") or row.get("by") != who:
            return False
        del claims[job_id]
        _write_claims(folder, claims)
        return True


def control_view(
    date: str | None = None, *, n: int | None = None, directory: Path | None = None, db_path: Path | None = None,
    claimant: str | None = None, pool: str | None = None,
) -> dict[str, Any]:
    folder = directory or data_dir()
    day = date or today_utc()
    payload = ensure_day(day, directory=folder, db_path=db_path)
    labels = latest_labels(folder)
    if pool is not None and pool not in (POOL_CONTROL, POOL_REVIEW):
        raise QcError("pool must be control or review.")
    items = [it for it in payload["items"] if pool is None or it.get("pool") == pool]
    rows = [_brief(it, labels) for it in items]
    now = _now()
    who = (claimant or "").strip()
    held = _live_claims(folder, now) if who else {}
    if n is None:
        free = [it for it, row in zip(items, rows) if not row["done"] and not _held_by_other(held.get(it["job_id"]), who)]
        pick = next((it for it in free if who and held.get(it["job_id"], {}).get("by") == who), free[0] if free else None)
    else:
        pick = next((it for it in items if it["n"] == int(n)), None)
        if pick is None:
            raise QcError("No such item.")
        if _held_by_other(held.get(pick["job_id"]), who):
            raise QcError("Someone else is looking at that email.")
    if pick is not None and who and n is None:
        with _LOCK:
            claims = _live_claims(folder, now)
            if _held_by_other(claims.get(pick["job_id"]), who):
                pick = None
            else:
                claims[pick["job_id"]] = {"by": who, "until": _iso(now + dt.timedelta(minutes=CLAIM_MINUTES))}
                _write_claims(folder, claims)
    return {
        "date": day,
        "total": len(items),
        "answered": sum(1 for row in rows if row["done"]),
        "pool_sizes": payload.get("pool_sizes", {}),
        "routes": sheet_routes(folder),
        "items": rows,
        "item": _public_item(pick, labels) if pick else None,
    }


def _public_item(item: dict[str, Any], labels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = dict(item)
    row = labels.get(item["job_id"])
    out["answer"] = row
    return out


def control_answer(
    date: str, job_id: str, *, verdict: str, route: str = "", also: str = "", logic: str = "",
    directory: Path | None = None, claimant: str | None = None, other_text: str = "",
) -> dict[str, Any]:
    folder = directory or data_dir()
    payload = ensure_day(date, directory=folder)
    item = next((it for it in payload["items"] if it["job_id"] == job_id), None)
    if item is None:
        raise QcError("That email is not in this day's control batch.")
    who = (claimant or "").strip()
    if who and _held_by_other(_live_claims(folder, _now()).get(job_id), who):
        raise QcError("Someone else has this email.")
    routes = sheet_routes(folder)
    if verdict == _AGREE:
        if is_undecided(item["applied_route"]):
            raise QcError("The classifier gave no route here: choose the right one.")
        chosen, no_clean = item["applied_route"], False
    elif verdict == "disagree":
        if route not in routes:
            raise QcError("Choose the right route.")
        if route == destinations.OTHER and not destinations.clean_other_text(other_text):
            raise QcError("Type where Other goes.")
        chosen, no_clean = route, False
    else:
        raise QcError("Agree or disagree.")
    other = also if also in routes else ""
    record = _label_record(
        item, route=chosen, also=other, no_clean=no_clean, logic=logic, date=date, pool=item["pool"], by=who,
        other_text=other_text,
    )
    if verdict == "disagree" and record["verdict"] == _AGREE:
        raise QcError("That is the classifier's own route: choose Agree, or pick a different one.")
    _append_label(folder, record)
    if who:
        with _LOCK:
            claims = _read_claims(folder)
            claims[job_id] = {"answered_by": who}
            _write_claims(folder, claims)
    return record



def decision_queue(db_path: Path | None = None, directory: Path | None = None) -> list[dict[str, Any]]:
    reviewed = reviewed_ids(directory) | human_resolved_ids(db_path)
    return split_pools(load_candidates(db_path), reviewed)[POOL_DECIDE]


def decide_view(offset: int = 0, *, directory: Path | None = None, db_path: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    queue = decision_queue(db_path, directory)
    moment = now or _now()
    oldest = parse_moment(queue[0]["created_utc"]) if queue else None
    item = None
    if queue:
        index = max(0, int(offset)) % len(queue)
        item = {**build_item(queue[index], index + 1), "total": len(queue)}
        item["pool"] = POOL_DECIDE
    return {
        "total": len(queue),
        "oldest_days": round((moment - oldest).total_seconds() / 86400, 1) if oldest else 0,
        "routes": sheet_routes(directory),
        "item": item,
        "recent": recent_decisions(directory, db_path),
    }


RECENT_DECISIONS = 5


def recent_decisions(directory: Path | None = None, db_path: Path | None = None, limit: int = RECENT_DECISIONS) -> list[dict[str, Any]]:
    labels = [r for r in latest_labels(directory or data_dir()).values() if r.get("pool") == POOL_DECIDE and (r.get("route") or r.get("no_clean_answer"))]
    labels.sort(key=lambda r: str(r.get("saved_utc") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    try:
        from mail_intake import human_decision
    except Exception:
        return out
    for row in labels[: max(0, int(limit))]:
        entry = {"route": str(row.get("route") or ""), "saved_utc": str(row.get("saved_utc") or ""), "by": str(row.get("by") or ""), "state": "waiting", "plain": "Waiting for the mail worker (about a minute)."}
        if not entry["route"]:
            entry.update(state="no_route", plain="No clean answer: nothing to apply.")
        else:
            try:
                decision = human_decision.latest_decision(str(row.get("job_id")), db_path=db_path)
            except Exception:
                decision = None
            if decision is not None and decision.applied:
                entry.update(state=decision.outcome or "applied", plain=decision.plain or "Applied.")
        out.append(entry)
    return out


def _record_resolution_event(job_id: str, record: dict[str, Any], db_path: Path | None) -> bool:
    try:
        from vergil.background_jobs import agent_queue_module

        agent_queue_module().record_event(
            job_id,
            "human_resolved",
            "A person chose the route in the CRM (Improve mail classifier). The mail worker applies it.",
            {
                "route": record["route"], "also": record["also"], "no_clean_answer": record["no_clean_answer"],
                **({"other_text": record["other_text"]} if record.get("other_text") else {}),
                "classifier_route": record["applied_route"], "route_source": record["route_source"],
                "verdict": record["verdict"], "applied": False,
                **({"by": record["by"]} if record.get("by") else {}),
                **({"note": " ".join(str(record["logic"]).split())[:300]} if record.get("logic") else {}),
            },
            db_path=db_path,
        )
        return True
    except Exception:
        return False


def decide_answer(
    job_id: str, *, route: str = "", also: str = "", logic: str = "",
    directory: Path | None = None, db_path: Path | None = None, by: str = "", other_text: str = "",
) -> dict[str, Any]:
    folder = directory or data_dir()
    queue = decision_queue(db_path, folder)
    rec = next((r for r in queue if r["job_id"] == job_id), None)
    if rec is None:
        raise QcError("That email is not waiting for a decision.")
    routes = sheet_routes(folder)
    if route and route not in routes:
        raise QcError("Choose one of the routes.")
    if not route:
        raise QcError("Choose where it goes.")
    if route == destinations.OTHER and not destinations.clean_other_text(other_text):
        raise QcError("Type where Other goes.")
    item = build_item({**rec, "pool": POOL_DECIDE}, 0)
    record = _label_record(
        item, route=route, also=also if also in routes else "", no_clean=False, logic=logic,
        date=today_utc(), pool=POOL_DECIDE, by=by, other_text=other_text,
    )
    _append_label(folder, record)
    record["event_recorded"] = _record_resolution_event(job_id, record, db_path)
    return record
