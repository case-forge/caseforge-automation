#!/usr/bin/env python3
"The client panel's Virtual scanner: file a stock copy of a common document for one client, and bill it."
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import uuid
from pathlib import Path
from typing import Any, Callable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql
import firm_profile

MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0036_matter_virtual_scans.sql"
DEFAULT_COMMON_DOCS_PATH = f"{firm_profile.load_profile().library_root}/{firm_profile.load_profile().common_documents_book}"
REMOVED_FOLDER = "000 Removed"
NMO_CAO_BOOK = firm_profile.load_profile().protective_orders_book
GUARD_REFUSED = (
    "The Graph guard refused this save: this client's folder is set read-only on the assignment board. "
    "Nothing was filed or billed: turn the switch off or file the document by hand."
)
ACTIVITY_STEP = "virtual_scan"
ACTIVITY_MODE = "virtual scanner"
BILL_CATEGORIES = ("routine_letter_in", "received_document_pages")
TITLE_PREFIX = "t:"
CATALOGUE_TTL_SECONDS = 60.0
MAX_SUFFIX = 50
_COLUMNS = (
    "scan_id", "matter_id", "document_id", "document_title", "date_received", "pressed_by", "pressed_utc",
    "filed_path", "filed_url", "billing_item_id", "billing_note", "pages", "text_chars", "status",
    "undone_by", "undone_utc", "moved_to", "copies",
)
WARN_COPIES = 2
MAX_COPIES = 20
_TITLE_COLUMNS = ("title_id", "title", "added_by", "added_utc", "removed_by", "removed_utc")


class VirtualScanError(ValueError):
    "A request refused for a reason a person can read and act on; the hub returns it as a 422."



_ensured: set[str] = set()


def _create_statements() -> list[str]:
    "The migration's CREATE statements only: its change-log attach lines are Postgres-only and run"
    text = "\n".join(line for line in MIGRATION_PATH.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip().upper().startswith("CREATE")]


def ensure_tables(conn) -> None:
    key = f"sqlite:{clientdb_sql._sqlite_path()}" if clientdb_sql._using_sqlite() else "pg"
    if key in _ensured:
        return
    cursor = conn.cursor()
    for stmt in _create_statements():
        cursor.execute(stmt)
    _ensured.add(key)


def _rows(cursor) -> list[dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _utc(now: dt.datetime | None = None) -> str:
    moment = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _matter_number(matter_id: Any) -> int:
    text = str(matter_id or "").strip()
    if not text.isdigit():
        raise VirtualScanError("matter_id must be a matter number")
    return int(text)


def scans_for(matter_id: Any) -> list[dict[str, Any]]:
    "Every scan for one matter, filed and undone, newest first."
    mid = _matter_number(matter_id)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM matter_virtual_scans WHERE matter_id = ? ORDER BY pressed_utc DESC",
            (mid,),
        )
        return [_scan_view(r) for r in _rows(cursor)]


def get_scan(scan_id: str) -> dict[str, Any] | None:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(f"SELECT {', '.join(_COLUMNS)} FROM matter_virtual_scans WHERE scan_id = ?", (_clean(scan_id, 64),))
        rows = _rows(cursor)
    return _scan_view(rows[0]) if rows else None


def _filed_scan(matter: int, document_id: str, date_received: str) -> dict[str, Any] | None:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM matter_virtual_scans "
            "WHERE matter_id = ? AND document_id = ? AND date_received = ? AND status = 'filed'",
            (matter, document_id, date_received),
        )
        rows = _rows(cursor)
    return _scan_view(rows[0]) if rows else None


def _insert_scan(row: dict[str, Any]) -> None:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        conn.cursor().execute(
            f"INSERT INTO matter_virtual_scans ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' for _ in _COLUMNS)})",
            tuple(row[c] for c in _COLUMNS),
        )


def _mark_undone(scan_id: str, by: str, moved_to: str, note: str, now: str) -> None:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        conn.cursor().execute(
            "UPDATE matter_virtual_scans SET status = 'undone', undone_by = ?, undone_utc = ?, moved_to = ?, "
            "billing_note = ? WHERE scan_id = ? AND status = 'filed'",
            (by, now, moved_to, note, scan_id),
        )


def _scan_view(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in _COLUMNS}
    out["matter_id"] = str(row.get("matter_id") or "")
    for key in ("pages", "text_chars"):
        out[key] = int(row[key]) if row.get(key) not in (None, "") else None
    out["copies"] = int(row.get("copies") or 1)
    for key in ("filed_path", "filed_url", "billing_item_id", "billing_note", "undone_by", "moved_to", "pressed_by"):
        out[key] = str(row.get(key) or "")
    out["undone_utc"] = str(row.get("undone_utc") or "")
    out["file_name"] = out["filed_path"].rsplit("/", 1)[-1] if out["filed_path"] else ""
    return out




def list_titles() -> list[dict[str, Any]]:
    "The typed titles not removed, oldest first."
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(_TITLE_COLUMNS)} FROM common_document_titles WHERE removed_utc IS NULL ORDER BY added_utc",
        )
        return _rows(cursor)


