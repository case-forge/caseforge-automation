import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from documents import audit_opening_letter_sources as auditor


def _write_docx(path: Path, paragraphs: list[str]) -> Path:
    from docx import Document

    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    doc.save(path)
    return path


def _good_ccl(path: Path) -> Path:
    return _write_docx(
        path,
        [
            "Date: 20 May 2026",
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            (
                "On 12 May 2026 the respondent John Ashtest pushed you, threatened you, "
                "and police attended. Crime ref 12/345/678 was provided."
            ),
            "You told us there had also been coercive control, harassment, and financial abuse.",
            "You remained afraid because the wider pattern had continued since separation.",
            "Our Advice",
            "Non-Molestation Order:",
            "We advised you about applying for a non-molestation order.",
        ],
    )


def _source(path: Path, text: str | None = None) -> Path:
    path.write_text(
        text
        or (
            "Jane Ashtest instructed CaseForge about John Ashtest. "
            "On 12 May 2026 John Ashtest pushed Jane, threatened her, and police attended. "
            "Crime ref 12/345/678 was recorded. "
            "The matter is for a non-molestation order. "
            "There had also been coercive control, harassment, financial abuse, and a wider pattern since separation."
        ),
        encoding="utf-8",
    )
    return path


def _draft(is_draft: bool = True, attachments: list[dict] | None = None) -> dict:
    return {
        "message": {
            "id": "draft-1",
            "isDraft": is_draft,
            "toRecipients": [{"emailAddress": {"address": "jane@example.test"}}],
            "ccRecipients": [],
            "bccRecipients": [],
        },
        "attachments": attachments
        if attachments is not None
        else [
            {"name": "Client Care Letter - ASHTEST.pdf"},
            {"name": "Privacy Notice - CaseForge.pdf"},
            {"name": "Terms of Business - CaseForge.pdf"},
            {"name": "image001.png", "isInline": True, "contentId": "sig"},
        ],
    }


def test_read_text_file_includes_table_cell_text(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Ordinary paragraph text")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Postcode"
    table.rows[0].cells[1].text = "AB1 2CD"
    path = tmp_path / "fl401.docx"
    doc.save(path)

    text = auditor.read_text_file(path)

    assert "Ordinary paragraph text" in text
    assert "AB1 2CD" in text


def test_read_text_file_skips_a_table_that_raises_instead_of_crashing(tmp_path, monkeypatch):

    class _BrokenRows:
        def __iter__(self):
            raise ValueError("no `tc` element at grid_offset=3")

    class _BrokenTable:
        rows = _BrokenRows()

    class _FakeParagraph:
        def __init__(self, text):
            self.text = text

    class _FakeDoc:
        paragraphs = [_FakeParagraph("Ordinary paragraph text")]
        tables = [_BrokenTable()]

    import docx

    monkeypatch.setattr(docx, "Document", lambda path: _FakeDoc())

    path = tmp_path / "broken.docx"
    path.write_bytes(b"placeholder")
    text = auditor.read_text_file(path)

    assert text == "Ordinary paragraph text"


def test_auditor_passes_supported_ccl_and_send_pack(tmp_path):
    ccl = _good_ccl(tmp_path / "ccl.docx")
    source = _source(tmp_path / "source.txt")
    draft = _draft()

    result = auditor.run_audit(
        ccl_docx=ccl,
        source_paths=[source],
        draft_message=draft["message"],
        draft_attachments=draft["attachments"],
        expected_recipients=["jane@example.test"],
    )

    assert result.passed
    assert result.blockers == 0
    check_names = {check["name"] for check in result.checks}
    assert "client_name" in check_names
    assert "attachment_ccl_pdf" in check_names
    assert "attachment_privacy_notice" in check_names
    assert "attachment_terms_of_business" in check_names


def test_auditor_blocks_unsupported_instruction_fact(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "On 12 May 2026 the respondent John Ashtest pushed you and destroyed your phone.",
            "Our Advice",
            "Non-Molestation Order:",
        ],
    )
    source = _source(tmp_path / "source.txt", "Jane Ashtest instructed CaseForge about John Ashtest and a non-molestation order.")

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not result.passed
    assert any(issue.code == "S030" for issue in result.issues)


