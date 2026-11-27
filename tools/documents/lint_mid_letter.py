#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from documents.letters import checks as letter_checks
from documents.letters import kinds as letter_kinds
from documents.lint_opening_letter import (
    LintIssue,
    LintResult,
    _document_xml,
    _parse_header_date,
    _reconstructed_text,
    check_placeholders,
    check_address_block as _ccl_check_address_block,
    check_salutation_not_doubled,
)

_CONFIRM_FLAG_RE = re.compile(
    r"\[TO CONFIRM[^\]]*\]|\bTO BE CONFIRMED\b|\bTBC\b|\bunconfirmed\b",
    re.IGNORECASE,
)
_HEADER_DATE_RE = letter_checks.HEADER_DATE_RE


def check_run_fonts_explicit(doc, result: LintResult) -> None:
    letter_checks.check_run_fonts_explicit(doc, result, code="M011")


def check_header_date_current(texts: list[str], result: LintResult, *, anchor_date=None) -> None:
    letter_checks.check_header_date_current(
        texts, result, code="M009", label="Letter",
        final_hearing_date=anchor_date, cap_days=7 if anchor_date else None,
    )


def _print_result(result: LintResult, *, use_json: bool) -> None:
    letter_checks.print_result(result, use_json=use_json)
_FIXED_MID_BOILERPLATE_RE = letter_kinds.MID_BOILERPLATE_RE
_SIGNATURE_ACK_RE = re.compile(
    r"i have read, understood and accept the information", re.IGNORECASE
)


def _paragraph_texts(doc) -> list[str]:
    return [p.text.strip() for p in doc.paragraphs]


def _first_index(texts: list[str], predicate) -> int | None:
    for idx, text in enumerate(texts):
        if predicate(text):
            return idx
    return None


def check_placeholder_codes(doc, result: LintResult) -> None:
    scratch = LintResult(result.path)
    check_placeholders(doc, scratch)
    remap = {"P001": "M001", "P015": "M002"}
    for issue in scratch.issues:
        result.add(remap.get(issue.code, issue.code), issue.severity, issue.message, issue.location)


def check_confirm_flags(doc, result: LintResult) -> None:
    xml = _reconstructed_text(_document_xml(doc))
    seen: set[str] = set()
    for match in _CONFIRM_FLAG_RE.finditer(xml):
        snippet = match.group(0)
        if snippet not in seen:
            seen.add(snippet)
            result.add(
                "M003", "warning",
                "Unresolved TO-CONFIRM / TBC flag still present — resolve it against the "
                "source documents or keep it as a deliberate bold in-letter flag before sending.",
                snippet[:100],
            )


def check_salutation(texts: list[str], result: LintResult) -> None:
    idx = _first_index(texts, lambda t: t.lower().startswith("dear "))
    if idx is None:
        result.add("M004", "error", "No 'Dear <name>,' salutation found.")
        return
    name = texts[idx][len("dear "):].rstrip(",").strip()
    if not name or "{{" in name:
        result.add("M004", "error", "Salutation is blank or unfilled.", texts[idx][:80])


def check_outcome_title(texts: list[str], result: LintResult) -> None:
    idx = _first_index(texts, lambda t: t.lower().startswith("court outcome:"))
    if idx is None:
        result.add("M005", "error", "No 'Court Outcome:' title line found.")
        return
    title = texts[idx][len("court outcome:"):].strip()
    if not title or "{{" in title or not re.search(r"[A-Za-z]", title):
        result.add("M005", "error", "'Court Outcome:' title is blank or malformed.", texts[idx][:100])


def check_case_reference(texts: list[str], result: LintResult) -> None:
    idx = _first_index(texts, lambda t: re.search(r"our\s+ref(erence)?:", t.lower()))
    if idx is None:
        result.add("M006", "warning", "No 'Our Reference' line found to check.")
        return
    match = re.search(r"our ref(?:erence)?:\s*(.*?)(?:your ref(?:erence)?:|$)", texts[idx], re.IGNORECASE)
    same_line_value = match.group(1).strip() if match else ""
    next_value = texts[idx + 1].strip() if idx + 1 < len(texts) else ""
    if "{{" in next_value or "{{" in same_line_value:
        result.add("M006", "error", "Case reference contains an unfilled placeholder.", next_value[:80])
    elif not next_value and not same_line_value:
        result.add("M006", "error", "Case reference value is blank.")