def add_title(title: str, by: str, *, now: dt.datetime | None = None) -> dict[str, Any]:
    "Add a document by its title alone (no stock copy yet). A title already listed, typed or in the"
    clean = _clean(title, 150)
    who = _clean(by, 200)
    if not clean:
        raise VirtualScanError("Type the document's title.")
    if not who:
        raise VirtualScanError("Type your name first.")
    if any(t["title"].lower() == clean.lower() for t in list_titles()):
        raise VirtualScanError(f"{clean!r} is already on the list.")
    row = {"title_id": uuid.uuid4().hex, "title": clean, "added_by": who, "added_utc": _utc(now), "removed_by": "", "removed_utc": None}
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        conn.cursor().execute(
            f"INSERT INTO common_document_titles ({', '.join(_TITLE_COLUMNS)}) VALUES ({', '.join('?' for _ in _TITLE_COLUMNS)})",
            tuple(row[c] for c in _TITLE_COLUMNS),
        )
    return row


def remove_title(title_id: str, by: str, *, now: dt.datetime | None = None) -> bool:
    "Take a typed title off the list (kept, with who and when). Returns whether one matched."
    ident = _clean(str(title_id).removeprefix(TITLE_PREFIX), 64)
    who = _clean(by, 200)
    if not who:
        raise VirtualScanError("Type your name first.")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT title_id FROM common_document_titles WHERE title_id = ? AND removed_utc IS NULL", (ident,))
        if not cursor.fetchall():
            return False
        cursor.execute(
            "UPDATE common_document_titles SET removed_by = ?, removed_utc = ? WHERE title_id = ? AND removed_utc IS NULL",
            (who, _utc(now), ident),
        )
        return True




def common_docs_path() -> str:
    import app_settings

    return app_settings.get_setting("common_documents_folder") or DEFAULT_COMMON_DOCS_PATH


LOCAL_STOCK_DIR = TOOLS_DIR.parent / "templates-general" / "Common Scanned Docs"


def _local_stock() -> bool:
    return common_docs_path() == DEFAULT_COMMON_DOCS_PATH and LOCAL_STOCK_DIR.is_dir() and any(LOCAL_STOCK_DIR.iterdir())


def _graph_token() -> str:
    from onboarding.pipeline import shared_token

    return shared_token()


def list_stock_files() -> list[dict[str, Any]]:
    "The files directly in the stock folder: id, name, size, content hash, address."
    if _local_stock():
        return [
            {"id": f.name, "name": f.name, "size": f.stat().st_size, "hash": hashlib.sha256(f.read_bytes()).hexdigest(), "web_url": ""}
            for f in sorted(LOCAL_STOCK_DIR.iterdir())
            if f.is_file()
        ]
    import graph_files

    listing = graph_files.list_children(common_docs_path(), access_token=_graph_token())
    out = []
    for item in listing.get("value") or []:
        if "file" not in item:
            continue
        hashes = (item.get("file") or {}).get("hashes") or {}
        out.append({
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "size": int(item.get("size") or 0),
            "hash": str(hashes.get("quickXorHash") or hashes.get("sha256Hash") or hashes.get("sha1Hash") or ""),
            "web_url": str(item.get("webUrl") or ""),
        })
    return out


def download_stock(name: str) -> bytes:
    "One stock file's bytes, read from the stock folder."
    if _local_stock():
        path = LOCAL_STOCK_DIR / Path(name).name
        if not path.is_file():
            raise VirtualScanError("That document is not in the stock folder any more.")
        return path.read_bytes()
    import graph_files

    with tempfile.TemporaryDirectory(prefix="virtual-scanner-") as tmp:
        out = Path(tmp) / "stock.pdf"
        graph_files.download(f"{common_docs_path()}/{name}", out, access_token=_graph_token())
        return out.read_bytes()


_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


def _stock_files_cached() -> list[dict[str, Any]]:
    with _CACHE_LOCK:
        if _CACHE and time.monotonic() - _CACHE["at"] < CATALOGUE_TTL_SECONDS and _CACHE["source"] is list_stock_files:
            return _CACHE["files"]
    files = list_stock_files()
    with _CACHE_LOCK:
        _CACHE.update(at=time.monotonic(), files=files, source=list_stock_files)
    return files


def forget_cached() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def title_of(file_name: str) -> str:
    return re.sub(r"\.pdf$", "", str(file_name or ""), flags=re.I).strip()


def _preferred(names: list[str]) -> str:
    "Which of several identical files names the entry: one without underscores (a person's title,"
    return sorted(names, key=lambda n: ("_" in n, len(n), n.lower()))[0]


