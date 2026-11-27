#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Emu, Pt

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import graph_files

try:
    from usage.output_feedback import record_output
except Exception:
    record_output = None

try:
    from billing import billing_items
except Exception:
    billing_items = None


def _parse_time_minutes(value: str) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return 24
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*h", text)
    min_match = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
    if hour_match or min_match:
        hours = float(hour_match.group(1)) if hour_match else 0.0
        minutes = float(min_match.group(1)) if min_match else 0.0
        return int(round(hours * 60 + minutes))
    bare_number = re.search(r"(\d+(?:\.\d+)?)", text)
    if bare_number:
        return int(round(float(bare_number.group(1))))
    return 24


def _is_hourly(category: str) -> bool:
    if billing_items is None:
        return True
    return bool(getattr(billing_items, "CATEGORY_RATES", {}).get(category, (None, True))[1])


def _schedule(item: dict[str, Any], category: str) -> int | None:
    given = item.get("schedule")
    if given in (1, 2):
        return int(given)
    return 1 if _is_hourly(category) else None


def _record_billing_item(item: dict[str, Any], filename: str, document_url: str = "") -> str | None:
    if billing_items is None:
        return None
    if item.get("skip_billing"):
        return None
    matter_id = str(item.get("matter_id") or item.get("internal_ref") or item.get("case_ref", "")).strip()
    if not matter_id:
        return None
    category_key = str(item.get("billing_category") or "attendance_preparation").strip()
    work_id = str(item.get("billing_work_id") or "").strip()
    try:
        if work_id:
            existing = billing_items.item_id_for_work(matter_id, work_id, category_key)
            if existing:
                return existing
        row = billing_items.record_item(
            matter_id=matter_id,
            item_date=str(item.get("date", "")).strip(),
            category=category_key,
            description=str(item.get("billing_description") or "").strip()
            or f"Attendance note - {_note_type(item.get('attendance_type'))}",
            minutes=_parse_time_minutes(item.get("time", "24 mins")) if _is_hourly(category_key) else 0,
            quantity=item.get("billing_quantity") or 1,
            work_id=work_id,
            case_ref=str(item.get("internal_ref") or item.get("case_ref", "")).strip(),
            client_name=str(item.get("client_name", "")).strip(),
            source_file=filename,
            party=str(item.get("party") or "").strip(),
            document_url=document_url,
            schedule=_schedule(item, category_key),
        )
        return row.get("item_id")
    except Exception:
        return None


GRAPH = graph_files.GRAPH


def _require_env(name: str) -> str:
    return graph_files.require_env(name)


def _token() -> str:
    return graph_files.token()


def _graph_json(url: str, token: str, *, method: str = "GET", body: bytes | None = None) -> dict:
    return graph_files.graph_json(url, token, method=method, body=body)


def _graph_bytes(url: str, token: str) -> bytes:
    return graph_files.graph_bytes(url, token)


def _shared_drive_id(token: str) -> str:
    return graph_files.shared_drive_id(token)


def _personal_drive_id(token: str) -> str:
    return graph_files.personal_drive_id(token)


NOTE_TYPES = ("Attendance", "Perusal", "Preparation")

_LEGACY_TYPES = {"case perusal": "Perusal"}


def _note_type(value: Any) -> str:
    text = " ".join(str(value or "").split())
    for label in NOTE_TYPES:
        if text.lower() == label.lower():
            return label
    return _LEGACY_TYPES.get(text.lower(), "Attendance")


def _text_width(doc: Document) -> int:
    section = doc.sections[0]
    return int(section.page_width - section.left_margin - section.right_margin)


