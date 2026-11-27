#!/usr/bin/env python3
"MCP server exposing this repo's CCL guardrail tools and Documenso envelope"
from __future__ import annotations

import argparse
import dataclasses
import difflib
import functools
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
for sub in ("tools", "tools/documents", "tools/agents", "tools/counsel"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from mcp.server.mcpserver import MCPServer
from vergil import chat_session, confined_paths
import firm_profile
from document_identity import attachment_identity_mismatch as _attachment_identity_mismatch
from document_identity import looks_like_client_care_letter as _looks_like_client_care_letter
from onboarding.matter_court import address_belongs_to_court as _address_belongs_to_court
from onboarding.matter_court import court_name_tokens as _court_name_tokens
from onboarding.pipeline import step_ref

mcp = MCPServer("caseforge-documents")

CCL_ENVELOPE_REFUSAL = {
    "error": (
        f"Client care letters are sent only through Case Flow ({step_ref('ccl')} in the client viewer), "
        "which files and bills the signed letter. No envelope was made."
    )
}
NO_MATTER_ENVELOPE_REFUSAL = {
    "error": (
        "A signing envelope needs the client's matter number (matter_id): the signed copy is filed "
        "by it, and without one it is left unfiled. No envelope was made."
    )
}

USAGE_LOG_PATH = REPO_ROOT / "telemetry" / "mcp-caseforge-documents-usage.jsonl"


_SAFE_TELEMETRY_FLAG_NAMES = ("recipient_confirmed_by_user", "confirmed_not_duplicate")


def _record_usage(tool_name: str, *, ok: bool, error_type: str = "", flags: dict[str, bool] | None = None) -> None:
    "Length/name only, never arguments or results -- those can carry client"
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool_name,
        "ok": ok,
        "error_type": error_type,
    }
    if flags:
        row["flags"] = flags
    try:
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from graph_mail_safe_ops import _append_jsonl_locked

        USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _append_jsonl_locked(USAGE_LOG_PATH, row)
    except Exception:
        pass


def _tracked(fn: Callable) -> Callable:
    "Wrap a tool function to log its invocation before returning its"

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        flags = {name: bool(kwargs[name]) for name in _SAFE_TELEMETRY_FLAG_NAMES if name in kwargs}
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            _record_usage(fn.__name__, ok=False, error_type=type(exc).__name__, flags=flags)
            raise
        _record_usage(fn.__name__, ok=not (isinstance(result, dict) and "error" in result), flags=flags)
        return result

    return wrapper


def _asdict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _asdict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_asdict(v) for v in obj]
    return obj


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def lint_ccl(file_path: str, kind: str = "opening") -> dict:
    "Lint a client care letter .docx for unresolved placeholders, present-tense"
    from documents.lint_letter import lint_file, resolve_kind

    path = Path(file_path)
    if not path.is_file():
        return {"error": f"File not found: {file_path}"}
    result = lint_file(path, resolve_kind(kind))
    return {
        "path": result.path,
        "error_count": result.errors,
        "warning_count": result.warnings,
        "passed": result.passed(),
        "issues": _asdict(result.issues),
    }


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def audit_ccl_sources(ccl_docx_path: str, source_paths: list[str]) -> dict:
    "Cross-check a drafted CCL's content against its source documents (SQL"
    from audit_opening_letter_sources import audit_sources

    docx = Path(ccl_docx_path)
    if not docx.is_file():
        return {"error": f"File not found: {ccl_docx_path}"}
    sources = [Path(p) for p in source_paths]
    missing = [str(p) for p in sources if not p.is_file()]
    if missing:
        return {"error": f"Source file(s) not found: {missing}"}
    result = audit_sources(docx, sources)
    return {
        "ccl_docx": result.ccl_docx,
        "sources": result.sources,
        "checks": result.checks,
        "issues": _asdict(result.issues),
    }


@mcp.tool()
@_tracked
def list_matter_folder(graph_path: str) -> dict:
    "List the files and subfolders directly inside a OneDrive/SharePoint"
    from graph_files import list_children

    anchor = chat_session.anchored_matter_id()
    if anchor:
        folder = ""
        try:
            from clientdb_sql import get_client_by_matter_id

            folder = str((get_client_by_matter_id(anchor) or {}).get("live_matter_folder") or "")
        except Exception:
            folder = ""
        if not chat_session.path_within_anchor_folder(graph_path, folder):
            return {"error": chat_session.ANCHORED_FOLDER_REFUSAL}
    try:
        payload = list_children(graph_path)
    except Exception as exc:
        return chat_session.failure(f"{type(exc).__name__}: {exc}", exc, where="list_matter_folder")
    items = [
        {"name": item.get("name"), "type": "folder" if item.get("folder") else "file"}
        for item in payload.get("value", [])
    ]
    return {"items": items}


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def convert_document_to_pdf(graph_path: str, output_path: str = "") -> dict:
    "Convert an Office document (.docx etc.) already in OneDrive/SharePoint"
    from graph_files import convert_to_pdf

    if str(output_path or "").strip():
        target = Path(os.path.realpath(output_path))
        if not any(target.is_relative_to(root) for root in confined_paths.allowed_roots()):
            return {"error": confined_paths.OUTSIDE_ROOTS_ERROR}
    else:
        target = confined_paths.default_output_dir() / f"{Path(graph_path).stem or 'document'}.pdf"
    try:
        return convert_to_pdf(graph_path, target)
    except Exception as exc:
        return chat_session.failure(f"{type(exc).__name__}: {exc}", exc, where="convert_document_to_pdf")


EMAIL_TEMPLATES_DIR = REPO_ROOT / "templates" / "Email Templates"


@mcp.tool()
@_tracked
def list_email_templates() -> dict:
    "List every reusable email template this firm actually has, so a"
    if not EMAIL_TEMPLATES_DIR.is_dir():
        return chat_session.failure(
            f"Template directory not found: {EMAIL_TEMPLATES_DIR}", plain="The email templates aren't available just now.", where="list_email_templates"
        )

    manifest_rows: dict[str, dict[str, str]] = {}
    manifest_path = EMAIL_TEMPLATES_DIR / "MANIFEST.md"
    if manifest_path.is_file():
        for line in manifest_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip().startswith("|") or "---" in line:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 4 or cells[0] == "Step":
                continue
            step, phase, variant, filename_cell = cells
            filename = filename_cell.strip("`")
            if filename:
                manifest_rows[filename] = {"phase": phase, "step": step, "variant": variant}

    templates = []
    for path in sorted(EMAIL_TEMPLATES_DIR.glob("*.eml")):
        row = {"filename": path.name}
        row.update(manifest_rows.get(path.name, {}))
        templates.append(row)
    return {"templates": templates}