def catalogue() -> dict[str, Any]:
    "The documents the tab lists, by title: one per distinct stock PDF (identical contents are one"
    documents: list[dict[str, Any]] = []
    other: list[str] = []
    folder_error = ""
    try:
        files = _stock_files_cached()
    except Exception:
        files = []
        folder_error = "Could not read the Common Scanned Docs folder just now."
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        if not f["name"].lower().endswith(".pdf"):
            other.append(f["name"])
            continue
        groups.setdefault(f["hash"] or f"id:{f['id']}", []).append(f)
    for group in groups.values():
        name = _preferred([f["name"] for f in group])
        main = next(f for f in group if f["name"] == name)
        documents.append({
            "document_id": main["id"],
            "title": title_of(name),
            "file_name": name,
            "has_file": True,
            "also_named": sorted(f["name"] for f in group if f["name"] != name),
            "web_url": main["web_url"],
            "added_by": "",
            "content_hash": main["hash"],
        })
    stock_titles = {d["title"].lower() for d in documents}
    for t in list_titles():
        if t["title"].lower() in stock_titles:
            continue
        documents.append({
            "document_id": f"{TITLE_PREFIX}{t['title_id']}",
            "title": t["title"],
            "file_name": "",
            "has_file": False,
            "also_named": [],
            "web_url": "",
            "added_by": t["added_by"],
            "content_hash": "",
        })
    documents.sort(key=lambda d: d["title"].lower())
    return {"folder": common_docs_path().rsplit("/", 1)[-1], "documents": documents, "other_files": sorted(other), "folder_error": folder_error}


def stock_document(document_id: str) -> dict[str, Any]:
    "The catalogue entry for a stock PDF, read afresh; refused for a typed title or an id not in the folder."
    ident = str(document_id or "").strip()
    if ident.startswith(TITLE_PREFIX):
        raise VirtualScanError("There is no stock copy of this document yet, so there is nothing to scan or view.")
    forget_cached()
    for doc in catalogue()["documents"]:
        if doc["document_id"] == ident and doc["has_file"]:
            return doc
    raise VirtualScanError("That document is not in the Common Scanned Docs folder any more.")


def stock_pdf(document_id: str) -> tuple[str, bytes]:
    "(file name, bytes) of one stock PDF, for the tab's viewer. Only a PDF in the stock folder."
    doc = stock_document(document_id)
    return doc["file_name"], download_stock(doc["file_name"])




def measure(data: bytes) -> dict[str, int | None]:
    "The PDF's page count and the characters of its own text (runs of white space counted as one"
    from pypdf import PdfReader

    import document_ocr

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
    except Exception:
        return {"pages": None, "text_chars": None}
    try:
        text = " ".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return {"pages": pages, "text_chars": None}
    chars = len(" ".join(text.split()))
    return {"pages": pages, "text_chars": chars if chars >= document_ocr.OCR_MIN_CHARS else None}


def billing_plan(pages: int | None, text_chars: int | None) -> dict[str, Any]:
    "How one scan bills (owner rule, 2026-10-16): at most ``RECEIVED_DOCUMENT_CHAR_LIMIT``"
    from billing import rates

    limit = rates.RECEIVED_DOCUMENT_CHAR_LIMIT
    measured = f"{pages if pages is not None else 'unknown'} page(s), {f'{text_chars:,}' if text_chars is not None else 'unknown'} characters"
    if limit is None:
        return {"category": "tbc", "quantity": pages or 1, "note": f"Rate TBC: the character limit is not set yet. {measured}."}
    if text_chars is None:
        return {"category": "tbc", "quantity": pages or 1, "note": f"Rate TBC: the characters are unknown (no text layer). {measured}."}
    if text_chars <= limit:
        return {"category": "routine_letter_in", "quantity": 1, "note": f"Routine letter in: {measured}, at or under {limit:,}."}
    if not pages:
        return {"category": "tbc", "quantity": 1, "note": f"Rate TBC: over {limit:,} characters but the page count is unknown. {measured}."}
    return {"category": "received_document_pages", "quantity": pages, "note": f"2 minutes per page: {measured}, over {limit:,}."}


def billing_plans(pages: int | None, text_chars: int | None) -> list[dict[str, Any]]:
    "The lines ONE posted copy bills as (owner rule, 2026-10-20): a document over the"
    plan = billing_plan(pages, text_chars)
    if plan["category"] != "received_document_pages":
        return [plan]
    return [
        {"category": "routine_letter_in", "quantity": 1, "note": "Routine letter in."},
        plan,
    ]


def work_id_for(document_id: str, date_received: str, copy: int = 1) -> str:
    "The billing ``work_id`` of one (document, date, posted copy); the matter is its own column. Fits 64."
    base = f"vscan:{hashlib.sha256(document_id.encode('utf-8')).hexdigest()[:20]}:{date_received}"
    return base if copy <= 1 else f"{base}:c{copy}"


def _existing_bill(matter_id: str, work_id: str, categories: tuple[str, ...] | None = None) -> str:
    from billing import billing_items

    for category in (*(categories or BILL_CATEGORIES), billing_items.TBC_CATEGORY):
        found = billing_items.item_id_for_work(matter_id, work_id, category)
        if found:
            return found
    return ""


