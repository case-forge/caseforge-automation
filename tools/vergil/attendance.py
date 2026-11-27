from __future__ import annotations

import datetime as dt
import importlib.util
import re
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import graph_files
import agwu
import matter_orders
from documents.order_text_case import normalise_order_text
from vergil.client_search import client_candidate_label
from vergil.formatting import (
    ATTENDANCE_SWITCHBOARD_CALLERS,
    clean_markdown_cell,
    parse_attendance_switchboard_shorthand,
    parse_backdate,
)
from vergil.primitives import REPO_ROOT, normalise_space, prompt_lower, ttl_cache
from vergil.prompt_routing import looks_like_client_care_letter_request
from vergil.user_state import is_guest

ATTENDANCE_CALL_FAQ = REPO_ROOT / "context" / "Attendance-Call-FAQ.md"


def attendance_note_caller_from_prompt(prompt: str) -> str:
    switch = parse_attendance_switchboard_shorthand(prompt)
    return str(switch.get("caller") or "Client")


def extract_attendance_caller_name(note: str) -> str:
    m = re.search(r"\bCaller name:\s*([^.\n]+)", str(note or ""), flags=re.I)
    return normalise_space(m.group(1)) if m else ""


def looks_like_attendance_note_request(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return (
        "attendance note" in text
        or re.search(r"\bmake\s+an?\s+an\b", text) is not None
        or re.search(r"\bcreate\s+an?\s+an\b", text) is not None
        or bool(parse_attendance_switchboard_shorthand(prompt))
    )


def extract_attendance_note_request(prompt: str) -> tuple[str, str]:
    raw_lines = [l.strip() for l in prompt.splitlines()]
    name = ""
    note_lines: list[str] = []

    _SKIP_KEYWORDS = ("attendance note", "tasks/", "agent.md", "make an", "create an", "backdate", "if the", "re-ask")

    for i, line in enumerate(raw_lines):
        switch = parse_attendance_switchboard_shorthand(line)
        if switch:
            name = str(switch.get("client") or "").strip()
            note_lines = raw_lines[i:]
            break
        m = re.search(r"(?:CLIENTNAME|\[client name\])\s*[—-]\s*(.+)", line, flags=re.I)
        if m:
            name = m.group(1).strip()
            note_lines = raw_lines[i + 1 :]
            break
        m = re.search(r"^\[([^\]]+)\]\s*[—\-]", line)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in ("client name", "name") and 1 <= len(candidate.split()) <= 5:
                name = candidate
                note_lines = raw_lines[i + 1 :]
                break
        m = re.search(r"(?:attendance note|make an? an|create an? an)\s+for\s+([^—\-\n]+?)(?:\s*[—\-]\s*(.+))?$", line, flags=re.I)
        if m:
            candidate = m.group(1).strip(" :-.")
            if "[" not in candidate and len(candidate.split()) <= 5:
                name = candidate
                rest = (m.group(2) or "").strip()
                note_lines = ([rest] if rest else []) + raw_lines[i + 1 :]
                break
        m = re.match(r"^([A-Za-z][^—\-\n]{1,40})\s*[—\-]", line)
        if m and not any(k in line.lower() for k in _SKIP_KEYWORDS):
            candidate = m.group(1).strip()
            if 1 < len(candidate.split()) <= 5 and "[" not in candidate:
                name = candidate
                note_lines = raw_lines[i + 1 :]
                break

    if not name:
        text = normalise_space(prompt)
        m = re.search(r"(?:attendance note|make an? an|create an? an)\s+for\s+([^—\-.]+)", text, flags=re.I)
        if m:
            candidate = m.group(1).strip(" :-.")
            candidate = re.sub(r"^\[|\]$", "", candidate).strip()
            name = candidate
        note_lines = []

    name = re.sub(r"^\[|\]$", "", name).strip()
    note = normalise_space(" ".join(note_lines)) if note_lines else normalise_space(prompt)
    return name, note


def load_attendance_note_tool():
    tool_path = REPO_ROOT / "tools" / "documents" / "create-attendance-note.py"
    spec = importlib.util.spec_from_file_location("caseforge_create_attendance_note", tool_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Attendance-note tool could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_attendance_note_row(
    rows: list[dict], client_query: str, *, was_fuzzy_resolved: bool = False
) -> tuple[dict, str]:
    if not rows:
        return {}, ""
    by_key: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("matter_id") or "").strip()
        if not key:
            key = "|".join(
                str(row.get(field) or "").strip().lower()
                for field in ("client_name", "matter_name", "company_reference")
            )
        by_key.setdefault(key, row)
    unique_rows = list(by_key.values())
    if len(unique_rows) == 1:
        if was_fuzzy_resolved:
            row = unique_rows[0]
            label = client_candidate_label(row)
            ref = str(row.get("company_reference") or "").strip()
            if ref:
                label = f"{label} - ref {ref}"
            return {}, (
                f"'{client_query}' didn't match a client directly. Closest guess: {label}. "
                "I have not created the attendance note. Confirm this is right, or give the CaseForge reference."
            )
        return unique_rows[0], ""

    query_norm = normalise_space(client_query).lower()
    exact_rows = [
        row for row in unique_rows
        if query_norm in {
            normalise_space(str(row.get("client_name") or "")).lower(),
            normalise_space(str(row.get("matter_name") or "")).lower(),
        }
    ]
    if len(exact_rows) == 1:
        return exact_rows[0], ""

    options = []
    for row in unique_rows[:6]:
        label = client_candidate_label(row)
        ref = str(row.get("company_reference") or "").strip()
        if ref:
            label = f"{label} - ref {ref}"
        options.append(f"- {label}")
    return {}, (
        f"I found more than one possible client for '{client_query}'. "
        "I have not created the attendance note. Please include the CaseForge reference or pick one:\n"
        + "\n".join(options)
    )


def choose_attendance_folder(children: list[dict], prompt: str) -> tuple[str, str]:
    matches = [
        item for item in children
        if item.get("folder") and "attendance" in str(item.get("name", "")).lower()
    ]
    if not matches:
        names = ", ".join(str(item.get("name", "")) for item in children[:12])
        raise RuntimeError(f"No attendance-note folder found in the live matter folder. Visible folders: {names}")
    lowered = prompt_lower(prompt)
    if any(token in lowered for token in ("non-mol", "non mol", "nmo", "fl401")):
        for item in matches:
            if "nmo" in str(item.get("name", "")).lower():
                return str(item["id"]), str(item.get("name") or "Attendance Notes")
    if any(token in lowered for token in ("cao", "c100", "pso", "fl404")):
        order_substrings = ("pso", "cao") if "pso" in lowered else ("cao", "pso")
        for substr in order_substrings:
            for item in matches:
                if substr in str(item.get("name", "")).lower():
                    return str(item["id"]), str(item.get("name") or "Attendance Notes")
    for order in ("nmo", "cao", "pso"):
        for item in matches:
            if order in str(item.get("name", "")).lower():
                return str(item["id"]), str(item.get("name") or "Attendance Notes")
    return str(matches[0]["id"]), str(matches[0].get("name") or "Attendance Notes")


def infer_an_fast_client_from_detail(extra_detail: str, candidates: list[dict]) -> str:
    detail = normalise_space(extra_detail).lower()
    if not detail:
        return ""
    for item in candidates:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if re.search(rf"\b{re.escape(name.lower())}\b", detail):
            return name
    for marker in (
        r"\bclient\s+([A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+){1,4})",
        r"\bfor\s+([A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+){1,4})",
        r"\bre\s+([A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+){1,4})",
        r"\babout\s+([A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+){1,4})",
    ):
        m = re.search(marker, extra_detail)
        if m:
            candidate = normalise_space(m.group(1))
            if candidate.lower() not in {"the client", "this matter"}:
                return candidate
    return ""


def looks_like_mixed_or_multi_attendance_workflow(prompt: str) -> bool:
    text = prompt_lower(prompt)
    if not looks_like_attendance_note_request(prompt):
        return False
    if looks_like_client_care_letter_request(prompt) or any(
        marker in text
        for marker in (
            "brief to counsel",
            "bundle",
            "statement of service",
            "email the court",
            "email counsel",
        )
    ):
        return True
    markers = re.findall(r"\b(?:attendance note|make\s+an?\s+an|create\s+an?\s+an|an\s*\d+|an\d+)\b", text)
    if len(markers) >= 2:
        return True
    return bool(re.search(r"\bthen\s+[a-z][a-z' -]{2,60}\.\s+(?:called|rang|wanted|asked)\b", text))


def draft_an_description(note: str, matter: str = "") -> str:
    low = note.lower()
    kind = "File Note" if any(t in low for t in ("email", "letter", "sent", "received", "correspondence")) else "Telephone Attendance"

    if any(t in low for t in ("breach", "breached", "violat")):
        action = "Breach"
    elif any(t in low for t in ("hearing", "court date", "listed for", "next hearing")):
        action = "Hearing"
    elif any(t in low for t in ("injunction", "order expir", "ran out", "expire")):
        action = "Injunction Expiry"
    elif any(t in low for t in ("application", "apply", "applied", "fl401", "c100", "issue proceedings")):
        action = "Application"
    elif any(t in low for t in ("service", "served", "bailiff", "process server")):
        action = "Service"
    elif any(t in low for t in ("police", "arrest", "caution", "crime report")):
        action = "Police Matter"
    elif any(t in low for t in ("legal aid", "laa", "merits", "certificate")):
        action = "Legal Aid"
    elif any(t in low for t in ("counsel", "barrister", "brief", "conference")):
        action = "Counsel"
    elif any(t in low for t in ("children", "child", "contact", "arrangement", "access")):
        action = "Children"
    else:
        action = "Advice"

    if matter and action != "Advice":
        subject = f"{matter} {action}"
    elif matter:
        subject = f"{matter} Advice"
    elif action != "Advice":
        subject = action
    else:
        subject = ""

    return f"{kind} - {subject}" if subject else kind


AN_VALID_CALLERS = {
    "client", "court", "counsel", "referralpartner", "solace", "respondent", "solicitor",
    "ncdv", "chambers", "other", "barrister", "police", "social services",
}
AN_VALID_ORDERS = {
    "nmo", "cao", "pso", "sio", "oo", "nmo-cao", "nmo-pso", "cao-pso",
    "nmo-cao-pso", "nmo-pso-cao", "pso-cao", "sio-nmo", "nmo-sio",
}
AN_COURT_REF_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]\d{5}$")
AN_CASEFORGE_REF_RE = re.compile(r"^(?:\d{6}/\d{2}[A-Z]{2}|[A-Z]{2}/[A-Z0-9]+/\d{6}/\d+[A-Z]{2})$")
AN_LEGAL_PHRASES = [
    r"would ordinarily be directed",
    r"as a matter of law",
    r"it is submitted",
    r"the court will",
    r"it should be noted that",
    r"legally speaking",
]
AN_FILENAME_RE = re.compile(
    r"^(?:AN\(\d{2}\.\d{2}\.\d{2}\)\([^)]+\)|\d{2}\.\d{1,2}\.\d{1,2}-AN-[^-]+)-[^-].+-[A-Z][A-Z\-]+\.docx$"
)


