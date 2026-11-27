#!/usr/bin/env python3
"Fill a court form (C100, C1A) from a client's witness statement in two model stages."
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

TOOLS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from pypdf import PdfReader

import field_shapes
import model_backend
import order_codes
from documents import c8_protection, c100_field_map, fill_c1a_pdf, form_standing_answers, pdf_field_labeller, sot_signature
from documents.address_utils import split_form_address
from documents.pdf_acroform_fill import field_max_lengths, fill_acroform, fit_text
from vergil.crn import normalise_company_reference

FORMS = {form: form_standing_answers.BLANK_FORMS[form] for form in ("c100", "c1a")}
REFERENCE_FIELDS = {"c100": c100_field_map.SOLICITOR_REFERENCE_FIELD, "c1a": fill_c1a_pdf.SOLICITOR_REFERENCE_FIELD}
CHUNK_FIELDS = 70
EXCLUDED_RE = re.compile(r"(?i)have you completed section|statement of truth|signature|signed by|date of signing")
_DATE_VALUE_RE = re.compile(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{4})$")
NARRATIVE_CHARS = 120
TBC = "TBC"

_NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.*)$", re.S)
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}

EXTRACT_SYSTEM = (
    "You extract facts from a client's own witness statement for a UK family-law firm. Use British "
    "English. Report only what the statement states: never infer, never fill a gap, never use outside "
    "knowledge. A fact that is not stated is null (or an empty list); an incident the statement does "
    "not date has a null date. Lines marked [heading] are the statement's own heading and name the "
    "parties and children. Give dates as YYYY-MM-DD when complete, otherwise exactly as written. Cite "
    "the numbered paragraphs each incident comes from. other_applicants (a second or further applicant), "
    "other_respondents (a second or further respondent), "
    "others_to_notify (someone who is not a party but must be told of the application, such as a carer who is "
    "not a parent) and other_children_not_in_application stay empty unless the statement names such a person. "
    "In risk_of_harm each concern is true only when the statement alleges it (domestic_abuse: any form of "
    "domestic abuse; child_abuse: abuse of a child; substance_misuse: drugs, alcohol or substance misuse by "
    "anyone with contact with the children; other_safety_welfare: a concern for the children's safety or "
    "welfare that is none of the other four, each such concern listed in one line in other_concerns), "
    "otherwise null. The applicant's title is as written (Mrs, Ms, Mr); interpreter_language only when "
    "the statement says the applicant needs an interpreter. Each incident's victims and witnesses name "
    "who was harmed and who saw or heard it, using the children's names where the statement gives them; "
    "abuse_types lists only those of physical, emotional, psychological, sexual, financial that the "
    "statement describes for that incident. applicant_abuse_types and children_abuse_types list, from the same "
    "five, the kinds the statement says the applicant and the children have experienced. abuse_kinds_listed is the "
    "list of kinds of abuse the statement itself names for the whole relationship, each as one lower-case word in the "
    "statement's own wording (for example physical, verbal, emotional, financial), in the order it gives them; never a "
    "kind it does not name. An incident's "
    "police_outcome is what the police did (for example \"No further action\", arrested, charged, cautioned), "
    "null when the statement does not say; the applicant reporting it to the police is not an outcome. "
    "Reply with strict JSON only, no fences, in exactly this shape: "
    '{"applicant": {"full_name": null, "first_names": null, "last_name": null, "dob": null, "sex": null, "address": null, "phone": null, "email": null, "title": null, "interpreter_language": null}, '
    '"respondent": {"full_name": null, "first_names": null, "last_name": null, "dob": null, "sex": null, "address": null, "phone": null, "email": null, "relationship_to_applicant": null, "substance_use": null}, '
    '"children": [{"full_name": null, "first_names": null, "last_name": null, "dob": null, "sex": null, "relationship_to_applicant": null, "respondent_has_parental_responsibility": null}], '
    '"relationship": {"started": null, "ended": null, "living_together": null}, '
    '"other_applicants": [], "other_respondents": [], "others_to_notify": [], "other_children_not_in_application": [], '
    '"risk_of_harm": {"domestic_abuse": null, "child_abduction": null, "child_abuse": null, "substance_misuse": null, "other_safety_welfare": null}, '
    '"other_concerns": [], "applicant_abuse_types": [], "children_abuse_types": [], "abuse_kinds_listed": [], "orders_sought": [], "urgent": null, "without_notice": null, "without_notice_reason": null, '
    '"incidents": [{"date": null, "summary": "", "victims": [], "witnesses": [], "abuse_types": [], "reported_to": [], "police_crime_ref": null, "police_outcome": null, "outcome": null, "paragraphs": []}], '
    '"abuse_alleged": [], "other_agencies_involved": [], "other_facts": []}'
)

MAP_SYSTEM = (
    "You complete part of a UK court form for a family-law firm, in British English, from structured "
    "facts. You are given the facts as JSON and a list of this part's form fields, one per line as "
    "`id | page | kind | question | label | options`. Decide which fields the facts answer. Rules: "
    "use only the facts, never invent or guess; leave a field out when the facts do not answer it; "
    "text fields get a string (dates as DD/MM/YYYY, postcodes as written); a field labelled first "
    "name(s) takes the given names only and one labelled last name the surname only (use the facts' "
    "first_names and last_name); a tick box is `true` only when the facts clearly say so, otherwise "
    "leave it out. Silence is never an answer: do not tick a \"No\" or \"Don't know\" box, or fill a "
    "field, because the facts do not mention the matter; put it in `tbc` with a short reason. A field "
    "that needs a person's judgement or information the facts lack also goes in `tbc`. For narrative boxes write plain "
    "factual prose from the facts only, neutral, no legal argument. "
    'Reply with strict JSON only, no fences: {"fills": {"<id>": <string or true>}, "tbc": {"<id>": "<reason>"}}.'
)




def statement_paragraphs(docx_path: Path | str) -> list[str]:
    "The statement as lines for a model: the heading block (court, parties, children, the"
    from docx import Document

    heading: list[str] = []
    body: list[str] = []
    started = False
    for p in Document(str(docx_path)).paragraphs:
        text = p.text.strip()
        if not text or set(text) <= {"_", "-", " "}:
            continue
        if re.match(r"^\d+\.\s", text.replace("\t", " ")):
            started = True
        if text.upper().startswith(("STATEMENT OF TRUTH", "I BELIEVE THAT THE FACTS")):
            break
        if started:
            body.append(re.sub(r"^(\d+)\.\s+", r"\1. ", text.replace("\t", " ")))
        elif not re.fullmatch(r"B\s*E\s*T\s*W\s*E\s*E\s*N:?", text, re.I):
            heading.append("[heading] " + text.replace("\n", " "))
    return heading + body



CALL_TIMEOUT_SECONDS = 300
CALL_RETRIES = 1


def _call(model: str, system: str, prompt: str, *, max_tokens: int, timeout: float = CALL_TIMEOUT_SECONDS) -> tuple[dict[str, Any], dict[str, Any]]:
    "One model call, retried once when the backend fails (a timeout or a transient error)."
    started = time.time()
    for attempt in range(1 + CALL_RETRIES):
        result = model_backend.run_model(
            model_backend.ROLE_FORM_FILL_STRONG, prompt, model=model, backend="openrouter", system_prompt=system,
            timeout=timeout, max_tokens=max_tokens, route_reason="form-fill-pipeline",
        )
        if result.ok:
            break
    meta = {"model": model, "ok": result.ok, "seconds": round(time.time() - started, 1), "usage": result.usage}
    if not result.ok:
        meta["error"] = result.attempts[-1].error if result.attempts else "unknown"
        return {}, meta
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.M).strip()
    try:
        return json.loads(raw), meta
    except json.JSONDecodeError as exc:
        meta["error"] = f"not JSON: {exc}"
        meta["raw"] = raw[:400]
        return {}, meta


_ISO_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")
_MONTH_NAMES = "|".join(_MONTHS)