def bill_scan(matter_id: str, doc_title: str, date_received: str, work_id: str, plan: dict[str, Any], *, by: str = "", client_name: str = "", document_url: str = "") -> tuple[str, str]:
    "(billing item id, what happened). The same (matter, document, date) is billed once: an earlier"
    from billing import billing_items

    existing = _existing_bill(matter_id, work_id, (plan["category"],) if plan["category"] != "tbc" else None)
    if existing:
        if billing_items.restore_item(existing, by=by or ACTIVITY_MODE):
            return existing, "Put the earlier charge for this document and date back on the bill."
        return existing, "Already billed for this document and date; not billed again."
    item_date = dt.date.fromisoformat(date_received).strftime("%d.%m.%y")
    description = f"Received document: {doc_title}"
    if plan["category"] == "tbc":
        row = billing_items.record_tbc_item(
            matter_id=matter_id, item_date=item_date, description=f"{description}. {plan['note']}",
            quantity=plan["quantity"], work_id=work_id, client_name=client_name, document_url=document_url,
        )
    else:
        row = billing_items.record_item(
            matter_id=matter_id, item_date=item_date, category=plan["category"], description=description,
            quantity=plan["quantity"], work_id=work_id, client_name=client_name, document_url=document_url,
        )
    return row["item_id"], plan["note"]


def bill_copies(matter_id: str, doc_title: str, date_received: str, document_id: str, plans: list[dict[str, Any]], copies: int, *, by: str = "", client_name: str = "", document_url: str = "") -> tuple[str, str]:
    "Bill every posted copy by every line of ``plans`` (each copy came in and is perused). Returns the"
    ids: list[str] = []
    notes: list[str] = []
    for copy in range(1, copies + 1):
        for plan in plans:
            item_id, note = bill_scan(matter_id, doc_title, date_received, work_id_for(document_id, date_received, copy), plan, by=by, client_name=client_name, document_url=document_url)
            ids.append(item_id)
            if copy == 1:
                notes.append(note)
    note = " ".join(notes)
    if copies > 1:
        note += f" Billed for each of the {copies} copies posted."
    return ",".join(i for i in ids if i), note




_UNSAFE_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def file_name(title: str, date_received: str, surname: str, n: int = 1) -> str:
    "``<Title> DD.MM.YY - SURNAME.pdf``; ``n`` > 1 adds `` (n)`` before the surname, so the name"
    clean = re.sub(r"\s+", " ", _UNSAFE_RE.sub(" ", title_of(title))).strip(" .")[:120] or "Document"
    day = dt.date.fromisoformat(date_received).strftime("%d.%m.%y")
    suffix = f" ({n})" if n > 1 else ""
    return f"{clean} {day}{suffix} - {surname.upper()}.pdf"


def upload_unused_name(data: bytes, folder: str, name_for: Callable[[int], str], token: str) -> dict[str, Any]:
    "Save ``data`` under the first free name, never replacing a file (Graph ``conflictBehavior=fail``:"
    import graph_files

    with tempfile.TemporaryDirectory(prefix="virtual-scanner-up-") as tmp:
        for n in range(1, MAX_SUFFIX + 1):
            name = name_for(n)
            local = Path(tmp) / f"{n}.pdf"
            local.write_bytes(data)
            try:
                item = graph_files.upload(local, f"{folder}/{name}", token, conflict_behavior="fail")
            except urllib.error.HTTPError as exc:
                if exc.code == 409:
                    continue
                raise
            return {**(item or {}), "name": name}
    raise VirtualScanError(f"Every name up to ({MAX_SUFFIX}) is taken in that folder. Nothing was filed.")


def read_only_folder(folder_path: str) -> bool:
    return f"/{NMO_CAO_BOOK.lower()}/" in f"/{str(folder_path or '').lower()}/"


def _london_today() -> dt.date:
    from zoneinfo import ZoneInfo

    return dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("Europe/London")).date()


def _check_date(date_received: str) -> str:
    text = str(date_received or "").strip()
    try:
        day = dt.date.fromisoformat(text)
    except ValueError as exc:
        raise VirtualScanError("Give the date the document came in (YYYY-MM-DD).") from exc
    if day > _london_today():
        raise VirtualScanError("The date it came in cannot be after today.")
    return day.isoformat()


def _log(matter_id: str, summary: str, by: str, links: list[dict[str, str]] | None = None) -> None:
    "A line in the client's Activity log. Best effort: the scan stands without it."
    try:
        from onboarding.pipeline import log_event

        log_event(matter_id, ACTIVITY_STEP, "ok", summary[:300], by, ACTIVITY_MODE, links=links)
    except Exception:
        pass


def _step_ref(key: str) -> str:
    "``\"step 1\"`` for a Case flow step key: the number comes from the pipeline registry."
    from onboarding.pipeline import step_ref

    return step_ref(key)


def _context(matter_id: str):
    from onboarding import pipeline

    try:
        return pipeline.load_context(matter_id)
    except pipeline.PipelineError as exc:
        raise VirtualScanError(str(exc)) from exc


