#!/usr/bin/env python3
"Matter facts read from a client's papers, for the record and the court forms."

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend
import clientdb_sql
import field_shapes
from agents.ccl_pipeline import (
    AI_EXP_ROOT,
    GatherError,
    _mail_client,
    find_referral_email,
    gather_client_facts,
    graph_files_token,
    html_to_text,
    list_ai_exp_clients,
)
from folder_surname import surname_of
import graph_files
from agwu.client import resolve_client
from documents.address_utils import normalise_address_line_values
from sql.split_name_address_fields import classify_name
from vergil import client_edits

BACKFILL_EDITOR = "system:matter-fact-extraction"

_ADDRESS_EDITABLE_FIELDS = ("address_line1", "address_line2", "address_line3", "address_line4", "address_postcode")


class FactExtractionError(RuntimeError):
    "Raised when the model call itself fails -- never for \"nothing found\","


_PROMPT_TEMPLATE = """You are extracting structured facts from family law source documents. These facts \
often only appear inside the court forms themselves (address/name tables), not the referral email.

Extract ONLY facts genuinely present in the text below. Never invent, guess, or infer a fact that isn't \
actually stated -- an empty result for something not present is correct and expected.

WITNESS STATEMENT:
{ws_text}

FL401 APPLICATION:
{fl401_text}

REFERRER REFERRAL EMAIL:
{referral_text}

Reply with strict JSON only, no markdown fences, no other text:
{{
  "respondent_address": {{"line1": "", "line2": "", "line3": "", "line4": "", "postcode": ""}},
  "client_address": {{"line1": "", "line2": "", "line3": "", "line4": "", "postcode": ""}},
  "children": [{{"name": "", "dob_iso_or_age": ""}}]
}}

Leave any field/line empty ("") when not stated. Only include a child if a name is actually given. \
"dob_iso_or_age" is whichever the text actually gives -- a date of birth (YYYY-MM-DD if determinable) \
or just an age in years as text (e.g. "7") -- never invented from context."""


def extract_facts(*, fl401_text: str, ws_text: str, referral_text: str) -> dict[str, Any]:
    prompt = _PROMPT_TEMPLATE.format(fl401_text=fl401_text[:6000], ws_text=ws_text[:6000], referral_text=referral_text[:3000])
    result = model_backend.run_model(model_backend.ROLE_MATTER_FACTS, prompt, backend="openrouter", timeout=90)
    if not result.ok:
        raise FactExtractionError(f"fact extraction call failed: {result.attempts[-1].error if result.attempts else 'unknown'}")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FactExtractionError(f"fact extraction did not return valid JSON: {exc}. Raw: {raw[:300]!r}") from exc
    if not isinstance(parsed, dict):
        raise FactExtractionError(f"fact extraction returned a non-object JSON value: {raw[:300]!r}")
    return parsed


def _clean_address(block: Any) -> dict[str, str]:
    "The extracted address block as it is written (gh#555): a trailing UK / United Kingdom label"
    block = block if isinstance(block, dict) else {}
    lines = normalise_address_line_values([str(block.get(f"line{i}") or "").strip() for i in range(1, 5)])
    return {
        "line1": lines[0],
        "line2": lines[1],
        "line3": lines[2],
        "line4": lines[3],
        "postcode": str(block.get("postcode") or "").strip(),
    }


def _clean_children(value: Any) -> list[dict[str, str]]:
    children = value if isinstance(value, list) else []
    cleaned = []
    for child in children:
        if not isinstance(child, dict):
            continue
        name = str(child.get("name") or "").strip()
        if not name:
            continue
        cleaned.append({"name": name, "dob_iso_or_age": str(child.get("dob_iso_or_age") or "").strip()})
    return cleaned


def fill_client_address(matter_id: str, address: dict[str, str], *, dry_run: bool = False) -> list[str]:
    "Fills the client's address only when every people.address_* field is blank: an extraction is one whole address,"
    field_map = {
        "address_line1": address["line1"],
        "address_line2": address["line2"],
        "address_line3": address["line3"],
        "address_line4": address["line4"],
        "address_postcode": address["postcode"],
    }
    if any(clientdb_sql.get_editable_field(matter_id, field_name) for field_name in field_map):
        return []
    changed: list[str] = []
    for field_name, new_value in field_map.items():
        if not new_value:
            continue
        changed.append(field_name)
        if not dry_run:
            client_edits.record_edit(
                matter_id=matter_id,
                field_name=field_name,
                new_value=new_value,
                note="Extracted from FL401/witness statement (matter_fact_extraction.py)",
                edited_by=BACKFILL_EDITOR,
            )
    return changed


def _respondent_party_row(matter_id: str) -> dict[str, Any] | None:
    sql = (
        "SELECT matter_party_id, address_line1, address_line2, address_line3, address_line4, address_postcode "
        "FROM matter_parties WHERE matter_id = ? AND role LIKE 'respondent'"
    )
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (matter_id,))
        cols = [col[0] for col in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return rows[0] if len(rows) == 1 else None


def fill_respondent_address(matter_id: str, address: dict[str, str], *, dry_run: bool = False) -> list[str]:
    "UPDATEs the address of the one respondent matter_parties row, only when every address column on it is blank:"
    row = _respondent_party_row(matter_id)
    if not row:
        return []
    column_map = {
        "address_line1": address["line1"],
        "address_line2": address["line2"],
        "address_line3": address["line3"],
        "address_line4": address["line4"],
        "address_postcode": address["postcode"],
    }
    if any(str(row.get(col) or "").strip() for col in column_map):
        return []
    to_set = {col: val for col, val in column_map.items() if val}
    if not to_set or dry_run:
        return list(to_set.keys())
    set_clause = ", ".join(f"{col} = ?" for col in to_set)
    still_blank = " AND ".join(f"COALESCE({col}, '') = ''" for col in column_map)
    sql = f"UPDATE matter_parties SET {set_clause} WHERE matter_party_id = ? AND {still_blank}"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (*to_set.values(), row["matter_party_id"]))
        if cursor.rowcount == 0:
            return []
    return list(to_set.keys())


def _existing_children_names(matter_id: str) -> set[str]:
    sql = "SELECT child_name FROM matter_children WHERE matter_id = ? AND LOWER(COALESCE(child_name, '')) NOT LIKE 'unnamed child%'"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (matter_id,))
        return {str(row[0] or "").strip().lower() for row in cursor.fetchall()}


def split_child_name(name: str) -> tuple[str, str, str]:
    "(first, middle, last), reusing `sql.split_name_address_fields."
    classified = classify_name(name)
    if classified:
        return classified
    return name, "", ""


def _generated_children_summary(matter_id: str) -> str:
    "The ``Name (dob)``, ``; ``-joined text the current ``matter_children`` rows make."
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT child_name, dob_iso FROM matter_children WHERE matter_id = ? AND LOWER(COALESCE(child_name, '')) NOT LIKE 'unnamed child%'", (matter_id,))
        rows = cursor.fetchall()
    parts = []
    for name, dob_iso in rows:
        piece = str(name or "Child")
        if dob_iso:
            piece += f" ({dob_iso})"
        parts.append(piece)
    return "; ".join(parts)


def _rebuild_children_summary(matter_id: str, previous: str) -> None:
    "Regenerates `matters.children_summary` from the full current"
    current = " ".join(str(clientdb_sql.get_editable_field(matter_id, "children_summary") or "").split()).lower()
    if current and current != " ".join(previous.split()).lower():
        return
    client_edits.record_edit(
        matter_id=matter_id,
        field_name="children_summary",
        new_value=_generated_children_summary(matter_id),
        note="Rebuilt from matter_children after matter_fact_extraction.py added a new row",
        edited_by=BACKFILL_EDITOR,
    )