def _dates_in(text: str) -> tuple[set[tuple[int, int, int]], set[tuple[int, int]]]:
    "(complete dates, year-month pairs) the text states, from ``1 October 2026``, ``October 2026``,"
    full: set[tuple[int, int, int]] = set()
    months: set[tuple[int, int]] = set()
    for m in re.finditer(rf"(?i)\b(?:(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?)?({_MONTH_NAMES})(?:\s+of)?,?\s+(\d{{4}})\b", text):
        month, year = _MONTHS[m.group(2).lower()], int(m.group(3))
        months.add((year, month))
        if m.group(1):
            full.add((year, month, int(m.group(1))))
    for m in re.finditer(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", text):
        full.add((int(m.group(3)), int(m.group(2)), int(m.group(1))))
        months.add((int(m.group(3)), int(m.group(2))))
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        full.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
        months.add((int(m.group(1)), int(m.group(2))))
    return full, months


def drop_unsupported_dates(facts: Any, statement: str, removed: list[str] | None = None) -> Any:
    "Facts with every ISO date the statement does not state replaced by None."
    full, months = _dates_in(statement)
    if isinstance(facts, dict):
        return {k: drop_unsupported_dates(v, statement, removed) for k, v in facts.items()}
    if isinstance(facts, list):
        return [drop_unsupported_dates(v, statement, removed) for v in facts]
    if isinstance(facts, str):
        m = _ISO_RE.match(facts)
        if m:
            year, month = int(m.group(1)), int(m.group(2))
            if (year, month, int(m.group(3))) in full if m.group(3) else (year, month) in months:
                return facts
            if removed is not None:
                removed.append(facts)
            return f"{year:04d}-{month:02d}" if m.group(3) and (year, month) in months else None
    return facts


def extract_facts(paragraphs: list[str], *, model: str | None = None, max_tokens: int = 6000) -> tuple[dict[str, Any], dict[str, Any]]:
    model = model or model_backend.model_for_role(model_backend.ROLE_FORM_FILL_CHEAP, backend="openrouter")
    facts, meta = _call(model, EXTRACT_SYSTEM, "Witness statement:\n\n" + "\n\n".join(paragraphs), max_tokens=max_tokens)
    if facts:
        removed: list[str] = []
        facts = drop_unsupported_dates(facts, "\n".join(paragraphs), removed)
        if removed:
            meta["dates_dropped"] = removed
    return facts, meta




def catalogue(form_pdf: Path | str) -> list[dict[str, Any]]:
    "Fields a model may fill: every labelled field the firm has not already filled."
    filled = {k for k, v in (PdfReader(str(form_pdf)).get_fields() or {}).items() if v.get("/V") not in (None, "", "/Off")}
    entries = []
    for w in pdf_field_labeller.label_widgets(form_pdf):
        if w["name"] in filled or w["kind"] in {"signature", "button"}:
            continue
        label = w["right"] if w["kind"] in {"checkbox", "radio"} and w["right"] else (w["above"] or w["left"] or w["right"] or w["tooltip"])
        if EXCLUDED_RE.search(f"{w['question']} {label} {w['above']}"):
            continue
        entries.append({**w, "id": len(entries), "label_text": label})
    return entries


def _line(e: dict[str, Any]) -> str:
    options = f"tick:{e['right'] or e['left']}" if e["kind"] in {"checkbox", "radio"} else (f"max {e['maxlen']}" if e["maxlen"] else "")
    return f"{e['id']} | p{e['page']} | {e['kind']} | {e['question'][:70]} | {e['label_text'][:70]} | {options}"


_SECTION_RE = re.compile(r"^(?:(\d{1,2})(?:\.\d{1,2})?[a-z]?\.?\s+(?=[A-Z])|Section\s+(\d+)\b)")


def section_groups(entries: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    "The catalogue cut at the form's own sections: ``(title, entries)`` in form order."
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    current = ""
    for e in entries:
        m = _SECTION_RE.match(e["question"])
        key = (m.group(1) or m.group(2)) if m else current
        if key != current or not groups:
            groups.append((e["question"] or f"page {e['page']}", []))
            current = key
        groups[-1][1].append(e)
    out: list[tuple[str, list[dict[str, Any]]]] = []
    for title, members in groups:
        for start in range(0, len(members), CHUNK_FIELDS):
            out.append((title, members[start : start + CHUNK_FIELDS]))
    return out


def map_facts(
    facts: dict[str, Any], entries: list[dict[str, Any]], *, form: str, model: str | None = None, sections: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    "Stage 2 over the catalogue in chunks (a form has hundreds of fields); merged fills and tbc."
    model = model or model_backend.model_for_role(model_backend.ROLE_FORM_FILL_STRONG, backend="openrouter")
    fills: dict[str, Any] = {}
    tbc: dict[str, str] = {}
    metas: list[dict[str, Any]] = []
    chunks = (
        section_groups(entries)
        if sections
        else [("", entries[start : start + CHUNK_FIELDS]) for start in range(0, len(entries), CHUNK_FIELDS)]
    )
    for title, chunk in chunks:
        prompt = (
            f"Form: {form.upper()}\n" + (f"Section being completed: {title}\n" if title else "") + f"\nFacts (JSON):\n{json.dumps(facts, ensure_ascii=False)}\n\n"
            "Fields (id | page | kind | question | label | options):\n" + "\n".join(_line(e) for e in chunk)
        )
        parsed, meta = _call(model, MAP_SYSTEM, prompt, max_tokens=4000)
        metas.append(meta)
        valid = {str(e["id"]) for e in chunk}
        fills.update({k: v for k, v in (parsed.get("fills") or {}).items() if str(k) in valid})
        tbc.update({k: str(v) for k, v in (parsed.get("tbc") or {}).items() if str(k) in valid})
    return {"fills": fills, "tbc": tbc}, metas




def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _haystack(statement: str, facts: dict[str, Any]) -> set[str]:
    blob = statement + " " + json.dumps(facts, ensure_ascii=False)
    tokens = _tokens(blob)
    for m in re.finditer(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+)\s+(\d{4})", blob):
        month = _MONTHS.get(m.group(2).lower())
        if month:
            tokens |= {str(int(m.group(1))), f"{int(m.group(1)):02d}", str(month), f"{month:02d}", m.group(3)}
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", blob):
        tokens |= {m.group(1), m.group(2), str(int(m.group(2))), m.group(3), str(int(m.group(3)))}
    return tokens


def grounded(value: str, haystack: set[str], dates: set[tuple[int, int, int]] | None = None) -> bool:
    "Every word and number of a short value appears in the statement or facts. A narrative box"
    m = _DATE_VALUE_RE.match(value.strip())
    if m and dates is not None:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1))) in dates
    words = _tokens(value)
    if not words:
        return True
    if len(value) <= NARRATIVE_CHARS:
        return all(w in haystack for w in words if any(c.isdigit() for c in w) or len(w) > 3) or len(words & haystack) / len(words) >= 0.8
    return len(words & haystack) / len(words) >= 0.7


