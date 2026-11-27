#!/usr/bin/env python3
"The court a matter is proceeding in: persist it per matter, read it off filed papers."
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from documents import soft_form_names

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
from documents.family_court_names import COURT_TYPE_SUFFIXES, MFC_TAIL_RE, family_court_place, is_pure_magistrates

DEFAULT_OPS_DB = ops_db.configured_ops_db_path() or REPO_ROOT / "ops" / "caseforge-ops.sqlite3"

REF_TYPE = "court"
AUTO_SOURCE = "court_finder_auto"


COURT_PATTERNS = [
    re.compile(r"\bIN\s+THE\s+FAMILY\s+COURT\s+(?:SITTING\s+)?AT[:\s]\s*([^\n\r]+)", re.IGNORECASE),
    re.compile(r"\bthe\s+Family\s+Court\s+(?:sitting\s+)?at\s+([^\n\r,;]+)", re.IGNORECASE),
]

_TAIL_RE = re.compile(
    r"\s*[,;:(].*$"
    r"|\s+(?:case\s+n(?:o|umber)\b|no\.\s*[A-Z0-9]|dated\b|on\s+\d|between\b|before\b|the\b|and\b|was\b|is\b).*$",
    re.IGNORECASE,
)

_PLACEHOLDER_RE = re.compile(r"_|\[|\]|\bTBC\b|^x+$|^town$|^court$", re.IGNORECASE)


def _clean_court_name(raw: str) -> str:
    value = " ".join(str(raw or "").split())
    value = MFC_TAIL_RE.sub("", value)
    value = _TAIL_RE.sub("", value)
    value = value.strip(" \t-–—:;,.…")
    if not value or not any(ch.isalpha() for ch in value):
        return ""
    if _PLACEHOLDER_RE.search(value):
        return ""
    if len(value) > 60:
        return ""
    if value.isupper():
        value = re.sub(r"(['’])S\b", r"\1s", value.title())
    mapped = family_court_place(value)
    if mapped is not None:
        return ""
    return value


def extract_court_from_text(text: str) -> str:
    "The court venue named in a document's text, or \"\" when none is found."
    for pattern in COURT_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            value = _clean_court_name(match.group(1))
            if value:
                return value
    return ""



CATEGORY_RANKS = {"sealed_order": 3, "signed_ws": 2, "court_form": 1, "draft": 0}

DOCUMENT_SUFFIXES = (".pdf", ".docx", ".doc")

_DRAFT_RE = re.compile(r"\b(draft|unsigned|unexecuted|template|blank)\b", re.IGNORECASE)
_FILED_MARK_RE = re.compile(r"\b(sealed|seal|issued|stamped|filed)\b", re.IGNORECASE)
_SIGNED_RE = re.compile(r"\b(signed|sworn|executed|sgd)\b", re.IGNORECASE)
_ORDER_RE = re.compile(r"\border\b|\bfl40[46]\w*\b", re.IGNORECASE)
_WS_RE = re.compile(r"witness[\s_-]*statement\b|\bws\b", re.IGNORECASE)
_COURT_ISSUED_RE = re.compile(r"notice[\s_-]+of[\s_-]+hearing|\bfl402\w*\b|\bn\d{2,3}\b", re.IGNORECASE)
_APPLICATION_RE = re.compile(r"\bfl401\w*\b|\bc100\b|\bc1a\b|\bfl403\w*\b", re.IGNORECASE)