@mcp.tool()
@_tracked
def read_email_template(filename: str) -> dict:
    "Read one template's real raw content from templates/Email"
    candidate = (EMAIL_TEMPLATES_DIR / filename).resolve()
    try:
        candidate.relative_to(EMAIL_TEMPLATES_DIR.resolve())
    except ValueError:
        return {"error": f"{filename!r} is not inside templates/Email Templates/."}
    if not candidate.is_file():
        real_names = [p.name for p in EMAIL_TEMPLATES_DIR.glob("*.eml")] if EMAIL_TEMPLATES_DIR.is_dir() else []
        closest = difflib.get_close_matches(filename, real_names, n=3, cutoff=0.3)
        hint = f" Closest real filename(s): {closest}." if closest else " Call list_email_templates for the real filenames."
        return {"error": f"Template not found: {filename!r}.{hint}"}
    _TEMPLATES_READ_THIS_SESSION.add(candidate.name)
    return {"content": candidate.read_text(encoding="utf-8", errors="replace")}


_TEMPLATES_READ_THIS_SESSION: set[str] = set()

_GENERIC_TEMPLATE_TOKENS = {
    "order", "client", "court", "letter", "final", "report", "request",
    "form", "send", "guide", "care", "reply", "new",
    "family", "children",
}
_TEMPLATE_FILENAME_STOPWORDS = {"to", "with", "for", "and", "a", "the", "of", "in", "on", "or", "at"}


def _template_signature_tokens(filename: str) -> set[str]:
    words = re.findall(r"[a-z]+", Path(filename).stem.lower())
    return {w for w in words if w not in _TEMPLATE_FILENAME_STOPWORDS}


def _template_signatures() -> dict[str, set[str]]:
    "{template filename: its own distinctive token set}, derived straight"
    if not EMAIL_TEMPLATES_DIR.is_dir():
        return {}
    signatures = {}
    for path in EMAIL_TEMPLATES_DIR.glob("*.eml"):
        tokens = _template_signature_tokens(path.name)
        if len(tokens) < 2:
            continue
        if not any(len(t) >= 5 and t not in _GENERIC_TEMPLATE_TOKENS for t in tokens):
            continue
        signatures[path.name] = tokens
    return signatures


def _matching_unread_templates(*texts: str) -> list[str]:
    "Templates whose own full token set is present in the combined"
    haystack = " ".join(re.sub(r"[^a-z0-9]+", " ", (t or "").lower()) for t in texts)
    words = set(haystack.split())
    return sorted(
        filename
        for filename, tokens in _template_signatures().items()
        if tokens <= words and filename not in _TEMPLATES_READ_THIS_SESSION
    )


@mcp.tool()
@_tracked
def resolve_known_recipient(category: str) -> dict:
    "Deterministic address book for the handful of recipients this repo"
    from email_sorter_common import REFERRALPARTNER_ADDRESSES

    table = {"referral_partner": list(REFERRALPARTNER_ADDRESSES)}
    key = (category or "").strip().lower()
    if key not in table:
        return {"error": f"Unknown recipient category {category!r}. Known categories: {sorted(table)}"}
    return {"category": key, "addresses": table[key]}


@mcp.tool()
@_tracked
def resolve_chambers_email(query: str) -> dict:
    "Deterministic chambers lookup over the firm's real chambers"
    from chambers import find_chambers_by_name

    try:
        return {"matches": find_chambers_by_name(query)}
    except SystemExit as exc:
        return chat_session.failure(
            f"Chambers dataset unavailable: {exc}", exc, plain="The chambers list isn't available just now.", where="resolve_chambers_email"
        )


_RECIPIENT_DISCOVERY_DOMAINS: dict[str, tuple[str, ...]] | None = None


def _recipient_discovery_domains() -> dict[str, tuple[str, ...]]:
    "Lazy-loaded so importing this module never requires email_sorter_common's"
    global _RECIPIENT_DISCOVERY_DOMAINS
    if _RECIPIENT_DISCOVERY_DOMAINS is None:
        from email_sorter_common import (
            CHAMBERS_DOMAINS,
            COURT_DOMAINS,
            DRUG_TEST_DOMAINS,
            POLICE_DOMAINS,
            PROCESS_SERVER_DOMAINS,
        )

        _RECIPIENT_DISCOVERY_DOMAINS = {
            "court": COURT_DOMAINS,
            "police": POLICE_DOMAINS,
            "process_server": PROCESS_SERVER_DOMAINS,
            "chambers": CHAMBERS_DOMAINS,
            "lab": DRUG_TEST_DOMAINS,
        }
    return _RECIPIENT_DISCOVERY_DOMAINS


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def find_recipient_candidates(category: str, query: str, matter_reference: str = "") -> dict:
    "Deterministic mailbox search for a real address at a known-good"
    from email_sorter_common import any_domain_match
    from graph_mail_safe_ops import search_messages
    from sos_to_court_draft import make_graph_client

    key = (category or "").strip().lower()
    domains_table = _recipient_discovery_domains()
    if key not in domains_table:
        return {"error": f"Unknown recipient category {category!r}. Known categories: {sorted(domains_table)}"}
    domains = domains_table[key]

    clean_query = (query or "").strip()
    if not clean_query:
        return {
            "error": (
                "query is required -- pass the court, police station, chambers, or "
                "process-server NAME to search for (for a court, the name on this matter's own papers), "
                "not a case reference -- this searches the whole mailbox on purpose, since "
                "the point is finding a recipient this matter has never corresponded with."
            )
        }
    court_tokens: list[str] = []
    if key == "court":
        court_tokens = _court_name_tokens(clean_query)
        if not court_tokens:
            return {
                "error": (
                    f"{clean_query!r} does not name a specific court. Pass the court's own name as "
                    "it appears on this matter's papers (the FL401, witness statement or a sealed "
                    "order), not a generic phrase -- a court address is only accepted when it "
                    "belongs to the court you asked for."
                )
            }

    from email_sorter_common import CASE_REFERENCE_RE

    clean_matter_reference = (matter_reference or "").strip()
    matter_reference_usable = bool(clean_matter_reference) and bool(
        CASE_REFERENCE_RE.fullmatch(clean_matter_reference)
    )
    if chat_session.in_chat() and clean_matter_reference.lower() not in chat_session.typed_references():
        matter_reference_usable = False

    try:
        client = make_graph_client()
    except SystemExit as exc:
        return chat_session.failure(
            f"Mailbox credentials not available: {exc}", exc, plain="The mailbox isn't available just now.", where="mailbox credentials"
        )

    try:
        hits = search_messages(client, clean_query, top=25)
    except Exception as exc:
        return chat_session.failure(
            f"Mailbox search failed: {type(exc).__name__}: {exc}", exc, plain="The mailbox search didn't work just now.", where="find_recipient_candidates"
        )

    candidates: dict[str, dict] = {}
    other_court_addresses: set[str] = set()
    for message in hits:
        if not isinstance(message, dict):
            continue
        is_this_matter = matter_reference_usable and any(
            match.group(0).strip().lower() == clean_matter_reference.lower()
            for match in CASE_REFERENCE_RE.finditer(
                f"{message.get('subject') or ''} {message.get('bodyPreview') or ''}"
            )
        )
        rows = [(message.get("from") or {}).get("emailAddress") or {}]
        for field in ("toRecipients", "ccRecipients", "bccRecipients"):
            rows.extend((row or {}).get("emailAddress") or {} for row in (message.get(field) or []))
        for row in rows:
            address = str((row or {}).get("address") or "").strip().lower()
            if not address or not any_domain_match([address], domains):
                continue
            if court_tokens and not _address_belongs_to_court(address, str((row or {}).get("name") or ""), court_tokens):
                other_court_addresses.add(address)
                continue
            entry = candidates.setdefault(
                address,
                {"address": address, "domain": address.rsplit("@", 1)[-1], "message_count": 0},
            )
            entry["message_count"] += 1
            if is_this_matter and "web_link" not in entry:
                from vergil.user_state import enforce_client_exposure_budget, mcp_budget_identity

                exposure = enforce_client_exposure_budget(
                    mcp_budget_identity(),
                    [{"matter_reference": clean_matter_reference, "address": address}],
                    source="mcp_find_recipient_candidates",
                )
                if exposure.get("block"):
                    continue
                entry["sample_subject"] = message.get("subject") or ""
                entry["sample_date"] = message.get("receivedDateTime") or message.get("sentDateTime") or ""
                entry["web_link"] = message.get("webLink") or ""

    if not candidates:
        other = (
            f" {len(other_court_addresses)} address(es) at other courts turned up in the search and "
            "were not used, because none names the court asked for."
            if other_court_addresses
            else ""
        )
        return {
            "category": key,
            "query": clean_query,
            "candidates": [],
            "error": (
                f"No {key} address found in this mailbox's correspondence matching "
                f"{clean_query!r}.{other} Do not guess one or fall back to another recipient "
                "category such as referrer -- tell the caseworker plainly that no address "
                "was found and ask them to supply the real one (gh#330/gh#333/gh#338: this "
                "exact gap produced a misdirected draft twice and a silent stall once)."
            ),
        }

    ranked = sorted(candidates.values(), key=lambda c: (-c["message_count"], c["address"]))[:5]
    for entry in ranked:
        entry["corroboration"] = f"seen on {entry.pop('message_count')} message(s) in this mailbox"

    return {"category": key, "query": clean_query, "candidates": ranked}