def _build_docx(output: Path, item: dict[str, Any]) -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    header = doc.add_paragraph()
    header_run = header.add_run("ATTENDANCE NOTE")
    header_run.bold = True

    internal_ref = str(item.get("internal_ref") or item.get("case_ref", "")).strip()
    table = doc.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = f"Client: {str(item['client_name']).strip()}"
    table.cell(0, 1).text = f"Case Ref: {internal_ref}"
    table.cell(1, 0).text = f"Time Engaged: {str(item.get('time', '24 mins')).strip()}"
    table.cell(1, 1).text = f"Tel: {str(item.get('phone', '')).strip()}"
    table.cell(2, 0).text = f"Matter: {str(item.get('matter', '')).strip()}"
    table.cell(2, 1).text = f"Date: {str(item['date']).strip()}"

    type_table = doc.add_table(rows=1, cols=len(NOTE_TYPES))
    type_table.style = "Table Grid"
    type_table.autofit = False
    marked = _note_type(item.get("attendance_type"))
    box_width = Emu(int(_text_width(doc) / len(NOTE_TYPES)))
    for label, column, cell in zip(NOTE_TYPES, type_table.columns, type_table.rows[0].cells):
        column.width = box_width
        cell.width = box_width
        mark = "x" if label == marked else "  "
        cell.text = f"{label} [{mark}]"

    doc.add_paragraph("")
    _add_body(doc, item)

    doc.save(output)


STRUCTURED_BODY_FIELDS = [
    ("activity", "Activity"),
    ("instructions_received", "Instructions received / matters considered"),
    ("advice_given", "Advice given"),
    ("action_agreed", "Action agreed"),
]


ACTIVITY_TODO_FIELDS = [
    ("activity", "Activity"),
    ("to_do", "To do"),
]
ACTIVITY_TODO_TYPES = ("Perusal", "Preparation")


def is_activity_todo(item: dict[str, Any]) -> bool:
    return "to_do" in item or _note_type(item.get("attendance_type")) in ACTIVITY_TODO_TYPES


def _add_activity_todo(doc: Document, item: dict[str, Any]) -> None:
    activity = " ".join(
        text for text in (str(item.get(key) or "").strip() for key in ("activity", "instructions_received", "advice_given", "note"))
        if text and text.rstrip(".").lower() not in {"none", "n/a", "nil"}
    )
    to_do = str(item.get("to_do") or "").strip() or str(item.get("action_agreed") or "").strip()
    if to_do.rstrip(".").lower() in {"", "none", "none recorded", "n/a", "nil"}:
        to_do = "None."
    for (_key, label), value in zip(ACTIVITY_TODO_FIELDS, (activity or "None.", to_do)):
        heading = doc.add_paragraph()
        heading.add_run(f"{label}:").bold = True
        doc.add_paragraph(value)


def _add_body(doc: Document, item: dict[str, Any]) -> None:
    if is_activity_todo(item):
        _add_activity_todo(doc, item)
        return
    has_structured = any(item.get(key) for key, _label in STRUCTURED_BODY_FIELDS)
    if not has_structured:
        for para in str(item.get("note", "")).split("\n\n"):
            doc.add_paragraph(para.strip())
        return
    for key, label in STRUCTURED_BODY_FIELDS:
        value = str(item.get(key, "")).strip() or "None"
        heading = doc.add_paragraph()
        heading.add_run(f"{label}:").bold = True
        doc.add_paragraph(value)


def _safe_filename(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch not in '<>:"/\\|?*').strip()
    return cleaned or "Attendance Note.docx"


def _name_date(value: Any) -> str:
    text = str(value or "").strip()
    found = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2})", text)
    if not found:
        return text
    day, month, year = (int(part) for part in found.groups())
    return f"{year:02d}.{month}.{day}"


def _default_filename(item: dict[str, Any]) -> str:
    return _safe_filename(
        f"{_name_date(item['date'])}-AN-{item.get('caller', 'Client')}-"
        f"{item.get('description', 'Call')}-{str(item['surname']).upper()}.docx"
    )


MAX_NAME_SUFFIX = 9