def check_and_fill(
    result: dict[str, Any],
    entries: list[dict[str, Any]],
    statement: str,
    facts: dict[str, Any],
    *,
    form_pdf: Path | str,
    out_pdf: Path | str,
    exclude: Iterable[str] = (),
    overrides: dict[str, Any] | None = None,
    form: str | None = None,
    matter: Mapping[str, Any] | None = None,
    c8_text: str | None = None,
    fl401: Mapping[str, Any] | str | None = None,
) -> dict[str, Any]:
    form = form or form_name(form_pdf)
    exclude = list(exclude)
    blocked = blocked_fields(form, facts)
    by_id = {str(e["id"]): e for e in entries}
    haystack = _haystack(statement, facts)
    dates = _dates_in(statement + " " + json.dumps(facts, ensure_ascii=False))[0]
    values: dict[str, Any] = {}
    report: dict[str, Any] = {"filled": [], "ungrounded": [], "dropped": [], "tbc": [], "blocked": []}
    for fid, value in (result.get("fills") or {}).items():
        e = by_id.get(str(fid))
        if e is None:
            report["dropped"].append({"id": fid, "why": "not a field in the catalogue"})
            continue
        ref = {"id": e["id"], "field": e["name"], "page": e["page"], "question": e["question"][:60], "label": e["label_text"][:60]}
        if e["name"] in blocked:
            report["blocked"].append({**ref, "why": blocked[e["name"]]})
            continue
        if e["kind"] in {"checkbox", "radio"}:
            if value is True:
                values[e["name"]] = True
                report["filled"].append({**ref, "value": True})
            else:
                report["dropped"].append({**ref, "why": f"tick box needs true, got {value!r}"})
            continue
        text = " ".join(str(value).split())
        if not text or text.upper() == TBC:
            continue
        if not grounded(text, haystack, dates):
            report["ungrounded"].append({**ref, "value": text[:120]})
            continue
        fitted = fit_text(text, e["maxlen"])
        if fitted is None:
            report["dropped"].append({**ref, "why": f"longer than the box ({e['maxlen']})", "value": text[:60]})
            continue
        text = fitted
        values[e["name"]] = text
        report["filled"].append({**ref, "value": text[:120]})
    dropped_by_person = [name for name in exclude if values.pop(name, None) is not None]
    reference_field = REFERENCE_FIELDS.get(form or "")
    reference = normalise_company_reference((matter or {}).get("company_reference"))
    if reference_field:
        if reference and reference_field not in exclude:
            values[reference_field] = reference
        report["reference"] = {"field": reference_field, "value": reference or None}
    derived = derived_values(form, facts, values, matter=matter, statement=statement)
    for name in derived["clear"] - set(derived["set"]):
        values.pop(name, None)
    values.update({name: value for name, value in derived["set"].items() if name not in exclude})
    report["derived"] = [{"field": name, "value": value, "why": derived["why"][name]} for name, value in derived["set"].items()]
    report["tbc"].extend(derived["tbc"])
    report["attention"] = derived["attention"]
    values.update(overrides or {})
    if form == "c1a":
        values = fill_c1a_pdf._with_abuse_pairs(values)
    if form == "c100":
        for field, dont_know in c100_field_map.DONT_KNOW_IF_EMPTY.items():
            if values.get(field):
                if dont_know not in (overrides or {}):
                    values.pop(dont_know, None)
            elif dont_know not in exclude:
                values[dont_know] = True
                report["derived"].append({"field": dont_know, "value": True, "why": "owner default: Don't know when not filled"})
    for name in [n for n in values if n in blocked]:
        values.pop(name)
        report["blocked"].append({"field": name, "why": blocked[name] + " (set by a person)"})
    report["c8"] = apply_c8(form, values, facts, statement, matter=matter, c8_text=c8_text, fl401=fl401, form_pdf=form_pdf)
    report["excluded"] = dropped_by_person
    report["overridden"] = sorted(overrides or {})
    for fid, why in (result.get("tbc") or {}).items():
        e = by_id.get(str(fid))
        if e:
            report["tbc"].append({"id": e["id"], "page": e["page"], "question": e["question"][:60], "label": e["label_text"][:60], "why": why})
    values = {name: uk_dates(value) if isinstance(value, str) else value for name, value in values.items()}
    report["fill"] = fill_acroform(template=Path(form_pdf), output=Path(out_pdf), facts=values, flatten=False)
    if form in sot_signature.FORMS:
        report["signature"] = sot_signature.sign_file(Path(out_pdf), form)
    for name, lengths in report["fill"]["overlong_fields"].items():
        report["dropped"].append({"field": name, "why": f"longer than the box ({lengths['max_length']})"})
    return report



ABUSE_KINDS = ("physical", "emotional", "psychological", "sexual", "financial")
_CHILD_WORDS = {"child", "children", "son", "sons", "daughter", "daughters", "baby", "kids"}
_NO_SUBSTANCE_RE = re.compile(r"(?i)^\s*(?:no|none|nil|not stated|not known|unknown|n/?a)\b")


def _child_tokens(facts: dict[str, Any]) -> set[str]:
    "Words that name a child: the children's given names and the usual words for a child. Surnames"
    given: set[str] = set()
    surnames: set[str] = set()
    for child in facts.get("children") or []:
        if not isinstance(child, dict):
            continue
        full = re.findall(r"[a-z0-9]+", str(child.get("full_name") or "").lower())
        given |= _tokens(str(child.get("first_names") or "")) | set(full[:-1] if len(full) > 1 else full)
        surnames |= _tokens(str(child.get("last_name") or "")) | set(full[-1:] if len(full) > 1 else [])
    return (_CHILD_WORDS | given) - surnames


def _names_a_child(people: Any, child_tokens: set[str]) -> bool:
    people = people if isinstance(people, list) else [people] if people else []
    return any(_tokens(str(person)) & child_tokens for person in people)


