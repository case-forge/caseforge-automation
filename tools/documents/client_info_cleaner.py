#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SOURCE_PRIORITY = {
    "later_update": 10,
    "client_update": 10,
    "solicitor_update": 10,
    "witness_statement": 20,
    "statement": 20,
    "referral": 30,
    "intro": 30,
    "referralpartner_referral": 30,
    "referralpartner_intro": 30,
    "fl401": 40,
    "c100": 40,
    "c1a": 40,
    "sql": 90,
    "existing_sql": 90,
}

FIELD_ALIASES = {
    "client_name": "client_name",
    "applicant_name": "client_name",
    "name": "client_name",
    "client_dob": "client_dob",
    "applicant_dob": "client_dob",
    "dob": "client_dob",
    "client_address": "applicant_address",
    "applicant_address": "applicant_address",
    "address": "applicant_address",
    "applicant_postcode": "applicant_postcode",
    "client_postcode": "applicant_postcode",
    "postcode": "applicant_postcode",
    "client_phone": "applicant_phone",
    "applicant_phone": "applicant_phone",
    "phone": "applicant_phone",
    "client_email": "applicant_email",
    "applicant_email": "applicant_email",
    "email": "applicant_email",
    "respondent_name": "respondent_name",
    "other_party_name": "respondent_name",
    "respondent_dob": "respondent_dob",
    "respondent_address": "respondent_address",
    "other_party_address": "respondent_address",
    "respondent_postcode": "respondent_postcode",
    "respondent_phone": "respondent_phone",
    "other_party_phone": "respondent_phone",
    "respondent_email": "respondent_email",
    "other_party_email": "respondent_email",
    "relationship_start": "relationship_start",
    "relationship_started": "relationship_start",
    "relationship_start_date": "relationship_start",
    "relationship_end": "relationship_end",
    "relationship_ended": "relationship_end",
    "relationship_end_date": "relationship_end",
    "has_c8": "has_c8",
    "c8": "has_c8",
    "c8_flag": "has_c8",
    "order_type": "order_type",
    "order_requested": "order_type",
}

