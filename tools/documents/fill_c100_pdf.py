"Durable C100 AcroForm filler."
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import london_time
from documents import sot_signature
from documents import form_standing_answers
from documents.c100_field_map import COURT_ONLY_FIELDS, FIELD_MAP, SOLICITOR_REFERENCE_FIELD
from documents.pdf_acroform_fill import fill_acroform
from vergil.crn import normalise_company_reference

BLANK_FORM = form_standing_answers.BLANK_FORMS["c100"]


def fill_c100(*, template: Path, output: Path, facts: dict, flatten: bool = False, company_reference: str | None = None) -> dict:
    unknown_keys = sorted(set(facts) - set(FIELD_MAP))
    raw_facts = {FIELD_MAP[key]: value for key, value in facts.items() if key in FIELD_MAP and FIELD_MAP[key] not in COURT_ONLY_FIELDS}
    raw_facts = {**form_standing_answers.standing_answers("c100"), **raw_facts}
    reference = normalise_company_reference(company_reference)
    if reference:
        raw_facts[SOLICITOR_REFERENCE_FIELD] = reference
    date_field = FIELD_MAP["statement_date"]
    if not str(raw_facts.get(date_field) or "").strip():
        raw_facts[date_field] = london_time.london_today().strftime("%d%m%Y")
    result = fill_acroform(template=template, output=output, facts=raw_facts, flatten=flatten)
    result["unknown_keys"] = unknown_keys
    result["solicitor_reference"] = raw_facts.get(SOLICITOR_REFERENCE_FIELD) or None
    result["signature"] = sot_signature.sign_file(output, "c100")
    return result


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts-json", required=True, help="Path to a JSON file of friendly-key -> value facts")
    parser.add_argument("--output", required=True, help="Output PDF path")
    parser.add_argument("--template", default=str(BLANK_FORM), help="Template PDF (default: the court's blank C100)")
    parser.add_argument("--flatten", action="store_true", help="Flatten the form fields in the output")
    parser.add_argument("--company-reference", help="The matter's company reference (YYMMDD/NNFL) for 14.2")
    return parser.parse_args()


def main():
    args = parse_args()
    facts = json.loads(Path(args.facts_json).read_text())
    result = fill_c100(
        template=Path(args.template),
        output=Path(args.output),
        facts=facts,
        flatten=args.flatten,
        company_reference=args.company_reference,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