def view(matter_id: Any) -> dict[str, Any]:
    "The tab: the catalogue, this client's scans, and whether scanning is possible for them."
    from onboarding.pipeline import court_common as cc

    mid = str(_matter_number(matter_id))
    ctx = _context(mid)
    refusal = ""
    folder = ""
    if not ctx.folder_path:
        refusal = "This client has no folder recorded, so nothing can be filed."
    else:
        try:
            folder = cc.court_orders_folder(ctx)
        except Exception:
            folder = ""
        if not folder:
            refusal = f"There is no single Court-Orders folder for {ctx.surname or 'this client'} to file into. Make the folders first (Case flow {_step_ref('folder')})."
    scans = scans_for(mid)
    from documents import virtual_scanner_hints

    shown = virtual_scanner_hints.hints(ctx, {p["file_name"] for p in scans}) if ctx.folder_path else virtual_scanner_hints.empty()
    return {
        "matter_id": mid,
        "today": _london_today().isoformat(),
        "can_scan": not refusal,
        "refusal": refusal,
        "court_orders_folder": folder.rsplit("/", 1)[-1] if folder else "",
        **catalogue(),
        "scans": scans,
        **shown,
    }


def check_copies(copies: Any) -> int:
    "The number of copies asked for: a whole number from 1 to MAX_COPIES."
    try:
        n = int(copies)
    except (TypeError, ValueError):
        raise VirtualScanError("Give the number of copies as a whole number.") from None
    if not 1 <= n <= MAX_COPIES:
        raise VirtualScanError(f"Copies must be between 1 and {MAX_COPIES}.")
    return n


def scan_document(matter_id: Any, document_id: str, date_received: str, by: str, *, copies: Any = 1, now: dt.datetime | None = None) -> dict[str, Any]:
    "File one stock copy for a client and bill it; see the module docstring. A second press for the"
    import graph_files

    from onboarding.pipeline import court_common as cc

    mid = str(_matter_number(matter_id))
    who = _clean(by, 200)
    if not who:
        raise VirtualScanError("Type your name first.")
    day = _check_date(date_received)
    n_copies = check_copies(copies)
    if str(document_id or "").startswith(TITLE_PREFIX):
        raise VirtualScanError("There is no stock copy of this document yet, so there is nothing to scan.")
    ctx = _context(mid)
    if not ctx.folder_path:
        raise VirtualScanError("This client has no folder recorded. Nothing was filed or billed.")
    earlier = _filed_scan(int(mid), str(document_id), day)
    if earlier:
        return {**earlier, "already": True, "message": f"Already scanned for {dt.date.fromisoformat(day):%d.%m.%y}: {earlier['file_name']}. Nothing was filed or billed again."}
    doc = stock_document(document_id)
    folder = cc.court_orders_folder(ctx)
    if not folder:
        raise VirtualScanError(
            f"There is no single Court-Orders folder for {ctx.surname or 'this client'} to file into. "
            f"Make the folders first (Case flow {_step_ref('folder')}). Nothing was filed or billed."
        )
    data = download_stock(doc["file_name"])
    sizes = measure(data)
    token = ctx.token()
    try:
        item = upload_unused_name(data, folder, lambda n: file_name(doc["title"], day, ctx.surname, n), token)
    except graph_files.GraphFileSafetyError as exc:
        raise VirtualScanError(GUARD_REFUSED) from exc
    filed_path = f"{folder}/{item['name']}"
    filed_url = str(item.get("webUrl") or "")
    try:
        billing_item_id, billing_note = bill_copies(mid, doc["title"], day, str(document_id), billing_plans(sizes["pages"], sizes["text_chars"]), n_copies, by=who, client_name=ctx.client_name, document_url=filed_url)
    except Exception as exc:
        billing_item_id, billing_note = "", f"Filed, but not billed ({type(exc).__name__}): add the charge by hand."
    row = {
        "scan_id": uuid.uuid4().hex,
        "matter_id": int(mid),
        "document_id": str(document_id),
        "document_title": doc["title"],
        "date_received": day,
        "pressed_by": who,
        "pressed_utc": _utc(now),
        "filed_path": filed_path,
        "filed_url": filed_url,
        "billing_item_id": billing_item_id,
        "billing_note": billing_note[:300],
        "pages": sizes["pages"],
        "text_chars": sizes["text_chars"],
        "status": "filed",
        "undone_by": "",
        "undone_utc": None,
        "moved_to": "",
        "copies": n_copies,
    }
    _insert_scan(row)
    _log(mid, f"Virtual scanner: filed {item['name']} in {folder.rsplit('/', 1)[-1]}. {billing_note}", who,
         [{"label": f"Open {item['name']}", "url": filed_url}] if filed_url.startswith("https://") else None)
    return {**_scan_view(row), "already": False, "message": f"Filed {item['name']} in {folder.rsplit('/', 1)[-1]} ({n_copies} {'copy' if n_copies == 1 else 'copies'}). {billing_note}"}