def add_new_children(matter_id: str, children: list[dict[str, str]], *, dry_run: bool = False) -> list[str]:
    "INSERTs one row per child not already present (matched case-"
    existing = _existing_children_names(matter_id)
    previous_summary: str | None = None
    added: list[str] = []
    for child in children:
        name = child["name"]
        if name.strip().lower() in existing:
            continue
        added.append(name)
        if dry_run:
            continue
        dob_or_age = child["dob_iso_or_age"]
        dob_iso = dob_or_age if re.match(r"^\d{4}-\d{2}-\d{2}$", dob_or_age) else ""
        notes = "" if dob_iso else (f"Age/DOB as stated in source: {dob_or_age}" if dob_or_age else "")
        name_first, name_middle, name_last = split_child_name(name)
        if previous_summary is None:
            previous_summary = _generated_children_summary(matter_id)
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO matter_children "
                "(matter_id, child_name, dob_iso, notes, source, name_first, name_middle, name_last) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (matter_id, name, dob_iso or None, notes or None, "matter_fact_extraction.py", name_first, name_middle or None, name_last or None),
            )
    if added and not dry_run:
        _rebuild_children_summary(matter_id, previous_summary or "")
    return added


def fill_children_from_statement(matter_id: str, children: list[dict[str, str]], *, dry_run: bool = False) -> list[str]:
    "Record the children a signed statement names (``[{\"child_name\", \"dob_iso\"}]``), filling gaps only: a child"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT child_id, child_name FROM matter_children WHERE matter_id = ? ORDER BY child_id", (matter_id,))
        rows = [(r[0], str(r[1] or "").strip()) for r in cursor.fetchall()]
    named = {name.lower() for _, name in rows if name and not name.lower().startswith("unnamed child")}
    unnamed = [cid for cid, name in rows if not name or name.lower().startswith("unnamed child")]
    previous_summary: str | None = None
    recorded: list[str] = []
    for child in children:
        name, dob = " ".join(str(child.get("child_name") or "").split()), str(child.get("dob_iso") or "")
        if not name or name.lower() in named:
            continue
        named.add(name.lower())
        recorded.append(name)
        if dry_run:
            continue
        if previous_summary is None:
            previous_summary = _generated_children_summary(matter_id)
        if not unnamed:
            add_new_children(matter_id, [{"name": name, "dob_iso_or_age": dob}])
            continue
        first, middle, last = split_child_name(name)
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE matter_children SET child_name = ?, name_first = ?, name_middle = ?, name_last = ?, "
                "dob_iso = COALESCE(dob_iso, ?), notes = COALESCE(notes, ?) WHERE child_id = ? AND matter_id = ?",
                (name, first, middle or None, last or None, dob or None, "Name and date of birth from the signed witness statement",
                 unnamed.pop(0), matter_id),
            )
    if recorded and not dry_run:
        _rebuild_children_summary(matter_id, previous_summary or "")
    return recorded


