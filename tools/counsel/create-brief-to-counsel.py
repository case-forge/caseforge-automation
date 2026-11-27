#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from docx import Document

try:
    from usage.output_feedback import record_output
except Exception:
    record_output = None


def iter_paragraphs(parent):
    for paragraph in getattr(parent, "paragraphs", []):
        yield paragraph
    for table in getattr(parent, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                yield from iter_paragraphs(cell)


def replace_in_paragraph(paragraph, replacements: dict[str, str]) -> None:
    full_text = "".join(run.text for run in paragraph.runs)
    if not full_text:
        return

    new_text = full_text
    for old, new in replacements.items():
        new_text = new_text.replace(old, new)

    if new_text == full_text:
        return

    if paragraph.runs:
        paragraph.runs[0].text = new_text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(new_text)


def populate(template: Path, output: Path, replacements: dict[str, str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, output)
    doc = Document(output)

    for paragraph in iter_paragraphs(doc):
        replace_in_paragraph(paragraph, replacements)

    doc.save(output)


def _title_case_name(value: str) -> str:
    words = [part.strip() for part in str(value or "").split() if part.strip()]
    return " ".join(word.capitalize() if word.isupper() else word for word in words)


def _record_brief_output(template: Path, output: Path, replacements: dict[str, str]) -> None:
    if record_output is None:
        return
    applicant = _title_case_name(replacements.get("{{APPLICANT_NAME}}", ""))
    respondent = _title_case_name(replacements.get("{{RESPONDENT_NAME}}", ""))
    case_number = str(replacements.get("{{CASE_NUMBER}}", "") or "").strip()
    hearing_type = str(replacements.get("{{HEARING_TYPE}}", "") or "").strip()
    hearing_date = str(replacements.get("{{HEARING_DATE_LONG}}", "") or "").strip()
    counsel_name = str(replacements.get("{{COUNSEL_NAME}}", "") or "").strip()
    title = f"Brief to Counsel | {case_number} | {applicant} v {respondent}".strip(" |")
    record_output(
        {
            "artefact_type": "brief_to_counsel",
            "client_name": applicant,
            "matter_ref": case_number,
            "path_or_message_id": str(output),
            "template_used": str(template.name),
            "title_or_subject": title or output.name,
            "prompt_summary": "brief to counsel generation",
            "agent_version": "create-brief-to-counsel.py",
            "metadata": {
                "output_path": str(output),
                "respondent_name": respondent,
                "hearing_type": hearing_type,
                "hearing_date": hearing_date,
                "counsel_name": counsel_name,
            },
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a brief-to-counsel docx from the filing template.")
    parser.add_argument("--template", required=True, help="Path to template .docx")
    parser.add_argument("--output", required=True, help="Path to output .docx")
    parser.add_argument("--payload", required=True, help="Path to JSON payload with placeholder values")
    args = parser.parse_args()

    template = Path(args.template)
    output = Path(args.output)
    payload_path = Path(args.payload)

    if not template.exists():
        raise SystemExit(f"Template not found: {template}")
    if not payload_path.exists():
        raise SystemExit(f"Payload not found: {payload_path}")

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    replacements = {str(k): str(v) for k, v in payload.items()}
    populate(template, output, replacements)
    try:
        _record_brief_output(template, output, replacements)
    except Exception:
        pass
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
