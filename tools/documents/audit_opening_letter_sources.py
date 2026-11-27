#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import order_codes

try:
    from graph_mail_safe_ops import GraphClient
except Exception:
    GraphClient = None


SECTION_HEADINGS = {
    "your instructions",
    "our advice",
    "your matter with us",
    "duration of the case",
    "action plan",
    "your responsibilities",
    "our responsibilities",
    "fees & costs",
    "fees and costs",
    "counsel",
    "supervision of your matter",
    "complaints procedure",
    "summary of harm and protective concerns",
}
FIRM_REF_RE = re.compile(r"\b\d{6}/\d{2}[A-Z]{2}\b", re.IGNORECASE)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
CRIME_REF_RE = re.compile(
    r"\b(?:crime\s+(?:reference\s+number|ref(?:erence)?|number|no\.?)\s*(?:is\s+|:\s*|\s+)?[A-Z0-9/-]*\d[A-Z0-9/-]*"
    r"|CAD\s*\d+|URN\s*\d+|\d{2}/\d+/\d+)\b",
    re.IGNORECASE,
)
POLICE_RE = re.compile(r"\b(?:police|crime\s+ref|crime\s+number|cad|urn|999|101)\b", re.IGNORECASE)
C8_RE = re.compile(r"\b(?:C8|confidential address|withheld address|protected address|address withheld)\b", re.IGNORECASE)
FIRM_ASSERTED_RISK_RE = re.compile(
    r"\byou\s+(?:are|were|have\s+been)\s+(?:at\s+risk|in\s+danger)\b"
    r"|\byou\s+(?:urgently\s+)?need(?:s)?\s+(?:the\s+)?protection\b",
    re.IGNORECASE,
)
WITHOUT_NOTICE_RE = re.compile(r"\b(?:without notice|urgent|ex parte|same day|immediate protection)\b", re.IGNORECASE)
DATE_TOKEN_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[A-Z][a-z]+(?:\s+\d{4})?)\b"
)
STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "been",
    "being",
    "could",
    "from",
    "have",
    "into",
    "that",
    "their",
    "there",
    "they",
    "this",
    "told",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
    "further",
    "instructed",
}
FALSE_RESPONDENT_NAMES = {
    "benefit analysis the funding",
}


@dataclass
class AuditIssue:
    code: str
    severity: str
    message: str
    location: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": _redact_sensitive(self.location),
        }


@dataclass
class AuditResult:
    ccl_docx: str
    sources: list[str]
    checks: list[dict[str, Any]] = field(default_factory=list)
    issues: list[AuditIssue] = field(default_factory=list)

    def add_issue(self, code: str, severity: str, message: str, location: str = "") -> None:
        self.issues.append(AuditIssue(code, severity, message, location))

    def add_check(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": status, "detail": _redact_sensitive(detail)})

    @property
    def blockers(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "blocker")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def passed(self) -> bool:
        return self.blockers == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "ccl_docx": self.ccl_docx,
            "sources": self.sources,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "checks": self.checks,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def normalise_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalise_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalise_space(value).lower()).strip()


def _redact_sensitive(value: str) -> str:
    text = str(value or "")
    text = POSTCODE_RE.sub("[postcode redacted]", text)
    text = re.sub(r"\b\d{1,5}\s+[A-Z][A-Za-z' -]{2,}\s+(?:Street|Road|Avenue|Lane|Close|Way|Drive|Court|Place)\b", "[address redacted]", text)
    return text


