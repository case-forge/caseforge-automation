"Durable C1A AcroForm filler."
import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import london_time
from documents import form_standing_answers, sot_signature
from documents.pdf_acroform_fill import fill_acroform
from vergil.crn import normalise_company_reference

BLANK_FORM = form_standing_answers.BLANK_FORMS["c1a"]
SOLICITOR_REFERENCE_FIELD = "Your solicitor's reference"
CHILD_ABUSE_BOXES = {
    kind: f"abuse children have experienced - {kind}" for kind in ("physical", "emotional", "psychological", "sexual", "financial")
}
APPLICANT_ABUSE_BOXES = {
    kind: f"abuse you have experienced - {kind}" for kind in ("physical", "emotional", "psychological", "sexual", "financial")
}
PAIRED_ABUSE_KINDS = ("emotional", "psychological")


def paired_abuse_kinds(kinds):
    "``kinds`` with both of emotional and psychological when either is present."
    kinds = set(kinds)
    return kinds | set(PAIRED_ABUSE_KINDS) if kinds & set(PAIRED_ABUSE_KINDS) else kinds


def _with_abuse_pairs(facts: dict) -> dict:
    "``facts`` (by field name) with both boxes of the pair ticked in a row where either is."
    facts = dict(facts)
    for boxes in (CHILD_ABUSE_BOXES, APPLICANT_ABUSE_BOXES):
        pair = [boxes[kind] for kind in PAIRED_ABUSE_KINDS]
        if any(facts.get(name) for name in pair):
            facts.update(dict.fromkeys(pair, True))
    return facts


C8_BOXES = {"yes": "Form C8 - yes", "no": "Form C8 - no", "not applicable": "Form C8 - not applicable"}
INCIDENT_COLUMNS = {
    "when": "Timing of abuse - {n}",
    "what": "Nature of behaviour - {n}",
    "who": "Who sought help from - {n}",
    "action": "Action taken - {n}",
}
INCIDENT_ROWS = 5
CHILD_ROWS = 3
CHILD_ROW_FIELDS: tuple[dict[str, str], ...] = tuple(
    {
        "name": f"Name of children - {n}",
        "dob_dd": f"Child {n} date of birth - DD",
        "dob_mm": f"Child {n} date of birth - MM",
        "dob_yyyy": f"Child {n} date of birth - YYYY",
        "male": f"Child {n} - male",
        "female": f"Child {n} - female",
        "relationship": f"Child {n} - relationship to you",
    }
    for n in range(1, CHILD_ROWS + 1)
)
ABDUCTION_BOXES = ("Risk of abduction - yes", "Risk of abduction - no")
SECTION3_DETAIL_FIELDS = frozenset({
    "Reason for belief the children may be abducted",
    "previous attempts - yes", "previous attempts - no", "previous attempts details",
    "Where are the children now",
    "Passport office notified - yes", "Passport office notified - no",
    "more than one passport - yes", "more than one passport - no",
    "In possession of the child(ren)'s passport - mother", "In possession of the child(ren)'s passport - father",
    "In possession of the child(ren)'s passport - other", "details of who hold the passports, if other",
    "authorities involved - yes", "authorities involved - no", "details of organisations involved",
})
OWNER_DEFAULTS: dict[str, tuple[object, tuple[str, ...]]] = {
    "agree to unsupervised time - no": (True, ("agree to unsupervised time - yes",)),
    "agree to supervised time - no": (True, ("agree to supervised time - yes",)),
    "agree to other contact - no": (True, ("agree to other contact - yes",)),
    "Check Box2": (True, ("Check Box1", "Check Box3")),
    "Check Box6": (True, ("Check Box5", "Check Box7", "Check Box8")),
}
STATEMENT_DATE_BOXES = ("Text9", "Text10", "Text11")
STATEMENT_OF_TRUTH_TICKS = ("Check Box2", "Check Box6")

LAST_FILLED_PAGE = 7
AFTER_SIGNATURE_REASON = "after the signature page: nothing is filled there"


@lru_cache(maxsize=4)
def fields_after_signature(template: Path = BLANK_FORM) -> frozenset[str]:
    "Every field on a page after the signature page of ``template``."
    names = set()
    for number, page in enumerate(PdfReader(str(template)).pages, 1):
        if number <= LAST_FILLED_PAGE:
            continue
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            name = annot.get("/T") or (annot.get("/Parent").get_object().get("/T") if annot.get("/Parent") else None)
            if annot.get("/Subtype") == "/Widget" and name:
                names.add(str(name))
    return frozenset(names)
OTHER_CONCERNS_BOXES = (
    "other concerns about your child(ren)\u2019s safety and wellbeing - yes",
    "other concerns about your child(ren)\u2019s safety and wellbeing - no",
)
OTHER_CONCERNS_DETAILS = "details of concerns"
GENDER_BOXES = {"male": "Gender - male", "female": "Gender - female"}
COURT_ONLY_FIELDS: frozenset[str] = frozenset()
COURT_ONLY_REASON = "to be completed by the court"


def fill_c1a(*, template: Path, output: Path, facts: dict, flatten: bool = False, company_reference: str | None = None) -> dict:
    facts = {name: value for name, value in facts.items() if name not in COURT_ONLY_FIELDS}
    facts = {**form_standing_answers.standing_answers("c1a"), **facts}
    facts = _with_abuse_pairs(facts)
    reference = normalise_company_reference(company_reference)
    if reference:
        facts[SOLICITOR_REFERENCE_FIELD] = reference
    if not any(str(facts.get(name) or "").strip() for name in STATEMENT_DATE_BOXES):
        today = london_time.london_today()
        facts.update(zip(STATEMENT_DATE_BOXES, (f"{today.day:02d}", f"{today.month:02d}", str(today.year))))
    for name in STATEMENT_OF_TRUTH_TICKS:
        _value, clears = OWNER_DEFAULTS[name]
        if not any(facts.get(box) for box in (name, *clears)):
            facts[name] = True
    result = fill_acroform(template=template, output=output, facts=facts, flatten=flatten)
    result["solicitor_reference"] = facts.get(SOLICITOR_REFERENCE_FIELD) or None
    result["signature"] = sot_signature.sign_file(output, "c1a")
    return result


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts-json", required=True, help="Path to a JSON file of field-name -> value facts")
    parser.add_argument("--output", required=True, help="Output PDF path")
    parser.add_argument("--template", default=str(BLANK_FORM), help="Template PDF (default: the court's blank C1A)")
    parser.add_argument("--flatten", action="store_true", help="Flatten the form fields in the output")
    parser.add_argument("--company-reference", help="The matter's company reference (YYMMDD/NNFL)")
    return parser.parse_args()


def main():
    args = parse_args()
    facts = json.loads(Path(args.facts_json).read_text())
    result = fill_c1a(
        template=Path(args.template),
        output=Path(args.output),
        facts=facts,
        flatten=args.flatten,
        company_reference=args.company_reference,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