def check_address_block(doc, result: LintResult) -> None:
    paragraphs = list(doc.paragraphs)
    if not paragraphs or not paragraphs[0].text.strip():
        result.add("M007", "error", "Client name (header line 1) is blank.")
        return
    email_idx = _first_index(
        [p.text.strip() for p in paragraphs[:15]], lambda t: t.lower().startswith("email:")
    )
    if email_idx is not None and email_idx >= 2:
        region = [p.text.strip() for p in paragraphs[1 : email_idx - 1]]
        if region and not any(region):
            result.add("M007", "error", "Address block is empty.")
            return
    scratch = LintResult(result.path)
    _ccl_check_address_block(paragraphs, scratch)
    for issue in scratch.issues:
        code = "M007" if issue.code == "P016" else issue.code
        result.add(code, issue.severity, issue.message, issue.location)


def check_narrative_not_empty(texts: list[str], result: LintResult) -> None:
    title_idx = _first_index(texts, lambda t: t.lower().startswith("court outcome:"))
    if title_idx is None:
        return
    end_idx = _first_index(
        texts,
        lambda t: bool(_FIXED_MID_BOILERPLATE_RE.search(t)) or t.lower() == "yours sincerely,",
    )
    if end_idx is None:
        end_idx = len(texts)
    narrative = [t for t in texts[title_idx + 1 : end_idx] if t]
    if not narrative:
        result.add("M008", "error", "Outcome narrative is empty — has not been drafted.")
    elif all(t.startswith("{{") and t.endswith("}}") for t in narrative):
        result.add("M008", "error", "Outcome narrative contains only a placeholder — has not been filled in.")


def check_signature_block(texts: list[str], result: LintResult) -> None:
    if any(_SIGNATURE_ACK_RE.search(t) for t in texts):
        result.add(
            "M010", "error",
            "Client signature acknowledgment block is present — this letter type should "
            "not carry a 'SIGNED:' / 'DATE:' / 'NAME:' block (only the Opening CCL and "
            "Terms of Business keep it).",
        )


def check_salutation_doubled(doc, result: LintResult) -> None:
    scratch = LintResult(result.path)
    check_salutation_not_doubled(doc.paragraphs, scratch)
    for issue in scratch.issues:
        result.add("M012", issue.severity, issue.message, issue.location)


def check_yours_sincerely(texts: list[str], result: LintResult) -> None:
    if not any(t.strip().lower() == "yours sincerely," for t in texts):
        result.add(
            "M013", "error",
            "No 'Yours sincerely,' line found before the firm signature block.",
        )


def lint_file(path: Path, *, anchor_date=None) -> LintResult:
    result = LintResult(str(path))
    try:
        from docx import Document
    except ImportError:
        result.add("SETUP", "error", "python-docx not installed. Run: pip install python-docx")
        return result

    try:
        doc = Document(str(path))
    except Exception as exc:
        result.add("PARSE", "error", f"Could not open file: {exc}")
        return result

    texts = _paragraph_texts(doc)
    if not texts:
        result.add("PARSE", "error", "Document has no paragraphs — may be corrupt or empty.")
        return result

    if not letter_kinds.check_declared_kind(
        texts, "court-outcome", result, location=path.name
    ):
        return result

    check_placeholder_codes(doc, result)
    check_confirm_flags(doc, result)
    check_salutation(texts, result)
    check_salutation_doubled(doc, result)
    check_outcome_title(texts, result)
    check_case_reference(texts, result)
    check_address_block(doc, result)
    check_narrative_not_empty(texts, result)
    check_header_date_current(texts, result, anchor_date=anchor_date)
    check_signature_block(texts, result)
    check_yours_sincerely(texts, result)
    check_run_fonts_explicit(doc, result)

    return result


def lint_dir(directory: Path) -> list[LintResult]:
    results = []
    for path in sorted(directory.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        if letter_kinds.match_filename("court-outcome", path.name):
            results.append(lint_file(path))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint a Court Outcome (mid-matter) client care letter .docx for format and policy compliance."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to a single .docx file to lint.")
    group.add_argument("--dir", type=Path, help="Directory to scan for mid-letter .docx files.")
    parser.add_argument("--json", action="store_true", help="Output results as JSON.")
    args = parser.parse_args()

    if args.file:
        results = [lint_file(args.file.resolve())]
    else:
        results = lint_dir(args.dir.resolve())
        if not results:
            print("No Court Outcome letter .docx files found in the specified directory.", file=sys.stderr)
            return 0

    for result in results:
        _print_result(result, use_json=args.json)

    any_fail = any(not r.passed() for r in results)
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