def _is_name_conflict(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "409" in text or "namealreadyexists" in text or "already exists" in text


def _numbered_filename(filename: str, number: int) -> str:
    stem, dot, ext = filename.rpartition(".")
    return f"{stem}-{number}.{ext}" if dot else f"{filename}-{number}"


def _upload_once(
    token: str,
    default_drive_id: str,
    personal_drive_id: str,
    item: dict[str, Any],
    content: bytes,
    filename: str,
) -> dict:
    encoded_name = urllib.parse.quote(filename, safe="")
    target_drive = str(item.get("destination_drive_id", "")).strip()
    if not target_drive:
        drive_name = str(item.get("destination_drive", "")).strip().lower()
        target_drive = personal_drive_id if drive_name == "personal" else default_drive_id
    folder_id = str(item.get("destination_folder_id", "")).strip()
    destination_path = str(item.get("destination_path", "")).strip().replace("\\", "/").strip("/")
    conflict_query = "?@microsoft.graph.conflictBehavior=fail"
    if folder_id:
        url = f"{GRAPH}/drives/{target_drive}/items/{folder_id}:/{encoded_name}:/content{conflict_query}"
    elif destination_path:
        encoded_path = urllib.parse.quote(f"{destination_path}/{filename}", safe="/")
        url = f"{GRAPH}/drives/{target_drive}/root:/{encoded_path}:/content{conflict_query}"
    else:
        raise RuntimeError("Each item needs destination_folder_id or destination_path")
    return _graph_json(url, token, method="PUT", body=content)


def _upload(
    token: str,
    default_drive_id: str,
    personal_drive_id: str,
    item: dict[str, Any],
    content: bytes,
    filename: str,
) -> dict:
    for number in range(1, MAX_NAME_SUFFIX + 1):
        candidate = filename if number == 1 else _numbered_filename(filename, number)
        try:
            return _upload_once(token, default_drive_id, personal_drive_id, item, content, candidate)
        except Exception as exc:
            if not _is_name_conflict(exc) or number == MAX_NAME_SUFFIX:
                raise
    raise RuntimeError("unreachable")


def _load_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.payload_json:
        payload = json.loads(args.payload_json)
    else:
        payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("items", [payload])
    if not isinstance(payload, list):
        raise RuntimeError("Payload must be a JSON object, an items object, or a list")
    return [dict(item) for item in payload]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and upload attendance-note .docx files")
    parser.add_argument("--payload-file")
    parser.add_argument("--payload-json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.payload_file and not args.payload_json:
        parser.error("--payload-file or --payload-json is required")

    token = _token()
    drive_id = _shared_drive_id(token)
    personal_drive_id = _personal_drive_id(token)
    items = _load_items(args)
    results = []
    with tempfile.TemporaryDirectory(prefix="caseforge-an-") as tmp:
        tmp_path = Path(tmp)
        for index, item in enumerate(items, start=1):
            filename = _safe_filename(str(item.get("filename") or _default_filename(item)))
            output = tmp_path / f"{index}-{filename}"
            _build_docx(output, item)
            if args.dry_run:
                results.append({"filename": filename, "bytes": output.stat().st_size, "dry_run": True})
                continue
            try:
                uploaded = _upload(token, drive_id, personal_drive_id, item, output.read_bytes(), filename)
            except Exception as exc:
                results.append({"filename": filename, "error": str(exc)[:600]})
                continue
            filename = str(uploaded.get("name") or filename)
            result_row = {
                "filename": filename,
                "id": uploaded.get("id"),
                "webUrl": graph_files.short_link_for_item(uploaded),
                "parentReference": uploaded.get("parentReference", {}),
            }
            if record_output is not None:
                try:
                    result_row["output_id"] = record_output(
                        {
                            "artefact_type": "attendance_note",
                            "client_name": str(item.get("client_name", "")).strip(),
                            "matter_ref": str(item.get("internal_ref") or item.get("case_ref", "")).strip(),
                            "path_or_message_id": str(uploaded.get("id", "")).strip(),
                            "template_used": "create-attendance-note.py house-structure build",
                            "title_or_subject": filename,
                            "prompt_summary": "attendance note creation",
                            "agent_version": "create-attendance-note.py",
                            "metadata": {"webUrl": uploaded.get("webUrl", "")},
                        }
                    )
                except Exception:
                    pass
            billing_item_id = _record_billing_item(item, filename, str(result_row.get("webUrl") or ""))
            if billing_item_id:
                result_row["billing_item_id"] = billing_item_id
            results.append(result_row)
    print(json.dumps({"created": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