def classify_filename(name: str) -> str:
    "Which court-evidence category a filename belongs to, or \"\" for none."
    lowered = str(name or "").strip().lower()
    if not lowered.endswith(DOCUMENT_SUFFIXES):
        return ""
    court_shaped = bool(
        _ORDER_RE.search(lowered)
        or _WS_RE.search(lowered)
        or _COURT_ISSUED_RE.search(lowered)
        or _APPLICATION_RE.search(lowered)
    )
    if not court_shaped:
        return ""
    if _DRAFT_RE.search(lowered) or soft_form_names.is_soft_copy(lowered):
        return "draft"
    if _ORDER_RE.search(lowered) and _FILED_MARK_RE.search(lowered):
        return "sealed_order"
    if _WS_RE.search(lowered) and _SIGNED_RE.search(lowered):
        return "signed_ws"
    if _COURT_ISSUED_RE.search(lowered):
        return "court_form"
    if _ORDER_RE.search(lowered):
        return "court_form"
    if _APPLICATION_RE.search(lowered) and _FILED_MARK_RE.search(lowered):
        return "court_form"
    return "draft"


def choose_court(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    "Pick the court from extracted candidates, or report TBC."
    named = [c for c in candidates if str(c.get("court") or "").strip()]
    eligible = [c for c in named if CATEGORY_RANKS.get(str(c.get("category")), -1) >= 1]
    if eligible:
        best = max(
            eligible,
            key=lambda c: (CATEGORY_RANKS[str(c["category"])], str(c.get("modified_utc") or "")),
        )
        return {"status": "found", **best}
    if named:
        return {
            "status": "tbc_drafts_only",
            "drafts": [str(c.get("name")) for c in named],
        }
    return {"status": "none"}




def _now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def record_court(
    matter_id: str,
    court_name: str,
    *,
    source: str,
    notes: str = "",
    is_primary: bool = True,
) -> dict[str, Any]:
    "Upsert the matter's court row, mirroring the notice_of_acting idiom."
    mid = str(matter_id or "").strip()
    court = " ".join(str(court_name or "").split())
    if not mid:
        raise ValueError("matter_id is required to record a court.")
    if not court:
        raise ValueError("A non-empty court name is required; never record a blank.")
    normalised = court.upper()
    src = (str(source or "").strip() or "manual")[:200]
    note_text = str(notes or "").strip()[:400]
    now = _now_z()

    from clientdb_sql import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        if is_primary:
            cursor.execute(
                "UPDATE matter_references SET is_primary = 0, updated_utc = ? "
                "WHERE matter_id = ? AND ref_type = ? AND ref_value_normalised <> ?",
                (now, mid, REF_TYPE, normalised),
            )
        cursor.execute(
            "SELECT reference_id FROM matter_references "
            "WHERE matter_id = ? AND ref_type = ? AND ref_value_normalised = ?",
            (mid, REF_TYPE, normalised),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT INTO matter_references ("
                " matter_id, ref_type, ref_value, ref_value_normalised, source, notes,"
                " is_primary, created_utc, updated_utc"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mid, REF_TYPE, court, normalised, src, note_text, 1 if is_primary else 0, now, now),
            )
        else:
            cursor.execute(
                "UPDATE matter_references SET ref_value = ?, source = ?, notes = ?, "
                "is_primary = ?, updated_utc = ? WHERE reference_id = ?",
                (court, src, note_text, 1 if is_primary else 0, now, row[0]),
            )
    return {
        "matter_id": mid,
        "court": court,
        "ref_type": REF_TYPE,
        "source": src,
        "notes": note_text,
        "is_primary": bool(is_primary),
    }


def record_court_selection(
    matter_id: str,
    court_name: str,
    *,
    postcode: str = "",
    service_area: str = "",
) -> dict[str, Any]:
    "Record the court a human explicitly picked (e.g. from the court finder)."
    context = "; ".join(
        part
        for part in (
            f"postcode {postcode.strip()}" if str(postcode or "").strip() else "",
            f"service area {service_area.strip()}" if str(service_area or "").strip() else "",
        )
        if part
    )
    notes = f"Chosen by a human from court-finder results ({context})" if context else "Chosen by a human from court-finder results"
    return record_court(matter_id, court_name, source="court_finder_selection", notes=notes)


def get_courts(matter_id: str) -> list[dict[str, Any]]:
    "Every court recorded for a matter, primary row first, then newest."
    mid = str(matter_id or "").strip()
    if not mid:
        return []
    from clientdb_sql import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ref_value, source, notes, is_primary, updated_utc "
            "FROM matter_references WHERE matter_id = ? AND ref_type = ? "
            "ORDER BY is_primary DESC, updated_utc DESC",
            (mid, REF_TYPE),
        )
        rows = cursor.fetchall()
    return [
        {
            "court": str(row[0] or ""),
            "source": str(row[1] or ""),
            "notes": str(row[2] or ""),
            "is_primary": bool(row[3]),
            "updated_utc": str(row[4] or ""),
        }
        for row in rows
    ]