def _move_into_removed(ctx, filed_path: str, token: str) -> str:
    "Move a filed copy into ``REMOVED_FOLDER`` in the client's folder, never replacing a file there."
    import graph_files

    removed = f"{ctx.folder_path}/{REMOVED_FOLDER}"
    top = {str(i.get("name") or "").lower() for i in graph_files.list_children(ctx.folder_path, access_token=token).get("value", [])}
    if REMOVED_FOLDER.lower() not in top:
        graph_files.create_folder(ctx.folder_path, REMOVED_FOLDER, access_token=token)
    have = {str(i.get("name") or "").lower() for i in graph_files.list_children(removed, access_token=token).get("value", [])}
    name = filed_path.rsplit("/", 1)[-1]
    stem, _, ext = name.rpartition(".")
    target_name = name
    n = 2
    while target_name.lower() in have:
        target_name = f"{stem} ({n}).{ext}"
        n += 1
    before = os.environ.get("CASEFORGE_GRAPH_FILE_MOVE_APPROVED")
    os.environ["CASEFORGE_GRAPH_FILE_MOVE_APPROVED"] = "1"
    try:
        graph_files.move_item(filed_path, f"{removed}/{target_name}", token)
    finally:
        if before is None:
            os.environ.pop("CASEFORGE_GRAPH_FILE_MOVE_APPROVED", None)
        else:
            os.environ["CASEFORGE_GRAPH_FILE_MOVE_APPROVED"] = before
    return f"{removed}/{target_name}"


def move_into_removed(ctx, path: str, token: str) -> str:
    "Move any file in the client's folder into ``REMOVED_FOLDER`` (never replacing, never deleting); returns where it went."
    blocked = move_blocked(ctx.folder_path)
    if blocked:
        raise VirtualScanError(blocked)
    return _move_into_removed(ctx, path, token)


def move_blocked(folder_path: str) -> str:
    "Why a file in this client's folder cannot be moved (its book takes no move), or \"\" when it can."
    if read_only_folder(folder_path):
        return f"This client's folder is in {NMO_CAO_BOOK}, which takes no move."
    return ""


def _move_back_to_scanned_docs(filed_path: str, token: str) -> str:
    "Put a confirmed scan back in the intake folder, under a free name, so it waits there again."
    import graph_files

    from scanned_docs import scan_rows

    folder = scan_rows.scanned_docs_path()
    have = {str(i.get("name") or "").lower() for i in graph_files.list_children(folder, access_token=token).get("value", [])}
    target = _free_name(filed_path.rsplit("/", 1)[-1], have)
    move_gated(filed_path, f"{folder}/{target}", token)
    return f"{folder}/{target}"


def undo_scan(scan_id: str, by: str, *, now: dt.datetime | None = None) -> dict[str, Any]:
    "Undo one scan: move the copy into ``000 Removed``, take its charge off the bill (restorable on"
    from billing import billing_items

    who = _clean(by, 200)
    if not who:
        raise VirtualScanError("Type your name first.")
    row = get_scan(scan_id)
    if row is None:
        raise VirtualScanError("No such scan.")
    if row["status"] == "undone":
        return {**row, "message": "Already undone."}
    ctx = _context(row["matter_id"])
    if read_only_folder(ctx.folder_path) or read_only_folder(row["filed_path"]):
        raise VirtualScanError(f"This client's folder is now in {NMO_CAO_BOOK}, which takes no move. Nothing was moved: undo it by hand.")
    moved_to = ""
    note = ""
    try:
        if str(row["document_id"]).startswith(SCAN_PREFIX):
            moved_to = _move_back_to_scanned_docs(row["filed_path"], ctx.token())
        else:
            moved_to = _move_into_removed(ctx, row["filed_path"], ctx.token())
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        note = "The filed copy was not in the folder any more, so nothing was moved."
    for item_id in filter(None, str(row["billing_item_id"] or "").split(",")):
        billing_items.remove_item(item_id, by=who)
    stamp = _utc(now)
    back = str(row["document_id"]).startswith(SCAN_PREFIX)
    message = (note or (f"Moved {row['file_name']} back to Scanned Docs." if back else f"Moved {row['file_name']} into {REMOVED_FOLDER}.")) + (" The charge is off the bill (the Billing tab's Removed list can put it back)." if row["billing_item_id"] else " Nothing was billed." + (" A record made in Case flow stays." if back else ""))
    _mark_undone(row["scan_id"], who, moved_to, message[:300], stamp)
    _log(row["matter_id"], f"Virtual scanner: undid {row['file_name']}. {message}", who)
    return {**row, "status": "undone", "undone_by": who, "undone_utc": stamp, "moved_to": moved_to, "billing_note": message[:300], "message": message}


SCAN_PREFIX = "scan:"


def _document_filed(document_id: str) -> dict[str, Any] | None:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM matter_virtual_scans WHERE document_id = ? AND status = 'filed'",
            (document_id,),
        )
        rows = _rows(cursor)
    return _scan_view(rows[0]) if rows else None


def _same_contents(item: dict[str, Any], folder_items: list[dict[str, Any]]) -> str:
    "The name of a file in ``folder_items`` with the same contents as ``item`` (the drive's own content"
    from scanned_docs import scan_rows

    mine = scan_rows._content_hash(item)
    if not mine:
        return ""
    return next((str(i.get("name") or "") for i in folder_items if "file" in i and scan_rows._content_hash(i) == mine), "")