def lint_an_item(item: dict, filename: str) -> list[str]:
    issues = []
    required = ("client_name", "internal_ref", "phone", "caller", "matter", "note", "date")
    for f in required:
        if not str(item.get(f) or "").strip():
            issues.append(f"MISSING_FIELD: '{f}' is empty")

    ref = str(item.get("internal_ref") or "").strip()
    if ref:
        if AN_COURT_REF_RE.match(ref):
            issues.append(f"COURT_REF: '{ref}' looks like a court case number — use CaseForge internal reference")
        elif not AN_CASEFORGE_REF_RE.match(ref):
            issues.append(f"REF_FORMAT: '{ref}' does not match expected NNNNNN/NNFL format")

    phone = str(item.get("phone") or "").strip()
    if phone:
        digits = re.sub(r"\D", "", phone)
        if not (10 <= len(digits) <= 13):
            issues.append(f"PHONE_FORMAT: '{phone}' — expected 10-13 digits for a UK number")

    caller = str(item.get("caller") or "").strip()
    if caller and caller.lower() not in AN_VALID_CALLERS:
        issues.append(f"INVALID_CALLER: '{caller}' — use: Client, Court, Counsel, Barrister, etc.")

    matter = str(item.get("matter") or "").strip()
    if matter and matter.lower() not in AN_VALID_ORDERS:
        issues.append(f"UNKNOWN_ORDER_TYPE: '{matter}' — expected: NMO, CAO, PSO, SIO, OO or combinations")

    note = str(item.get("note") or "").strip()
    word_count = len(note.split()) if note else 0
    if word_count < 15:
        issues.append(f"EMPTY_BODY: body has {word_count} words — attendance note appears empty")
    elif word_count < 30:
        issues.append(f"SHORT_BODY: body has {word_count} words — check this is a complete record")

    for phrase in AN_LEGAL_PHRASES:
        if re.search(phrase, note, re.I):
            issues.append(f"LEGAL_COMMENTARY: body contains '{phrase}' — ANs are factual records only")
            break

    if not AN_FILENAME_RE.match(filename):
        issues.append(f"FILENAME_CONVENTION: '{filename}' — expected YY.MM.DD-AN-Caller-Description-SURNAME.docx")

    return issues