def get_court(matter_id: str) -> dict[str, Any] | None:
    "The recorded court for a matter, or None. Primary row wins, then newest."
    rows = get_courts(matter_id)
    return rows[0] if rows else None


def recorded_courts_for_matters(matter_ids: list[str]) -> dict[str, str]:
    "``get_court``'s court name for many matters in one read: ``{matter_id: court}``, only matters with a court."
    ids = list(dict.fromkeys(str(m).strip() for m in matter_ids if str(m or "").strip()))
    if not ids:
        return {}
    from clientdb_sql import get_connection

    marks = ", ".join("?" for _ in ids)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT matter_id, ref_value FROM matter_references WHERE ref_type = ? AND matter_id IN ({marks}) "
            "ORDER BY is_primary DESC, updated_utc DESC",
            (REF_TYPE, *ids),
        )
        rows = cursor.fetchall()
    found: dict[str, str] = {}
    for matter_id, court in rows:
        name = " ".join(str(court or "").split())
        if name:
            found.setdefault(str(matter_id), name)
    return found


def hearing_courts_for_matters(matter_ids: list[str]) -> dict[str, set[str]]:
    "Every court named by a matter's hearings that are not vacated: ``{matter_id: {court, ...}}``. Most matters"
    ids = list(dict.fromkeys(str(m).strip() for m in matter_ids if str(m or "").strip()))
    if not ids:
        return {}
    from clientdb_sql import get_connection

    marks = ", ".join("?" for _ in ids)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT matter_id, court FROM matter_hearings WHERE matter_id IN ({marks}) AND status <> 'vacated'", tuple(ids))
        rows = cursor.fetchall()
    found: dict[str, set[str]] = {}
    for matter_id, court in rows:
        name = " ".join(str(court or "").split())
        if name:
            found.setdefault(str(matter_id), set()).add(name)
    return found


def recorded_court_name(matter_id: str) -> str:
    "The recorded court's name for a matter, or \"\" -- never guessed."
    if not matter_id:
        return ""
    try:
        row = get_court(matter_id)
    except Exception:
        return ""
    return str((row or {}).get("court") or "").strip()


def auto_record_court(matter_id: str, court_name: str, *, postcode: str = "", service_area: str = "") -> dict[str, Any]:
    "Record a finder-found court ONLY when the matter has no court yet."
    if get_court(matter_id):
        return {"ok": True, "recorded": False, "reason": "a court is already recorded"}
    context = "; ".join(p for p in (f"postcode {postcode.strip()}" if postcode.strip() else "",
                                    f"service area {service_area.strip()}" if service_area.strip() else "") if p)
    row = record_court(matter_id, court_name, source=AUTO_SOURCE,
                       notes=f"Found automatically by the court finder ({context})" if context else "Found automatically by the court finder")
    return {"ok": True, "recorded": True, "court": row["court"]}


SIGNED_WS_SOURCE = "signed_ws_heading"


def court_from_statement_pdf(pdf_bytes: bytes) -> str:
    "The venue in a statement PDF's heading (first page), or \"\" for none, a placeholder or a magistrates' court."
    import io

    from pypdf import PdfReader

    try:
        pages = PdfReader(io.BytesIO(pdf_bytes)).pages
        return extract_court_from_text(pages[0].extract_text() or "") if pages else ""
    except Exception:
        return ""