def test_auditor_warns_when_respondent_not_identified(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "On 12 May 2026 you described harassment and fear after separation.",
            "Our Advice",
            "Non-Molestation Order:",
        ],
    )
    source = _source(tmp_path / "source.txt")

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert any(issue.code == "S011" and issue.severity == "warning" for issue in result.issues)


def test_auditor_accepts_concise_against_respondent_wording(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            (
                "You instructed us in relation to your application for a Non-Molestation Order, "
                "which you sought on a without notice basis against John Ashtest."
            ),
            "On 12 May 2026 John Ashtest pushed you, threatened you, and police attended. Crime ref 12/345/678 was provided.",
            "Our Advice",
            "Non-Molestation Order:",
        ],
    )
    source = _source(tmp_path / "source.txt")

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any(issue.code == "S011" for issue in result.issues)
    assert any(check["name"] == "respondent_name" and check["detail"] == "John Ashtest" for check in result.checks)


def test_auditor_ignores_cost_v_benefit_heading_as_respondent_name(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "You instructed us in relation to your application for a Non-Molestation Order against John Ashtest.",
            "On 12 May 2026 John Ashtest shouted at you and you felt afraid.",
            "Our Advice",
            "Non-Molestation Order:",
            "Cost v Benefit Analysis",
            "The Funding Code is a set of rules used to decide what individual cases will be funded.",
        ],
    )
    source = _source(tmp_path / "source.txt")

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any("Benefit Analysis" in issue.location for issue in result.issues)
    assert any(check["name"] == "respondent_name" and check["detail"] == "John Ashtest" for check in result.checks)


def test_auditor_accepts_title_case_order_against_respondent_wording(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "You instructed us in relation to a Non-Molestation Order against John Ashtest.",
            "On 12 May 2026 John Ashtest shouted at you and you felt afraid.",
            "Our Advice",
            "Non-Molestation Order:",
        ],
    )
    source = _source(tmp_path / "source.txt")

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any(issue.code == "S011" for issue in result.issues)
    assert any(check["name"] == "respondent_name" and check["detail"] == "John Ashtest" for check in result.checks)


def test_auditor_does_not_match_occupation_order_acronym_inside_words(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "You instructed us in relation to a Non-Molestation Order against John Ashtest.",
            "On 12 May 2026 John Ashtest shouted at you near the school and you felt afraid.",
            "Our Advice",
            "Non-Molestation Order:",
            "The order may support clear handover arrangements connected with school.",
        ],
    )
    source = _source(
        tmp_path / "source.txt",
        "Jane Ashtest instructed CaseForge about John Ashtest and a non-molestation order. "
        "On 12 May 2026 John Ashtest shouted near the school and she felt afraid. "
        "The cool-down period and school handover were discussed.",
    )

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any(check["name"] == "order_OO" for check in result.checks)
    assert not any(issue.code == "S013" and "OO" in issue.message for issue in result.issues)


def test_auditor_accepts_ordinal_of_month_dates(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "On 11 April 2026 John Ashtest shouted at you and police attended.",
            "Our Advice",
            "Non-Molestation Order:",
        ],
    )
    source = _source(
        tmp_path / "source.txt",
        "Jane Ashtest instructed CaseForge about John Ashtest and a non-molestation order. On the 11th of April 2026 John Ashtest shouted at her and police attended.",
    )

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any(issue.code == "S021" for issue in result.issues)


def test_auditor_ignores_standard_advice_police_wording_for_crime_ref_warning(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "You instructed us in relation to your application for a Non-Molestation Order against John Ashtest.",
            "On 12 May 2026 John Ashtest shouted at you and you felt afraid.",
            "Our Advice",
            "Non-Molestation Order:",
            "If the Respondent breaches the order, you should contact the police immediately.",
        ],
    )
    source = _source(
        tmp_path / "source.txt",
        "Jane Ashtest instructed CaseForge about John Ashtest and a non-molestation order. On 12 May 2026 John Ashtest shouted at her and she felt afraid.",
    )

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any(issue.code == "S022" for issue in result.issues)