def _apply_extracted_facts(matter_id: str, client_name: str, facts: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    result: dict[str, Any] = {"matter_id": matter_id, "client_name": client_name}
    result["client_address_fields_filled"] = fill_client_address(matter_id, _clean_address(facts.get("client_address")), dry_run=dry_run)
    result["respondent_address_fields_filled"] = fill_respondent_address(matter_id, _clean_address(facts.get("respondent_address")), dry_run=dry_run)
    result["children_added"] = add_new_children(matter_id, _clean_children(facts.get("children")), dry_run=dry_run)
    return result


def backfill_matter(client_name: str, matter_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    facts_input = gather_client_facts(client_name)
    facts = extract_facts(
        fl401_text=facts_input["fl401_text"],
        ws_text=facts_input["ws_text"],
        referral_text=facts_input["referral_body_text"],
    )
    return _apply_extracted_facts(matter_id, client_name, facts, dry_run=dry_run)


def gather_facts_with_explicit_files(client_name: str, *, fl401_filename: str = "", ws_filename: str) -> dict[str, Any]:
    "Same shape as `gather_client_facts`, but for a client whose real"
    access_token = graph_files_token()
    surname = surname_of(client_name)
    folder_path = f"{AI_EXP_ROOT}/{client_name}/Preliminary-Docs-{surname}"
    listing = graph_files.list_children(folder_path, access_token)
    real_names = {it.get("name") for it in (listing.get("value", []) if isinstance(listing, dict) else [])}
    wanted = [ws_filename] + ([fl401_filename] if fl401_filename else [])
    missing = [name for name in wanted if name not in real_names]
    if missing:
        raise GatherError(f"{client_name}: explicit filename(s) not present in a real listing of {folder_path}: {', '.join(missing)}")

    mail_client = _mail_client()
    referral = find_referral_email(client_name, mail_client=mail_client)
    with_tmp = REPO_ROOT / "tmp" / "matter-fact-extraction" / surname
    with_tmp.mkdir(parents=True, exist_ok=True)
    ws_path = with_tmp / "WS-explicit.docx"
    graph_files.download(f"{folder_path}/{ws_filename}", ws_path)

    from documents.audit_opening_letter_sources import read_text_file

    fl401_text = ""
    if fl401_filename:
        fl401_path = with_tmp / "FL401-explicit.docx"
        graph_files.download(f"{folder_path}/{fl401_filename}", fl401_path)
        fl401_text = read_text_file(fl401_path)

    referral_full = mail_client.graph("GET", mail_client.mailbox_path(f"/messages/{referral['id']}?$select=body"))
    referral_body_raw = (referral_full.get("body") or {}).get("content", "") if isinstance(referral_full, dict) else ""

    return {
        "client_name": client_name,
        "fl401_text": fl401_text,
        "ws_text": read_text_file(ws_path),
        "referral_body_text": html_to_text(referral_body_raw),
    }


def backfill_matter_with_explicit_files(
    client_name: str, matter_id: str, *, fl401_filename: str = "", ws_filename: str, dry_run: bool = False
) -> dict[str, Any]:
    facts_input = gather_facts_with_explicit_files(client_name, fl401_filename=fl401_filename, ws_filename=ws_filename)
    facts = extract_facts(
        fl401_text=facts_input["fl401_text"],
        ws_text=facts_input["ws_text"],
        referral_text=facts_input["referral_body_text"],
    )
    return _apply_extracted_facts(matter_id, client_name, facts, dry_run=dry_run)


def resolve_matter_id(client_name: str) -> str | None:
    "The client's real matter_id via Agwu -- THE client lookup for"
    resolution = resolve_client(client_name, caller="matter_fact_extraction")
    if resolution.status != "resolved" or not resolution.top:
        return None
    matter_id = resolution.top.row.get("matter_id")
    return str(matter_id) if matter_id is not None else None


def scan(*, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    "Backfill every AI-EXP client that resolves to a real matter_id."
    access_token = graph_files_token()
    clients = list_ai_exp_clients(access_token=access_token)
    if limit:
        clients = clients[:limit]
    summary: dict[str, Any] = {"scanned": len(clients), "applied": [], "skipped_no_matter": [], "errored": []}
    for client_name in clients:
        matter_id = resolve_matter_id(client_name)
        if not matter_id:
            summary["skipped_no_matter"].append(client_name)
            continue
        try:
            result = backfill_matter(client_name, matter_id, dry_run=dry_run)
        except (GatherError, FactExtractionError) as exc:
            summary["errored"].append({"client_name": client_name, "matter_id": matter_id, "reason": str(exc)})
            continue
        summary["applied"].append(result)
    return summary




SOURCE_INTRO, SOURCE_FL401, SOURCE_STATEMENT, SOURCE_ID = "intro", "fl401", "statement", "id"
SOURCE_RECORD = "record"
SOURCE_LABELS = {
    SOURCE_RECORD: "client record",
    SOURCE_INTRO: "referrer intro",
    SOURCE_FL401: "referrer's FL401",
    SOURCE_STATEMENT: "signed witness statement",
    SOURCE_ID: "ID document",
}
IDENTITY_ORDER = (SOURCE_ID, SOURCE_STATEMENT, SOURCE_FL401, SOURCE_INTRO)
DEFAULT_ORDER = (SOURCE_STATEMENT, SOURCE_FL401, SOURCE_INTRO)
IDENTITY_FACTS = {"applicant.name", "applicant.dob", "applicant.sex", "respondent.name", "respondent.dob", "respondent.sex"}
SHEET_EDITOR = "system:fact-sheet"
SHEET_VERSION = 1
REPORT_NAME = "Facts-check-{surname}.txt"
FACT_LABELS = {
    "applicant.name": "Client's name",
    "applicant.dob": "Client's date of birth",
    "applicant.sex": "Client's sex",
    "respondent.name": "Respondent's name",
    "respondent.dob": "Respondent's date of birth",
    "respondent.sex": "Respondent's sex",
    "respondent.address": "Respondent's address",
    "relationship.lived_together": "Lived together",
    "relationship.married": "Married or in a civil partnership",
    "relationship.start_year": "Relationship start year",
    "relationship.end_year": "Relationship end year",
    "relationship.marriage_date": "Wedding date (FL401 4.3)",
    "bail.conditions": "Bail conditions (FL401 1.5)",
    "bail.end_date": "Bail end date (FL401 1.6)",
    "police.crime_refs": "Police crime reference(s)",
    "c8.requested": "C8 (contact details kept from the respondent)",
    "children": "Children",
}

_SHEET_PROMPT = """You read the papers of one UK family-law client and extract facts from EACH paper separately.
Use ONLY what each paper states. Never guess, never invent, never copy a value from one paper into another.
A fact a paper does not state is "" (or null, or []). Dates are UK, day first: 03/05/2010 is 2010-05-03. Give full dates as YYYY-MM-DD.
In an intro "PR" is parental responsibility, never a person; a child named only "PR" is not a child.
For every yes/no answer give "quote": the exact words of the paper that say it (copied character for character), or leave the answer null.

{papers}

Reply with strict JSON only, no fences: one key per paper given above ({keys}), each holding exactly:
{{"applicant": {{"full_name": "", "dob": "", "sex": ""}},
 "respondent": {{"full_name": "", "dob": "", "sex": "", "address_lines": [], "postcode": ""}},
 "children": [{{"full_name": "", "dob": "", "respondent_has_pr": null}}],
 "relationship": {{"lived_together": null, "lived_together_quote": "", "married": null, "married_quote": "", "start_year": "", "end_year": "", "marriage_date": ""}},
 "bail": {{"conditions": null, "quote": "", "end_date": ""}},
 "crime_refs": [],
 "c8": {{"requested": null, "quote": ""}}}}
"sex" is "Female" or "Male" only when the paper prints it against a Sex or Gender label (an ID's "Sex F"); never from a name, a title, a pronoun or a photograph.
"marriage_date" is the date of the wedding or civil ceremony (YYYY-MM-DD, or the year alone when only the year is written).
"bail.end_date" is the date the respondent's bail conditions end. "crime_refs" are police crime or incident reference numbers as written.
"c8.requested" is true only when the paper says the client's address or contact details must be kept from the respondent."""

_PAPER_CHARS = 9000
_UK_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$")


def model_read_sources(texts: dict[str, str]) -> dict[str, Any] | None:
    "One model call over every paper (OpenRouter, zero data retention). ``{source: facts}`` as the model gave them, or"
    keys = [k for k in (SOURCE_INTRO, SOURCE_FL401, SOURCE_STATEMENT, SOURCE_ID) if str(texts.get(k) or "").strip()]
    if not keys:
        return {}
    papers = "\n\n".join(f"=== PAPER \"{k}\" ({SOURCE_LABELS[k]}) ===\n{str(texts[k])[:_PAPER_CHARS]}" for k in keys)
    try:
        result = model_backend.run_model(
            model_backend.ROLE_MATTER_FACTS, _SHEET_PROMPT.format(papers=papers, keys=", ".join(keys)), backend="openrouter", timeout=150
        )
        if not result.ok:
            return None
        found = re.search(r"\{.*\}", str(result.text or ""), re.S)
        data = json.loads(found.group(0) if found else "")
    except Exception:
        return None
    return {k: v for k, v in data.items() if k in keys and isinstance(v, dict)} if isinstance(data, dict) else None




def _flat(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("’", "'")).strip().lower()


def _words(text: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _flat(text).replace("'", "")))


def _compact(text: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def dates_in(text: Any) -> set[str]:
    "Every date the text writes, read UK day first, as ISO (``field_audit.intro_dates``: one reader of dates)."
    from onboarding.field_audit import intro_dates

    return intro_dates(str(text or ""))


def iso_date(value: Any) -> str:
    "A model's date as ISO: ``YYYY-MM-DD`` as given, or the one date a UK-written value reads as; else \"\"."
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return dt.date.fromisoformat(text).isoformat()
        except ValueError:
            return ""
    found = dates_in(text)
    return next(iter(found)) if len(found) == 1 else ""


def name_in(name: Any, text: Any) -> bool:
    "Every word of the name is a word of the text (case and apostrophes ignored)."
    wanted = _words(name)
    return bool(wanted) and wanted <= _words(text)


def quote_in(quote: Any, text: Any) -> bool:
    "The quote (two words or more) is in the text, case and spacing ignored."
    q = _flat(quote).strip(" .\"'")
    return len(q.split()) >= 2 and q in _flat(text)


def year_in(year: Any, text: Any) -> bool:
    y = str(year or "").strip()
    return bool(re.fullmatch(r"(?:19|20)\d{2}", y)) and bool(re.search(rf"(?<!\d){y}(?!\d)", str(text or "")))


def postcode_in(postcode: Any, text: Any) -> str:
    "The postcode in its one-space form when it is a UK postcode written in the text, else \"\"."
    pc = re.sub(r"\s+", "", str(postcode or "").upper())
    if len(pc) < 5 or not _UK_POSTCODE_RE.match(pc) or pc.lower() not in _compact(text):
        return ""
    return f"{pc[:-3]} {pc[-3:]}"


_SEX_LABEL_RE = re.compile(r"(?i)\b(?:sex|gender)\b[^A-Za-z0-9\n]{0,6}(female|male|f|m)\b")


def sex_label_value(text: Any) -> str:
    "``female`` or ``male`` when the text prints a sex against a sex or gender label (as in sex: f) and every"
    found = {"female" if m.group(1).lower() in ("f", "female") else "male" for m in _SEX_LABEL_RE.finditer(str(text or ""))}
    return found.pop() if len(found) == 1 else ""


def ref_in(ref: Any, text: Any) -> bool:
    r = _compact(ref)
    return len(r) >= 5 and any(c.isdigit() for c in r) and r in _compact(text)


def _reading(kind: str, raw: Any, text: str, extra_dates: set[str] = frozenset()) -> tuple[dict[str, Any], int]:
    "One paper's facts as the model gave them, each kept only when the paper writes it. ``(facts, values dropped)``."
    raw = raw if isinstance(raw, dict) else {}
    dates = dates_in(text) | set(extra_dates)
    out: dict[str, Any] = {}
    dropped = 0

    def keep(key: str, value: Any, ok: bool) -> None:
        nonlocal dropped
        if value in (None, "", [], {}):
            return
        if ok:
            out[key] = value
        else:
            dropped += 1

    def date(value: Any) -> tuple[str, bool]:
        iso = iso_date(value)
        return iso, bool(iso) and iso in dates

    for role in ("applicant", "respondent"):
        if kind == SOURCE_ID and role == "respondent":
            continue
        party = raw.get(role) if isinstance(raw.get(role), dict) else {}
        name = " ".join(str(party.get("full_name") or "").split())
        keep(f"{role}.name", name, name_in(name, text))
        dob, ok = date(party.get("dob"))
        keep(f"{role}.dob", dob or party.get("dob"), bool(dob) and ok)
        sex = sex_label_value(text)
        given = field_shapes.stored_sex_word(str(party.get("sex") or "").strip())
        keep(f"{role}.sex", given.capitalize(), bool(given) and given == sex)
    respondent = raw.get("respondent") if isinstance(raw.get("respondent"), dict) else {}
    lines = [" ".join(str(x or "").split()) for x in (respondent.get("address_lines") or []) if str(x or "").strip()][:4]
    postcode = postcode_in(respondent.get("postcode"), text)
    if lines:
        if all(name_in(line, text) for line in lines) and postcode:
            out["respondent.address"] = {"lines": lines, "postcode": postcode}
        else:
            dropped += 1
    rel = raw.get("relationship") if isinstance(raw.get("relationship"), dict) else {}
    for key in ("lived_together", "married"):
        answer = rel.get(key)
        if isinstance(answer, bool):
            keep(f"relationship.{key}", answer, quote_in(rel.get(f"{key}_quote"), text))
    for key in ("start_year", "end_year"):
        y = str(rel.get(key) or "").strip()
        keep(f"relationship.{key}", y, year_in(y, text))
    wedding = str(rel.get("marriage_date") or "").strip()
    if wedding:
        if re.fullmatch(r"(?:19|20)\d{2}", wedding):
            keep("relationship.marriage_date", wedding, year_in(wedding, text))
        else:
            iso, ok = date(wedding)
            keep("relationship.marriage_date", iso or wedding, ok)
    bail = raw.get("bail") if isinstance(raw.get("bail"), dict) else {}
    if isinstance(bail.get("conditions"), bool):
        keep("bail.conditions", bail["conditions"], quote_in(bail.get("quote"), text) and "bail" in _flat(bail.get("quote")))
    if bail.get("end_date"):
        iso, ok = date(bail.get("end_date"))
        keep("bail.end_date", iso or bail.get("end_date"), ok and "bail" in _flat(text))
    refs = [str(r).strip() for r in (raw.get("crime_refs") or []) if str(r or "").strip()]
    good = [r for r in refs if ref_in(r, text)]
    dropped += len(refs) - len(good)
    if good:
        out["police.crime_refs"] = good
    c8 = raw.get("c8") if isinstance(raw.get("c8"), dict) else {}
    if isinstance(c8.get("requested"), bool):
        keep("c8.requested", c8["requested"], quote_in(c8.get("quote"), text))
    children = []
    for child in raw.get("children") or []:
        if not isinstance(child, dict):
            continue
        name = " ".join(str(child.get("full_name") or "").split())
        if not name or _is_not_a_child(name):
            continue
        if not name_in(name, text):
            dropped += 1
            continue
        dob, ok = date(child.get("dob"))
        if child.get("dob") and not ok:
            dropped += 1
        pr = child.get("respondent_has_pr")
        children.append({"name": name, "dob": dob if ok else "", "pr": pr if isinstance(pr, bool) else None})
    if children:
        out["children"] = children
    return out, dropped


def _is_not_a_child(name: str) -> bool:
    from onboarding import intro_children

    return intro_children.is_marker_name(name) or intro_children.is_placeholder_child(name)




def _ymd(day: str, month: str, year: str) -> str:
    try:
        return dt.date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return ""


def fl401_box_facts(updates: dict[str, Any]) -> dict[str, Any]:
    "Facts from referrer's FL401 soft copy as ``fill_fl401_pdf.updates_from_docx`` read its boxes. A form box is"
    from documents import fill_fl401_pdf as f

    u = {k: str(v or "").strip() for k, v in (updates or {}).items()}
    out: dict[str, Any] = {}

    def name(first: str, last: str) -> str:
        return " ".join(p for p in (u.get(first, ""), u.get(last, "")) if p)

    for key, value in (("applicant.name", name("2.1 First name(s)", "2.1 Last name")), ("respondent.name", name("3.1 First name(s)", "3.1 Last name"))):
        if value:
            out[key] = value
    for key, stem in (("applicant.dob", "2.3 Your date of birth"), ("respondent.dob", "3.3 The respondent's date of birth")):
        iso = _ymd(u.get(f"{stem} - DD", ""), u.get(f"{stem} - MM", ""), u.get(f"{stem} - YYYY", ""))
        if iso:
            out[key] = iso
    stem = "3.5 Respondent's full current address: "
    lines = [u.get(stem + part, "") for part in ("Building and street", "Second line of address", "Town or city")]
    postcode = postcode_in(u.get(stem + "postcode", ""), u.get(stem + "postcode", ""))
    if any(lines) and postcode:
        out["respondent.address"] = {"lines": [line for line in lines if line], "postcode": postcode}
    rel_start = u.get("4.2 When did your relationship start and when did it end? Start - YYYY", "")
    rel_end = u.get("4.2 When did your relationship start and when did it end? End - YYYY", "")
    if re.fullmatch(r"(?:19|20)\d{2}", rel_start):
        out["relationship.start_year"] = rel_start
    if re.fullmatch(r"(?:19|20)\d{2}", rel_end):
        out["relationship.end_year"] = rel_end
    wed = [u.get(f"{f.WEDDING_PREFIX} - {p}", "") or u.get(f"{f.WEDDING_PREFIX} {p}", "") for p in ("DD", "MM", "YYYY")]
    if _ymd(*wed):
        out["relationship.marriage_date"] = _ymd(*wed)
    elif re.fullmatch(r"(?:19|20)\d{2}", wed[2]):
        out["relationship.marriage_date"] = wed[2]
    ticks = {k[len("4.1 "):] for k, v in u.items() if k.startswith("4.1 ") and f.is_on(v)}
    if ticks & {"Live together as a couple", "Formerly lived together as a couple"}:
        out["relationship.lived_together"] = True
    elif any("does not live with me" in t for t in ticks):
        out["relationship.lived_together"] = False
    if ticks & {"Married or in a civil partnership", "Formerly married or in a civil partnership"}:
        out["relationship.married"] = True
    if f.is_on(u.get(f.BAIL_YES_FIELD)):
        out["bail.conditions"] = True
    elif f.is_on(u.get(f.BAIL_NO_FIELD)):
        out["bail.conditions"] = False
    bail_end = _ymd(*(u.get(f"When do the bail conditions end? {p}", "") for p in f.BAIL_END_FIELDS))
    if bail_end:
        out["bail.end_date"] = bail_end
    children = []
    for row in f._child_rows_from(u):
        child_name = " ".join(row.get(f.CHILD_FIELD_STEMS[0], "").split())
        if not child_name or _is_not_a_child(child_name):
            continue
        d, m, y = f.split_date(row.get(f.CHILD_FIELD_STEMS[1], ""))
        children.append({"name": child_name, "dob": _ymd(d, m, y), "pr": None})
    if children:
        out["children"] = children
    return out


def statement_child_facts(text: str) -> list[dict[str, Any]]:
    "The statement's children by the deterministic reader (``draft_orders.children_from_statement``, gh#1780)."
    try:
        from documents import draft_orders

        found = draft_orders.children_from_statement(text)
    except Exception:
        return []
    return [{"name": c["child_name"], "dob": c["dob_iso"], "pr": None} for c in found if c.get("child_name")]


def intro_bail_facts(text: str) -> dict[str, Any]:
    "The intro's bail line by ``fill_fl401_pdf.bail_conditions``: Yes only on a date or a stated condition."
    from documents import fill_fl401_pdf

    yes, end = fill_fl401_pdf.bail_conditions(text)
    out: dict[str, Any] = {}
    if yes:
        out["bail.conditions"] = True
        if end and _ymd(end[0], end[1], end[2]):
            out["bail.end_date"] = _ymd(end[0], end[1], end[2])
    return out


def _children_key(children: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(_compact(c.get("name")), str(c.get("dob") or "")) for c in children}


def shadow_outcome(det: list[dict[str, Any]], model: list[dict[str, Any]] | None) -> str:
    "The statement's child reader against the model, as ``field_audit``'s shadow outcomes (counts only)."
    det_k, model_k = _children_key(det), _children_key(model or [])
    if det_k and model_k:
        return "agree" if det_k == model_k else "disagree"
    return "model_only" if model_k else "det_only" if det_k else "neither"




def _same_value(fact: str, a: Any, b: Any) -> bool:
    if fact.endswith(".name"):
        from onboarding.field_audit import names_conflict

        return not names_conflict(a, b)
    if fact == "respondent.address":
        return _compact((a or {}).get("postcode")) == _compact((b or {}).get("postcode"))
    if fact == "police.crime_refs":
        return {_compact(x) for x in a or []} == {_compact(x) for x in b or []}
    if fact == "relationship.marriage_date":
        return str(a)[:4] == str(b)[:4] and (len(str(a)) == 4 or len(str(b)) == 4 or str(a) == str(b))
    return a == b


def _same_child(a: dict[str, Any], b: dict[str, Any]) -> bool:
    "The same child: one name holds all the other's words (\"Amy Example\" and \"Amy Jo Example\"), or the first names"
    wa, wb = _words(a.get("name")), _words(b.get("name"))
    return bool(wa and wb) and (wa <= wb or wb <= wa or _first(a) == _first(b))


def _first(child: dict[str, Any]) -> str:
    words = str(child.get("name") or "").split()
    return words[0].lower() if words else ""


def merge_readings(readings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    "``facts``, ``children`` and ``clashes`` from each paper's checked facts, by the order of papers."
    facts: dict[str, dict[str, Any]] = {}
    clashes: list[dict[str, Any]] = []
    keys = sorted({k for r in readings.values() for k in r if k != "children"})
    for fact in keys:
        order = IDENTITY_ORDER if fact in IDENTITY_FACTS else DEFAULT_ORDER
        given = [(src, readings[src][fact]) for src in order if src in readings and fact in readings[src]]
        if not given:
            continue
        (src, value), rest = given[0], given[1:]
        facts[fact] = {"value": value, "source": src}
        others = [{"source": s, "value": v} for s, v in rest if not _same_value(fact, value, v)]
        if others:
            clashes.append({"fact": fact, "chosen": {"source": src, "value": value}, "others": others})
    children: list[dict[str, Any]] = []
    for src in IDENTITY_ORDER:
        for child in (readings.get(src) or {}).get("children") or []:
            match = next((c for c in children if _same_child(c, child)), None)
            if match is None:
                children.append({**child, "source": src, "dob_source": src if child.get("dob") else ""})
                continue
            if child.get("dob") and not match.get("dob"):
                match["dob"], match["dob_source"] = child["dob"], src
            elif child.get("dob") and match.get("dob") and child["dob"] != match["dob"]:
                clashes.append({"fact": f"children.{_first(match)}.dob", "chosen": {"source": match["dob_source"], "value": match["dob"]},
                                "others": [{"source": src, "value": child["dob"]}]})
            if match.get("pr") is None and isinstance(child.get("pr"), bool):
                match["pr"] = child["pr"]
    return {"facts": facts, "children": children, "clashes": clashes}


APPLICANT_SEX_GAP = ("Client's sex: no paper gives it (C100 11.1 and C1A section 1 stay blank; record it on the matter, "
                     "never from a first name).")


def sheet_gaps(sheet: dict[str, Any]) -> list[str]:
    "The facts a court form needs that no paper gave, as the report's plain lines."
    facts = sheet.get("facts") or {}
    gaps = []
    if "respondent.address" not in facts:
        gaps.append("Respondent's full address with its postcode: no paper gives it (write Unknown only if it is not known).")
    if "respondent.dob" not in facts:
        gaps.append("Respondent's date of birth: no paper gives it.")
    if "applicant.dob" not in facts:
        gaps.append("Client's date of birth: no paper gives it.")
    if "applicant.sex" not in facts:
        gaps.append(APPLICANT_SEX_GAP)
    if (facts.get("bail.conditions") or {}).get("value") is True and "bail.end_date" not in facts:
        gaps.append("Bail end date (FL401 1.6): the papers say there are bail conditions but give no end date.")
    married = (facts.get("relationship.married") or {}).get("value") is True
    wedding = str((facts.get("relationship.marriage_date") or {}).get("value") or "")
    if married and not wedding:
        gaps.append("Wedding date (FL401 4.3): the papers say married but give no date.")
    elif len(wedding) == 4:
        gaps.append(f"Wedding date (FL401 4.3): only the year {wedding} is written; the full date is needed.")
    for child in sheet.get("children") or []:
        if not child.get("dob"):
            gaps.append(f"Date of birth of the child {_first(child).title() or 'named'}: no paper gives it.")
    return gaps


def build_fact_sheet(
    texts: dict[str, str], *, fl401_updates: dict[str, Any] | None = None, read: Callable[[dict[str, str]], dict[str, Any] | None] | None = None
) -> dict[str, Any]:
    "The fact sheet from the papers' texts (``{source: text}``) and the FL401 soft copy's parsed boxes. The model reads"
    texts = {k: str(v or "") for k, v in texts.items() if str(v or "").strip()}
    got = (read or model_read_sources)(texts)
    readings: dict[str, dict[str, Any]] = {}
    dropped: dict[str, int] = {}
    box_dates: set[str] = set()
    boxes = fl401_box_facts(fl401_updates or {}) if fl401_updates else {}
    for value in boxes.values():
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            box_dates.add(value)
    for kind, text in texts.items():
        reading, lost = _reading(kind, (got or {}).get(kind), text, box_dates if kind == SOURCE_FL401 else frozenset())
        readings[kind], dropped[kind] = reading, lost
    if boxes:
        readings[SOURCE_FL401] = {**readings.get(SOURCE_FL401, {}), **boxes}
    det_children = statement_child_facts(texts.get(SOURCE_STATEMENT, "")) if SOURCE_STATEMENT in texts else []
    model_children = (readings.get(SOURCE_STATEMENT) or {}).get("children") if got is not None else None
    if det_children and not (readings.get(SOURCE_STATEMENT) or {}).get("children"):
        readings.setdefault(SOURCE_STATEMENT, {})["children"] = det_children
    if SOURCE_INTRO in texts and "bail.conditions" not in readings.get(SOURCE_INTRO, {}):
        readings.setdefault(SOURCE_INTRO, {}).update(intro_bail_facts(texts[SOURCE_INTRO]))
    sheet: dict[str, Any] = {"version": SHEET_VERSION, "model_used": got is not None, "dropped": dropped, **merge_readings(readings)}
    sheet["gaps"] = sheet_gaps(sheet)
    sheet["shadow"] = {"statement.children": shadow_outcome(det_children, model_children)} if SOURCE_STATEMENT in texts and got is not None else {}
    return sheet



_FL401_NAME_RE = re.compile(r"(?i)(?<![a-z0-9])fl\s*-?\s*401(?![0-9])")


def choose_referral_partner_fl401(items: list[dict[str, Any]], surname: str = "") -> dict[str, Any]:
    "referrer's FL401 soft copy in Preliminary Docs: a Word file whose name says FL401 (\"Jane Doe FL401.docx\","
    from documents import soft_form_names

    found = []
    for item in items:
        name = str(item.get("name") or "")
        low = name.lower()
        if "folder" in item or not low.endswith(".docx") or not _FL401_NAME_RE.search(name):
            continue
        if re.search(r"(?i)(?<![a-z])(draft|filled|fl403)(?![a-z])", name) or soft_form_names.parse_soft_name(name):
            continue
        found.append(item)
    found.sort(key=lambda i: str(i.get("lastModifiedDateTime") or ""), reverse=True)
    return found[0] if found else {}


_ID_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".pdf")
_ID_NAME_RE = re.compile(r"(?i)(?<![a-z0-9])(?:id|passport|driv(?:ing|er'?s?)[ ._-]*licen[cs]e|licen[cs]e|brp|photo[ ._-]*id)(?![a-z0-9])")
ID_PROMPT = (
    "This is a photograph or scan of a UK identity document (passport, driving licence or residence permit). "
    "Copy only these printed fields, one per line, as 'Label: value' using the document's own wording: Surname, "
    "Given names, Date of birth, Sex. Copy a field only if it is printed on the document; leave out any field that is "
    "not printed (a UK driving licence prints no sex). Never infer a value from a name or a photograph. Do not copy "
    "the document number, the machine-readable lines, the address or the signature. If the image is not an identity "
    "document or cannot be read, reply exactly UNREADABLE."
)


def choose_id_document(items: list[dict[str, Any]]) -> dict[str, Any]:
    "The client's ID in Preliminary Docs: an image or PDF whose name says ID, passport, driving licence or BRP (referrer"
    found = []
    for item in items:
        name = str(item.get("name") or "")
        if "folder" in item or not name.lower().endswith(_ID_IMAGE_SUFFIXES) or not _ID_NAME_RE.search(name):
            continue
        if re.search(r"(?i)(?<![a-z])(draft|statement|ws|intro|loa|c100|c1a|fl401)(?![a-z])", name):
            continue
        found.append(item)
    found.sort(key=lambda i: str(i.get("lastModifiedDateTime") or ""), reverse=True)
    return found[0] if found else {}


def read_id_image(data: bytes, suffix: str, *, vision: Callable[..., str] | None = None) -> str:
    "The ID's printed fields as text, by the vision model (``model_backend.run_vision``: OpenRouter, zero data retention)."
    import document_ocr

    image = document_ocr.rasterize_pdf_page(data, 1) if suffix.lower() == ".pdf" else data
    text = (vision or model_backend.run_vision)(image, ID_PROMPT, max_tokens=400)
    text = str(text or "").strip()
    return "" if not text or text.upper().startswith("UNREADABLE") else text


def discover_sources(ctx: Any) -> dict[str, dict[str, Any]]:
    "The matter's papers: ``{source: {\"name\", \"path\", \"version\"}}`` for the intro, referrer's FL401 and the"
    from onboarding.pipeline import court_common as cc
    from onboarding.pipeline import step_statement

    prelim = cc.prelim_path(ctx)
    items = [i for i in (cc.listing(ctx, prelim) or []) if "folder" not in i]
    out: dict[str, dict[str, Any]] = {}

    def entry(folder: str, item: dict[str, Any]) -> dict[str, Any]:
        return {"name": str(item.get("name") or ""), "path": f"{folder}/{item.get('name')}",
                "version": str(item.get("eTag") or item.get("lastModifiedDateTime") or item.get("size") or "")}

    intro = sorted((i for i in items if re.match(r"(?i)^intro\b.*\.pdf$", str(i.get("name") or ""))),
                   key=lambda i: str(i.get("lastModifiedDateTime") or ""), reverse=True)
    if intro:
        out[SOURCE_INTRO] = entry(prelim, intro[0])
    fl401 = choose_referral_partner_fl401(items, ctx.surname)
    if fl401:
        out[SOURCE_FL401] = entry(prelim, fl401)
    id_item = choose_id_document(items)
    if id_item:
        out[SOURCE_ID] = entry(prelim, id_item)
    signed = cc.signed_ws(ctx)
    if signed:
        folder, _, name = signed.rpartition("/")
        item = next((i for i in cc.listing(ctx, folder) or [] if str(i.get("name") or "") == name), {"name": name})
        out[SOURCE_STATEMENT] = entry(folder, item)
    else:
        docx = next((i for i in items if str(i.get("name") or "").lower() == step_statement.output_name(ctx).lower()), None)
        if docx:
            out[SOURCE_STATEMENT] = entry(prelim, docx)
    return out


def fingerprint(sources: dict[str, dict[str, Any]]) -> str:
    return "|".join(f"{k}={sources[k]['path']}@{sources[k]['version']}" for k in sorted(sources)) + f"|v{SHEET_VERSION}"


def read_papers(sources: dict[str, dict[str, Any]]) -> tuple[dict[str, str], dict[str, Any]]:
    "``(texts, FL401 boxes)``: each paper downloaded into a temporary folder and read (PDF text layer, Word text with"
    import tempfile

    from documents import fill_fl401_pdf
    from onboarding.pipeline import court_common as cc
    from documents import draft_orders

    texts: dict[str, str] = {}
    boxes: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="fact-sheet-") as tmp:
        for kind, src in sources.items():
            try:
                local = Path(tmp) / f"{kind}{Path(src['name']).suffix.lower()}"
                local.write_bytes(cc.download(src["path"]))
            except Exception as exc:
                print(f"fact sheet: {kind} not fetched ({type(exc).__name__})", file=sys.stderr)
                continue
            if kind == SOURCE_ID:
                try:
                    text = read_id_image(local.read_bytes(), local.suffix)
                except Exception as exc:
                    print(f"fact sheet: id not read ({type(exc).__name__})", file=sys.stderr)
                    continue
                if text:
                    texts[kind] = text
                continue
            try:
                texts[kind] = draft_orders.extract_document_text(local)
            except Exception as exc:
                print(f"fact sheet: {kind} text not read ({type(exc).__name__})", file=sys.stderr)
            if kind == SOURCE_FL401:
                try:
                    boxes = fill_fl401_pdf.updates_from_docx(local)[0]
                except Exception as exc:
                    print(f"fact sheet: {kind} boxes not read ({type(exc).__name__})", file=sys.stderr)
    return texts, boxes




def _one_party(parties: list[dict[str, Any]], roles: set[str]) -> dict[str, Any] | None:
    rows = [p for p in parties if str(p.get("role") or "").strip().lower() in roles]
    return rows[0] if len(rows) == 1 else None


def _notify(matter_id: str, client_name: str, title: str, detail: str, key: str, notes: list[str], dry_run: bool) -> None:
    notes.append(title)
    if dry_run:
        return
    from onboarding import field_audit

    field_audit.RecordWriter().notify(matter_id, client_name, title, detail, key)


MATTER_FACT_COLUMNS = {
    "relationship.lived_together": "lived_together",
    "relationship.married": "married",
    "relationship.start_year": "relationship_start",
    "relationship.end_year": "relationship_end",
    "relationship.marriage_date": "marriage_date",
    "bail.conditions": "bail_conditions",
    "bail.end_date": "bail_end_date",
    "police.crime_refs": "crime_refs",
}
_FILL_ONLY_COLUMNS = {"relationship_start", "relationship_end", "marriage_date", "bail_end_date"}


def _record_value(value: Any) -> str:
    "A sheet value as its record column holds it: yes/no, the date or year as written, references one per line."
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return "\n".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def _source_phrase(fact: dict[str, Any]) -> str:
    return SOURCE_LABELS.get(str(fact.get("source") or ""), "papers")


def apply_fact_sheet(matter_id: str, sheet: dict[str, Any], *, client_name: str = "", has_c8: bool | None = None, dry_run: bool = False) -> dict[str, Any]:
    "Fill the record's gaps from the sheet and raise a ``field_audit`` notice (accept or reject) for each value the"
    mid = str(matter_id)
    facts = sheet.get("facts") or {}
    filled: list[str] = []
    notices: list[str] = []
    children = [{"child_name": c["name"], "dob_iso": c["dob"]} for c in sheet.get("children") or [] if c.get("name") and c.get("dob")]
    if children:
        filled += [f"child named: {n}" for n in fill_children_from_statement(mid, children, dry_run=dry_run)]
        for row in clientdb_sql.list_children(mid):
            match = next((c for c in sheet.get("children") or [] if c.get("dob") and _same_child({"name": row.get("child_name")}, c)), None)
            if not match or _is_not_a_child(str(row.get("child_name") or "")):
                continue
            have = str(row.get("dob_iso") or "")[:10]
            if not have:
                filled.append(f"child date of birth: {row.get('child_name')}")
                if not dry_run:
                    clientdb_sql.update_child(str(row["child_id"]), {"dob_iso": match["dob"]})
            elif have != match["dob"]:
                _notify(mid, client_name, f"Check {row.get('child_name')}'s date of birth",
                        f"The record has {have}; the {SOURCE_LABELS.get(match.get('dob_source'), 'papers')} gives {match['dob']}. Change it on the Details tab only if the paper is right.",
                        f"field_audit:{mid}:child.{_compact(row.get('child_name'))}.dob|{match['dob']}", notices, dry_run)
    parties = clientdb_sql.list_parties(mid)
    for role, roles in (("respondent", {"respondent"}), ("applicant", {"applicant", "client"})):
        party = _one_party(parties, roles)
        if party is None:
            continue
        pid = str(party.get("party_id") or party.get("matter_party_id") or "")
        dob = facts.get(f"{role}.dob")
        if dob:
            have = str(party.get("dob_iso") or "")[:10]
            if not have:
                filled.append(f"{role} date of birth")
                if not dry_run:
                    clientdb_sql.update_party(pid, {"dob_iso": dob["value"]})
            elif have != dob["value"]:
                _notify(mid, client_name, f"Check the {role}'s dob", f"The record has {have}; the {_source_phrase(dob)} gives {dob['value']}. Accept to change it.",
                        f"field_audit:{mid}:{role}.dob_iso:{dob['value']}", notices, dry_run)
        party_sex = facts.get(f"{role}.sex") if role == "respondent" else None
        if party_sex:
            have_sex = str(party.get("sex") or "").strip()
            if not have_sex:
                filled.append("respondent sex")
                if not dry_run:
                    clientdb_sql.update_party(pid, {"sex": party_sex["value"]})
            elif have_sex.lower() != str(party_sex["value"]).lower():
                _notify(mid, client_name, "Check the respondent's sex", f"The record has {have_sex}; the {_source_phrase(party_sex)} gives {party_sex['value']}. Change it on the Details tab only if the paper is right.",
                        f"field_audit:{mid}:respondent.sex|{_compact(party_sex['value'])}", notices, dry_run)
        name = facts.get(f"{role}.name")
        if name and role == "respondent":
            from onboarding.field_audit import names_conflict

            if names_conflict(party.get("display_name"), name["value"]):
                _notify(mid, client_name, "Check the respondent's name", f"The record has {party.get('display_name')}; the {_source_phrase(name)} gives {name['value']}. Accept to change it.",
                        f"field_audit:{mid}:respondent.display_name:{name['value']}", notices, dry_run)
        address = facts.get("respondent.address") if role == "respondent" else None
        if address:
            parts = ("address_line1", "address_line2", "address_line3", "address_line4", "address_postcode")
            text = str(party.get("address_text") or "").strip()
            blank = not any(str(party.get(p) or "").strip() for p in parts) and (not text or text.lower() == "unknown")
            value = address["value"]
            if blank:
                filled.append("respondent address")
                if not dry_run:
                    lines = (list(value["lines"]) + ["", "", "", ""])[:4]
                    clientdb_sql.update_party(pid, {**{f"address_line{i}": lines[i - 1] for i in range(1, 5)}, "address_postcode": value["postcode"]})
            elif _compact(party.get("address_postcode")) != _compact(value["postcode"]) and _compact(value["postcode"]) not in _compact(text):
                written = ", ".join([*value["lines"], value["postcode"]])
                _notify(mid, client_name, "Check the respondent's address", f"The record has {text or 'an address with no postcode'}; the {_source_phrase(address)} gives {written}. Change it on the Details tab only if the paper is right.",
                        f"field_audit:{mid}:respondent.address|{_compact(value['postcode'])}", notices, dry_run)
    applicant_dob = facts.get("applicant.dob")
    if applicant_dob and not str(clientdb_sql.get_editable_field(mid, "dob_iso") or "").strip():
        filled.append("client date of birth (client record)")
        if not dry_run:
            client_edits.record_edit(matter_id=mid, field_name="dob_iso", new_value=applicant_dob["value"],
                                     note=f"From the {_source_phrase(applicant_dob)} (fact sheet)", edited_by=SHEET_EDITOR)
    applicant_sex = facts.get("applicant.sex")
    if applicant_sex:
        have_sex = str(clientdb_sql.get_editable_field(mid, "sex") or "").strip()
        if not have_sex:
            filled.append("client sex (client record)")
            if not dry_run:
                client_edits.record_edit(matter_id=mid, field_name="sex", new_value=applicant_sex["value"],
                                         note=f"From the {_source_phrase(applicant_sex)} (fact sheet)", edited_by=SHEET_EDITOR)
        elif have_sex.lower() != str(applicant_sex["value"]).lower():
            _notify(mid, client_name, "Check the client's sex", f"The record has {have_sex}; the {_source_phrase(applicant_sex)} gives {applicant_sex['value']}. Change it on the Details tab only if the paper is right.",
                    f"field_audit:{mid}:sex|{_compact(applicant_sex['value'])}", notices, dry_run)
    for fact, column in MATTER_FACT_COLUMNS.items():
        entry = facts.get(fact)
        value = _record_value(entry["value"]) if entry else ""
        if not value:
            continue
        have = str(clientdb_sql.get_editable_field(mid, column) or "").strip()
        if not have:
            filled.append(f"{FACT_LABELS.get(fact, column).lower()} (client record)")
            if not dry_run:
                client_edits.record_edit(matter_id=mid, field_name=column, new_value=value,
                                         note=f"From the {_source_phrase(entry)} (fact sheet)", edited_by=SHEET_EDITOR)
        elif _compact(have) != _compact(value) and column not in _FILL_ONLY_COLUMNS:
            _notify(mid, client_name, f"Check {FACT_LABELS.get(fact, column).lower()}",
                    f"The record has {have}; the {_source_phrase(entry)} gives {value}. Change it on the Details tab only if the paper is right.",
                    f"field_audit:{mid}:{column}|{_compact(value)}", notices, dry_run)
    c8 = facts.get("c8.requested")
    if c8 and c8["value"] is True and has_c8 is False:
        _notify(mid, client_name, "Check C8: the papers ask to keep the client's details private",
                f"The {_source_phrase(c8)} asks for the client's contact details to be kept from the respondent, and the record has no C8 flag. Set it on the Details tab if that is right.",
                f"field_audit:{mid}:c8|requested", notices, dry_run)
    return {"filled": filled, "notices": notices}




def _shown(fact: str, value: Any) -> str:
    if fact == "respondent.address" and isinstance(value, dict):
        return ", ".join([*value.get("lines", []), value.get("postcode", "")])
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def report_text(sheet: dict[str, Any]) -> str:
    "The short clean-up list a person reads: what each paper gave, the clashes and the gaps. Never sent anywhere."
    lines = ["Facts check: what the papers say, for a person to decide", ""]
    read = [f"{SOURCE_LABELS[k]} ({v['name']})" for k, v in (sheet.get("sources") or {}).items() if k in SOURCE_LABELS]
    lines.append("Read: " + ("; ".join(read) if read else "no paper found") + ". ID document: " + ("read." if SOURCE_ID in (sheet.get("sources") or {}) else "none found or not readable."))
    if not sheet.get("model_used"):
        lines.append("THE MODEL COULD NOT RUN: only the FL401's own boxes, the statement's children lines and the intro's bail line were read.")
    clashes = sheet.get("clashes") or []
    lines.append("")
    lines.append(f"Papers that disagree ({len(clashes)}):" if clashes else "Papers that disagree: none.")
    for c in clashes:
        label = FACT_LABELS.get(c["fact"], c["fact"].replace(".", " "))
        others = "; ".join(f"the {SOURCE_LABELS.get(o['source'], o['source'])} gives {_shown(c['fact'], o['value'])}" for o in c["others"])
        lines.append(f"  - {label}: the {SOURCE_LABELS.get(c['chosen']['source'], '')} gives {_shown(c['fact'], c['chosen']['value'])} (used); {others}.")
    gaps = sheet.get("gaps") or []
    lines.append(f"Missing ({len(gaps)}):" if gaps else "Missing: nothing a form needs.")
    lines += [f"  - {g}" for g in gaps]
    applied = sheet.get("applied") or {}
    if applied.get("filled"):
        lines.append("Filled into the record (it was blank): " + "; ".join(applied["filled"]) + ".")
    if applied.get("notices"):
        lines.append("Raised for a person to accept or reject: " + "; ".join(applied["notices"]) + ".")
    lines += ["", "What the forms use:"]
    for fact, entry in sorted((sheet.get("facts") or {}).items()):
        lines.append(f"  {FACT_LABELS.get(fact, fact)}: {_shown(fact, entry['value'])} ({SOURCE_LABELS.get(entry['source'], entry['source'])})")
    for child in sheet.get("children") or []:
        lines.append(f"  Child: {child['name']}, born {child.get('dob') or 'date not given'} ({SOURCE_LABELS.get(child.get('source'), '')})")
    return "\n".join(lines) + "\n"


def stored_sheet(matter_id: Any, *, db_path: Any = None) -> dict[str, Any] | None:
    "The matter's last fact sheet from the ops database (no paper is read and no model called), or None."
    try:
        import ops_db

        with ops_db.connect(db_path) as conn:
            row = conn.execute("SELECT fingerprint, sheet, made_utc FROM matter_fact_sheets WHERE matter_id = ?", (str(matter_id),)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        sheet = json.loads(row[1])
    except ValueError:
        return None
    if not isinstance(sheet, dict):
        return None
    sheet["facts"] = {**(sheet.get("facts") or {}), **record_facts(matter_id)}
    return {**sheet, "fingerprint": row[0], "made_utc": row[2]}


def thin_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    "The sheet as it is stored once ``apply_fact_sheet`` has run: the facts the record now holds (``MATTER_FACT_COLUMNS``)"
    return {**sheet, "facts": {k: v for k, v in (sheet.get("facts") or {}).items() if k not in MATTER_FACT_COLUMNS}}


def _typed(fact: str, text: str) -> Any:
    "A record column's text as the sheet fact it came from (``True``, a list of references, the year, or the text)."
    if fact in ("relationship.lived_together", "relationship.married", "bail.conditions"):
        return {"yes": True, "no": False}.get(text.lower())
    if fact == "police.crime_refs":
        return [line.strip() for line in text.splitlines() if line.strip()]
    if fact in ("relationship.start_year", "relationship.end_year"):
        found = re.findall(r"(?:19|20)\d{2}", text)
        return found[-1] if found else None
    return text


def record_facts(matter_id: Any) -> dict[str, Any]:
    "The facts of ``MATTER_FACT_COLUMNS`` the matter's record holds, as sheet facts (``source: record``). Empty when the"
    out: dict[str, Any] = {}
    for fact, column in MATTER_FACT_COLUMNS.items():
        try:
            have = str(clientdb_sql.get_editable_field(str(matter_id), column) or "").strip()
        except Exception:
            return {}
        value = _typed(fact, have) if have else None
        if value not in (None, "", []):
            out[fact] = {"value": value, "source": SOURCE_RECORD}
    return out


def store_sheet(matter_id: Any, print_: str, sheet: dict[str, Any], *, db_path: Any = None) -> None:
    import ops_db

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    body = json.dumps({k: v for k, v in sheet.items() if k not in ("fingerprint", "made_utc")}, ensure_ascii=False, default=str)
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO matter_fact_sheets (matter_id, fingerprint, sheet, made_utc) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(matter_id) DO UPDATE SET fingerprint = excluded.fingerprint, sheet = excluded.sheet, made_utc = excluded.made_utc",
            (str(matter_id), print_, body, now),
        )


def _log_shadow(matter_id: str, sheet: dict[str, Any]) -> None:
    "One ``field_audit`` shadow line (outcome counts only, never a value), read by ``field_audit.shadow_report``."
    if not sheet.get("shadow"):
        return
    try:
        from onboarding import field_audit

        field_audit.log_line({"kind": "shadow", "counts": {k: {v: 1} for k, v in sheet["shadow"].items()}, "by": "fact-sheet"})
    except Exception:
        pass


def fact_sheet_for(ctx: Any, *, force: bool = False, apply: bool = True, upload: bool = True, read: Callable[..., Any] | None = None,
                   db_path: Any = None) -> dict[str, Any]:
    "The matter's fact sheet, made once per version of its papers: the papers found, read, checked and merged; the"
    sources = discover_sources(ctx)
    print_ = fingerprint(sources)
    stored = stored_sheet(ctx.matter_id, db_path=db_path)
    if stored and not force and stored.get("fingerprint") == print_:
        return {**stored, "status": "unchanged"}
    if not sources:
        return {"status": "no_papers", "facts": {}, "children": [], "clashes": [], "gaps": [], "sources": {}}
    texts, boxes = read_papers(sources)
    sheet = build_fact_sheet(texts, fl401_updates=boxes, read=read)
    sheet["sources"] = {k: {"name": v["name"]} for k, v in sources.items() if k in texts}
    sheet["applied"] = apply_fact_sheet(str(ctx.matter_id), sheet, client_name=getattr(ctx, "client_name", ""),
                                        has_c8=getattr(ctx, "has_c8", None), dry_run=not apply)
    try:
        if APPLICANT_SEX_GAP in sheet.get("gaps", []) and str(clientdb_sql.get_editable_field(str(ctx.matter_id), "sex") or "").strip():
            sheet["gaps"] = [g for g in sheet["gaps"] if g != APPLICANT_SEX_GAP]
    except Exception:
        pass
    if upload and apply:
        try:
            import tempfile

            import graph_files
            from onboarding.pipeline import court_common as cc

            name = REPORT_NAME.format(surname=ctx.surname)
            with tempfile.TemporaryDirectory(prefix="fact-sheet-report-") as tmp:
                note = Path(tmp) / name
                note.write_text(report_text(sheet), encoding="utf-8")
                graph_files.upload(note, cc.guarded_path(f"{cc.prelim_path(ctx)}/{name}"), ctx.token(), conflict_behavior="replace")
            sheet["report"] = name
        except Exception as exc:
            print(f"fact sheet: clean-up list not saved ({type(exc).__name__})", file=sys.stderr)
    if apply:
        store_sheet(ctx.matter_id, print_ if sheet.get("model_used") else "", thin_sheet(sheet), db_path=db_path)
        _log_shadow(str(ctx.matter_id), sheet)
    return {**sheet, "status": "made"}


def form_facts(sheet: dict[str, Any] | None) -> dict[str, Any]:
    "The sheet as the form fillers want it: ``{fact: value}`` plus ``children`` (name and ISO date of birth)."
    if not sheet:
        return {}
    out = {fact: entry["value"] for fact, entry in (sheet.get("facts") or {}).items() if isinstance(entry, dict)}
    out["children"] = [{"name": c["name"], "dob": c.get("dob") or ""} for c in sheet.get("children") or [] if c.get("name")]
    return out


def check_lines(sheet: dict[str, Any] | None, surname: str = "") -> list[str]:
    "Case flow's lines about the sheet (court pack step): how many clashes and gaps, where the list is. No values."
    if not sheet or sheet.get("status") == "no_papers":
        return []
    clashes, gaps = sheet.get("clashes") or [], sheet.get("gaps") or []
    where = REPORT_NAME.format(surname=surname) if surname else "the Facts-check list"
    if not clashes and not gaps:
        return [f"Facts check: the papers agree and nothing a form needs is missing ({where})."]
    labels = [FACT_LABELS.get(c["fact"], "a child's date of birth" if c["fact"].startswith("children.") else c["fact"]) for c in clashes]
    line = f"Facts check: {len(clashes)} for a person to decide, {len(gaps)} missing: see {where} in Preliminary Docs."
    return [line] + ([f"Papers disagree on: {', '.join(labels)}."] if labels else [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-name", help="AI-EXP client folder name, exactly as it appears on OneDrive")
    parser.add_argument("--matter-id", help="caseforge-clientdb matter_id to write facts onto")
    parser.add_argument("--scan", action="store_true", help="Backfill every AI-EXP client that resolves to a real matter_id")
    parser.add_argument("--limit", type=int, default=None, help="With --scan, cap how many clients are processed")
    parser.add_argument("--dry-run", action="store_true", help="Extract and report but do not write")
    parser.add_argument("--fl401-filename", default="", help="Explicit real FL401 filename, when the automatic finder can't resolve it. Omit for a PSO/CAO-only matter with no fresh FL401 at all.")
    parser.add_argument("--ws-filename", help="Explicit real witness-statement filename, when the automatic finder can't resolve it. Triggers the explicit-files path on its own.")
    parser.add_argument("--fact-sheet", action="store_true", help="Make the matter's fact sheet (gh#1450) for --matter-id: any book. With --dry-run nothing is written or saved")
    parser.add_argument("--force", action="store_true", help="With --fact-sheet, read the papers again even when they have not changed")
    args = parser.parse_args(argv)

    if args.fact_sheet:
        if not args.matter_id:
            parser.error("--fact-sheet needs --matter-id")
        from onboarding import pipeline as intake_pipeline

        sheet = fact_sheet_for(intake_pipeline.load_context(args.matter_id), force=args.force or args.dry_run, apply=not args.dry_run)
        print(json.dumps({
            "matter_id": args.matter_id, "status": sheet.get("status"), "model_used": sheet.get("model_used"),
            "papers": sorted((sheet.get("sources") or {}).keys()), "facts": sorted((sheet.get("facts") or {}).keys()),
            "children": len(sheet.get("children") or []), "clashes": [c["fact"] for c in sheet.get("clashes") or []],
            "gaps": len(sheet.get("gaps") or []), "filled": len((sheet.get("applied") or {}).get("filled") or []),
            "notices": len((sheet.get("applied") or {}).get("notices") or []), "shadow": sheet.get("shadow"),
        }, indent=2))
        return 0

    if args.scan:
        summary = scan(dry_run=args.dry_run, limit=args.limit)
        print(json.dumps(summary, indent=2, default=str))
        return 1 if summary["errored"] else 0

    if not args.client_name or not args.matter_id:
        parser.error("--client-name and --matter-id (or --scan) are required")

    try:
        if args.ws_filename:
            result = backfill_matter_with_explicit_files(
                args.client_name,
                args.matter_id,
                fl401_filename=args.fl401_filename,
                ws_filename=args.ws_filename,
                dry_run=args.dry_run,
            )
        else:
            result = backfill_matter(args.client_name, args.matter_id, dry_run=args.dry_run)
    except (GatherError, FactExtractionError) as exc:
        print(json.dumps({"client_name": args.client_name, "matter_id": args.matter_id, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