def record_court_from_signed_statement(matter_id: str, pdf_bytes: bytes) -> dict[str, Any]:
    "Record the court a filed signed statement's heading names, only when nothing is recorded or the one"
    court = court_from_statement_pdf(pdf_bytes)
    if not court:
        return {"ok": True, "recorded": False, "reason": "no court in the heading"}
    rows = get_courts(matter_id)
    if rows and any(row["source"] != AUTO_SOURCE for row in rows):
        return {"ok": True, "recorded": False, "reason": "a court is already recorded from a higher-priority source"}
    row = record_court(matter_id, court, source=SIGNED_WS_SOURCE, notes="Read from the heading of the filed signed witness statement")
    return {"ok": True, "recorded": True, "court": row["court"]}





EASY_COURT_MARGIN_MILES = 3.0


def hard_court_route(name: str) -> str:
    "\"portal\" or \"call_first\" when the court takes applications only through the portal or only after a phone"
    try:
        from onboarding.pipeline import portal_courts

        if portal_courts.portal_court(name):
            return "portal"
        if portal_courts.call_first_court(name):
            return "call_first"
    except Exception:
        return ""
    return ""


def _miles(court: dict[str, Any]) -> float | None:
    value = court.get("distance_miles", court.get("distance"))
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def first_family_court(courts: list[dict[str, Any]]) -> dict[str, Any] | None:
    "The court to use from the finder's rows (in distance order): the nearest family court (any row except a pure"
    family = [c for c in courts if str(c.get("name") or "").strip() and not is_pure_magistrates(str(c.get("name") or "").strip())]
    if not family:
        return None
    top = family[0]
    anchor = _miles(top)
    if anchor is None or not hard_court_route(str(top.get("name") or "")):
        return top
    for court in family[1:]:
        miles = _miles(court)
        if miles is None or miles > anchor + EASY_COURT_MARGIN_MILES:
            continue
        if not hard_court_route(str(court.get("name") or "")):
            return court
    return top


def venue_from_finder_name(name: str) -> str:
    "Strip a known court-type suffix from a finder name, leaving the place name."
    value = " ".join(str(name or "").split())
    mapped = family_court_place(value)
    if mapped is not None:
        return ""
    if re.fullmatch(r"(?i)central family court", value):
        return "Central Family Court"
    for suffix in COURT_TYPE_SUFFIXES:
        if value.lower().endswith(" " + suffix):
            return value[: -len(suffix)].strip()
    return value