@ttl_cache(300)
def load_attendance_switchboards() -> dict[str, list[dict[str, str]]]:
    boards = {"Client": [], "External": []}
    try:
        text = ATTENDANCE_CALL_FAQ.read_text(encoding="utf-8")
    except Exception:
        return boards

    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## Client Switchboard"):
            section = "Client"
            continue
        if line.startswith("## External Switchboard"):
            section = "External"
            continue
        if line.startswith("## "):
            section = ""
            continue
        if not section or not line.startswith("|"):
            continue
        cells = [clean_markdown_cell(cell) for cell in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() == "code" or set(cells[0]) <= {"-"}:
            continue
        code = cells[0].strip()
        if not re.fullmatch(r"\d", code):
            continue
        boards[section].append(
            {
                "code": code,
                "query": cells[1],
                "wording": cells[2],
            }
        )
    return boards

def attendance_switchboard_entries_for_caller(caller: str) -> list[dict[str, str]]:
    caller = ATTENDANCE_SWITCHBOARD_CALLERS.get(str(caller or "").strip().lower(), "Client")
    board_name = "Client" if caller == "Client" else "External"
    return list(load_attendance_switchboards().get(board_name) or [])

def attendance_switchboard_wording(caller: str, codes: list[str]) -> str:
    entries = attendance_switchboard_entries_for_caller(caller)
    by_code = {str(item.get("code")): str(item.get("wording") or "").strip() for item in entries}
    parts: list[str] = []
    for code in codes:
        wording = by_code.get(str(code), "")
        if wording and wording not in parts:
            parts.append(wording)
    return " ".join(parts)

def draft_attendance_note_body(note: str, caller: str = "Client") -> str:
    cleaned = normalise_space(note)
    caller_name = extract_attendance_caller_name(cleaned)
    caller_prefix = f"Telephone attendance with {caller}"
    if caller_name and caller.lower() != "client":
        caller_prefix += f" ({caller_name})"
    caller_prefix += "."
    cleaned = re.sub(r"\bCaller name:\s*[^.]+\.?", "", cleaned, flags=re.I).strip()
    switch = parse_attendance_switchboard_shorthand(note)
    if switch:
        caller = str(switch.get("caller") or caller or "Client")
        caller_prefix = f"Telephone attendance with {caller}"
        if caller_name and caller.lower() != "client":
            caller_prefix += f" ({caller_name})"
        caller_prefix += "."
        codes = [str(code) for code in (switch.get("codes") or [])]
        wording = attendance_switchboard_wording(caller, codes)
        if wording:
            extra = cleaned.replace(str(switch.get("line") or ""), "", 1).strip()
            extra = re.sub(r"\bCaller name:\s*[^.]+\.?", "", extra, flags=re.I).strip()
            extra = re.sub(r"^extra detail:\s*", "", extra, flags=re.I).strip()
            extra = re.sub(
                r"[\s\.]*(?:this\s+an?\s+is\s+from\b|backdate\s+(?:it\s+)?(?:to|this)\b|this\s+is\s+from\b|from\s+(?:last\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b).+$",
                "",
                extra,
                flags=re.I | re.DOTALL,
            ).strip()
            if extra:
                wording = f"{wording} {extra[0].upper() + extra[1:] if extra else extra}"
            return f"{caller_prefix} {wording}"
    if not cleaned:
        return f"{caller_prefix} Caller called to discuss the matter. Advice and next steps were discussed."
    cleaned = re.sub(
        r"[\s\.]*(?:this\s+an?\s+is\s+from\b|backdate\s+(?:it\s+)?(?:to|this)\b|this\s+is\s+from\b|from\s+(?:last\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b).+$",
        "",
        cleaned,
        flags=re.I | re.DOTALL,
    ).strip()
    cleaned = re.sub(r"\bR\b", "Respondent", cleaned)
    cleaned = cleaned.replace("so longas", "so long as")
    cleaned = cleaned.replace("asjed wgether", "asked whether")
    cleaned = cleaned.replace("mumber", "number")
    cleaned = cleaned.replace("porta Ventura", "Fuerteventura")
    return f"{caller_prefix} {cleaned[0].upper() + cleaned[1:] if cleaned else cleaned}"


def attendance_note_link(filename: str, uploaded: dict) -> str:
    web_url = graph_files.short_link_for_item(uploaded)
    return f"[{filename}]({web_url})" if web_url else filename


def build_attendance_note_response(prompt: str, username: str | None) -> str:
    from vergil.graph_folders import (
        cache_verified_folder_location,
        extract_graph_matter_snapshot,
        find_attendance_folder,
        find_attendance_folder_location_by_search,
        lookup_cached_folder_location,
        normalise_matter_folder_path,
    )

    if is_guest(username):
        return "Ask a supervisor."
    client_query, raw_note = extract_attendance_note_request(prompt)
    if len(client_query) < 2:
        return "Tell me the client name and the call note."

    try:
        tool = load_attendance_note_tool()
        token = tool._token()
        shared_drive_id = tool._shared_drive_id(token)
        personal_drive_id = tool._personal_drive_id(token)
        try:
            _result = agwu.resolve_client(client_query, limit=5, caller="vergil.attendance.build_attendance_note_response")
            rows, display_query = [m.row for m in _result.matches], _result.display_query
            _was_exact = bool(_result.top and "exact_search" in _result.top.match_sources)
        except Exception:
            rows = []
            display_query = client_query
            _was_exact = False

        if rows:
            row, ambiguity = select_attendance_note_row(
                rows, client_query, was_fuzzy_resolved=not _was_exact
            )
            if ambiguity:
                return ambiguity
        else:
            row = extract_graph_matter_snapshot(tool, token, shared_drive_id, client_query, prompt)
        client_name = str(row.get("client_name") or row.get("matter_name") or client_query).strip()
        internal_ref = str(row.get("company_reference") or row.get("case_reference") or "").strip()
        matter_path = normalise_matter_folder_path(str(row.get("live_matter_folder") or ""))
        folder_id = str(row.get("attendance_folder_id") or "").strip()
        folder_name = str(row.get("attendance_folder_name") or "").strip()
        cached_location = lookup_cached_folder_location(row, client_name)
        if cached_location:
            matter_path = matter_path or normalise_matter_folder_path(str(cached_location.get("matter_folder_path") or ""))
            folder_id = folder_id or str(cached_location.get("attendance_folder_id") or "").strip()
            folder_name = folder_name or str(cached_location.get("attendance_folder_name") or "").strip()
        if not folder_id:
            if not matter_path:
                row = extract_graph_matter_snapshot(tool, token, shared_drive_id, client_name, prompt)
                internal_ref = internal_ref or str(row.get("company_reference") or row.get("case_reference") or "").strip()
                folder_id = str(row.get("attendance_folder_id") or "").strip()
                folder_name = str(row.get("attendance_folder_name") or "").strip()
                matter_path = normalise_matter_folder_path(str(row.get("live_matter_folder") or ""))
            else:
                try:
                    folder_id, folder_name = find_attendance_folder(tool, token, shared_drive_id, matter_path, prompt)
                    cache_verified_folder_location(
                        row,
                        drive_id=shared_drive_id,
                        matter_path=matter_path,
                        attendance_folder_id=folder_id,
                        attendance_folder_name=folder_name,
                    )
                except Exception:
                    matter_folder, folder_id, folder_name = find_attendance_folder_location_by_search(
                        tool, token, shared_drive_id, client_name, prompt
                    )
                    cache_verified_folder_location(
                        row,
                        drive_id=shared_drive_id,
                        matter_folder=matter_folder,
                        attendance_folder_id=folder_id,
                        attendance_folder_name=folder_name,
                    )
        if not internal_ref:
            return f"Found {client_name}, but the internal CaseForge reference is missing. I have not created the AN."
        backdate = parse_backdate(prompt)
        if backdate:
            london_now = dt.datetime.combine(backdate, dt.time(9, 0), tzinfo=ZoneInfo("Europe/London"))
        else:
            london_now = dt.datetime.now(ZoneInfo("Europe/London"))
        surname = client_name.split()[-1] if client_name.split() else client_query.split()[-1]
        resolved_orders = matter_orders.resolve_row(row, load_rows=True)
        matter = ",".join(resolved_orders.codes) if resolved_orders.structured else normalise_order_text(
            str(row.get("order_requested_text") or row.get("matter_name") or "").strip()
        )
        if not matter and folder_name:
            fn_upper = folder_name.upper()
            _order_tokens = ["NMO", "CAO", "PSO", "SIO", "OO"]
            found = [t for t in _order_tokens if t in fn_upper]
            if found:
                matter = "-".join(found)
        caller = attendance_note_caller_from_prompt(prompt)
        item = {
            "client_name": client_name,
            "surname": surname,
            "date": london_now.strftime("%d.%m.%y"),
            "caller": caller,
            "matter": matter,
            "description": draft_an_description(raw_note, matter),
            "note": draft_attendance_note_body(raw_note, caller=caller),
            "internal_ref": internal_ref,
            "phone": str(row.get("phone_primary") or "").strip(),
            "time": "24 mins",
            "destination_folder_id": folder_id,
        }
        filename = tool._safe_filename(tool._default_filename(item))
        with tempfile.TemporaryDirectory(prefix="caseforge-chat-an-") as tmp:
            tmp_path = Path(tmp)
            template = tmp_path / "template.docx"
            output = tmp_path / filename
            tool._download_template(token, template)
            tool._populate_docx(template, output, item)
            lint_issues = lint_an_item(item, filename)
            uploaded = tool._upload(token, shared_drive_id, personal_drive_id, item, output.read_bytes(), filename)
        try:
            from usage.output_feedback import record_output

            record_output(
                {
                    "artefact_type": "attendance_note",
                    "client_name": client_name,
                    "matter_ref": internal_ref,
                    "path_or_message_id": str(uploaded.get("webUrl") or uploaded.get("id") or ""),
                    "template_used": "tools/documents/create-attendance-note.py",
                    "title_or_subject": str(item.get("description") or ""),
                    "prompt_summary": raw_note[:500],
                    "agent_version": "caseforge-chat",
                    "metadata": {
                        "filename": filename,
                        "folder_name": folder_name,
                        "uploaded_id": str(uploaded.get("id") or ""),
                        "caller": caller,
                        "matter": matter,
                        "source": "caseforge-chat-attendance-note",
                    },
                }
            )
        except Exception:
            pass
    except Exception as exc:
        return f"Attendance note creation failed: {exc}"

    link = attendance_note_link(filename, uploaded)
    c8_suffix = " C8/safety material found; check withheld fields before respondent-facing use." if row.get("has_c8") else ""
    response = f"Created attendance note for {client_name} ({internal_ref}) in {folder_name}:\n\n{link}{c8_suffix}"
    if lint_issues:
        response += "\n\n**Quality check warnings:**\n" + "\n".join(f"- {i}" for i in lint_issues)
    return response