def test_auditor_blocks_firm_asserted_risk_phrasing(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "You instructed us in relation to your application for a Non-Molestation Order against John Ashtest.",
            "On 12 May 2026 John Ashtest assaulted you. Crime reference: 25009990003.",
            "You are at risk of significant harm and urgently need the protection of the Court.",
            "Our Advice",
            "Non-Molestation Order:",
            "If the Respondent breaches the order, you should contact the police immediately.",
        ],
    )
    source = _source(
        tmp_path / "source.txt",
        "Jane Ashtest instructed CaseForge about John Ashtest. On 12 May 2026 John Ashtest assaulted her. "
        "Crime Reference Number: 25009990003.",
    )

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert any(issue.code == "S031" for issue in result.issues)
    assert not result.passed


def test_auditor_matches_crime_ref_with_natural_is_phrasing(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "You instructed us in relation to your application for a Non-Molestation Order against John Ashtest.",
            "On 12 May 2026 John Ashtest assaulted you. The Crime Reference Number is 13259990002.",
            "Our Advice",
            "Non-Molestation Order:",
            "If the Respondent breaches the order, you should contact the police immediately.",
        ],
    )
    source = _source(
        tmp_path / "source.txt",
        "Jane Ashtest instructed CaseForge about John Ashtest. On 12 May 2026 John Ashtest assaulted her. "
        "Crime Reference Number: 13259990002.",
    )

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any(issue.code == "S022" for issue in result.issues)
    assert any(
        check["name"] == "crime_or_cad_reference" and check["status"] == "pass"
        for check in result.checks
    )


def test_auditor_matches_crime_ref_across_differing_label_wording(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "You instructed us in relation to your application for a Non-Molestation Order against John Ashtest.",
            "On 12 May 2026 John Ashtest assaulted you. Crime reference: 25009990003.",
            "Our Advice",
            "Non-Molestation Order:",
            "If the Respondent breaches the order, you should contact the police immediately.",
        ],
    )
    source = _source(
        tmp_path / "source.txt",
        "Jane Ashtest instructed CaseForge about John Ashtest. On 12 May 2026 John Ashtest assaulted her. "
        "Crime Reference Number: 25009990003.",
    )

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])

    assert not any(issue.code == "S022" for issue in result.issues)
    assert any(
        check["name"] == "crime_or_cad_reference" and check["status"] == "pass"
        for check in result.checks
    )


def test_auditor_blocks_and_redacts_c8_address_detail(tmp_path):
    ccl = _write_docx(
        tmp_path / "ccl.docx",
        [
            "Our Reference: 260520/01FL",
            "Dear Jane Ashtest",
            "Your Instructions",
            "C8 confidential address. You live at 10 Example Street ZZ99 9ZZ.",
        ],
    )
    source = _source(tmp_path / "source.txt", "Jane Ashtest C8 confidential address protected.")

    result = auditor.run_audit(ccl_docx=ccl, source_paths=[source])
    payload = result.to_dict()

    assert any(issue.code == "S023" for issue in result.issues)
    assert "ZZ99 9ZZ" not in json.dumps(payload)
    assert "[postcode redacted]" in json.dumps(payload)


def test_auditor_blocks_bad_draft_attachment_pack(tmp_path):
    ccl = _good_ccl(tmp_path / "ccl.docx")
    source = _source(tmp_path / "source.txt")
    draft = _draft(
        attachments=[
            {"name": "Client Care Letter - ASHTEST.pdf"},
            {"name": "Privacy Notice - CaseForge.pdf"},
            {"name": "extra.pdf"},
        ]
    )

    result = auditor.run_audit(
        ccl_docx=ccl,
        source_paths=[source],
        draft_message=draft["message"],
        draft_attachments=draft["attachments"],
    )

    assert not result.passed
    assert any(issue.code == "D005" for issue in result.issues)
    assert any(issue.code == "D006" for issue in result.issues)


def test_auditor_blocks_when_draft_payload_is_empty_but_not_none(tmp_path):
    ccl = _good_ccl(tmp_path / "ccl.docx")
    source = _source(tmp_path / "source.txt")

    result = auditor.run_audit(
        ccl_docx=ccl,
        source_paths=[source],
        draft_message={},
        draft_attachments=[],
    )

    assert not result.passed
    assert any(issue.code == "D007" for issue in result.issues)