def suggest_court(
    postcode_sources: list[tuple[str, str]],
    service_area: str = "domestic-abuse",
    *,
    finder: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    "A court *suggestion* from the first usable postcode, most trusted source first."
    if finder is None:
        from documents.court_finder import find_nearest_courts, normalise_postcode

        finder = find_nearest_courts
    else:
        from documents.court_finder import normalise_postcode

    for source, text in postcode_sources:
        postcode = normalise_postcode(text)
        if not postcode:
            continue
        result = finder(postcode, service_area, limit=5, detail_limit=0)
        if not result.get("ok"):
            return {"status": "tbc", "reason": str(result.get("message") or "court finder returned nothing"), "postcode_source": source}
        courts = result.get("nearest_courts") or result.get("courts") or []
        if not courts:
            return {"status": "tbc", "reason": "court finder returned no courts", "postcode_source": source}
        top = first_family_court(courts)
        if top is None:
            return {"status": "tbc", "reason": "the court finder gave only magistrates' courts; the nearest family court needs choosing", "postcode_source": source}
        courts = [top] + [c for c in courts if c is not top and not is_pure_magistrates(str(c.get("name") or ""))]
        full_name = str(top.get("name") or "")
        return {
            "status": "suggested",
            "court": venue_from_finder_name(full_name),
            "finder_name": full_name,
            "distance_miles": top.get("distance_miles"),
            "postcode_source": source,
            "service_area": service_area,
            "alternatives": [str(c.get("name") or "") for c in courts[1:4]],
        }
    return {"status": "tbc", "reason": "no valid postcode in any source"}




def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def find_candidate_files(matter_folder_path: str, db_path: Path = DEFAULT_OPS_DB) -> list[dict[str, Any]]:
    "Court-evidence candidates under a matter folder, best-ranked first."
    folder = str(matter_folder_path or "").replace("\\", "/").strip("/")
    if not folder:
        return []
    if not Path(db_path).exists():
        raise SystemExit(
            f"No OneDrive index at {db_path}. Build one with:\n"
            "  python3 tools/graph_index.py refresh"
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute(
            r"""
            SELECT path, name, modified_utc FROM onedrive_items
            WHERE item_type = 'file' AND deleted_at_utc IS NULL
              AND path LIKE ? ESCAPE '\'
            """,
            (f"{_escape_like(folder)}/%",),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    candidates = []
    for path, name, modified_utc in rows:
        category = classify_filename(name)
        if not category:
            continue
        candidates.append(
            {
                "path": str(path),
                "name": str(name),
                "category": category,
                "modified_utc": str(modified_utc or ""),
            }
        )
    return sorted(
        candidates,
        key=lambda c: (CATEGORY_RANKS[c["category"]], c["modified_utc"]),
        reverse=True,
    )


def resolve_matter_folder(query: str = "", matter_id: str = "") -> dict[str, Any]:
    "Resolve ``{\"matter_id\", \"path\", \"name\"}`` for a matter, index-first."
    import agwu

    text = " ".join(str(query or "").split())
    resolved_mid = str(matter_id or "").strip()

    if not resolved_mid and text:
        try:
            client_result = agwu.resolve_client(text, caller="court_of_record.resolve_matter_folder")
        except Exception:
            client_result = None
        if client_result is not None and client_result.status == "resolved" and client_result.top is not None:
            resolved_mid = str(client_result.top.row.get("matter_id") or "")

    def _usable(resolution) -> bool:
        "A resolution only counts if it actually carries a folder path."
        return resolution is not None and resolution.status != "not_found" and bool(resolution.matter_folder_path)

    result = None
    if resolved_mid:
        try:
            result = agwu.resolve_folder(
                resolved_mid, allow_live_fallback=False, caller="court_of_record.resolve_matter_folder"
            )
        except Exception:
            result = None
    if not _usable(result) and text:
        try:
            result = agwu.resolve_folder(
                text, allow_live_fallback=True, caller="court_of_record.resolve_matter_folder"
            )
        except Exception:
            result = None

    if _usable(result):
        path = result.matter_folder_path
        return {
            "matter_id": resolved_mid,
            "path": path,
            "name": Path(path).name if path else "",
        }
    raise SystemExit(
        "Could not resolve a live matter folder. Pass --folder explicitly, or "
        "refresh the index: python3 tools/graph_index.py refresh"
    )


def extract_text_from_file(path: Path, max_pages: int = 4) -> str:
    "Text from the head of a PDF/docx. The court heading lives on page 1."
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])
    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs[:120])
    return ""


