
from __future__ import annotations

import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable

from scanned_docs import intake_facts

CALLER = "scanned_docs.scan_resolver"
MAX_PAGES = 3
MAX_CANDIDATES = 5
POINTS = {"surname_in_name": 30, "reference": 45, "full_name": 25, "surname_in_text": 10, "party": 8, "hearing_date": 15}
PARTY_CAP = 16
AMBIGUOUS_GAP = 15
HIGH, MEDIUM = 80, 50

COURT_REF_RE = re.compile(r"\b[A-Z]{1,3}\s*\d{2}\s*[A-Z]\s*\d{5}\b", re.IGNORECASE)
_NUMERIC_DATE_RE = intake_facts.FILENAME_DATE_RE
_WRITTEN_DATE_RE = intake_facts.FILENAME_DATE_WRITTEN_RE
_MIN_REF_LEN = 6

_text_cache: dict[tuple[str, str], str] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 200


def confidence_words(confidence: int) -> str:
    return "High" if confidence >= HIGH else "Medium" if confidence >= MEDIUM else "Low"


def compact(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _words(value: Any) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", str(value or "")) if len(w) > 1]


def _has_word(text_upper: str, word: str) -> bool:
    return bool(re.search(rf"(?<![A-Z]){re.escape(word.upper())}(?![A-Z])", text_upper))


def text_dates(text: str) -> set[str]:
    found: set[str] = set()
    for d, mo, y in _NUMERIC_DATE_RE.findall(text):
        iso = intake_facts._iso(y, int(mo), int(d))
        if iso:
            found.add(iso)
    for d, mon, y in _WRITTEN_DATE_RE.findall(text):
        iso = intake_facts._iso(y, intake_facts._MONTH_NUMBER[mon[:3].lower()], int(d))
        if iso:
            found.add(iso)
    return found


def text_references(text: str) -> list[str]:
    seen: list[str] = []
    for m in COURT_REF_RE.finditer(text):
        ref = compact(m.group(0))
        if ref not in seen:
            seen.append(ref)
    return seen


def matter_references(row: dict[str, Any]) -> list[str]:
    out = []
    for part in str(row.get("reference_summary") or "").split("|"):
        value = compact(part.split(":", 1)[-1])
        if len(value) >= _MIN_REF_LEN and value not in out:
            out.append(value)
    case_ref = compact(row.get("case_reference"))
    if len(case_ref) >= _MIN_REF_LEN and case_ref not in out:
        out.append(case_ref)
    return out


def party_names(row: dict[str, Any]) -> list[str]:
    mine = " ".join(_words(row.get("client_name"))).upper()
    out = []
    for part in str(row.get("party_summary") or "").split("|"):
        name = part.split(":", 1)[-1].strip()
        if len(_words(name)) >= 2 and " ".join(_words(name)).upper() != mine and name not in out:
            out.append(name)
    return out


def _norm(value: Any) -> str:
    return " ".join(re.sub(r"[^A-Z]+", " ", str(value or "").upper()).split())


def _surname_of(row: dict[str, Any]) -> str:
    words = _words(row.get("client_name"))
    return words[-1].upper() if words else ""


def _candidate_view(candidate: dict[str, Any], reasons: list[str], points: int) -> dict[str, Any]:
    row = candidate["row"]
    return {
        "matter_id": str(row.get("matter_id") or ""),
        "client_name": str(row.get("client_name") or row.get("matter_name") or ""),
        "closed": bool(row.get("closed_at")),
        "confidence": min(100, points),
        "reasons": reasons,
        "ambiguous": False,
    }


def score_candidates(
    name: str,
    text: str,
    candidates: Iterable[dict[str, Any]],
    *,
    scan_date: str = "",
    date_source: str = "",
) -> list[dict[str, Any]]:
    surname = intake_facts.filename_surname(name) or ""
    upper = str(text or "").upper()
    refs_in_text = set(text_references(text))
    dates = text_dates(text)
    if scan_date and date_source == "filename":
        dates.add(scan_date)
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        row = cand["row"]
        reasons: list[str] = []
        points = 0
        mine = _surname_of(row)
        if surname and (_norm(surname) == _norm(mine) or _norm(row.get("client_name")).endswith(" " + _norm(surname))):
            points += POINTS["surname_in_name"]
            reasons.append(f"Surname {surname.title()} is in the file name")
        shared = [r for r in matter_references(row) if r in refs_in_text]
        if shared:
            points += POINTS["reference"]
            reasons.append(f"Case number {shared[0]} in the text matches this matter")
        words = _words(row.get("client_name"))
        if upper and len(words) >= 2 and all(_has_word(upper, w) for w in (words[0], words[-1])):
            points += POINTS["full_name"]
            reasons.append("Client's full name is in the text")
        elif upper and mine and _has_word(upper, mine):
            points += POINTS["surname_in_text"]
            reasons.append("Client's surname is in the text")
        named = [p for p in party_names(row) if upper and all(_has_word(upper, w) for w in (_words(p)[0], _words(p)[-1]))]
        if named:
            points += min(PARTY_CAP, POINTS["party"] * len(named))
            reasons.append("Another party's name is in the text")
        hearings = {str(d)[:10] for d in cand.get("hearing_dates") or [] if d}
        match = sorted(dates & hearings)
        if match:
            points += POINTS["hearing_date"]
            reasons.append(f"Date {match[0][8:]}.{match[0][5:7]}.{match[0][2:4]} is a hearing date on this matter")
        view = _candidate_view(cand, reasons, points)
        scored.append(view)
    scored.sort(key=lambda c: (-c["confidence"], int(c["matter_id"] or 0)))
    scored = [c for c in scored if c["confidence"] > 0][:MAX_CANDIDATES]
    if len(scored) >= 2:
        gap = scored[0]["confidence"] - scored[1]["confidence"]
        if gap < AMBIGUOUS_GAP:
            penalty = AMBIGUOUS_GAP - gap
            top, second = scored[0], scored[1]
            top["confidence"] = max(0, top["confidence"] - penalty)
            second["confidence"] = min(second["confidence"], top["confidence"])
            top["ambiguous"] = second["ambiguous"] = True
            top["reasons"].append(f"Close to {second['client_name']} (within {gap} points), so confidence is lowered by {penalty}")
            second["reasons"].append(f"Close to {top['client_name']} (within {gap} points)")
    for c in scored:
        c["words"] = confidence_words(c["confidence"])
    return scored


_ORDER_HEAD_RE = re.compile(r"\bORDER\b")
_NOTICE_RE = re.compile(r"NOTICE OF (?:THE )?(?:HEARING|PROCEEDINGS)|HEARING NOTICE|\bNOH\b")
_COURT_RE = re.compile(r"FAMILY COURT|FAMILY PROCEEDINGS|BEFORE (?:DISTRICT|DEPUTY|HIS|HER|THE)|UPON HEARING|IT IS ORDERED")


def classify_scan(name: str, text: str = "") -> str:
    from documents import virtual_scanner_hints as hints

    found = hints.classify(name)
    if found:
        return found["kind"]
    head = str(text or "")[:800].upper()
    if _NOTICE_RE.search(head):
        return "notice_of_hearing"
    if _ORDER_HEAD_RE.search(head) and _COURT_RE.search(head):
        return "order"
    return "other"




def scan_text(folder: str, name: str, item_key: str = "") -> str:
    if not name.lower().endswith(".pdf"):
        return ""
    key = (item_key or name, "")
    with _cache_lock:
        if key in _text_cache:
            return _text_cache[key]
    import document_ocr
    import graph_files

    text = ""
    try:
        with tempfile.TemporaryDirectory(prefix="scan-resolver-") as tmp:
            out = Path(tmp) / "scan.pdf"
            graph_files.download(f"{folder}/{name}", out)
            text, _used_ocr = document_ocr.read_pdf_text_with_ocr_fallback(out.read_bytes(), max_pages=MAX_PAGES)
    except Exception:
        text = ""
    with _cache_lock:
        if len(_text_cache) >= _CACHE_MAX:
            _text_cache.pop(next(iter(_text_cache)))
        _text_cache[key] = text
    return text


def gather(name: str, text: str) -> list[dict[str, Any]]:
    from agwu import resolve_client

    queries = []
    surname = intake_facts.filename_surname(name)
    if surname:
        queries.append(surname)
    queries.extend(text_references(text)[:3])
    rows: dict[str, dict[str, Any]] = {}
    for q in queries:
        for match in resolve_client(q, limit=6, caller=CALLER).matches:
            rows.setdefault(str(match.row.get("matter_id")), match.row)
    return [{"row": row, "hearing_dates": hearing_dates(row.get("matter_id"))} for row in rows.values()]


def hearing_dates(matter_id: Any) -> list[str]:
    try:
        from hearing_calendar import hearing_store

        from hearing_calendar import hearing_dates as hd

        return [d.isoformat() for h in hearing_store.list_hearings("2000-01-01", "2100-12-31", matter_id=int(matter_id)) for d in (hd.span_days(h) or [])]
    except Exception:
        return []


def resolve_scan(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("name") or "")
    text = scan_text(str(row.get("folder") or ""), name, f"{row.get('id')}|{row.get('modified_utc')}")
    candidates = score_candidates(
        name, text, gather(name, text), scan_date=str(row.get("scan_date") or ""), date_source=str(row.get("date_source") or "")
    )
    return {
        "id": row.get("id") or "",
        "name": name,
        "text_read": bool(text.strip()),
        "kind": classify_scan(name, text),
        "candidates": candidates,
        "label": "An estimate from the file name and the document's text, not checked. Nothing is filed until you confirm.",
    }


def resolve_scans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [resolve_scan(r) for r in rows]


def _row_for_item(item_id: str) -> dict[str, Any]:
    from scanned_docs import scan_rows

    for row in scan_rows.list_scans()["rows"]:
        if row["id"] == str(item_id):
            return row
    raise ScanNotWaiting("That scan is no longer waiting in Scanned Docs. Refresh the list.")


class ScanNotWaiting(ValueError):
    pass


def candidates_for_item(item_id: str) -> dict[str, Any]:
    from documents.virtual_scanner import VirtualScanError

    try:
        return resolve_scan(_row_for_item(item_id))
    except ScanNotWaiting as exc:
        raise VirtualScanError(str(exc)) from exc


MAX_FOR_CLIENT = 10


def court_orders_items(ctx: Any) -> tuple[str, list[dict[str, Any]]]:
    import graph_files

    from onboarding.pipeline import court_common as cc

    try:
        folder = cc.court_orders_folder(ctx) if ctx.folder_path else ""
        if not folder:
            return "", []
        items = graph_files.list_children(folder, access_token=ctx.token()).get("value", [])
    except Exception:
        return "", []
    return folder, [i for i in items if isinstance(i, dict) and "file" in i]


def filed_hashes(ctx: Any) -> set[str]:
    from scanned_docs import scan_rows

    return {h for h in (scan_rows._content_hash(i) for i in court_orders_items(ctx)[1]) if h}



MATCH_KINDS = ("order", "notice_of_hearing")
KIND_WORDS = {"order": "order", "notice_of_hearing": "notice of hearing"}
MAX_FILED_READS = 30


def paper_facts(text: str) -> dict[str, Any]:
    return {"refs": set(text_references(text)), "kind": classify_scan("", text), "dates": text_dates(text)}


def likely_duplicate(scan_text_: str, filed: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    mine = paper_facts(scan_text_)
    if not (mine["refs"] and mine["dates"] and mine["kind"] in MATCH_KINDS):
        return None
    for paper in filed:
        theirs = paper_facts(str(paper.get("text") or ""))
        refs, dates = mine["refs"] & theirs["refs"], mine["dates"] & theirs["dates"]
        if refs and dates and theirs["kind"] == mine["kind"]:
            case_number, day = sorted(refs)[0], sorted(dates)[-1]
            return {
                "name": str(paper.get("name") or ""),
                "web_url": str(paper.get("web_url") or ""),
                "case_number": case_number,
                "kind": mine["kind"],
                "date": day,
                "reason": (f"Looks like {paper.get('name')}, already in Court-Orders: same case number ({case_number}), "
                           f"same type of paper ({KIND_WORDS[mine['kind']]}) and a date in both ({day}). "
                           "Check before filing it; nothing was skipped."),
            }
    return None


def filed_papers(folder: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in [i for i in items if str(i.get("name") or "").lower().endswith(".pdf")][:MAX_FILED_READS]:
        key = f"{folder}/{item.get('name')}|{item.get('id')}|{item.get('lastModifiedDateTime')}"
        out.append({"name": item["name"], "web_url": item.get("webUrl") or "", "text": scan_text(folder, str(item["name"]), key)})
    return out


def candidates_for_client(matter_id: Any) -> dict[str, Any]:
    from scanned_docs import scan_rows

    mid = str(matter_id).strip()
    from documents import virtual_scanner

    ctx = virtual_scanner._context(mid)
    surname = str(ctx.surname or "").upper()
    days = set(hearing_dates(mid))
    folder, items = court_orders_items(ctx)
    filed = {h for h in (scan_rows._content_hash(i) for i in items) if h}
    papers: list[dict[str, Any]] | None = None
    out = []
    for row in scan_rows.list_scans()["rows"]:
        if row.get("content_hash") and row["content_hash"] in filed:
            continue
        by_name = bool(surname) and (intake_facts.filename_surname(row["name"]) or "") == surname
        by_date = row["date_source"] == "filename" and row["scan_date"] in days
        if not (by_name or by_date):
            continue
        resolved = resolve_scan(row)
        if any(c["matter_id"] == mid for c in resolved["candidates"]):
            entry = {**resolved, "scan_date": row["scan_date"], "date_source": row["date_source"], "web_url": row["web_url"]}
            if items:
                if papers is None:
                    papers = filed_papers(folder, items)
                text = scan_text(str(row.get("folder") or ""), str(row["name"]), f"{row.get('id')}|{row.get('modified_utc')}")
                if match := likely_duplicate(text, papers):
                    entry["likely_duplicate"] = match
            out.append(entry)
        if len(out) >= MAX_FOR_CLIENT:
            break
    return {"matter_id": mid, "scans": out}