CURRENT_UPDATE_TARGETS = {
    "applicant_address": "matter_parties.address_text[Applicant]",
    "respondent_address": "matter_parties.address_text[Respondent]",
    "applicant_phone": "people.phone_primary",
    "applicant_email": "people.email_primary",
    "respondent_phone": "matter_parties.phone_primary[Respondent]",
    "respondent_email": "matter_parties.email_primary[Respondent]",
    "relationship_start": "matters.relationship_start",
    "relationship_end": "matters.relationship_end",
}

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
WITHHELD_RE = re.compile(r"\b(c8|withheld|w/h|confidential|unknown|n/a|not known)\b", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


@dataclass(frozen=True)
class ParsedFact:
    field: str
    value: str
    source_kind: str
    source_label: str
    source_date: str
    source_rank: int
    source_index: int

    def sort_key(self) -> tuple[int, int, int]:
        return (self.source_rank, -_date_key(self.source_date).toordinal(), -self.source_index)

    def public_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "source_kind": self.source_kind,
            "source_label": self.source_label,
            "source_date": self.source_date,
            "source_rank": self.source_rank,
        }


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalise_source_kind(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", clean_text(value).lower()).strip("_")
    if text in {"ws", "witness", "witness_statement"}:
        return "witness_statement"
    if text in {"referral_partner", "referral_partner_referral", "referralpartner_referral", "referral_pdf"}:
        return "referral"
    if text in {"referral_partner_intro", "referralpartner_intro", "intro_pdf", "intro_email"}:
        return "intro"
    if text in {"client", "client_email", "client_message", "direct_update"}:
        return "client_update"
    return text or "unknown"


def source_rank(source_kind: str) -> int:
    return SOURCE_PRIORITY.get(normalise_source_kind(source_kind), 80)


def canonical_field(name: Any) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", clean_text(name).lower()).strip("_")
    return FIELD_ALIASES.get(key, key)


def _date_key(value: str) -> dt.date:
    text = clean_text(value)
    if not text:
        return dt.date.min
    for raw in (text[:10], text):
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            pass
    year = first_year(text)
    return dt.date(year, 1, 1) if year else dt.date.min


def first_year(value: Any) -> int | None:
    match = YEAR_RE.search(clean_text(value))
    return int(match.group(1)) if match else None


def normalise_postcode(value: Any) -> str:
    match = POSTCODE_RE.search(clean_text(value).upper())
    return f"{match.group(1)} {match.group(2)}".upper() if match else ""


def is_blank_or_withheld(value: Any) -> bool:
    text = clean_text(value)
    return not text or bool(WITHHELD_RE.search(text))


def _normalise_for_compare(field: str, value: Any) -> str:
    text = clean_text(value)
    if field.endswith("_email"):
        return text.lower()
    if field.endswith("_phone"):
        digits = re.sub(r"\D+", "", text)
        return "0" + digits[2:] if digits.startswith("44") and len(digits) == 12 else digits
    if field.endswith("_address"):
        text = re.sub(r"\b(united kingdom|great britain|england|uk)\b", "", text, flags=re.I)
        return re.sub(r"[^a-z0-9]+", "", text.lower())
    if field in {"relationship_start", "relationship_end"}:
        year = first_year(text)
        return str(year or text.lower())
    return text.lower()


def _extract_facts(source: dict[str, Any], source_index: int) -> list[ParsedFact]:
    kind = normalise_source_kind(source.get("source_kind") or source.get("kind") or source.get("type"))
    rank = int(source.get("source_rank") or source_rank(kind))
    label = clean_text(source.get("source_label") or source.get("label") or kind)
    source_date = clean_text(source.get("source_date") or source.get("date") or source.get("modified_at"))
    raw_facts = source.get("facts") if isinstance(source.get("facts"), dict) else source
    facts: list[ParsedFact] = []
    for raw_field, raw_value in raw_facts.items():
        if raw_field in {"source_kind", "kind", "type", "source_rank", "source_label", "label", "source_date", "date", "modified_at", "facts"}:
            continue
        field = canonical_field(raw_field)
        value = clean_text(raw_value)
        if not value:
            continue
        facts.append(
            ParsedFact(
                field=field,
                value=value,
                source_kind=kind,
                source_label=label,
                source_date=source_date,
                source_rank=rank,
                source_index=source_index,
            )
        )
    return facts


def parsed_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources = payload.get("sources")
    if isinstance(sources, list):
        out = [source for source in sources if isinstance(source, dict)]
    else:
        out = []
    sql_current = payload.get("sql_current") or payload.get("current")
    if isinstance(sql_current, dict) and payload.get("include_current_as_source"):
        out.append({"source_kind": "sql", "source_label": "Current SQL", "facts": sql_current})
    return out


def collect_facts(payload: dict[str, Any]) -> dict[str, list[ParsedFact]]:
    collected: dict[str, list[ParsedFact]] = {}
    for index, source in enumerate(parsed_sources(payload)):
        for fact in _extract_facts(source, index):
            collected.setdefault(fact.field, []).append(fact)
    return collected


def choose_facts(collected: dict[str, list[ParsedFact]]) -> dict[str, ParsedFact]:
    chosen: dict[str, ParsedFact] = {}
    for field, facts in collected.items():
        chosen[field] = sorted(facts, key=lambda fact: fact.sort_key())[0]
    return chosen


def _has_c8(chosen: dict[str, ParsedFact]) -> bool:
    fact = chosen.get("has_c8")
    return bool(fact and clean_text(fact.value).lower() in {"1", "true", "yes", "y", "c8"})


def _issue(severity: str, code: str, field: str, message: str, sources: list[ParsedFact] | None = None) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "field": field,
        "message": message,
        "sources": [source.public_dict() for source in sources or []],
    }