def scan_matter(
    matter_id: str,
    folder_path: str,
    *,
    db_path: Path = DEFAULT_OPS_DB,
    max_docs: int = 4,
    write: bool = True,
    download_fn: Callable[[str, Path], Any] | None = None,
    extract_fn: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    "Scan a matter's folder for the court on filed papers; write when found."
    if download_fn is None:
        import graph_files

        def download_fn(remote: str, local: Path) -> None:
            graph_files.download(remote, local)

    extract = extract_fn or (lambda local: extract_text_from_file(local))

    all_candidates = find_candidate_files(folder_path, db_path=db_path)
    eligible = [c for c in all_candidates if CATEGORY_RANKS[c["category"]] >= 1][: max(1, max_docs)]
    drafts = [c for c in all_candidates if CATEGORY_RANKS[c["category"]] == 0][:2]

    examined: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="court-of-record-") as tmp:
        tmp_dir = Path(tmp)

        def _examine(candidate: dict[str, Any]) -> None:
            local = tmp_dir / Path(candidate["name"]).name
            entry = dict(candidate)
            try:
                download_fn(candidate["path"], local)
                entry["court"] = extract_court_from_text(extract(local))
            except Exception as exc:
                entry["court"] = ""
                entry["error"] = str(exc)
            examined.append(entry)

        for candidate in eligible:
            _examine(candidate)
        if not any(e.get("court") and CATEGORY_RANKS[e["category"]] >= 1 for e in examined):
            for candidate in drafts:
                _examine(candidate)

    decision = choose_court(examined)
    report: dict[str, Any] = {
        "matter_id": matter_id,
        "folder": folder_path,
        "candidates_indexed": len(all_candidates),
        "examined": [
            {k: e.get(k) for k in ("name", "category", "court", "modified_utc", "error") if e.get(k) is not None}
            for e in examined
        ],
        "decision": decision,
        "written": False,
    }
    if decision["status"] == "found" and write:
        if not str(matter_id or "").strip():
            report["decision"] = {**decision, "status": "found_no_matter_id"}
            return report
        row = record_court(
            matter_id,
            decision["court"],
            source=f"document:{decision['name']}"[:200],
            notes=f"Extracted from {decision['category']} (modified {decision.get('modified_utc') or 'unknown'}) by court_of_record scan",
        )
        report["written"] = True
        report["row"] = row
    return report




def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Read the court off filed papers in the live matter folder.")
    p_scan.add_argument("--matter-id", default="", help="matter_id for the write (resolved from --name when omitted)")
    p_scan.add_argument("--name", default="", help="client/matter name to resolve the live folder")
    p_scan.add_argument("--folder", default="", help="explicit matter folder path (skips resolution)")
    p_scan.add_argument("--db", default=str(DEFAULT_OPS_DB), help="ops sqlite path (OneDrive index)")
    p_scan.add_argument("--max-docs", type=int, default=4, help="max write-eligible documents to download")
    p_scan.add_argument("--dry-run", action="store_true", help="report only; write nothing")

    p_get = sub.add_parser("get", help="Show the recorded court for a matter.")
    p_get.add_argument("--matter-id", required=True)

    p_rec = sub.add_parser("record", help="Record a human-chosen court for a matter.")
    p_rec.add_argument("--matter-id", required=True)
    p_rec.add_argument("--court", required=True, help="venue name only, e.g. 'West London'")
    p_rec.add_argument("--source", default="manual", help="e.g. court_finder_selection")
    p_rec.add_argument("--notes", default="")

    args = ap.parse_args(argv)

    if args.cmd == "get":
        row = get_court(args.matter_id)
        if row is None:
            print(f"No court recorded for matter {args.matter_id} (TBC).")
            return 1
        print(json.dumps({"matter_id": args.matter_id, **row}, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "record":
        row = record_court(args.matter_id, args.court, source=args.source, notes=args.notes)
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0

    matter_id = args.matter_id.strip()
    folder = args.folder.strip()
    if not folder:
        resolved = resolve_matter_folder(args.name, matter_id=matter_id)
        folder = resolved["path"]
        matter_id = matter_id or str(resolved.get("matter_id") or "")
        print(f"Resolved folder: {folder}")
    report = scan_matter(
        matter_id,
        folder,
        db_path=Path(args.db),
        max_docs=args.max_docs,
        write=not args.dry_run,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report["decision"]["status"]
    if status == "found":
        return 0
    if status == "tbc_drafts_only":
        print("TBC: only draft/unsigned documents name a court. Nothing was written.")
        return 1
    if status == "found_no_matter_id":
        print("A court was found but no matter_id was resolved; re-run with --matter-id to write it.")
        return 1
    print("TBC: no examined document names a court. Nothing was written.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