_FIRM_MAIL_DOMAINS = set(firm_profile.load_profile().firm_domains)


def _address_domain(address: str) -> str:
    clean = str(address or "").strip().lower()
    return clean.rsplit("@", 1)[-1] if "@" in clean else ""


def _chambers_email_set() -> set[str]:
    from chambers import _load as _load_chambers_data

    try:
        data = _load_chambers_data()
    except SystemExit:
        return set()
    return {str(c.get("email", "")).strip().lower() for c in data.get("chambers", []) if c.get("email")}


_NOTICE_OF_ACTING_RE = re.compile(r"notice[\s_-]+of[\s_-]+acting", re.IGNORECASE)


def _is_notice_of_acting(subject: str, body: str, attachments: Any) -> bool:
    "A draft whose subject, or whose attachment filename, names a Notice of Acting."
    names = " ".join(Path(str(a)).name for a in (attachments or []))
    return bool(_NOTICE_OF_ACTING_RE.search(f"{subject or ''} {names}"))


_ATTACHMENT_CLAIM_RE = re.compile(
    r"find\s+(?:attached|enclosed)|"
    r"attached\s+(?:is|are)|enclosed\s+(?:is|are)|see\s+(?:the\s+)?attached",
    re.IGNORECASE,
)


def _body_claims_an_attachment(body: str) -> bool:
    "gh#333/gh#334/gh#335, one root cause across three real incidents: a"
    text = re.sub(r"<[^>]+>", " ", body or "")
    return bool(_ATTACHMENT_CLAIM_RE.search(text))


_MULTI_FORMAT_CLAIM_RE = re.compile(r"\bword\b.{0,80}\bpdf\b|\bpdf\b.{0,80}\bword\b", re.IGNORECASE | re.DOTALL)
_FORMAT_WORD_RE = re.compile(r"\bformat", re.IGNORECASE)
_WORD_DOC_EXTENSIONS = {".doc", ".docx"}


def _body_claims_multiple_formats(body: str) -> bool:
    "gh#328: a real incident distinct from the zero-attachment class"
    text = re.sub(r"<[^>]+>", " ", body or "")
    return bool(_MULTI_FORMAT_CLAIM_RE.search(text) and _FORMAT_WORD_RE.search(text))


_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

_TIME_TOKEN = r"\d{1,2}[:.]\d{2}\s*(?:am|pm|AM|PM)?"
_HEADER_HEARING_RE = re.compile(rf"Hearing:\s*(.{{2,60}}?)\s+At\s+({_TIME_TOKEN})", re.IGNORECASE | re.DOTALL)
_LISTED_HEARING_PARAGRAPH_RE = re.compile(
    r"listed for a hearing at:?\s*(.{0,400}?)(?:Time estimate|We are arranging|$)",
    re.IGNORECASE | re.DOTALL,
)


def _header_and_paragraph_hearing_disagree(body: str) -> bool:
    "gh#327: order-to-client.eml reuses {{NEXT_DATE}}/{{NEXT_TIME}} in"
    text = re.sub(r"<[^>]+>", " ", body or "")
    text = re.sub(r"[ \t]+", " ", text)

    header_match = _HEADER_HEARING_RE.search(text)
    if not header_match:
        return False
    header_date = header_match.group(1).strip().rstrip(",")
    header_time = header_match.group(2).strip().rstrip(",.")
    if not header_date or not header_time:
        return False

    para_match = _LISTED_HEARING_PARAGRAPH_RE.search(text)
    if not para_match:
        return False
    paragraph_block = para_match.group(1)

    return header_date not in paragraph_block or header_time not in paragraph_block


_FORWARD_LOOKING_ATTENDANCE_RE = re.compile(
    r"you (?:are|will be|have been) required to attend|"
    r"you must attend|"
    r"your attendance (?:is|will be) required|"
    r"required to attend (?:the )?(?:hearing|court)(?:\s+in person)?|"
    r"please attend (?:the )?court on",
    re.IGNORECASE,
)


def _body_claims_forward_looking_attendance(body: str) -> bool:
    "gh#335: deliberately narrow to imperative, present-tense \"you must"
    text = re.sub(r"<[^>]+>", " ", body or "")
    return bool(_FORWARD_LOOKING_ATTENDANCE_RE.search(text))


