#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from graph_mail_safe_ops import GraphClient, _must
from hearing_calendar.hearing_dates import short_date


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
TELEMETRY_DIR = REPO_ROOT / "telemetry"
INDEX_PATH = TELEMETRY_DIR / "saved-email-thread-index.json"
PRINT_SCRIPT = TOOLS_DIR / "documents" / "print_email_to_pdf.py"


def _bootstrap_val_env() -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from env_bootstrap import load_repo_secrets

        load_repo_secrets()
    except Exception:
        pass

def parse_args() -> argparse.Namespace:
    _bootstrap_val_env()
    parser = argparse.ArgumentParser(
        description=(
            "Catch up a matter thread from Inbox and Sent Items and save matching "
            "emails to PDF with continuous numbering."
        )
    )
    parser.add_argument("--tenant-id", default=os.getenv("GRAPH_TENANT_ID", ""))
    parser.add_argument("--client-id", default=os.getenv("GRAPH_MAIL_CLIENT_ID", os.getenv("GRAPH_CLIENT_ID", "")))
    parser.add_argument(
        "--client-secret",
        default=os.getenv("GRAPH_MAIL_CLIENT_SECRET", os.getenv("GRAPH_CLIENT_SECRET", "")),
    )
    parser.add_argument("--mailbox-upn", default=os.getenv("GRAPH_MAILBOX_UPN", ""))
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--retry-base-seconds", type=float, default=0.8)

    parser.add_argument("--output-folder", required=True, help="Target matter correspondence folder")
    parser.add_argument("--case-number", action="append", default=[], help="Case number match token (repeatable)")
    parser.add_argument("--alias", action="append", default=[], help="Name/email/subject token match (repeatable)")
    parser.add_argument("--surname-label", required=True, help="Filename suffix label, e.g. TASICH")
    parser.add_argument("--start-date", default="", help="Local date YYYY-MM-DD; default = 7 days ago")
    parser.add_argument("--top", type=int, default=150, help="Messages to inspect per folder")
    parser.add_argument("--dry-run", action="store_true", help="Show matched messages without printing")
    parser.add_argument("--chrome-path", default="", help="Optional browser path for PDF printing")
    parser.add_argument("--runtime-label", default=os.getenv("CASEFORGE_RUNTIME_LABEL", "codex"))
    parser.add_argument("--model-label", default=os.getenv("CASEFORGE_MODEL_LABEL", os.getenv("MODEL_NAME", "codex")))
    parser.add_argument("--client-name", default="", help="Client name for startup allow-list enforcement")
    parser.add_argument("--root-label", default="", help="Live root label, for example NMO-CAO or a worker's book")
    parser.add_argument("--allow-list", default="", help="Optional startup allow-list JSON path")
    parser.add_argument(
        "--enforce-startup-allow-list",
        action="store_true",
        help="Require the startup allow-list gate before printing PDFs",
    )
    return parser.parse_args()


def iso_start_utc(start_date: str) -> str:
    if start_date.strip():
        day = dt.date.fromisoformat(start_date.strip())
    else:
        day = dt.date.today() - dt.timedelta(days=7)
    stamp = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
    return stamp.isoformat().replace("+00:00", "Z")


def message_time(row: Dict[str, Any]) -> dt.datetime:
    direction = str(row.get("_direction", "")).strip().lower()
    if direction == "in":
        raw = str(row.get("receivedDateTime") or row.get("sentDateTime") or "").strip()
    else:
        raw = str(row.get("sentDateTime") or row.get("receivedDateTime") or "").strip()
    if not raw:
        return dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))


def recipients_blob(rows: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for row in rows or []:
        email = (row or {}).get("emailAddress") or {}
        name = str(email.get("name", "")).strip()
        address = str(email.get("address", "")).strip()
        if name:
            parts.append(name)
        if address:
            parts.append(address)
    return " ".join(parts)


def message_haystack(row: Dict[str, Any]) -> str:
    from_blob = recipients_blob([row.get("from") or {}])
    sender_blob = recipients_blob([row.get("sender") or {}])
    pieces = [
        str(row.get("subject", "")),
        str(row.get("bodyPreview", "")),
        from_blob,
        sender_blob,
        recipients_blob(row.get("toRecipients") or []),
        recipients_blob(row.get("ccRecipients") or []),
        recipients_blob(row.get("bccRecipients") or []),
        str(row.get("internetMessageId", "")),
        str(row.get("conversationId", "")),
    ]
    return " ".join(pieces).lower()


def clean_token(value: str) -> str:
    return value.replace("\xa0", " ").strip().lower()


def subject_stem(subject: str) -> str:
    text = subject.replace("\xa0", " ").strip()
    while True:
        updated = re.sub(r"^(re|fw|fwd):\s*", "", text, flags=re.IGNORECASE)
        if updated == text:
            break
        text = updated.strip()
    if not text:
        text = "email"
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.lower()).strip("-")
    if not text:
        text = "email"
    return text[:70].strip("-") or "email"