def _read_docx_text(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("python-docx is required to read .docx files") from exc
    doc = Document(str(path))
    lines = [para.text for para in doc.paragraphs if normalise_space(para.text)]
    for table in doc.tables:
        try:
            for row in table.rows:
                for cell in row.cells:
                    if normalise_space(cell.text):
                        lines.append(cell.text)
        except ValueError:
            continue
    return "\n".join(lines)


def _read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to read .pdf files") from exc
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        raw = page.extract_text() or ""
        joined = " ".join(normalise_space(line) for line in raw.splitlines() if normalise_space(line))
        pages.append(joined)
    answers = _form_answers(reader)
    return "\n".join(pages + ([answers] if answers else []))


def _form_answers(reader: Any) -> str | None:
    try:
        fields = reader.get_fields() or {}
    except Exception:
        return None
    if not fields:
        return None
    values = []
    for field_ in fields.values():
        value = field_.get("/V") if hasattr(field_, "get") else None
        if isinstance(value, str) and not value.startswith("/") and normalise_space(value):
            values.append(normalise_space(value))
    return "\n".join(values)


def pdf_form_answers(path: Path) -> str | None:
    try:
        from pypdf import PdfReader

        return _form_answers(PdfReader(str(path)))
    except Exception:
        return None


def read_text_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _read_docx_text(path)
    if suffix == ".pdf":
        return _read_pdf_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def _is_heading(line: str) -> bool:
    return normalise_space(line).lower() in SECTION_HEADINGS


def _section_lines(text: str, heading: str) -> list[str]:
    inside = False
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = normalise_space(raw)
        if not line:
            continue
        if line.lower() == heading.lower():
            inside = True
            continue
        if inside and _is_heading(line):
            break
        if inside:
            lines.append(line)
    return lines


def _source_chunks(text: str) -> list[str]:
    chunks = [normalise_space(line) for line in str(text or "").splitlines() if normalise_space(line)]
    if not chunks:
        chunks = [normalise_space(text)]
    if len(chunks) > 1:
        chunks.append(" ".join(chunks))
    return chunks


def _significant_words(text: str) -> set[str]:
    words = {
        word
        for word in re.findall(r"[a-z0-9']{4,}", normalise_space(text).lower())
        if word not in STOPWORDS and not word.isdigit()
    }
    return words


def _source_coverage_score(paragraph: str, source_chunks: Sequence[str]) -> float:
    target = _significant_words(paragraph)
    if len(target) < 4:
        return 1.0
    best = 0.0
    for chunk in source_chunks:
        words = _significant_words(chunk)
        if not words:
            continue
        best = max(best, len(target & words) / len(target))
    return best


def _parse_date_token(raw: str, *, default_year: int | None = None) -> str:
    value = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", normalise_space(raw), flags=re.IGNORECASE)
    value = re.sub(r"\b(\d{1,2})\s+of\s+", r"\1 ", value, flags=re.IGNORECASE)
    year = default_year or dt.date.today().year
    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d.%m.%y",
        "%d-%m-%y",
        "%d %B %Y",
        "%d %b %Y",
        "%d %B",
        "%d %b",
    )
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(value, fmt).date()
            if fmt in {"%d %B", "%d %b"}:
                parsed = parsed.replace(year=year)
            return parsed.isoformat()
        except ValueError:
            continue
    return normalise_key(value)


def _date_values(text: str) -> set[str]:
    values: set[str] = set()
    for token in DATE_TOKEN_RE.findall(str(text or "")):
        values.add(_parse_date_token(token))
    return {value for value in values if value}


def _contains_any_alias(text: str, aliases: Iterable[str]) -> bool:
    key = f" {normalise_key(text)} "
    return any(f" {alias_key} " in key for alias in aliases if (alias_key := normalise_key(alias)))


def _orders_in_text(text: str) -> list[str]:
    return list(order_codes.codes_in_text(text))


def _extract_client_name(ccl_text: str) -> str:
    for line in str(ccl_text or "").splitlines()[:80]:
        text = normalise_space(line)
        match = re.match(r"Dear\s+(.+?)[,\.]?$", text, flags=re.IGNORECASE)
        if match:
            return normalise_space(match.group(1))
    return ""