def _lookup_matter_row(matter_id: str) -> dict | None:
    "The matter's own client row (``clientdb_sql.get_client_by_matter_id``),"
    clean_id = str(matter_id or "").strip()
    if not clean_id:
        return None
    try:
        from clientdb_sql import get_client_by_matter_id

        return get_client_by_matter_id(clean_id) or None
    except Exception:
        return None


def _c8_detail_in_draft(matter_id: str, subject: str, body: str, attachments: list[str] | None) -> str:
    "A warning when a draft for a C8 matter repeats the client's withheld address, postcode, phone or email"
    row = _lookup_matter_row(matter_id)
    if not row:
        return ""
    from documents import c8_protection
    from vergil import model_safe

    if not c8_protection.detect(matter=row)["c8"]:
        return ""
    protected = model_safe.protected_values_for_row(row)
    names = " ".join(Path(str(p)).name for p in attachments or [])
    for label, text in (("subject", subject), ("body", body), ("an attachment name", names)):
        if text and c8_protection.redact_text(text, protected) != text:
            return (
                f"This matter has a C8, so the client's address, phone and email are withheld from the other side, "
                f"and the {label} repeats one of them. Check the recipient before sending."
            )
    return ""


def _with_ai_drafted_note(body: str, warning: str) -> str:
    "``body`` with a one-line AI DRAFTED note on top, in the body's own markup (HTML or plain text)."
    note = f"AI DRAFTED: {warning} Delete this line before sending."
    if "<" in body and ">" in body:
        return f"<p><b>{note}</b></p>{body}"
    return f"{note}\n\n{body}"


_UNSET: Any = object()


def _matter_appears_concluded(matter_id: str, *, row: Any = _UNSET) -> bool:
    "gh#335: a deterministic liveness check reusing matter_live_status/"
    if row is _UNSET:
        row = _lookup_matter_row(matter_id)
    if not row:
        return False
    if row.get("closed_at"):
        return True
    if row.get("live_matter_folder"):
        return False

    last_email = row.get("last_material_email_received")
    if not last_email:
        return False

    try:
        from vergil.formatting import parse_iso_dt
        from vergil.retrieval import STALE_CORRESPONDENCE_DAYS
    except Exception:
        return False
    parsed = parse_iso_dt(str(last_email))
    if not parsed:
        return False

    import datetime as dt

    now = dt.datetime.now(parsed.tzinfo) if parsed.tzinfo else dt.datetime.now()
    return (now - parsed).days >= STALE_CORRESPONDENCE_DAYS


def _matter_id_client_mismatch(
    matter_id: str, *, client_name: str, known_client_email: str, row: dict | None
) -> str:
    "gh#356: matter_id is a bare, caller-supplied value the model asserts,"
    from recipient_identity import names_refer_to_same_person

    if not str(matter_id or "").strip() or not row:
        return ""
    clean_email = str(known_client_email or "").strip().lower()
    matter_email = str(row.get("client_email") or "").strip().lower()
    if clean_email and matter_email and clean_email != matter_email:
        return "known_client_email is not the email on record for this matter's client"
    clean_name = str(client_name or "").strip()
    matter_name = str(row.get("client_name") or "").strip()
    if clean_name and matter_name and not names_refer_to_same_person(clean_name, matter_name):
        return "client_name is not the name on record for this matter's client"
    return ""


def _verified_client_email(claimed: str, row: dict | None) -> str:
    "``claimed`` (lower-cased) when it is the client email on the matter's own record, else ''."
    from recipient_identity import same_address

    clean = str(claimed or "").strip().lower()
    recorded = str((row or {}).get("client_email") or "").strip().lower()
    return clean if clean and recorded and same_address(clean, recorded) else ""


def _expected_client_names(row: dict | None, client_name: str) -> list[str]:
    "The expected side of the recipient check: the matter's own SQL row"
    if row:
        parts = " ".join(str(row.get(k) or "").strip() for k in ("name_first", "name_middle", "name_last")).strip()
        names = [str(row.get("client_name") or "").strip(), parts, str(row.get("aka_name") or "").strip()]
        names = [n for n in names if n]
        if names:
            return names
    return [str(client_name or "").strip()] if str(client_name or "").strip() else []


def _is_non_client_address(address: str, *, referralpartner: set[str], chambers_emails: set[str]) -> bool:
    "Firm, referrer, chambers and public-body addresses are never the"
    from recipient_identity import is_institutional_address

    return (
        address in referralpartner
        or address in chambers_emails
        or _address_domain(address) in _FIRM_MAIL_DOMAINS
        or is_institutional_address(address)
    )


def _client_recipient_check(
    *,
    row: dict | None,
    client_name: str,
    known_client_email: str,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    body: str,
    matter_id: str = "",
) -> Any:
    "gh#356: is a client-facing draft actually going to the client?"
    from email_sorter_common import REFERRALPARTNER_ADDRESSES
    from recipient_identity import (
        MATCH,
        address_near_miss,
        check_client_recipient,
        other_client_owners,
        same_address,
        salutation_verdict,
    )

    names = _expected_client_names(row, client_name)
    recorded = str((row or {}).get("client_email") or "").strip().lower()
    client_emails = {e for e in (recorded, str(known_client_email or "").strip().lower()) if e}
    clean = lambda addresses: [str(a or "").strip().lower() for a in addresses if str(a or "").strip()]
    to_, everyone = clean(to), clean(list(to) + list(cc) + list(bcc))

    is_client_email = lambda a: any(same_address(a, e) for e in client_emails)
    referralpartner = {a.strip().lower() for a in REFERRALPARTNER_ADDRESSES}
    chambers_emails = _chambers_email_set()
    expected_matter_id = str(matter_id or "").strip() if row else ""
    personal = [
        a for a in dict.fromkeys(everyone)
        if is_client_email(a) or not _is_non_client_address(a, referralpartner=referralpartner, chambers_emails=chambers_emails)
    ]
    owner_lookup = _client_email_owner_lookup(personal) if personal and (names or expected_matter_id) else None
    other = (
        other_client_owners(personal, owner_lookup, expected_names=names, expected_matter_id=expected_matter_id)
        if owner_lookup is not None
        else {}
    )

    facing = [a for a in everyone if is_client_email(a) or (recorded and address_near_miss(a, recorded)) or a in other]
    if salutation_verdict(body, names) == MATCH:
        facing += [a for a in to_ if a not in facing]
    facing = [a for a in dict.fromkeys(facing) if a in personal]
    if not facing and owner_lookup is not None and owner_lookup.error:
        facing = list(personal)
    if not facing:
        return None
    copied = [
        a for a in everyone
        if a not in facing and not _is_non_client_address(a, referralpartner=referralpartner, chambers_emails=chambers_emails)
    ]
    return check_client_recipient(
        expected_names=names,
        addresses=list(dict.fromkeys(facing + copied)),
        body=body,
        recorded_addresses=[recorded] if recorded else [],
        owner_lookup=owner_lookup,
        expected_matter_id=expected_matter_id,
        confirmed_addresses=_confirmed_client_emails(expected_matter_id),
    )