def _free_name(name: str, taken: set[str]) -> str:
    "`name`, or with \" (2)\", \" (3)\" ... before the \" - SURNAME\" tail (or the extension), never a taken one."
    if name.lower() not in taken:
        return name
    stem, dot, ext = name.rpartition(".")
    stem, ext = (stem, dot + ext) if dot else (name, "")
    head, sep, tail = stem.rpartition(" - ")
    for n in range(2, MAX_SUFFIX + 1):
        candidate = (f"{head} ({n}){sep}{tail}" if sep else f"{stem} ({n})") + ext
        if candidate.lower() not in taken:
            return candidate
    raise VirtualScanError(f"Every name up to ({MAX_SUFFIX}) is taken in that folder. Nothing was moved.")


def move_gated(source: str, target: str, token: str) -> dict[str, Any]:
    "`graph_files.move_item` with the owner-approved move gate on for this one call only. Also the move the"
    import graph_files

    before = os.environ.get("CASEFORGE_GRAPH_FILE_MOVE_APPROVED")
    os.environ["CASEFORGE_GRAPH_FILE_MOVE_APPROVED"] = "1"
    try:
        return graph_files.move_item(source, target, token) or {}
    finally:
        if before is None:
            os.environ.pop("CASEFORGE_GRAPH_FILE_MOVE_APPROVED", None)
        else:
            os.environ["CASEFORGE_GRAPH_FILE_MOVE_APPROVED"] = before


def _record_order(mid: str, scan: dict[str, Any], who: str, confirm: bool, kind: str) -> dict[str, Any] | None:
    "Hand a filed scan that is a court order to Case flow (the ``court_reply`` step, the court's reply); None for anything"
    from onboarding import pipeline
    from scanned_docs import scan_resolver

    if kind != "order" and scan_resolver.classify_scan(scan["file_name"]) != "order":
        return None
    try:
        return pipeline.record_scanned_order(mid, scan["filed_path"], who, confirm=confirm, ctx=_context(mid))
    except (pipeline.PipelineError, VirtualScanError) as exc:
        return {"ok": False, "needs_confirm": False, "message": f"Case flow was not told: {exc}"}


def confirm_scan(item_id: str, matter_id: Any, copies: Any, by: str, *, confirm: bool = False, kind: str = "", now: dt.datetime | None = None) -> dict[str, Any]:
    "Confirm a scan waiting in Scanned Docs belongs to this client: MOVE it (not copy) into the client's"
    import graph_files

    from onboarding.pipeline import court_common as cc
    from scanned_docs import scan_rows

    mid = str(_matter_number(matter_id))
    who = _clean(by, 200)
    if not who:
        raise VirtualScanError("Type your name first.")
    n_copies = check_copies(copies)
    item = _clean(item_id, 200)
    if not item:
        raise VirtualScanError("Pick a scan to confirm.")
    document_id = f"{SCAN_PREFIX}{item}"
    earlier = _document_filed(document_id)
    if earlier:
        if str(earlier["matter_id"]) != mid:
            return {**earlier, "already": True, "case_flow": None,
                    "message": f"Already filed for matter {earlier['matter_id']}: {earlier['file_name']}. Nothing was moved."}
        flow = _record_order(mid, earlier, who, confirm, kind) if confirm else None
        return {**earlier, "already": True, "case_flow": flow, "message": f"Already filed for this client: {earlier['file_name']}. Nothing was moved."}
    ctx = _context(mid)
    if not ctx.folder_path:
        raise VirtualScanError("This client has no folder recorded. Nothing was moved.")
    folder = cc.court_orders_folder(ctx)
    if not folder:
        raise VirtualScanError(
            f"There is no single Court-Orders folder for {ctx.surname or 'this client'} to file into. "
            f"Make the folders first (Case flow {_step_ref('folder')}). Nothing was moved."
        )
    if read_only_folder(folder) or read_only_folder(ctx.folder_path):
        raise VirtualScanError(GUARD_REFUSED)
    token = ctx.token()
    source_folder = scan_rows.scanned_docs_path()
    listing = graph_files.list_children(source_folder, access_token=token).get("value", [])
    found = next((i for i in listing if str(i.get("id") or "") == item and "file" in i), None)
    if not found:
        raise VirtualScanError("That scan is no longer waiting in Scanned Docs. Refresh the list.")
    name = str(found.get("name") or "")
    filed_now = graph_files.list_children(folder, access_token=token).get("value", [])
    same = _same_contents(found, filed_now)
    if same:
        where = folder.rsplit("/", 1)[-1]
        return {"already": True, "case_flow": None, "matter_id": mid, "file_name": same,
                "message": f"Already in {where} as {same}: the same file, byte for byte. Nothing was moved, recorded or billed."}
    taken = {str(i.get("name") or "").lower() for i in filed_now}
    target_name = _free_name(name, taken)
    try:
        moved = move_gated(f"{source_folder}/{name}", f"{folder}/{target_name}", token)
    except graph_files.GraphFileSafetyError as exc:
        raise VirtualScanError(GUARD_REFUSED) from exc
    date, _source = scan_rows.scan_date(name, found.get("createdDateTime"), found.get("lastModifiedDateTime"))
    day = date or _london_today().isoformat()
    filed_url = str(moved.get("webUrl") or found.get("webUrl") or "")
    sizes: dict[str, int | None] = {"pages": None, "text_chars": None}
    billing_item_id = ""
    try:
        with tempfile.TemporaryDirectory(prefix="scan-confirm-") as tmp:
            local = Path(tmp) / "scan.pdf"
            graph_files.download(f"{folder}/{target_name}", local, access_token=token)
            sizes = measure(local.read_bytes())
        billing_item_id, billing_note = bill_copies(mid, title_of(target_name)[:300], day, document_id, billing_plans(sizes["pages"], sizes["text_chars"]), n_copies, by=who, client_name=ctx.client_name, document_url=filed_url)
    except Exception as exc:
        billing_note = f"Filed, but not billed ({type(exc).__name__}): add the charge by hand."
    row = {
        "scan_id": uuid.uuid4().hex,
        "matter_id": int(mid),
        "document_id": document_id,
        "document_title": title_of(target_name)[:300],
        "date_received": day,
        "pressed_by": who,
        "pressed_utc": _utc(now),
        "filed_path": f"{folder}/{target_name}",
        "filed_url": filed_url,
        "billing_item_id": billing_item_id,
        "billing_note": billing_note[:300],
        "pages": sizes["pages"],
        "text_chars": sizes["text_chars"],
        "status": "filed",
        "undone_by": "",
        "undone_utc": None,
        "moved_to": "",
        "copies": n_copies,
    }
    try:
        _insert_scan(row)
    except Exception as exc:
        raise VirtualScanError(
            f"The scan was moved to {folder.rsplit('/', 1)[-1]} as {target_name} but could not be recorded ({type(exc).__name__}). Tell the owner."
        ) from exc
    where = folder.rsplit("/", 1)[-1]
    copy_word = "copy" if n_copies == 1 else "copies"
    _log(mid, f"Scanned Docs: moved {target_name} into {where}, {n_copies} {copy_word}. {billing_note}", who,
         [{"label": f"Open {target_name}", "url": row["filed_url"]}] if row["filed_url"].startswith("https://") else None)
    view = _scan_view(row)
    flow = _record_order(mid, view, who, confirm, kind)
    message = f"Filed {target_name} in {where} ({n_copies} {copy_word}). {billing_note}"
    if flow:
        message += " " + str(flow.get("message") or "")
    return {**view, "already": False, "message": message, "case_flow": flow}