def _extract_respondent_names(ccl_text: str) -> list[str]:
    names: list[str] = []
    patterns = (
        r"\b(?i:(?:respondent|other party|former partner|ex-partner)\s+(?:is|was|:)?\s*)([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3})",
        r"\b(?i:(?:non[-\s]molestation order|occupation order|order|application))\b[^.\n]{0,140}?\b(?i:against)\s+(?:(?i:the\s+respondent)\s*,?\s+)?([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3})",
        r"\b[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3}\s+(?i:v)\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3})\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, ccl_text):
            name = normalise_space(match.group(1)).strip(" .,:;")
            name_key = normalise_key(name)
            if (
                name
                and name.lower() not in {"the respondent", "your former partner"}
                and name_key not in FALSE_RESPONDENT_NAMES
                and name not in names
            ):
                names.append(name)
    return names[:3]


def _source_has_name(source_key: str, name: str) -> bool:
    parts = [normalise_key(part) for part in name.split() if len(part) > 1]
    return bool(parts) and all(part in source_key for part in parts)


def _real_attachment_names(attachments: Sequence[Mapping[str, Any]]) -> list[str]:
    names: list[str] = []
    for attachment in attachments:
        name = normalise_space(attachment.get("name"))
        if not name:
            continue
        if bool(attachment.get("isInline")) or attachment.get("contentId"):
            continue
        lower = name.lower()
        if lower.startswith("image") and lower.endswith((".png", ".jpg", ".jpeg", ".gif")):
            continue
        names.append(name)
    return names


def _attachment_matches(names: Sequence[str]) -> dict[str, list[str]]:
    matches = {"ccl_pdf": [], "privacy_notice": [], "terms_of_business": [], "unexpected": []}
    for name in names:
        key = normalise_key(name)
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf" and any(token in key for token in ("client care", "care letter", "opening letter", "ccl")):
            matches["ccl_pdf"].append(name)
        elif suffix == ".pdf" and "privacy" in key and "notice" in key:
            matches["privacy_notice"].append(name)
        elif suffix == ".pdf" and "terms" in key and "business" in key:
            matches["terms_of_business"].append(name)
        else:
            matches["unexpected"].append(name)
    return matches


def audit_draft(
    result: AuditResult,
    message: Mapping[str, Any],
    attachments: Sequence[Mapping[str, Any]],
    *,
    expected_recipient_count: int = 1,
    expected_recipients: Sequence[str] = (),
) -> None:
    if not message:
        result.add_issue("D007", "blocker", "Draft message payload is empty; recipients/attachments could not be verified.")
        return
    if not bool(message.get("isDraft")):
        result.add_issue("D001", "blocker", "Outlook item is not a draft. Do not treat it as send-ready.")
    else:
        result.add_check("outlook_draft_state", "pass", "Message is still a draft")

    to_recipients = list(message.get("toRecipients") or [])
    cc_recipients = list(message.get("ccRecipients") or [])
    bcc_recipients = list(message.get("bccRecipients") or [])
    if len(to_recipients) != expected_recipient_count:
        result.add_issue("D002", "blocker", f"Draft has {len(to_recipients)} To recipients; expected {expected_recipient_count}.")
    else:
        result.add_check("recipient_count", "pass", f"{len(to_recipients)} To recipient(s)")
    if cc_recipients or bcc_recipients:
        result.add_issue("D003", "blocker", "Draft has unexpected CC/BCC recipients.")
    else:
        result.add_check("cc_bcc", "pass", "No CC/BCC recipients")

    if expected_recipients:
        found = {
            normalise_space(((row.get("emailAddress") or {}).get("address") or "")).lower()
            for row in to_recipients
            if isinstance(row, Mapping)
        }
        expected = {normalise_space(item).lower() for item in expected_recipients if normalise_space(item)}
        missing = sorted(expected - found)
        if missing:
            result.add_issue("D004", "blocker", f"Draft is missing expected recipient(s): {', '.join(missing)}")
        else:
            result.add_check("recipient_addresses", "pass", "Expected recipient address(es) present")

    real_names = _real_attachment_names(attachments)
    matches = _attachment_matches(real_names)
    for key, label in (
        ("ccl_pdf", "client care letter PDF"),
        ("privacy_notice", "Privacy Notice"),
        ("terms_of_business", "Terms of Business"),
    ):
        if len(matches[key]) != 1:
            result.add_issue("D005", "blocker", f"Draft must have exactly one {label} attachment.")
        else:
            result.add_check(f"attachment_{key}", "pass", matches[key][0])
    if matches["unexpected"]:
        result.add_issue("D006", "blocker", f"Draft has unexpected real attachment(s): {', '.join(matches['unexpected'])}")


def audit_sources(ccl_docx: Path, source_paths: Sequence[Path]) -> AuditResult:
    result = AuditResult(str(ccl_docx), [str(path) for path in source_paths])
    try:
        ccl_text = read_text_file(ccl_docx)
    except Exception as exc:
        result.add_issue("S000", "blocker", f"Could not read CCL docx: {exc}")
        return result

    source_texts: list[str] = []
    for path in source_paths:
        try:
            source_texts.append(read_text_file(path))
        except Exception as exc:
            result.add_issue("S001", "blocker", f"Could not read source {path.name}: {exc}")
    source_text = "\n".join(source_texts)
    source_key = normalise_key(source_text)
    source_chunks = _source_chunks(source_text)

    if not source_paths:
        result.add_issue("S002", "blocker", "At least one source document is required.")
    elif source_text.strip():
        result.add_check("source_documents", "pass", f"{len(source_paths)} source file(s)")

    client_name = _extract_client_name(ccl_text)
    if client_name:
        if _source_has_name(source_key, client_name):
            result.add_check("client_name", "pass", client_name)
        else:
            result.add_issue("S010", "blocker", "Client name in the CCL was not found in the supplied sources.", client_name)
    else:
        result.add_issue("S010", "warning", "Could not identify the client name from the CCL salutation.")

    respondents = _extract_respondent_names(ccl_text)
    if respondents:
        for respondent in respondents:
            if _source_has_name(source_key, respondent):
                result.add_check("respondent_name", "pass", respondent)
            else:
                result.add_issue("S011", "blocker", "Respondent/other-party name in the CCL was not found in the supplied sources.", respondent)
    else:
        result.add_issue("S011", "warning", "Could not identify a respondent/other-party name in the CCL.")

    refs = FIRM_REF_RE.findall(ccl_text)
    if refs:
        result.add_check("caseforge_reference_format", "pass", refs[0].upper())
    else:
        result.add_issue("S012", "blocker", "No CaseForge reference in YYMMDD/NNXX format was found in the CCL.")

    orders = _orders_in_text(ccl_text)
    if orders:
        for order in orders:
            if order in order_codes.codes_in_text(source_text):
                result.add_check(f"order_{order}", "pass", order)
            else:
                result.add_issue("S013", "blocker", f"Order type {order} appears in the CCL but not in the supplied sources.")
    else:
        result.add_issue("S013", "warning", "No recognised order type was found in the CCL.")

    if WITHOUT_NOTICE_RE.search(ccl_text):
        if WITHOUT_NOTICE_RE.search(source_text):
            result.add_check("without_notice_or_urgency", "pass", "Wording supported by source")
        else:
            result.add_issue("S014", "blocker", "Without-notice/urgent wording appears in the CCL but not in the supplied sources.")

    instruction_lines = _section_lines(ccl_text, "Your Instructions")
    if not instruction_lines:
        result.add_issue("S020", "blocker", "Could not find a populated Your Instructions section to audit.")
    ccl_instruction_text = "\n".join(instruction_lines)

    source_dates = _date_values(source_text)
    ccl_dates = _date_values(ccl_instruction_text)
    if ccl_dates:
        unsupported = sorted(ccl_dates - source_dates)
        if unsupported:
            result.add_issue("S021", "blocker", "Incident date in Your Instructions was not found in the supplied sources.", ", ".join(unsupported))
        else:
            result.add_check("incident_date", "pass", ", ".join(sorted(ccl_dates)))
    elif instruction_lines:
        result.add_issue("S021", "warning", "No key incident date was found in Your Instructions.")

    def _crime_ref_code(match_text: str) -> str:
        tail = re.search(r"[A-Z0-9/-]+$", match_text.strip(), re.IGNORECASE)
        return normalise_key(tail.group(0)) if tail else normalise_key(match_text)

    ccl_crime_refs = {normalise_space(match.group(0)) for match in CRIME_REF_RE.finditer(ccl_text)}
    source_crime_codes = {_crime_ref_code(match.group(0)) for match in CRIME_REF_RE.finditer(source_text)}
    if ccl_crime_refs:
        for ref in sorted(ccl_crime_refs):
            if _crime_ref_code(ref) in source_crime_codes:
                result.add_check("crime_or_cad_reference", "pass", ref)
            else:
                result.add_issue("S022", "blocker", "Crime/CAD reference in the CCL was not found in the supplied sources.", ref)
    elif POLICE_RE.search(ccl_instruction_text):
        result.add_issue("S022", "warning", "Police involvement is mentioned but no crime/CAD reference was found in the CCL.")

    c8_relevant = bool(C8_RE.search(ccl_text) or C8_RE.search(source_text))
    if c8_relevant:
        leaked_postcodes = POSTCODE_RE.findall(ccl_instruction_text)
        if leaked_postcodes:
            result.add_issue("S023", "blocker", "C8/confidential-address material appears to include a postcode in Your Instructions.", ccl_instruction_text[:160])
        elif re.search(r"\b(?:lives at|address is|resides at)\b", ccl_instruction_text, flags=re.IGNORECASE):
            result.add_issue("S023", "blocker", "C8/confidential-address material appears to include address wording in Your Instructions.", ccl_instruction_text[:160])
        else:
            result.add_check("c8_redaction", "pass", "No protected address detail found in Your Instructions")

    for idx, paragraph in enumerate(instruction_lines, start=1):
        if len(paragraph) < 50:
            continue
        score = _source_coverage_score(paragraph, source_chunks)
        if score >= 0.45:
            result.add_check("instruction_source_coverage", "pass", f"paragraph {idx}: {score:.0%} source overlap")
        else:
            result.add_issue(
                "S030",
                "blocker",
                f"Major factual paragraph {idx} in Your Instructions does not have enough source support.",
                paragraph[:180],
            )

    risk_matches = [m.group(0) for m in FIRM_ASSERTED_RISK_RE.finditer(ccl_instruction_text)]
    if risk_matches:
        result.add_issue(
            "S031",
            "blocker",
            "Your Instructions asserts risk/danger/need for protection as the firm's own finding rather than "
            "attributing it to the client's account (\"you told us...\"/\"you said...\").",
            ", ".join(sorted(set(risk_matches))),
        )
    else:
        result.add_check("client_voice_attribution", "pass", "No firm-asserted risk/danger phrasing found")

    return result


def _graph_client_from_env() -> GraphClient:
    if GraphClient is None:
        raise RuntimeError("Graph mail helper is unavailable.")
    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()
    client_id = os.getenv("GRAPH_MAIL_CLIENT_ID", "").strip() or os.getenv("GRAPH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GRAPH_MAIL_CLIENT_SECRET", "").strip() or os.getenv("GRAPH_CLIENT_SECRET", "").strip()
    mailbox_upn = os.getenv("GRAPH_MAILBOX_UPN", "").strip()
    missing = [
        name
        for name, value in (
            ("GRAPH_TENANT_ID", tenant_id),
            ("GRAPH_MAIL_CLIENT_ID/GRAPH_CLIENT_ID", client_id),
            ("GRAPH_MAIL_CLIENT_SECRET/GRAPH_CLIENT_SECRET", client_secret),
            ("GRAPH_MAILBOX_UPN", mailbox_upn),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing Graph mail env var(s): {', '.join(missing)}")
    return GraphClient(tenant_id, client_id, client_secret, mailbox_upn, 2, 0.5)


def fetch_draft_message(message_id: str, client: Any | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    graph = client or _graph_client_from_env()
    quoted = urllib.parse.quote(message_id, safe="")
    message = graph.graph(
        "GET",
        graph.mailbox_path(f"/messages/{quoted}"),
        params={
            "$select": "id,subject,isDraft,toRecipients,ccRecipients,bccRecipients,hasAttachments,categories",
        },
    )
    payload = graph.graph("GET", graph.mailbox_path(f"/messages/{quoted}/attachments"))
    attachments = payload.get("value") if isinstance(payload, Mapping) else []
    return dict(message), [dict(item) for item in attachments or [] if isinstance(item, Mapping)]


def _load_draft_json(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "message" in payload:
        message = payload.get("message") or {}
        attachments = payload.get("attachments") or payload.get("message", {}).get("attachments") or []
    else:
        message = payload
        attachments = payload.get("attachments") if isinstance(payload, dict) else []
    if isinstance(attachments, dict):
        attachments = attachments.get("value") or []
    return dict(message), [dict(item) for item in attachments or [] if isinstance(item, Mapping)]


def run_audit(
    *,
    ccl_docx: Path,
    source_paths: Sequence[Path],
    draft_message: Mapping[str, Any] | None = None,
    draft_attachments: Sequence[Mapping[str, Any]] = (),
    expected_recipient_count: int = 1,
    expected_recipients: Sequence[str] = (),
) -> AuditResult:
    result = audit_sources(ccl_docx, source_paths)
    if draft_message is not None:
        audit_draft(
            result,
            draft_message,
            draft_attachments,
            expected_recipient_count=expected_recipient_count,
            expected_recipients=expected_recipients,
        )
    return result


def _print_result(result: AuditResult, *, use_json: bool) -> None:
    payload = result.to_dict()
    if use_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    status = "PASS" if result.passed else "FAIL"
    print(f"[{status}] {result.ccl_docx}")
    if result.checks:
        print("Checks:")
        for check in result.checks:
            detail = f" - {check['detail']}" if check.get("detail") else ""
            print(f"  {check['name']}: {check['status']}{detail}")
    if result.issues:
        print("Issues:")
        for issue in result.issues:
            location = f" ({_redact_sensitive(issue.location)})" if issue.location else ""
            print(f"  {issue.severity.upper()} {issue.code}: {issue.message}{location}")
    print(f"Blockers: {result.blockers}; warnings: {result.warnings}")


def _bootstrap_val_env() -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from env_bootstrap import load_repo_secrets

        load_repo_secrets()
    except Exception:
        pass

def main(argv: Sequence[str] | None = None) -> int:
    _bootstrap_val_env()
    parser = argparse.ArgumentParser(description="Audit a client care letter against source documents and an optional Outlook draft.")
    parser.add_argument("--ccl-docx", type=Path, required=True, help="Completed CCL .docx to audit.")
    parser.add_argument("--source", type=Path, action="append", default=[], help="Source document/text/PDF path. Repeat for multiple sources.")
    parser.add_argument("--draft-message-id", default="", help="Optional Outlook draft message id to preflight through Graph.")
    parser.add_argument("--draft-json", type=Path, help="Optional local JSON fixture for draft preflight.")
    parser.add_argument("--expected-recipient-count", type=int, default=1)
    parser.add_argument("--expected-recipient", action="append", default=[], help="Expected To recipient address. Repeatable.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    draft_message: dict[str, Any] | None = None
    draft_attachments: list[dict[str, Any]] = []
    if args.draft_json:
        draft_message, draft_attachments = _load_draft_json(args.draft_json)
    elif args.draft_message_id:
        draft_message, draft_attachments = fetch_draft_message(args.draft_message_id)

    result = run_audit(
        ccl_docx=args.ccl_docx,
        source_paths=args.source,
        draft_message=draft_message,
        draft_attachments=draft_attachments,
        expected_recipient_count=args.expected_recipient_count,
        expected_recipients=args.expected_recipient,
    )
    _print_result(result, use_json=bool(args.json))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