def next_sequence_number(output_folder: Path) -> int:
    highest = 0
    if not output_folder.exists():
        return 1
    for item in output_folder.iterdir():
        if not item.is_file():
            continue
        match = re.match(r"^(\d+)(?:\.\s|\[(?:in|out)\]|-(?:in|out|mail)-\d{2}\.\d{1,2}\.\d{1,2}-)", item.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def load_index() -> Dict[str, Any]:
    if not INDEX_PATH.exists():
        return {"version": 1, "entries": {}}
    try:
        payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "entries": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "entries": {}}
    payload.setdefault("version", 1)
    payload.setdefault("entries", {})
    if not isinstance(payload["entries"], dict):
        payload["entries"] = {}
    return payload


def save_index(payload: Dict[str, Any]) -> None:
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    temp = INDEX_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(INDEX_PATH)


def index_key(output_folder: Path, row: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(output_folder).lower(),
            str(row.get("internetMessageId", "")).strip().lower(),
            str(row.get("id", "")).strip().lower(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def indexed_as_saved(index_payload: Dict[str, Any], output_folder: Path, row: Dict[str, Any]) -> bool:
    entry = index_payload.get("entries", {}).get(index_key(output_folder, row))
    if not isinstance(entry, dict):
        return False
    pdf_path = Path(str(entry.get("pdf_path", "")).strip())
    return pdf_path.exists()


def folder_query(
    client: GraphClient,
    folder_name: str,
    order_by: str,
    filter_expr: str,
    top: int,
) -> List[Dict[str, Any]]:
    payload = client.graph(
        "GET",
        client.mailbox_path(f"/mailFolders/{folder_name}/messages"),
        params={
            "$top": str(max(1, top)),
            "$orderby": order_by,
            "$select": (
                "id,subject,receivedDateTime,sentDateTime,from,sender,toRecipients,"
                "ccRecipients,bccRecipients,hasAttachments,internetMessageId,"
                "conversationId,webLink,bodyPreview"
            ),
            "$filter": filter_expr,
        },
    )
    rows = payload.get("value", []) or []
    return [row for row in rows if isinstance(row, dict)]


def collect_candidates(client: GraphClient, start_iso_utc: str, top: int) -> List[Dict[str, Any]]:
    inbox = folder_query(client, "inbox", "receivedDateTime desc", f"receivedDateTime ge {start_iso_utc}", top)
    sent = folder_query(client, "sentitems", "sentDateTime desc", f"sentDateTime ge {start_iso_utc}", top)
    rows: List[Dict[str, Any]] = []
    for row in inbox:
        copy = dict(row)
        copy["_folder"] = "inbox"
        copy["_direction"] = "in"
        rows.append(copy)
    for row in sent:
        copy = dict(row)
        copy["_folder"] = "sentitems"
        copy["_direction"] = "out"
        rows.append(copy)
    by_id: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        by_id[str(row.get("id", "")).strip()] = row
    return sorted(by_id.values(), key=message_time)


def filter_candidates(rows: Iterable[Dict[str, Any]], needles: Sequence[str]) -> List[Dict[str, Any]]:
    active_needles = [clean_token(value) for value in needles if clean_token(value)]
    if not active_needles:
        return list(rows)
    matched: List[Dict[str, Any]] = []
    for row in rows:
        haystack = message_haystack(row)
        if any(needle in haystack for needle in active_needles):
            matched.append(row)
    return matched


def build_filename(seq: int, row: Dict[str, Any], surname_label: str) -> str:
    moment = message_time(row).astimezone()
    stem = subject_stem(str(row.get("subject", "")))
    direction = str(row.get("_direction", "mail")).lower()
    return f"{seq}-{direction}-{short_date(moment.date())}-{moment:%H%M}-{stem}-{surname_label}.pdf"


def run_print(
    message_id: str,
    output_pdf: Path,
    chrome_path: str,
    runtime_label: str,
    model_label: str,
    client_name: str = "",
    root_label: str = "",
    allow_list: str = "",
    enforce_startup_allow_list: bool = False,
) -> None:
    command = [
        sys.executable,
        str(PRINT_SCRIPT),
        "--message-id", message_id,
        "--output", str(output_pdf),
    ]
    if chrome_path.strip():
        command.extend(["--browser-path", chrome_path.strip()])
    if client_name.strip():
        command.extend(["--matter-id", client_name.strip()])
    subprocess.run(command, check=True, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)


def log_run(
    output_folder: Path,
    written_files: Sequence[Path],
    runtime_label: str,
    model_label: str,
    command_text: str,
) -> None:
    telemetry_script = TOOLS_DIR / "telemetry_sqlite.py"
    if not telemetry_script.exists():
        return
    try:
        args_list = [
            sys.executable, str(telemetry_script),
            "log",
            "--event-name", "save-matter-email-thread",
            "--command", command_text,
            "--files-read", str(Path(__file__)),
            "--files-written", *[str(p) for p in written_files],
        ]
        if runtime_label:
            args_list += ["--runtime-label", runtime_label]
        if model_label:
            args_list += ["--model-label", model_label]
        subprocess.run(args_list, check=False, cwd=str(REPO_ROOT), capture_output=True, timeout=120)
    except Exception:
        pass


def main() -> int:
    args = parse_args()

    output_folder = Path(args.output_folder).expanduser()
    output_folder.mkdir(parents=True, exist_ok=True)

    client = GraphClient(
        tenant_id=_must(args.tenant_id, "GRAPH_TENANT_ID / --tenant-id"),
        client_id=_must(args.client_id, "GRAPH_MAIL_CLIENT_ID or GRAPH_CLIENT_ID / --client-id"),
        client_secret=_must(args.client_secret, "GRAPH_MAIL_CLIENT_SECRET or GRAPH_CLIENT_SECRET / --client-secret"),
        mailbox_upn=_must(args.mailbox_upn, "GRAPH_MAILBOX_UPN / --mailbox-upn"),
        max_retries=max(0, int(args.max_retries)),
        retry_base_seconds=max(0.1, float(args.retry_base_seconds)),
    )

    start_iso = iso_start_utc(args.start_date)
    needles = list(args.case_number) + list(args.alias)
    rows = collect_candidates(client, start_iso, args.top)
    matched = filter_candidates(rows, needles)
    index_payload = load_index()

    results: List[Dict[str, Any]] = []
    sequence = next_sequence_number(output_folder)
    written_files: List[Path] = []

    for row in matched:
        already_saved = indexed_as_saved(index_payload, output_folder, row)
        filename = build_filename(sequence, row, args.surname_label)
        output_pdf = output_folder / filename
        result = {
            "direction": row.get("_direction"),
            "time": message_time(row).astimezone().isoformat(),
            "subject": row.get("subject", ""),
            "from": ((row.get("from") or {}).get("emailAddress") or {}).get("address", ""),
            "to": [((item.get("emailAddress") or {}).get("address", "")) for item in (row.get("toRecipients") or [])],
            "message_id": row.get("id", ""),
            "internet_message_id": row.get("internetMessageId", ""),
            "has_attachments": bool(row.get("hasAttachments", False)),
            "already_saved": already_saved,
            "suggested_pdf": str(output_pdf),
        }
        results.append(result)
        if already_saved or args.dry_run:
            if args.dry_run and not already_saved:
                sequence += 1
            continue

        run_print(
            message_id=str(row.get("id", "")).strip(),
            output_pdf=output_pdf,
            chrome_path=args.chrome_path,
            runtime_label=args.runtime_label,
            model_label=args.model_label,
            client_name=args.client_name,
            root_label=args.root_label,
            allow_list=args.allow_list,
            enforce_startup_allow_list=args.enforce_startup_allow_list,
        )
        written_files.append(output_pdf)
        index_payload["entries"][index_key(output_folder, row)] = {
            "saved_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "pdf_path": str(output_pdf),
            "folder": str(output_folder),
            "subject": str(row.get("subject", "")),
            "internet_message_id": str(row.get("internetMessageId", "")),
            "message_id": str(row.get("id", "")),
        }
        sequence += 1

    if written_files:
        save_index(index_payload)
        log_run(
            output_folder=output_folder,
            written_files=[INDEX_PATH, *written_files],
            runtime_label=args.runtime_label,
            model_label=args.model_label,
            command_text=" ".join(sys.argv),
        )

    print(json.dumps({"start_iso_utc": start_iso, "matched_count": len(results), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