def child_incidents(facts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    "(incidents with a child among the victims, incidents a child witnessed but was not a victim of)."
    tokens = _child_tokens(facts)
    victim: list[dict[str, Any]] = []
    witnessed: list[dict[str, Any]] = []
    for incident in facts.get("incidents") or []:
        if not isinstance(incident, dict):
            continue
        if _names_a_child(incident.get("victims"), tokens):
            victim.append(incident)
        elif _names_a_child(incident.get("witnesses"), tokens):
            witnessed.append(incident)
    return victim, witnessed


def _abuse_types(incident: dict[str, Any]) -> set[str]:
    return {str(kind).strip().lower() for kind in incident.get("abuse_types") or []} & set(ABUSE_KINDS)


def risks_supported(facts: dict[str, Any]) -> dict[str, str]:
    "Page 4 concerns the facts support, each with the fact that supports it. Never from silence:"
    stated = facts.get("risk_of_harm") if isinstance(facts.get("risk_of_harm"), dict) else {}
    out = {key: "risk_of_harm" for key in c100_field_map.RISK_OF_HARM_BOXES if stated.get(key) is True}
    incidents = [i for i in facts.get("incidents") or [] if isinstance(i, dict)]
    if "domestic_abuse" not in out:
        if [a for a in facts.get("abuse_alleged") or [] if str(a or "").strip()]:
            out["domestic_abuse"] = "abuse_alleged"
        elif any(_abuse_types(i) for i in incidents):
            out["domestic_abuse"] = "an incident with abuse_types"
    if "child_abuse" not in out and child_incidents(facts)[0]:
        out["child_abuse"] = "an incident with a child among its victims"
    if "substance_misuse" not in out:
        respondent = facts.get("respondent") if isinstance(facts.get("respondent"), dict) else {}
        use = respondent.get("substance_use")
        if use is True or (isinstance(use, str) and use.strip() and not _NO_SUBSTANCE_RE.match(use)):
            out["substance_misuse"] = "respondent.substance_use"
    return out


_FEMALE = field_shapes.FEMALE_WORDS
_MALE = field_shapes.MALE_WORDS


def applicant_sex(applicant: dict[str, Any]) -> str:
    "``female`` or ``male`` from the applicant's stated sex, else from a title; \"\" when neither says."
    for key in ("sex", "title"):
        found = field_shapes.sex_word(applicant.get(key))
        if found:
            return found
    return ""


_RESPONDENT_HE_RE = re.compile(r"(?i)\brespondent\b[^.]{0,100}?\b(he|his|him)\b")
_RESPONDENT_SHE_RE = re.compile(r"(?i)\brespondent\b[^.]{0,100}?\b(she|her)\b")


def respondent_sex_from_statement(statement: str) -> str:
    "``male`` or ``female`` from the pronouns the statement uses within a clause of \"the Respondent\": one kind only,"
    he, she = len(_RESPONDENT_HE_RE.findall(statement or "")), len(_RESPONDENT_SHE_RE.findall(statement or ""))
    if he and he >= 3 * she:
        return "male"
    if she and she >= 3 * he:
        return "female"
    return ""


_JOINT_CHILDREN_RE = re.compile(
    r"(?i)\b(?:child|children|son|sons|daughter|daughters)\s+(?:together\s+)?with\s+the\s+respondent\b"
    r"|\bour\s+(?:child|children|son|sons|daughter|daughters)\b"
    r"|\bwe\s+have\s+(?:a|one|two|three|four|five|\d+)\s+(?:child|children|sons?|daughters?)\b"
    r"|\brespondent\s+is\s+(?:the|their|her|his)\s+(?:biological\s+)?(?:father|mother)\b"
)


def children_are_both_parties(statement: str) -> bool:
    "True when the statement says the children are the applicant's and the Respondent's together."
    return bool(_JOINT_CHILDREN_RE.search(statement or ""))


_NICKNAME_RE = re.compile(r"""(?ix)\s*[(\[]\s*(?:aka|a\.k\.a\.?|also\s+known\s+as|known\s+as)\b[^)\]]*[)\]]|\s+(?:aka|a\.k\.a\.?)\s+\S+|\s*["\u201c][^"\u201d]+["\u201d]""")


_ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


def uk_dates(text: str) -> str:
    "Dates written as ``2026-10-06`` in a form's free text read ``06/10/2026``: the firm writes dates day first."
    return _ISO_DATE_RE.sub(lambda m: f"{m.group(3)}/{m.group(2)}/{m.group(1)}", text)


def strip_nickname(name: Any) -> Any:
    "A name without its nickname (\"Kit (AKA Kitty)\" is \"Kit\"): the forms carry legal names only."
    return " ".join(_NICKNAME_RE.sub("", name).split()) if isinstance(name, str) else name


def strip_nicknames(facts: dict[str, Any]) -> dict[str, Any]:
    "``facts`` with every party's and child's name cleaned by ``strip_nickname``."
    people = [facts.get(k) for k in ("applicant", "respondent")] + list(facts.get("children") or [])
    for person in people:
        if isinstance(person, dict):
            for key in ("full_name", "first_names", "last_name"):
                if key in person:
                    person[key] = strip_nickname(person[key])
    return facts


def matter_contacts(matter_id: Any) -> dict[str, dict[str, str]]:
    "The applicant's and respondent's phone and email from the matter's party rows; {} when the database is out of reach."
    try:
        import clientdb_sql

        parties = clientdb_sql.list_parties(str(matter_id))
    except Exception:
        return {}
    out: dict[str, dict[str, str]] = {}
    for party in parties:
        role = str(party.get("role") or "").strip().lower()
        if role in {"applicant", "respondent"} and role not in out:
            out[role] = {"phone": str(party.get("phone_primary") or ""), "email": str(party.get("email_primary") or "")}
    return out


def matter_sexes(matter_id: Any) -> dict[str, dict[str, str]]:
    "The stored sex of the matter's client (``applicant``) and its respondent party row, each"
    try:
        import clientdb_sql

        mid = str(matter_id)
        out: dict[str, dict[str, str]] = {
            "applicant": {"sex": clientdb_sql.get_editable_field(mid, "sex") or "", "sex_other": clientdb_sql.get_editable_field(mid, "sex_other") or ""}
        }
        for party in clientdb_sql.list_parties(mid):
            if str(party.get("role") or "").strip().lower() == "respondent":
                out["respondent"] = {"sex": str(party.get("sex") or ""), "sex_other": str(party.get("sex_other") or ""),
                                     "party_id": str(party.get("party_id") or "")}
                break
        return out
    except Exception:
        return {}


def with_stored_sex(facts: dict[str, Any], matter: Mapping[str, Any] | None) -> dict[str, Any]:
    "``facts`` with the matter's stored sex (``matter[\"sexes\"]``) in the applicant's and respondent's"
    sexes = (matter or {}).get("sexes")
    if not isinstance(sexes, Mapping) or not isinstance(facts, dict):
        return facts
    out = dict(facts)
    for party in ("applicant", "respondent"):
        stored = field_shapes.stored_sex_word((sexes.get(party) or {}).get("sex"))
        person = out.get(party) if isinstance(out.get(party), dict) else {}
        if stored and not applicant_sex(person):
            out[party] = {**person, "sex": stored}
    return out


def record_learned_sex(matter: Mapping[str, Any] | None, facts: dict[str, Any], statement: str) -> list[str]:
    "Record on the matter a sex the statement gave, for each person whose stored sex is blank; a stored value"
    sexes = (matter or {}).get("sexes")
    matter_id = str((matter or {}).get("matter_id") or "")
    if not matter_id or not isinstance(sexes, Mapping):
        return []
    written: list[str] = []
    try:
        from vergil import client_edits

        applicant = facts.get("applicant") if isinstance(facts.get("applicant"), dict) else {}
        respondent = facts.get("respondent") if isinstance(facts.get("respondent"), dict) else {}
        learned = {"applicant": applicant_sex(applicant), "respondent": applicant_sex(respondent) or respondent_sex_from_statement(statement)}
        for party, word in learned.items():
            have = sexes.get(party) or {}
            if not word or str(have.get("sex") or "").strip():
                continue
            if party == "applicant":
                client_edits.record_edit(matter_id=matter_id, field_name="sex", new_value=word.capitalize(),
                                         note="read from the statement", edited_by="system:form-fill")
            elif have.get("party_id"):
                client_edits.update_party(matter_id=matter_id, party_id=have["party_id"], fields={"sex": word.capitalize()},
                                          note="read from the statement", edited_by="system:form-fill")
            else:
                continue
            written.append(party)
    except Exception:
        return written
    return written


GENERIC_REASON_KEYS = ("urgent_hearing_reasons", "without_notice_reasons")


_KIND_WORD_RE = re.compile(r"^[a-z]{4,20}$")


def stated_kinds(facts: dict[str, Any], statement: str | None = None) -> list[str]:
    "The kinds of abuse the statement lists (``abuse_kinds_listed``: its own words, in its order, such as verbal), each"
    listed: list[str] = []
    for kind in facts.get("abuse_kinds_listed") or []:
        word = str(kind or "").strip().lower()
        if _KIND_WORD_RE.match(word) and word not in listed and (statement is None or re.search(rf"(?i)\b{word}", statement)):
            listed.append(word)
    if listed:
        return listed
    return [k for k in ABUSE_KINDS if k in _kinds(facts.get("applicant_abuse_types")) | _kinds(facts.get("children_abuse_types"))]


def generic_reasons(facts: dict[str, Any], statement: str | None = None) -> dict[str, str]:
    "``{field key: sentence}`` for 6.2 and 6.5, from the kinds of abuse the statement lists (``stated_kinds``). {} when no"
    kinds = stated_kinds(facts, statement)
    if not kinds or not (facts.get("urgent") is True or facts.get("without_notice") is True):
        return {}
    listed = kinds[0] if len(kinds) == 1 else ", ".join(kinds[:-1]) + " and " + kinds[-1]
    children = len(child_rows(facts))
    whom = "the applicant" if not children else "the applicant and the child" if children == 1 else "the applicant and the children"
    out = {"urgent_hearing_reasons": f"There is a risk of significant harm to {whom} if the respondent is given notice, due to a history of {listed} abuse."}
    if facts.get("without_notice") is True:
        out["without_notice_reasons"] = f"Giving notice to the respondent would put {whom} at risk of significant harm, due to a history of {listed} abuse."
    return out


def without_notice_sought(facts: dict[str, Any], values: dict[str, Any]) -> str:
    "Why A3 is Yes, or \"\" when nothing says an urgent or without notice hearing is sought."
    if facts.get("without_notice") is True:
        return "without_notice"
    if facts.get("urgent") is True:
        return "urgent"
    if any(values.get(name) for name in c100_field_map.SECTION6_ANSWER_FIELDS):
        return "section 6 is answered"
    return ""


def _address_values(address: Any, boxes: dict[str, str]) -> dict[str, str]:
    parts = split_form_address(str(address or ""))
    if not (parts["line1"] and (parts["town"] or parts["postcode"])):
        return {}
    return {boxes[key]: parts[key] for key in ("line1", "line2", "town", "postcode")}


_CHILDREN_ORDERS = ("CAO", "PSO", "SIO")


def orders_applied_for(facts: dict[str, Any], matter: Mapping[str, Any] | None = None) -> dict[str, str]:
    "The children orders applied for (CAO, PSO, SIO), each with the source that names it: the"
    out: dict[str, str] = {}
    for source, items in (("the matter's orders", (matter or {}).get("order_codes")), ("orders_sought", facts.get("orders_sought"))):
        text = " ; ".join(str(item) for item in (items if isinstance(items, (list, tuple)) else [items]) if item)
        for code in order_codes.codes_in_text(text):
            if code in _CHILDREN_ORDERS and code not in out:
                out[code] = source
    return out


_NATURE_SENTENCES = {
    "PSO": "A Prohibited Steps Order to prevent the Respondent from removing the {children} from the Applicant's care.",
    "CAO": "A Child Arrangements Order that the {lives} with the Applicant and {does} not spend time with the Respondent.",
}


def nature_of_application(codes: Iterable[str], child_count: int) -> str:
    "Page 4's \"Nature of application\": one sentence per Prohibited Steps Order and Child Arrangements"
    one = child_count == 1
    words = {"children": "child" if one else "children", "lives": "child lives" if one else "children live",
             "does": "does" if one else "do"}
    wanted = set(codes)
    return " ".join(sentence.format(**words) for code, sentence in _NATURE_SENTENCES.items() if code in wanted)


def _date_parts(value: Any) -> tuple[str, str, str] | None:
    "(DD, MM, YYYY) of a complete, real date given as YYYY-MM-DD or D/M/YYYY; None for anything else."
    import datetime

    text = " ".join(str(value or "").split())
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    plain = _DATE_VALUE_RE.match(text)
    if iso:
        year, month, day = (int(g) for g in iso.groups())
    elif plain:
        day, month, year = (int(g) for g in plain.groups())
    else:
        return None
    try:
        datetime.date(year, month, day)
    except ValueError:
        return None
    return f"{day:02d}", f"{month:02d}", f"{year:04d}"


_PARENT_WORDS = {"mother": "Mother", "mum": "Mother", "mom": "Mother", "father": "Father", "dad": "Father"}
_CHILD_SEX_WORDS = {"daughter": "female", "girl": "female", "son": "male", "boy": "male"}


def _word(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def child_rows(facts: dict[str, Any]) -> list[dict[str, Any]]:
    "The facts' named children as form rows, in the statement's order: ``first``, ``last`` and"
    applicant = facts.get("applicant") if isinstance(facts.get("applicant"), dict) else {}
    rows: list[dict[str, Any]] = []
    for child in facts.get("children") or []:
        if not isinstance(child, dict):
            continue
        full = " ".join(str(child.get("full_name") or "").split())
        first = " ".join(str(child.get("first_names") or "").split())
        last = " ".join(str(child.get("last_name") or "").split())
        words = full.split()
        if len(words) > 1:
            first, last = first or " ".join(words[:-1]), last or words[-1]
        elif not first and not last:
            first = full
        full = full or " ".join(part for part in (first, last) if part)
        if not full:
            continue
        stated = " ".join(str(child.get("relationship_to_applicant") or "").split())
        relation = _word(stated)
        sex_word = _word(child.get("sex"))
        sex = "female" if sex_word in _FEMALE else "male" if sex_word in _MALE else _CHILD_SEX_WORDS.get(sex_word) or _CHILD_SEX_WORDS.get(relation, "")
        if relation in _PARENT_WORDS:
            parent, as_child = _PARENT_WORDS[relation], {"female": "Daughter", "male": "Son"}.get(sex, "")
        elif relation in {"son", "daughter", "child"}:
            parent, as_child = {"female": "Mother", "male": "Father"}.get(applicant_sex(applicant), ""), relation.capitalize()
        else:
            parent = as_child = stated
        rows.append({"first": first, "last": last, "full": full, "dob": _date_parts(child.get("dob")), "sex": sex,
                     "parent": parent, "child": as_child})
    return rows


def code_owned_fields(form: str | None, facts: dict[str, Any] | None) -> set[str]:
    "Fields a model is never asked for, because the code sets or empties them from the facts: the"
    facts = facts if isinstance(facts, dict) else {}
    count = len(child_rows(facts))
    owned: set[str] = set()
    if form == "c100":
        for index, boxes in enumerate(c100_field_map.CHILD_ROW_FIELDS):
            owned.update(boxes[part] for part in (c100_field_map.CHILD_IDENTITY_PARTS if index < count else boxes))
        owned.update(c100_field_map.FIELD_MAP[key] for key in GENERIC_REASON_KEYS)
    elif form == "c1a":
        for boxes in fill_c1a_pdf.CHILD_ROW_FIELDS:
            owned.update(boxes.values())
        if "child_abduction" not in risks_supported(facts):
            owned |= fill_c1a_pdf.SECTION3_DETAIL_FIELDS
    if form in FORMS:
        owned |= set(form_standing_answers.standing_answers(form))
    return owned


def derived_values(form: str | None, facts: dict[str, Any], values: dict[str, Any], *, matter: Mapping[str, Any] | None = None, statement: str = "") -> dict[str, Any]:
    "Answers worked out from the facts in code, applied over the model's; a person's overrides still win."
    facts = with_stored_sex(facts if isinstance(facts, dict) else {}, matter)
    out: dict[str, Any] = {"set": {}, "clear": set(), "why": {}, "tbc": [], "attention": []}

    def tick(yes: str, no: str | None, why: str) -> None:
        out["set"][yes] = True
        out["why"][yes] = why
        if no:
            out["clear"].add(no)

    def put(name: str, value: Any, why: str, clears: Iterable[str] = ()) -> None:
        out["set"][name] = value
        out["why"][name] = why
        out["clear"].update(clears)

    if form in FORMS:
        for name, value in form_standing_answers.standing_answers(form).items():
            put(name, value, "standing answer: the firm's details")
    if form == "c100":
        m = c100_field_map.FIELD_MAP
        for name, (value, clears) in c100_field_map.OWNER_DEFAULTS.items():
            put(name, value, "owner default", clears)
        risks = risks_supported(facts)
        for key, why in risks.items():
            if key != "other_safety_welfare":
                tick(*c100_field_map.RISK_OF_HARM_BOXES[key], why)
        for key in ("child_abduction", "child_abuse", "substance_misuse"):
            if key not in risks:
                yes, no = c100_field_map.RISK_OF_HARM_BOXES[key]
                put(no, True, "owner default: No when the facts do not support it", (yes,))
        other_yes, other_no = c100_field_map.RISK_OF_HARM_BOXES["other_safety_welfare"]
        if "other_safety_welfare" in risks:
            tick(other_yes, other_no, risks["other_safety_welfare"])
            concerns = "; ".join(str(c).strip() for c in facts.get("other_concerns") or [] if str(c or "").strip())
            out["attention"].append({"field": other_yes, "page": 4, "why": "page 4 'Other safety or welfare concerns' is ticked Yes: "
                                     + (concerns or "the statement raises a concern outside the other four") + ". Check it and the C1A."})
        else:
            put(other_no, True, "owner default", (other_yes,))
        reasons = generic_reasons(facts, statement)
        for key, sentence in reasons.items():
            put(c100_field_map.FIELD_MAP[key], sentence, "6.2 and 6.5: the kinds of abuse only, one sentence for every client")
        if (facts.get("urgent") is True or facts.get("without_notice") is True) and not reasons:
            out["tbc"].append({"field": "6.2 reasons for urgency", "page": 25,
                               "why": "no kind of abuse is named in the facts: write the kinds of abuse, no facts"})
        why = without_notice_sought(facts, values)
        if why:
            tick(*c100_field_map.URGENT_HEARING_BOXES, why)
        if facts.get("without_notice") is False:
            out["attention"].append({"field": m["without_notice_ground"], "page": 17,
                                     "why": "the facts say the application is on notice, so 3e's without notice ground is not ticked; choose the 3e ground"})
        else:
            put(m["without_notice_ground"], True, "owner default: 3e, the application is made without notice")
        out["attention"].append({"field": m["miam_da_evidence_support_letter"], "page": 15,
                                 "why": "3a relies on the domestic abuse support organisation's letter: attach it (the form has no box for its reference)"})
        applicant = facts.get("applicant") if isinstance(facts.get("applicant"), dict) else {}
        language = str(applicant.get("interpreter_language") or "").strip()
        if language:
            put(m["interpreter_yes"], True, "applicant.interpreter_language", (m["interpreter_no"],))
            put(c100_field_map.INTERPRETER_FOR_APPLICANT, True, "applicant.interpreter_language")
            put(c100_field_map.INTERPRETER_LANGUAGE, language, "applicant.interpreter_language")
        else:
            out["clear"].update(m[k] for k in ("welsh_yes", "welsh_no", "interpreter_yes", "interpreter_no",
                                               "intermediary_yes", "intermediary_no", "disability_yes", "disability_no"))
        sex = applicant_sex(applicant)
        if sex:
            yes, other = (m["applicant1_female"], m["applicant1_male"]) if sex == "female" else (m["applicant1_male"], m["applicant1_female"])
            put(yes, True, "applicant.sex or title", (other,))
        else:
            out["tbc"].append({"field": "11.1 Applicant 1 sex", "page": 34, "why": "the facts give neither the applicant's sex nor a title"})
        respondent = facts.get("respondent") if isinstance(facts.get("respondent"), dict) else {}
        r_stated = applicant_sex(respondent)
        r_sex = r_stated or respondent_sex_from_statement(statement)
        if r_sex:
            yes, other = ("Check Box 2012", "Check Box 2013") if r_sex == "male" else ("Check Box 2013", "Check Box 2012")
            put(yes, True, "respondent.sex, or the statement's pronouns for the Respondent", (other,))
            if not r_stated:
                out["attention"].append({"field": yes, "page": 37, "why": "12.1 sex is read from the statement's pronouns: check it"})
        contacts = (matter or {}).get("contacts") if isinstance((matter or {}).get("contacts"), dict) else {}
        for party, phone, email in (("applicant", m["applicant1_phone"], m["applicant1_email"]), ("respondent", m["respondent1_phone"], m["respondent1_email"])):
            have = contacts.get(party) if isinstance(contacts.get(party), dict) else {}
            for name, key in ((phone, "phone"), (email, "email")):
                if str(have.get(key) or "").strip():
                    put(name, str(have[key]).strip(), f"the matter's {party} {key}")
        orders = orders_applied_for(facts, matter)
        for code, why in orders.items():
            put(c100_field_map.ORDER_TYPE_BOXES[code], True, why)
        nature = nature_of_application(orders, len(child_rows(facts)))
        if nature:
            put(m["order_sought_nature"], nature, "the orders applied for")
        born = _date_parts(applicant.get("dob"))
        if born:
            put(m["applicant1_dob"], "".join(born), "applicant.dob")
        rows = child_rows(facts)
        order_names = ", ".join(c100_field_map.ORDER_NAMES[code] for code in orders_applied_for(facts, matter))
        sexes_known = bool(sex and r_sex)
        respondent_parent = {"male": "Father", "female": "Mother"}.get(r_sex or "", "") if sexes_known else ""

        def settled(word: str) -> str:
            return "Parent" if word in ("Mother", "Father") and not sexes_known else word
        joint = children_are_both_parties(statement)
        applicant_parent = ({"male": "Father", "female": "Mother"}.get(sex, "") if sexes_known else "") or "Parent"
        for index, boxes in enumerate(c100_field_map.CHILD_ROW_FIELDS):
            page, label = 7 + index // 2, f"1.1 child {index + 1}"
            if index >= len(rows):
                out["clear"].update(boxes.values())
                continue
            row = rows[index]
            out["clear"].update(boxes[part] for part in c100_field_map.CHILD_IDENTITY_PARTS)
            both_parents = row["parent"] in ("Mother", "Father") and respondent_parent
            applicant_relationship = settled(row["parent"]) or (applicant_parent if joint else "")
            respondent_relationship = (respondent_parent if both_parents else "") or ((respondent_parent or "Parent") if joint else "")
            cells = {"first_name": row["first"], "last_name": row["last"], "dob": "".join(row["dob"] or ()),
                     "order_type": order_names, "applicant_relationship": applicant_relationship,
                     "respondent_relationship": respondent_relationship,
                     "female": row["sex"] == "female", "male": row["sex"] == "male"}
            for part, value in cells.items():
                if value:
                    put(boxes[part], value, "the facts' children")
            for part, missing in (("dob", "date of birth"), ("applicant_relationship", "the applicant's relationship to the child"),
                                  ("respondent_relationship", "the respondent's relationship to the child"),
                                  ("order_type", "the orders applied for")):
                if not cells[part]:
                    out["tbc"].append({"field": f"{label} {missing}", "page": page, "why": "the facts do not give it"})
            if not row["sex"]:
                out["tbc"].append({"field": f"{label} sex", "page": page, "why": "the facts do not give it"})
        applicant_name = " ".join(str(applicant.get("full_name") or "").split())
        respondent_name = " ".join(str(respondent.get("full_name") or "").split())
        strict = rows and respondent_parent and all(r["parent"] in ("Mother", "Father") for r in rows)
        both = rows and joint and all(r["parent"] in ("", "Mother", "Father", "Parent") for r in rows)
        if (strict or both) and applicant_name and respondent_name:
            applicant_word = (settled(rows[0]["parent"]) or applicant_parent).lower()
            parents = f"{applicant_name} ({applicant_word}) and {respondent_name} ({(respondent_parent or 'Parent').lower()})"
            put(m["parents_names"], parents,
                "1.4: the applicant and respondent are the parents of every child", (c100_field_map.FIELD_MAP["q1_4_no"],))
            put(m["parental_responsibility"], parents, "1.5: the parents of every child, written as in 1.4")
            put(m["q1_4_yes"], True, "1.4: the applicant and respondent are the parents of every child")
            out["attention"].append({"field": m["parents_names"], "page": 9,
                                     "why": "1.4 and 1.1's respondent relationship assume the respondent is the other parent: check"})
            out["attention"].append({"field": m["parental_responsibility"], "page": 10,
                                     "why": "1.5 repeats the 1.4 parents' names: check who has parental responsibility"})
        elif rows:
            out["tbc"].append({"field": "1.4 parents of the children", "page": 9,
                               "why": "the facts do not give both parents' relationships to every child"})
        if len(rows) > c100_field_map.CHILD_ROWS:
            out["tbc"].append({"field": "1.1 children", "page": 8,
                               "why": f"{len(rows) - c100_field_map.CHILD_ROWS} more child(ren) than the form's rows: continue on a separate sheet"})
        for party, boxes, always in (("respondent", c100_field_map.RESPONDENT1_ADDRESS_FIELDS, True),
                                     ("applicant", c100_field_map.APPLICANT1_ADDRESS_FIELDS, False)):
            if not always and not any(values.get(name) for name in boxes.values()):
                continue
            person = facts.get(party) if isinstance(facts.get(party), dict) else {}
            for name, text in _address_values(person.get("address"), boxes).items():
                if text:
                    out["set"][name] = text
                    out["why"][name] = f"{party}.address"
                else:
                    out["clear"].add(name)
            if party == "respondent":
                from documents.fill_fl401_pdf import ADDRESS_UNKNOWN, address_state

                state = address_state(" ".join(out["set"].get(name, "") for name in boxes.values()))
                if state == "unknown":
                    out["set"][boxes["line1"]] = ADDRESS_UNKNOWN
                    out["clear"].discard(boxes["line1"])
                    out["why"][boxes["line1"]] = "respondent.address: none recorded"
                elif state == "no_postcode":
                    out["tbc"].append({"field": "12.1 respondent's address postcode", "page": 37,
                                       "why": "respondent address has no postcode: find it"})
    elif form == "c1a":
        rows = child_rows(facts)
        for index, boxes in enumerate(fill_c1a_pdf.CHILD_ROW_FIELDS):
            out["clear"].update(boxes.values())
            if index >= len(rows):
                continue
            row = rows[index]
            day, month, year = row["dob"] or ("", "", "")
            cells = {"name": row["full"], "dob_dd": day, "dob_mm": month, "dob_yyyy": year, "relationship": row["child"],
                     "female": row["sex"] == "female", "male": row["sex"] == "male"}
            for part, value in cells.items():
                if value:
                    put(boxes[part], value, "the facts' children")
            for part, missing in (("dob_dd", "date of birth"), ("relationship", "relationship to you")):
                if not cells[part]:
                    out["tbc"].append({"field": f"child {index + 1} {missing}", "page": 1, "why": "the facts do not give it"})
            if not row["sex"]:
                out["tbc"].append({"field": f"child {index + 1} sex", "page": 1, "why": "the facts do not give it"})
        if len(rows) > fill_c1a_pdf.CHILD_ROWS:
            out["tbc"].append({"field": "children", "page": 1,
                               "why": f"{len(rows) - fill_c1a_pdf.CHILD_ROWS} more child(ren) than the form's rows: continue on a separate sheet"})
        victim, witnessed = child_incidents(facts)
        children = fill_c1a_pdf.paired_abuse_kinds(set().union(*(_abuse_types(i) for i in victim)) | _kinds(facts.get("children_abuse_types")))
        applicant = fill_c1a_pdf.paired_abuse_kinds(
            set().union(*(_abuse_types(i) for i in applicant_incidents(facts))) | _kinds(facts.get("applicant_abuse_types")))
        for row, boxes, kinds, why in (
            ("children", fill_c1a_pdf.CHILD_ABUSE_BOXES, children, "the children's abuse in the facts"),
            ("applicant", fill_c1a_pdf.APPLICANT_ABUSE_BOXES, applicant, "the applicant's abuse in the facts"),
        ):
            for kind, name in boxes.items():
                if kind in kinds:
                    tick(name, None, why)
                else:
                    out["clear"].add(name)
        stated = facts.get("risk_of_harm") if isinstance(facts.get("risk_of_harm"), dict) else {}
        if stated.get("child_abuse") is True and not children:
            out["tbc"].append({"field": "abuse children have experienced", "page": 2,
                               "why": "child abuse is alleged but the facts give no kind: a person ticks the children's row"})
        table = incident_table(facts)
        for name, value in table["set"].items():
            put(name, value, "the facts' incidents")
        out["clear"].update(table["clear"])
        out["tbc"].extend(table["tbc"])
        out["attention"].extend(table["attention"])
        if witnessed:
            out["tbc"].append({"field": "abuse children have experienced", "page": 2,
                               "why": f"{len(witnessed)} incident(s) a child witnessed without being a victim: a person decides the harm"})
        risks = risks_supported(facts)
        yes, no = fill_c1a_pdf.ABDUCTION_BOXES
        if "child_abduction" in risks:
            tick(yes, no, risks["child_abduction"])
            out["attention"].append({"field": yes, "page": 4, "why": "section 3 'risk of abduction' is ticked Yes: check its reasons, "
                                     "previous attempts, passport and authorities boxes against the statement"})
        else:
            put(no, True, "owner default: No when the facts do not support it", (yes,))
            out["clear"].update(fill_c1a_pdf.SECTION3_DETAIL_FIELDS)
        yes, no = fill_c1a_pdf.OTHER_CONCERNS_BOXES
        put(no, True, "owner default: section 4 is always No", (yes,))
        out["clear"].add(fill_c1a_pdf.OTHER_CONCERNS_DETAILS)
        person = facts.get("applicant") if isinstance(facts.get("applicant"), dict) else {}
        sex = applicant_sex(person)
        if sex:
            other = "female" if sex == "male" else "male"
            put(fill_c1a_pdf.GENDER_BOXES[sex], True, "applicant.sex or title", (fill_c1a_pdf.GENDER_BOXES[other],))
        else:
            out["tbc"].append({"field": "section 1 gender", "page": 1, "why": "the facts give neither the applicant's sex nor a title"})
        for name, (value, clears) in fill_c1a_pdf.OWNER_DEFAULTS.items():
            put(name, value, "owner default", clears)
    return out


def _kinds(items: Any) -> set[str]:
    return {str(kind).strip().lower() for kind in (items if isinstance(items, list) else [])} & set(ABUSE_KINDS)


_APPLICANT_WORDS = {"me", "myself", "applicant", "mother", "mum"}


def applicant_incidents(facts: dict[str, Any]) -> list[dict[str, Any]]:
    "Incidents with the applicant among the victims: by given name, or as \"me\" or \"the applicant\"."
    applicant = facts.get("applicant") if isinstance(facts.get("applicant"), dict) else {}
    full = re.findall(r"[a-z0-9]+", str(applicant.get("full_name") or "").lower())
    tokens = _APPLICANT_WORDS | _tokens(str(applicant.get("first_names") or "")) | set(full[:-1] if len(full) > 1 else full)
    tokens -= _child_tokens(facts)
    return [i for i in facts.get("incidents") or [] if isinstance(i, dict) and _names_a_child(i.get("victims"), tokens)]


_POLICE_OUTCOME_RE = re.compile(
    r"(?i)\b(?:no\s+further\s+action|nfa|arrest(?:ed)?|charged|caution(?:ed)?|bail(?:ed)?|released|convicted|"
    r"warning|harassment\s+notice|no\s+action|took\s+no\s+action|did\s+(?:not|nothing))\b"
)


def _police_outcome(incident: dict[str, Any]) -> str:
    "What the police did: ``police_outcome``, else an ``outcome`` that reads as a police outcome."
    for key in ("police_outcome", "outcome"):
        text = " ".join(str(incident.get(key) or "").split())
        if not text or (key == "outcome" and not _POLICE_OUTCOME_RE.search(text)):
            continue
        if re.match(r"(?i)^(?:i|she|he|the applicant)\s+(?:reported|called|rang|phoned|contacted)\b", text):
            continue
        return text
    return ""


def _when(value: Any) -> str:
    text = " ".join(str(value or "").split())
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.fullmatch(r"(\d{4})-(\d{2})", text)
    return f"{m.group(2)}/{m.group(1)}" if m else text


def incident_table(facts: dict[str, Any]) -> dict[str, Any]:
    "The C1A's page 3 table from the facts' incidents, row by row (the model is never asked)."
    cols = fill_c1a_pdf.INCIDENT_COLUMNS
    out: dict[str, Any] = {
        "set": {},
        "clear": {pattern.format(n=n) for pattern in cols.values() for n in range(1, fill_c1a_pdf.INCIDENT_ROWS + 1)},
        "tbc": [],
        "attention": [],
    }
    incidents = [i for i in facts.get("incidents") or [] if isinstance(i, dict) and str(i.get("summary") or "").strip()]
    rows = list(range(min(len(incidents), fill_c1a_pdf.INCIDENT_ROWS)))
    own = [index for index, incident in enumerate(incidents) if any(incident is a for a in applicant_incidents(facts))]
    if own and not set(own) & set(rows):
        dated = [index for index in own if _ISO_RE.match(str(incidents[index].get("date") or ""))]
        keep = max(dated, key=lambda index: (str(incidents[index]["date"]), index)) if dated else own[-1]
        displaced = rows[-1]
        rows = sorted(rows[:-1] + [keep])
        why = (f"the table kept a row for the abuse of the applicant ({_when(incidents[keep].get('date')) or 'undated'}), so this "
               f"incident is not in it: {' '.join(str(incidents[displaced].get('summary')).split())[:120]}")
        out["tbc"].append({"field": "incident table", "page": 3, "why": why})
        out["attention"].append({"field": "incident table", "page": 3, "why": why + ". Continue on a separate sheet if it is needed."})
    elif not own and _kinds(facts.get("applicant_abuse_types")):
        out["attention"].append({"field": "incident table", "page": 3,
                                 "why": "abuse of the applicant is alleged but no incident has the applicant among its victims: add one to the table"})
    for n, incident in enumerate((incidents[index] for index in rows), 1):
        reported = incident.get("reported_to") if isinstance(incident.get("reported_to"), list) else [incident.get("reported_to")]
        cells = {
            "when": _when(incident.get("date")),
            "what": " ".join(str(incident.get("summary")).split()),
            "who": ", ".join(" ".join(str(r).split()) for r in reported if str(r or "").strip()),
            "action": _police_outcome(incident),
        }
        for key, value in cells.items():
            if value:
                out["set"][cols[key].format(n=n)] = value
        if not cells["action"]:
            out["tbc"].append({"field": cols["action"].format(n=n), "page": 3,
                               "why": f"incident {n}: the statement does not say what the police did"})
    if len(incidents) > fill_c1a_pdf.INCIDENT_ROWS:
        out["tbc"].append({"field": "incident table", "page": 3,
                           "why": f"{len(incidents) - fill_c1a_pdf.INCIDENT_ROWS} more incident(s) than the table's rows: continue on a separate sheet"})
    return out


def _max_lengths(form_pdf: Path | str) -> dict[str, int]:
    return field_max_lengths(PdfReader(str(form_pdf)))


def apply_c8(
    form: str | None,
    values: dict[str, Any],
    facts: dict[str, Any],
    statement: str,
    *,
    matter: Mapping[str, Any] | None = None,
    c8_text: str | None = None,
    fl401: Mapping[str, Any] | str | None = None,
    form_pdf: Path | str | None = None,
) -> dict[str, Any]:
    "C8 detection and protection, in place on ``values``, after the model and a person's overrides."
    found = c8_protection.detect(c8_text=c8_text, matter=matter, fl401=fl401, statement=statement)
    result: dict[str, Any] = {**found, "withheld": [], "redacted": []}
    if form == "c1a":
        boxes = fill_c1a_pdf.C8_BOXES
        answer = "yes" if found["c8"] else "no"
        for key, name in boxes.items():
            values.pop(name, None)
        values[boxes[answer]] = True
    if not found["c8"]:
        return result
    applicant = facts.get("applicant") if isinstance(facts.get("applicant"), dict) else {}
    applicant_contact = {"address": applicant.get("address"), "phone": applicant.get("phone"), "email": applicant.get("email")}
    contact = c100_field_map.C8_APPLICANT_CONTACT_FIELDS if form == "c100" else frozenset()
    protected = c8_protection.protected_values(applicant_contact, matter, c8_text=c8_text)
    result.update(c8_protection.protect(values, protected, contact_fields=contact,
                                        max_lengths=_max_lengths(form_pdf) if form_pdf else None))
    return result


def form_name(form_pdf: Path | str) -> str | None:
    "``c100`` or ``c1a`` when ``form_pdf`` is one of the court blanks the pipeline fills, else None."
    target = Path(form_pdf).resolve()
    return next((name for name, path in FORMS.items() if path.resolve() == target), None)


def blocked_fields(form: str | None, facts: dict[str, Any] | None) -> dict[str, str]:
    "Fields of ``form`` that must stay empty for these facts (field name to reason). The court's"
    closed: dict[str, str] = {}
    if form == "c100":
        closed = {**c100_field_map.CLOSED_FIELDS, **c100_field_map.blocked_fields(facts)}
    elif form == "c1a":
        closed = {
            **dict.fromkeys(fill_c1a_pdf.fields_after_signature(FORMS["c1a"]), fill_c1a_pdf.AFTER_SIGNATURE_REASON),
            **dict.fromkeys(fill_c1a_pdf.COURT_ONLY_FIELDS, fill_c1a_pdf.COURT_ONLY_REASON),
        }
    standing = form_standing_answers.standing_answers(form) if form in FORMS else {}
    return {name: why for name, why in closed.items() if name not in standing}




def _same_person(a: Any, b: Any) -> bool:
    wa, wb = str(a or "").lower().split(), str(b or "").lower().split()
    return bool(wa and wb) and (set(wa) <= set(wb) or set(wb) <= set(wa) or wa[0] == wb[0])


def with_fact_sheet(facts: dict[str, Any], sheet: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    "``facts`` with their blanks filled from the matter's fact sheet (gh#1450; ``matter_fact_extraction``): a child's"
    if not sheet:
        return facts, []
    from matter_fact_extraction import form_facts

    values = form_facts(dict(sheet))
    facts = json.loads(json.dumps(facts))
    filled: list[str] = []
    children = [c for c in facts.get("children") or [] if isinstance(c, dict)]
    for child in values.get("children") or []:
        match = next((c for c in children if _same_person(c.get("full_name") or " ".join(filter(None, (c.get("first_names"), c.get("last_name")))), child["name"])), None)
        if match is None:
            children.append({"full_name": child["name"], "dob": child.get("dob") or None})
            filled.append("children")
        elif child.get("dob") and not match.get("dob"):
            match["dob"] = child["dob"]
            filled.append("children.dob")
    facts["children"] = children
    for role in ("applicant", "respondent"):
        party = facts.get(role) if isinstance(facts.get(role), dict) else {}
        if values.get(f"{role}.dob") and not party.get("dob"):
            party["dob"] = values[f"{role}.dob"]
            filled.append(f"{role}.dob")
        facts[role] = party
    address = values.get("respondent.address")
    if isinstance(address, Mapping) and address.get("postcode") and not str(facts["respondent"].get("address") or "").strip():
        facts["respondent"]["address"] = ", ".join([*address.get("lines", []), address["postcode"]])
        filled.append("respondent.address")
    return facts, sorted(set(filled))


def run(
    statement_docx: Path | str, form: str, out_pdf: Path | str, *, cheap: str | None = None, strong: str | None = None, facts: dict[str, Any] | None = None,
    sections: bool = False,
    exclude: Iterable[str] = (),
    overrides: dict[str, Any] | None = None,
    matter: Mapping[str, Any] | None = None,
    c8_text: str | None = None,
    fl401: Mapping[str, Any] | str | None = None,
    fact_sheet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    "Statement to filled form. ``facts`` may be passed to reuse one extraction across strong models;"
    cheap = cheap or model_backend.model_for_role(model_backend.ROLE_FORM_FILL_CHEAP, backend="openrouter")
    strong = strong or model_backend.model_for_role(model_backend.ROLE_FORM_FILL_STRONG, backend="openrouter")
    form_pdf = FORMS[form]
    paragraphs = statement_paragraphs(statement_docx)
    statement = "\n".join(paragraphs)
    meta: dict[str, Any] = {}
    if facts is None:
        facts, meta["extract"] = extract_facts(paragraphs, model=cheap)
        if not facts:
            return {"ok": False, "stage": "extract", "meta": meta}
    facts = strip_nicknames(facts)
    facts, meta["fact_sheet_filled"] = with_fact_sheet(facts, fact_sheet)
    if matter and matter.get("matter_id") and "contacts" not in matter:
        matter = {**matter, "contacts": matter_contacts(matter["matter_id"])}
    if matter and matter.get("matter_id") and "sexes" not in matter:
        matter = {**matter, "sexes": matter_sexes(matter["matter_id"])}
    record_learned_sex(matter, facts, statement)
    facts = with_stored_sex(facts, matter)
    closed = set(blocked_fields(form, facts)) | {REFERENCE_FIELDS[form]} | code_owned_fields(form, facts)
    entries = [e for e in catalogue(form_pdf) if e["name"] not in closed]
    mapped, meta["map"] = map_facts(facts, entries, form=form, model=strong, sections=sections)
    report = check_and_fill(
        mapped, entries, statement, facts, form_pdf=form_pdf, out_pdf=out_pdf, exclude=exclude, overrides=overrides, form=form, matter=matter,
        c8_text=c8_text, fl401=fl401,
    )
    return {"ok": True, "cheap": cheap, "strong": strong, "facts": facts, "meta": meta, **report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("statement", type=Path)
    parser.add_argument("--form", choices=sorted(FORMS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cheap", default=None, help="Model for stage 1 (default: the form_fill_cheap role).")
    parser.add_argument("--strong", default=None, help="Model for stage 2 (default: the form_fill_strong role).")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--sections", action="store_true", help="Map one form section at a time.")
    parser.add_argument("--company-reference", help="The matter's company reference (YYMMDD/NNFL), the solicitor's reference.")
    args = parser.parse_args(argv)
    matter = {"company_reference": args.company_reference} if args.company_reference else None
    report = run(args.statement, args.form, args.out, cheap=args.cheap, strong=args.strong, sections=args.sections, matter=matter)
    text = json.dumps(report, indent=1, ensure_ascii=False)
    (args.report.write_text(text, encoding="utf-8") if args.report else print(text))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