def lint_missing_postcodes(collected: dict[str, list[ParsedFact]], chosen: dict[str, ParsedFact]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    has_c8 = _has_c8(chosen)
    for field in ("applicant_address", "respondent_address"):
        for fact in collected.get(field, []):
            if is_blank_or_withheld(fact.value):
                continue
            if field == "applicant_address" and has_c8:
                continue
            postcode_field = "applicant_postcode" if field == "applicant_address" else "respondent_postcode"
            related_postcodes = [
                candidate for candidate in collected.get(postcode_field, [])
                if candidate.source_kind == fact.source_kind and candidate.source_label == fact.source_label
            ]
            if normalise_postcode(fact.value) or any(normalise_postcode(candidate.value) for candidate in related_postcodes):
                continue
            severity = "review" if fact.source_kind in {"fl401", "c100", "c1a"} else "info"
            issues.append(
                _issue(
                    severity,
                    "MISSING_POSTCODE",
                    field,
                    f"{fact.source_label} has {field.replace('_', ' ')} but no valid UK postcode.",
                    [fact],
                )
            )
    return issues


def lint_relationship_dates(collected: dict[str, list[ParsedFact]], chosen: dict[str, ParsedFact]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in ("relationship_start", "relationship_end"):
        facts = collected.get(field, [])
        if not facts:
            continue
        chosen_fact = chosen[field]
        chosen_year = first_year(chosen_fact.value)
        for fact in facts:
            if fact == chosen_fact:
                continue
            year = first_year(fact.value)
            if not chosen_year or not year or year == chosen_year:
                continue
            likely_decade_typo = abs(chosen_year - year) == 10 and chosen_year % 10 == year % 10
            code = "LIKELY_DECADE_TYPO" if likely_decade_typo else "RELATIONSHIP_YEAR_CONFLICT"
            severity = "blocker" if likely_decade_typo and fact.source_kind in {"fl401", "c100", "c1a"} else "review"
            issues.append(
                _issue(
                    severity,
                    code,
                    field,
                    (
                        f"{fact.source_label} gives {field.replace('_', ' ')} as {fact.value}; "
                        f"{chosen_fact.source_label} gives {chosen_fact.value}."
                    ),
                    [chosen_fact, fact],
                )
            )
    start = chosen.get("relationship_start")
    end = chosen.get("relationship_end")
    start_year = first_year(start.value) if start else None
    end_year = first_year(end.value) if end else None
    if start_year and end_year and end_year < start_year:
        issues.append(
            _issue(
                "blocker",
                "RELATIONSHIP_END_BEFORE_START",
                "relationship_end",
                f"Relationship end year {end_year} is before start year {start_year}.",
                [start, end],
            )
        )
    return issues


def lint_fl401_required_fields(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        kind = normalise_source_kind(source.get("source_kind") or source.get("kind") or source.get("type"))
        if kind not in {"fl401", "c100", "c1a"}:
            continue
        facts = {fact.field: fact for fact in _extract_facts(source, index)}
        for field in ("relationship_start", "relationship_end"):
            if field not in facts:
                label = clean_text(source.get("source_label") or source.get("label") or kind)
                issues.append(
                    {
                        "severity": "review",
                        "code": "APPLICATION_RELATIONSHIP_DATE_MISSING",
                        "field": field,
                        "message": f"{label} does not include parsed {field.replace('_', ' ')}.",
                        "sources": [],
                    }
                )
    return issues


def build_update_recommendations(payload: dict[str, Any], chosen: dict[str, ParsedFact]) -> list[dict[str, Any]]:
    current = payload.get("sql_current") or payload.get("current") or {}
    if not isinstance(current, dict):
        return []
    current_by_field = {canonical_field(key): clean_text(value) for key, value in current.items()}
    updates: list[dict[str, Any]] = []
    for field, target in CURRENT_UPDATE_TARGETS.items():
        fact = chosen.get(field)
        if not fact:
            continue
        current_value = current_by_field.get(field, "")
        if _normalise_for_compare(field, current_value) == _normalise_for_compare(field, fact.value):
            continue
        updates.append(
            {
                "field": field,
                "target": target,
                "current_value": current_value,
                "new_value": fact.value,
                "source_kind": fact.source_kind,
                "source_label": fact.source_label,
                "reason": "replace current value from highest-priority parsed source",
            }
        )
    return updates


def clean_client_info(payload: dict[str, Any]) -> dict[str, Any]:
    sources = parsed_sources(payload)
    collected = collect_facts(payload)
    chosen = choose_facts(collected)
    issues = []
    issues.extend(lint_missing_postcodes(collected, chosen))
    issues.extend(lint_relationship_dates(collected, chosen))
    issues.extend(lint_fl401_required_fields(sources))
    severity_order = {"blocker": 0, "review": 1, "info": 2}
    issues.sort(key=lambda item: (severity_order.get(str(item.get("severity")), 9), str(item.get("code")), str(item.get("field"))))
    updates = build_update_recommendations(payload, chosen)
    return {
        "ok": not any(issue["severity"] == "blocker" for issue in issues),
        "chosen": {field: fact.public_dict() for field, fact in sorted(chosen.items())},
        "issues": issues,
        "updates": updates,
        "summary": {
            "source_count": len(sources),
            "field_count": len(chosen),
            "blockers": sum(1 for issue in issues if issue["severity"] == "blocker"),
            "review": sum(1 for issue in issues if issue["severity"] == "review"),
            "info": sum(1 for issue in issues if issue["severity"] == "info"),
            "updates": len(updates),
        },
    }


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean parsed client facts and flag source conflicts.")
    parser.add_argument("--input-json", type=Path, required=True, help="Parsed source facts JSON.")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional path for the cleaner result.")
    parser.add_argument("--fail-on-blocker", action="store_true", help="Exit 2 when blocker issues are found.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = clean_client_info(load_payload(args.input_json))
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.fail_on_blocker and not result["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