def _confirmed_client_emails(matter_id: str) -> list[str]:
    "Addresses a person has confirmed as this matter's client's own (never raises; none on any error)."
    if not matter_id:
        return []
    try:
        from onboarding.pipeline.email_confirmation import confirmed_addresses

        return confirmed_addresses(matter_id)
    except Exception:
        return []


def _client_email_owner_lookup(addresses: list[str]) -> Any:
    "gh#458: which client records carry these addresses"
    from recipient_identity import OwnerLookup

    try:
        from clientdb_sql import client_email_owner_lookup

        return client_email_owner_lookup(addresses)
    except Exception as exc:
        return OwnerLookup(error=f"the client database lookup failed: {type(exc).__name__}")


def _attach_one_document(client: Any, message_id: str, graph_path: str, *, staged: bool = False) -> dict:
    "Shared by attach_document_to_draft and create_mail_draft's own"
    import graph_mail_safe_ops as mail_ops

    local_path = Path(graph_path)
    tmp_dir: str | None = None
    try:
        if local_path.is_file():
            local_path = Path(os.path.realpath(local_path))
            if not staged and not any(local_path.is_relative_to(root) for root in confined_paths.allowed_roots()):
                return {"error": confined_paths.OUTSIDE_ROOTS_ERROR}
        else:
            import graph_files

            tmp_dir = tempfile.mkdtemp(prefix="caseforge-attach-")
            local_path = Path(tmp_dir) / Path(graph_path).name
            graph_files.download(graph_path, local_path)

        result = mail_ops.add_attachment_to_message(client, message_id, local_path)
        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "bytes": result.get("size"),
            "method": result.get("method"),
        }
    except Exception as exc:
        return chat_session.failure(f"{type(exc).__name__}: {exc}", exc, where="attach_document")
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _stage_attachments(paths: list[str]) -> tuple[str | None, list[Path], str]:
    "gh#560: resolve every attachment to readable local bytes before any"
    tmp_dir: str | None = None
    staged: list[Path] = []
    problems: list[str] = []
    for index, raw in enumerate(paths):
        clean = str(raw or "").strip()
        if not clean:
            problems.append(f"attachment {index + 1} is an empty path")
            continue
        local = Path(clean)
        if local.is_file():
            local = Path(os.path.realpath(local))
            if not any(local.is_relative_to(root) for root in confined_paths.allowed_roots()):
                problems.append(f"{Path(clean).name!r} is not in a folder attachments may come from")
                continue
        else:
            try:
                import graph_files

                if tmp_dir is None:
                    tmp_dir = tempfile.mkdtemp(prefix="caseforge-attach-")
                local = Path(tmp_dir) / str(index) / Path(clean).name
                graph_files.download(clean, local)
            except Exception as exc:
                problems.append(f"{Path(clean).name!r} could not be found or fetched ({type(exc).__name__})")
                continue
        try:
            with local.open("rb") as handle:
                readable = bool(handle.read(1))
        except OSError as exc:
            problems.append(f"{Path(clean).name!r} cannot be read ({type(exc).__name__})")
            continue
        if not readable:
            problems.append(f"{Path(clean).name!r} is empty")
            continue
        staged.append(local)
    if problems:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return None, [], "; ".join(problems)
    return tmp_dir, staged, ""


_EXTERNAL_RECIPIENT_PLACEHOLDERS = (
    "{{CHAMBERS_EMAIL}}",
    "{{COURT_EMAIL}}",
    "{{POLICE_EMAIL}}",
    "{{PROCESS_SERVER_EMAIL}}",
    "{{LAB_EMAIL}}",
    "{{RECIPIENT_EMAIL}}",
)
_REFERRALPARTNER_OR_CLIENT_PLACEHOLDERS = ("{{REFERRAL_PARTNER_EMAIL}}", "{{CLIENT_EMAIL}}")