def scan_order(matter_id: Any, folder: str, name: str, by: str, *, confirm: bool = False) -> dict[str, Any]:
    "Scan order, on the client's Scanner tab: a scanned order already in one of the client's Court-Orders"
    from onboarding import pipeline

    mid = str(_matter_number(matter_id))
    who = _clean(by, 200)
    if not who:
        raise VirtualScanError("Type your name first.")
    clean_folder, clean_name = str(folder or "").strip(), str(name or "").strip()
    if not clean_folder or not clean_name or "/" in clean_folder or "/" in clean_name:
        raise VirtualScanError("Pick an order filed in the client's Court-Orders folder.")
    ctx = _context(mid)
    try:
        out = pipeline.record_scanned_order(mid, f"{ctx.folder_path}/{clean_folder}/{clean_name}", who, confirm=confirm, ctx=ctx)
    except pipeline.PipelineError as exc:
        raise VirtualScanError(str(exc)) from exc
    return out


def reprice(*, apply: bool = False) -> list[dict[str, Any]]:
    "Once ``RECEIVED_DOCUMENT_CHAR_LIMIT`` is set: the TBC rows of filed scans that now have a"
    from billing import billing_items

    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(f"SELECT {', '.join(_COLUMNS)} FROM matter_virtual_scans WHERE status = 'filed' AND billing_item_id != ''")
        rows = [_scan_view(r) for r in _rows(cursor)]
    out = []
    for row in rows:
        plans = billing_plans(row["pages"], row["text_chars"])
        for copy, item_id in enumerate(filter(None, str(row["billing_item_id"]).split(",")), start=1):
            item = billing_items.get_item(item_id)
            if not item or item["category"] != billing_items.TBC_CATEGORY:
                continue
            plan = plans[0]
            done = False
            if apply and plan["category"] != "tbc":
                done = billing_items.settle_tbc_item(item_id, plan["category"], quantity=plan["quantity"])
                for extra in plans[1:]:
                    bill_scan(str(row["matter_id"]), row["document_title"], row["date_received"], work_id_for(row["document_id"], row["date_received"], copy), extra, by=ACTIVITY_MODE)
            out.append({"scan_id": row["scan_id"], "billing_item_id": item_id, "category": plan["category"], "note": plan["note"], "applied": done})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalogue", help="scan the live catalogue as JSON")
    rp = sub.add_parser("reprice", help="price TBC rows once the character limit is set")
    rp.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "catalogue":
        print(json.dumps(catalogue(), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(reprice(apply=args.apply), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