def _template_plain_text_lines(eml_text: str) -> list[str]:
    "Pull the text/plain MIME part's real body lines out of one of this"
    match = re.search(r"Content-Type:\s*text/plain[^\n]*\n\n(.*?)\n--_", eml_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    return [re.sub(r"\s+", " ", line).strip() for line in match.group(1).splitlines() if line.strip()]


def _template_to_placeholder(eml_text: str) -> str:
    match = re.search(r"^To:\s*(.+)$", eml_text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _external_recipient_template_signatures() -> dict[str, list[str]]:
    "Reads the real templates under EMAIL_TEMPLATES_DIR -- never a"
    if not EMAIL_TEMPLATES_DIR.is_dir():
        return {}

    safe_lines: set[str] = set()
    external: dict[str, list[str]] = {}
    for path in EMAIL_TEMPLATES_DIR.glob("*.eml"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        placeholder = _template_to_placeholder(text)
        if placeholder in _REFERRALPARTNER_OR_CLIENT_PLACEHOLDERS:
            safe_lines.update(line.lower() for line in _template_plain_text_lines(text))
        elif placeholder in _EXTERNAL_RECIPIENT_PLACEHOLDERS:
            candidates = [
                line
                for line in _template_plain_text_lines(text)
                if "{{" not in line and len(line) >= 20
            ]
            if candidates:
                external[path.name] = candidates

    return {
        name: [line for line in lines if line.lower() not in safe_lines]
        for name, lines in external.items()
    }


def _matching_external_recipient_template(body: str) -> str:
    "Returns the template filename a drafted body looks like it came"
    text = re.sub(r"<[^>]+>", " ", body or "")
    text = re.sub(r"\s+", " ", text)
    for filename, phrases in _external_recipient_template_signatures().items():
        for phrase in phrases:
            if phrase and phrase in text:
                return filename
    return ""


def _unverified_recipients(
    client: Any,
    addresses: list[str],
    *,
    known_client_email: str,
) -> list[str]:
    "gh#311: the deterministic half of the fix -- an address is trusted"
    from email_sorter_common import REFERRALPARTNER_ADDRESSES
    from recipient_identity import same_address

    known = {a.strip().lower() for a in REFERRALPARTNER_ADDRESSES}
    if known_client_email.strip():
        known.add(known_client_email.strip().lower())
    chambers_emails = _chambers_email_set()

    unverified = []
    for address in addresses:
        clean = str(address or "").strip().lower()
        if not clean:
            continue
        if (
            clean in known
            or (known_client_email.strip() and same_address(clean, known_client_email))
            or clean in chambers_emails
            or _address_domain(clean) in _FIRM_MAIL_DOMAINS
        ):
            continue
        import graph_mail_safe_ops as mail_ops

        if mail_ops.address_has_prior_correspondence(client, clean):
            continue
        unverified.append(address)
    return unverified


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def create_mail_draft(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    client_name: str = "",
    matter_ref: str = "",
    matter_id: str = "",
    prompt_summary: str = "",
    known_client_email: str = "",
    recipient_confirmed_by_user: bool = False,
    attachments: list[str] | None = None,
) -> dict:
    "Creates a real draft email in the firm mailbox via Microsoft Graph"
    import graph_mail_safe_ops as mail_ops
    from sos_to_court_draft import make_graph_client

    c8_warning = _c8_detail_in_draft(matter_id, subject, body, attachments)

    from onboarding.pipeline.court_common import bundle_counsel_bcc

    to, cc, bcc, bcc_counsel = bundle_counsel_bcc(matter_id, subject, list(to), list(cc or []), list(bcc or []))

    try:
        client = make_graph_client()
    except SystemExit as exc:
        return chat_session.failure(
            f"Mailbox credentials not available: {exc}", exc, plain="The mailbox isn't available just now.", where="mailbox credentials"
        )

    matter_row = _lookup_matter_row(matter_id) if matter_id else None
    claimed_client_email = known_client_email
    known_client_email = _verified_client_email(claimed_client_email, matter_row)
    recipient_confirmed_by_user = recipient_confirmed_by_user and chat_session.person_confirmed(
        list(to) + list(cc or []) + list(bcc or [])
    )

    warnings: list[str] = []
    if not recipient_confirmed_by_user:
        unverified = _unverified_recipients(
            client, list(to) + list(cc or []) + list(bcc or []), known_client_email=known_client_email
        )
        if unverified:
            warnings.append(
                f"Could not verify recipient address(es) {unverified!r} against the firm's own domain, referrer, the "
                "chambers dataset, the client's recorded address, or this mailbox's prior correspondence. Check each "
                "address before sending. A client's own address is checked only when matter_id is passed and it is the "
                "one on that matter's record. In chat, an address the caseworker typed themselves counts as confirmed."
            )

    from email_sorter_common import REFERRALPARTNER_ADDRESSES

    referralpartner = {a.strip().lower() for a in REFERRALPARTNER_ADDRESSES}
    all_recipients = [str(a or "").strip().lower() for a in list(to) + list(cc or []) + list(bcc or [])]
    if all_recipients and all(a in referralpartner for a in all_recipients):
        matched_template = _matching_external_recipient_template(body)
        if matched_template:
            return {
                "error": (
                    f"This body looks like it was drafted from {matched_template!r}, whose own "
                    "template is addressed to a court/police/chambers/other external party, not "
                    "referrer -- refusing to draft it to referrer instead (gh#330/gh#333: this "
                    "exact misdirection happened three times in one stress-test session). Find "
                    "the real recipient via retrieve_matter_context's prior correspondence, "
                    "resolve_chambers_email for a chambers, or ask the caseworker plainly which "
                    "address is missing -- do not default to referrer when the real recipient "
                    "can't be found."
                )
            }

    client_address = str(known_client_email or "").strip().lower()
    if client_address and client_address in all_recipients and _is_notice_of_acting(subject, body, attachments):
        return {
            "error": (
                "A Notice of Acting is filed with the court and served on the other side; it is "
                "not sent to the client, so this draft to the client is refused (owner rule, "
                "2026-09-25: a from-scratch NoA test emailed the client a Notice of Acting). If "
                "the client needs to hear that the firm is now acting, that is a client care "
                "letter, not a NoA -- ask the caseworker which they want."
            )
        }

    if not attachments and _body_claims_an_attachment(body):
        return {
            "error": (
                "The body says something like 'please find attached'/'enclosed' but no "
                "attachments were supplied. Pass attachments=[<real path(s) from "
                "list_matter_folder>], or remove the attachment language from the body if "
                "none is actually needed -- a draft that claims an attachment it doesn't "
                "have is exactly the failure this check exists to stop."
            )
        }

    if attachments and _body_claims_multiple_formats(body):
        exts = {Path(p).suffix.lower() for p in attachments}
        if not (exts & _WORD_DOC_EXTENSIONS) or ".pdf" not in exts:
            return {
                "error": (
                    "The body claims both Word and PDF formats are provided, but the "
                    "attachments supplied don't cover both (gh#328: a real 2026-09-19 "
                    "incident sent only PDFs while the body promised a choice of format). "
                    "Pass the original .docx alongside the PDF conversion, or change the "
                    "body text to match what's actually being sent."
                )
            }

    if attachments:
        mismatch = _attachment_identity_mismatch(body, attachments)
        if mismatch:
            return {
                "error": (
                    f"Attachment/body mismatch: {mismatch} (gh#333: a real 2026-09-19 incident "
                    "attached 'Notice of Acting - PRINCE.docx' to a body promising the "
                    "Non-Molestation Order and Statement of Service -- one file, so the "
                    "attachment-claim gate above passed; one file, so the format-count gate "
                    "never armed either). Re-check which document you actually meant via "
                    "list_matter_folder, or correct the body text if the attachment is right "
                    "and the wording is wrong. This check only fires when it can confidently "
                    "identify both the body's claim and the attachment's type -- an "
                    "unrecognised filename or a generic body claim is never blocked."
                )
            }

    if _header_and_paragraph_hearing_disagree(body):
        return {
            "error": (
                "The body's \"Hearing: X At Y\" header and its \"listed for a hearing at\" "
                "paragraph give different dates/times (gh#327: a real 2026-09-19 incident "
                "put the order-made hearing in the header and the genuine next hearing in "
                "the paragraph -- a client reading only the header would believe the wrong "
                "date is their hearing). Both must show the same real next hearing -- "
                "re-check which one is actually upcoming via retrieve_matter_context."
            )
        }

    from recipient_identity import ALLOW_UNKNOWN, NEEDS_CONFIRMATION, REFUSE

    identity_mismatch = _matter_id_client_mismatch(
        matter_id, client_name=client_name, known_client_email=claimed_client_email, row=matter_row
    )
    if identity_mismatch:
        warnings.append(
            f"matter_id {matter_id} does not match the client this draft is for: {identity_mismatch}. Check which "
            "matter this draft belongs to before sending (gh#356: a matter_id held over from an earlier client would "
            "point every matter check at the wrong client). The matter's own checks were skipped."
        )
        matter_row = None

    recipient_check = _client_recipient_check(
        row=matter_row,
        client_name=client_name,
        known_client_email=known_client_email,
        to=list(to),
        cc=list(cc or []),
        bcc=list(bcc or []),
        body=body,
        matter_id=matter_id,
    )
    if recipient_check is not None and recipient_check.decision == REFUSE:
        warnings.append(
            f"{recipient_check.reason} A greeting to someone else, or a near miss of the client's recorded address, is "
            "not the client: correct the greeting, the address or the matter_id before sending (gh#356)."
        )
    elif (
        recipient_check is not None
        and recipient_check.decision == NEEDS_CONFIRMATION
        and not recipient_confirmed_by_user
    ):
        warnings.append(
            f"This draft is client-facing, but {recipient_check.reason} Check the address against the client's record "
            "before sending (gh#356). If the caseworker has confirmed this exact address themselves, pass "
            "recipient_confirmed_by_user=true and this warning goes."
        )

    if matter_id and _body_claims_forward_looking_attendance(body):
        if _matter_appears_concluded(matter_id, row=matter_row):
            return {
                "error": (
                    f"This body tells the recipient they must attend or are required to be "
                    f"present, but matter {matter_id} looks concluded or inactive (gh#335: a "
                    "real incident sent a \"you are required to attend\" letter for a hearing "
                    "over a year in the past, on a matter with no live folder and no "
                    "correspondence since). Confirm with the caseworker that this matter is "
                    "genuinely still live before drafting present-tense attendance content -- "
                    "closing correspondence about a concluded matter is fine, this check only "
                    "fires on forward-looking \"must attend\" language."
                )
            }

    leftover = _LEFTOVER_PLACEHOLDER_RE.findall(f"{subject}\n{body}")
    if leftover:
        return {
            "error": (
                f"subject/body still contains unfilled template placeholder(s) {sorted(set(leftover))!r} "
                "-- every {{PLACEHOLDER}} in a template is boilerplate that must be replaced with a "
                "real looked-up value before drafting, never sent as literal template text."
            )
        }

    unread_templates = _matching_unread_templates(prompt_summary, subject, body)
    if unread_templates:
        return {
            "error": (
                f"This request looks like it matches existing template(s) {unread_templates!r} under "
                "templates/Email Templates/, which read_email_template hasn't been called for yet this "
                "conversation (gh#316: create_mail_draft has drafted from scratch when a matching "
                "template already existed and should have shaped the subject/body). Call "
                "read_email_template on the best-fitting one (even just to confirm it doesn't actually "
                "apply), then call create_mail_draft again -- reading it is free and clears this check "
                "either way, whether or not its structure ends up used."
            )
        }

    staged_dir, staged, attachment_problem = _stage_attachments(list(attachments)) if attachments else (None, [], "")
    if attachment_problem:
        return {
            "error": (
                f"Attachment check failed before any draft was made: {attachment_problem}. "
                "No draft was created (gh#560: checking at attach time left a draft without "
                "its attachment). Re-check the path(s) with list_matter_folder and try again."
            )
        }

    try:
        try:
            result = mail_ops.create_mail_draft(
                client,
                to=to,
                cc=cc or [],
                bcc=bcc or [],
                subject=subject,
                body=_with_ai_drafted_note(body, c8_warning) if c8_warning else body,
                client_name=client_name,
                matter_ref=matter_ref,
                template_used="vergil create_mail_draft",
                prompt_summary=prompt_summary or "Vergil chat email draft",
            )
        except mail_ops.UnsupportedMailCategoryError as exc:
            return {"error": str(exc)}
        except ValueError as exc:
            return chat_session.failure(str(exc), exc, where="create_mail_draft")
        except Exception as exc:
            return chat_session.failure(f"{type(exc).__name__}: {exc}", exc, where="create_mail_draft")

        if staged:
            message_id = result.get("id")
            result["attachments"] = [_attach_one_document(client, message_id, str(path), staged=True) for path in staged]
    finally:
        if staged_dir:
            shutil.rmtree(staged_dir, ignore_errors=True)

    if c8_warning:
        result["c8_warning"] = c8_warning

    if bcc_counsel:
        result["counsel_bcc"] = f"Counsel ({bcc_counsel}) is in BCC: a bundle to the court copies counsel blind."

    if recipient_check is not None:
        summary = recipient_check.summary()
        if recipient_check.decision == NEEDS_CONFIRMATION:
            summary["note"] = "Drafted on the caseworker's confirmation of this address (recipient_confirmed_by_user)."
        elif recipient_check.decision == ALLOW_UNKNOWN:
            summary["note"] = "The recipient could not be checked against the client's name. Confirm it before sending."
        result["recipient_check"] = summary

    if warnings:
        result["warnings"] = warnings
        result["note"] = (
            "The draft is made and marked AI DRAFTED; nothing is sent. Read the warnings and fix the recipient before "
            "sending."
        )

    return result


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def attach_document_to_draft(message_id: str, graph_path: str) -> dict:
    "Attaches a real file to an existing mail draft created by"
    from sos_to_court_draft import make_graph_client

    try:
        client = make_graph_client()
    except SystemExit as exc:
        return chat_session.failure(
            f"Mailbox credentials not available: {exc}", exc, plain="The mailbox isn't available just now.", where="mailbox credentials"
        )

    return _attach_one_document(client, message_id, graph_path)


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def check_documenso_envelope_status(document_ids: list[str]) -> dict:
    "Check the signing status of existing Documenso envelopes by document id."
    from documenso_envelopes import api_enabled, poll_envelopes

    if not api_enabled():
        return chat_session.failure(
            "DOCUMENSO_API_ENABLED is not set to 1 -- Documenso integration is off.",
            plain="Signing links aren't switched on, so there is nothing to check.",
            where="check_documenso_envelope_status",
        )
    try:
        results = poll_envelopes(document_ids)
    except Exception as exc:
        return chat_session.failure(f"{type(exc).__name__}: {exc}", exc, where="check_documenso_envelope_status")
    return {"results": results}


def _recipient_email_mismatch(matter_id: str, recipient_email: str) -> dict | None:
    "A refusal when the signer's address is not the client's recorded address for ``matter_id`` and, in a chat session,"
    from recipient_identity import same_address

    recorded = str((_lookup_matter_row(matter_id) or {}).get("client_email") or "").strip()
    if not recorded or same_address(recipient_email, recorded) or chat_session.person_confirmed([recipient_email]):
        return None
    return {
        "error": (
            "Refusing to create a signing envelope: that address is not the client's address on this matter's record. "
            "If the caseworker means to send it there, ask them to type the address in this conversation."
        )
    }


def _name_mismatch_error(path: Path, recipient_name: str) -> dict | None:
    "Deterministic guard against a wrong-client envelope: refuses unless"
    from audit_opening_letter_sources import read_text_file

    try:
        text = read_text_file(path).lower()
    except Exception as exc:
        return chat_session.failure(
            f"Could not read {path.name} to verify the recipient name: {type(exc).__name__}: {exc}",
            exc,
            plain="Couldn't read the document to check the recipient's name.",
            where="documenso recipient check",
        )
    tokens = [tok for tok in re.split(r"\s+", recipient_name.strip().lower()) if len(tok) > 1]
    missing = [tok for tok in tokens if not re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", text)]
    if tokens and missing:
        return {
            "error": (
                f"Refusing to create a signing envelope: {path.name} does not appear to "
                f"mention '{recipient_name}' (missing: {', '.join(missing)}). This is very "
                "likely the wrong document for this recipient -- verify the file before retrying."
            )
        }
    return None


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def create_documenso_signing_envelope(
    title: str,
    label: str,
    pdf_path: str,
    recipient_name: str,
    recipient_email: str,
    confirmed_not_duplicate: bool = False,
    matter_id: str = "",
) -> dict:
    "Create a Documenso envelope for one PDF and one signer, returning a"
    from documenso_envelopes import api_enabled, create_envelope, find_existing_envelope, record_open_envelopes

    if not api_enabled():
        return chat_session.failure(
            "DOCUMENSO_API_ENABLED is not set to 1 -- envelope creation is gated "
            "behind explicit owner opt-in and was not attempted.",
            plain="Signing links aren't switched on, so nothing was created.",
            where="create_documenso_envelope",
        )
    if _looks_like_client_care_letter(title, label, Path(pdf_path).name):
        return dict(CCL_ENVELOPE_REFUSAL)
    path = confined_paths.resolve_within_roots(pdf_path)
    if path is None or not path.is_file():
        return {"error": f"File not found: {pdf_path}"}
    mismatch = _name_mismatch_error(path, recipient_name)
    if mismatch:
        return mismatch
    if not str(matter_id or "").strip():
        return dict(NO_MATTER_ENVELOPE_REFUSAL)
    wrong_signer = _recipient_email_mismatch(matter_id, recipient_email)
    if wrong_signer:
        return wrong_signer
    if not confirmed_not_duplicate:
        existing = find_existing_envelope(title)
        if existing:
            return {
                "error": (
                    f"An envelope titled {existing.get('title')!r} already exists on record "
                    f"(status {existing.get('status')!r}, created {existing.get('created_utc')!r}) -- "
                    "refusing to create another before checking (gh#329). If this is a genuine "
                    "resend (the prior one expired/bounced, or the caseworker explicitly asked for "
                    "a new one), call again with confirmed_not_duplicate=true; otherwise check with "
                    "the caseworker first."
                )
            }
    try:
        pdf_bytes = path.read_bytes()
        envelope = create_envelope(
            title=title,
            label=label,
            pdf_bytes=pdf_bytes,
            recipient_name=recipient_name,
            recipient_email=recipient_email,
            external_id=str(matter_id).strip(),
        )
    except Exception as exc:
        return chat_session.failure(f"{type(exc).__name__}: {exc}", exc, where="create_documenso_envelope")
    record_open_envelopes([envelope])
    return _asdict(envelope)


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def create_multi_document_documenso_envelope(
    title: str,
    document_paths: list[str],
    document_titles: list[str],
    recipient_name: str,
    recipient_email: str,
    confirmed_not_duplicate: bool = False,
    matter_id: str = "",
) -> dict:
    "Create ONE Documenso envelope holding several DISTINCT PDFs for one"
    from documenso_envelopes import api_enabled, create_multi_document_envelope, find_existing_envelope, record_open_envelopes

    if not api_enabled():
        return chat_session.failure(
            "DOCUMENSO_API_ENABLED is not set to 1 -- envelope creation is gated "
            "behind explicit owner opt-in and was not attempted.",
            plain="Signing links aren't switched on, so nothing was created.",
            where="create_documenso_envelope",
        )
    if _looks_like_client_care_letter(title, *document_titles, *(Path(p).name for p in document_paths)):
        return dict(CCL_ENVELOPE_REFUSAL)
    if len(document_paths) != len(document_titles):
        return {"error": "document_paths and document_titles must be the same length."}
    if not document_paths:
        return {"error": "No document_paths were supplied."}
    resolved = [confined_paths.resolve_within_roots(p) for p in document_paths]
    missing = [p for p, real in zip(document_paths, resolved) if real is None or not real.is_file()]
    if missing:
        return {"error": f"File(s) not found: {missing}"}
    document_paths = [str(real) for real in resolved]
    if all(_name_mismatch_error(Path(p), recipient_name) for p in document_paths):
        return {
            "error": (
                f"Refusing to create a signing envelope: none of the supplied documents "
                f"appear to mention '{recipient_name}'. This is very likely the wrong "
                "document set for this recipient -- verify the files before retrying."
            )
        }
    if not str(matter_id or "").strip():
        return dict(NO_MATTER_ENVELOPE_REFUSAL)
    wrong_signer = _recipient_email_mismatch(matter_id, recipient_email)
    if wrong_signer:
        return wrong_signer
    if not confirmed_not_duplicate:
        existing = find_existing_envelope(title)
        if existing:
            return {
                "error": (
                    f"An envelope titled {existing.get('title')!r} already exists on record "
                    f"(status {existing.get('status')!r}, created {existing.get('created_utc')!r}) -- "
                    "refusing to create another before checking (gh#329). If this is a genuine "
                    "resend (the prior one expired/bounced, or the caseworker explicitly asked for "
                    "a new one), call again with confirmed_not_duplicate=true; otherwise check with "
                    "the caseworker first."
                )
            }
    try:
        documents = [(doc_title, Path(p).read_bytes()) for doc_title, p in zip(document_titles, document_paths)]
        envelope = create_multi_document_envelope(
            title=title,
            documents=documents,
            recipient_name=recipient_name,
            recipient_email=recipient_email,
            external_id=str(matter_id).strip(),
        )
    except Exception as exc:
        return chat_session.failure(f"{type(exc).__name__}: {exc}", exc, where="create_documenso_envelope")
    record_open_envelopes([envelope])
    return _asdict(envelope)


def _http_token() -> str:
    return os.getenv("CASEFORGE_MCP_DOCUMENTS_TOKEN", "").strip()


def _bearer_protected_app():
    "Wrap FastMCP's streamable-http ASGI app with the same bearer-token gate"
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    token = _http_token()
    if not token:
        raise SystemExit(
            "CASEFORGE_MCP_DOCUMENTS_TOKEN is not set. This service can create live Documenso "
            "envelopes; there is no unauthenticated mode. Set it and re-run."
        )

    class _BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            header = request.headers.get("authorization", "")
            presented = header[7:] if header.lower().startswith("bearer ") else ""
            if not presented or not secrets.compare_digest(presented.encode(), token.encode()):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    inner = mcp.streamable_http_app()
    return Starlette(routes=inner.routes, middleware=[Middleware(_BearerAuth)], lifespan=inner.router.lifespan_context)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        host = os.getenv("CASEFORGE_MCP_DOCUMENTS_HOST", "127.0.0.1")
        port = int(os.getenv("CASEFORGE_MCP_DOCUMENTS_PORT", "8766"))
        app = _bearer_protected_app()
        import uvicorn

        uvicorn.run(app, host=host, port=port)
