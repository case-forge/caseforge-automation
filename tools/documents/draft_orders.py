#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import os
import re
import tempfile
import sys
import urllib.error
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from london_time import london_today
from documents import client_info_cleaner
from documents.court_heading import court_place
from documents import docx_template_fill
from documents import order_registry
from documents import fill_fl401_pdf
from documents import soft_form_names
from documents import sot_signature
import graph_files
import child_age
import matter_orders
import order_codes as order_codes_module
from field_shapes import known_value
from onboarding import notice_of_acting

from agwu import children as agwu_children


REPO_ROOT = TOOLS_DIR.parent
NMO_TEMPLATE = order_registry.house_order_path("NMO")
OO_TEMPLATE = order_registry.house_order_path("OO")
PSO_TEMPLATE = order_registry.house_order_path("PSO")

SOURCE_FL401_RE = re.compile(r"\b(fl401|application)\b", re.I)
WITNESS_RE = re.compile(r"\b(witness\s+statement|statement)\b", re.I)
EXCLUDED_STATEMENT_RE = re.compile(r"\b(statement\s+of\s+service|bank\s+statement|position\s+statement|statement\s+of\s+account)\b", re.I)


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalise_graph_path(value: Any) -> str:
    try:
        return graph_files.normalise_onedrive_path(str(value or "")).__dict__["relative_path"]
    except Exception:
        return str(value or "").replace("\\", "/").strip("/")


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._()' -]+", "", clean_text(value)).strip(" .")
    return cleaned or "FL401 pack"


split_name = fill_fl401_pdf.split_name


def _surname(full_name: str) -> str:
    parts = clean_text(full_name).split()
    return parts[-1].upper() if parts else "CLIENT"


def order_codes(details: Mapping[str, Any]) -> set[str]:
    return notice_of_acting.normalise_order_codes(details)


def has_nmo_matter(details: Mapping[str, Any]) -> bool:
    if "NMO" in notice_of_acting.normalise_order_codes(details):
        return True
    if not clean_text(details.get("order_requested_text") or ""):
        return "NMO" in matter_orders.resolve_orders(clean_text(details.get("matter_name") or "")).codes
    return False


def order_type_text(details: Mapping[str, Any]) -> str:
    codes = order_codes(details)
    ordered = [code for code in ("NMO", "OO", "CAO", "PSO", "SIO") if code in codes]
    if ordered:
        return " ".join(ordered)
    return clean_text(details.get("order_requested_text") or "")


def matter_tracker_notes(matter_id: str) -> str:
    if not clean_text(matter_id):
        return ""
    try:
        from clientdb_sql import get_connection

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tracker_notes FROM matters WHERE CAST(matter_id AS NVARCHAR(128)) = ?", (matter_id,))
            row = cursor.fetchone()
        return clean_text(row[0]) if row else ""
    except Exception:
        return ""


def load_parties(matter_id: str) -> list[dict[str, Any]]:
    if not clean_text(matter_id):
        return []
    from clientdb_sql import list_parties

    return list_parties(matter_id)


_STATEMENT_CHILD_RE = re.compile(
    r"(?<![\w'’-])([A-Z][\w'’]*(?:[ -][A-Z][\w'’]*){1,3}),?\s+(?:who\s+)?(?:was\s+)?born\s+on\s+(?:the\s+)?"
    r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[A-Za-z]{3,9},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})"
)
_STATEMENT_CHILD_CONTEXT_RE = re.compile(r"(?i)\b(child|children|son|sons|daughter|daughters)\b")
_NOT_A_CHILD_WORDS = {"the", "respondent", "applicant", "i", "my", "he", "she", "they", "mr", "mrs", "ms", "miss"}


def children_from_statement(text: str) -> list[dict[str, str]]:
    out: dict[str, str] = {}
    in_list = False
    for para in re.split(r"\n+", str(text or "")):
        is_item = bool(re.match(r"\s*(?:\(?[a-h]\)|[a-h]\.|\(?[ivx]{1,4}\)|[ivx]{1,4}\.|[-•])\s", para))
        about_children = bool(_STATEMENT_CHILD_CONTEXT_RE.search(para))
        if not (about_children or (in_list and is_item)):
            in_list = False
            continue
        in_list = about_children or is_item
        for m in _STATEMENT_CHILD_RE.finditer(para):
            name = " ".join(m.group(1).split())
            if name.split()[0].lower() in _NOT_A_CHILD_WORDS:
                continue
            day, month, year = fill_fl401_pdf.full_date(re.sub(r"(?i)\bof\s+|,", " ", m.group(2)))
            if day and month and year:
                out.setdefault(name, f"{year}-{month}-{day}")
    return [{"child_name": name, "dob_iso": dob} for name, dob in out.items()]


def children_with_statement(rows: list[dict[str, Any]], statement_text: str) -> list[dict[str, Any]]:
    if any(clean_text(row.get("child_name")) for row in rows):
        return rows
    named = children_from_statement(statement_text)
    if not named:
        return rows
    template = rows[0] if len(rows) == len(named) == 1 else {}
    return [{**{k: v for k, v in template.items() if k not in ("child_name", "dob_iso")}, **child} for child in named]


def stored_fact_sheet(matter_id: Any) -> dict[str, Any] | None:
    try:
        import matter_fact_extraction

        return matter_fact_extraction.stored_sheet(clean_text(matter_id))
    except Exception:
        return None


def sheet_values(sheet: Mapping[str, Any] | None) -> dict[str, Any]:
    if not sheet:
        return {}
    import matter_fact_extraction

    return matter_fact_extraction.form_facts(dict(sheet))


def _sheet_date(value: Any) -> str:
    text = clean_text(value)
    return text if re.fullmatch(r"(?:19|20)\d{2}", text) else _dmy(text)


def fallback_with_sheet(fallback: dict[str, Any], values: Mapping[str, Any]) -> list[str]:
    filled: list[str] = []

    def put(key: str, value: Any, *, replace: bool = False) -> None:
        if clean_text(value) and (replace or not clean_text(fallback.get(key))):
            fallback[key] = clean_text(value)
            filled.append(key)

    put("applicant_dob", _sheet_date(values.get("applicant.dob")))
    put("respondent_name", values.get("respondent.name"))
    put("respondent_dob", _sheet_date(values.get("respondent.dob")))
    address = values.get("respondent.address")
    if isinstance(address, Mapping) and address.get("postcode"):
        have = fill_fl401_pdf.address_state(clean_text(fallback.get("respondent_address")))
        put("respondent_address", ", ".join([*address.get("lines", []), address["postcode"]]), replace=have != "ok")
    put("relationship_start", values.get("relationship.start_year"))
    put("relationship_end", values.get("relationship.end_year"))
    return filled


def sheet_bail(values: Mapping[str, Any]) -> tuple[bool | None, tuple[str, str, str] | None] | None:
    stated = values.get("bail.conditions")
    end = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", clean_text(values.get("bail.end_date")))
    parts = (end.group(3), end.group(2), end.group(1)) if end else None
    if isinstance(stated, bool):
        return stated, parts if stated else None
    return (True, parts) if parts else None


def _same_child_name(a: Any, b: Any) -> bool:
    wa, wb = set(clean_text(a).lower().split()), set(clean_text(b).lower().split())
    return bool(wa and wb) and (wa <= wb or wb <= wa or clean_text(a).lower().split()[0] == clean_text(b).lower().split()[0])


def children_for_forms(rows: list[dict[str, Any]], sheet_children: Sequence[Mapping[str, Any]], statement_text: str) -> list[dict[str, Any]]:
    if any(clean_text(row.get("child_name")) for row in rows):
        out = []
        for row in rows:
            if not clean_text(row.get("dob_iso")):
                match = next((c for c in sheet_children if c.get("dob") and _same_child_name(row.get("child_name"), c.get("name"))), None)
                if match:
                    row = {**row, "dob_iso": match["dob"]}
            out.append(row)
        return out
    named = [{"child_name": clean_text(c.get("name")), "dob_iso": clean_text(c.get("dob"))} for c in sheet_children if clean_text(c.get("name"))]
    if not named:
        return children_with_statement(rows, statement_text)
    template = rows[0] if len(rows) == len(named) == 1 else {}
    return [{**{k: v for k, v in template.items() if k not in ("child_name", "dob_iso")}, **child} for child in named]


def load_children(matter_id: str) -> list[dict[str, Any]]:
    try:
        import clientdb_sql

        from onboarding import intro_children

        return [row for row in intro_children.tidy_children([dict(row) for row in clientdb_sql.list_children(clean_text(matter_id))]) if not intro_children.is_placeholder_child(row.get("child_name"))]
    except Exception:
        return []


def has_children(details: Mapping[str, Any], children: list[Mapping[str, Any]]) -> bool:
    return bool(children) or clean_text(known_value(details.get("children_summary"))).lower() not in {"", "none", "no", "n/a", "nil"}


def party_by_role(parties: list[Mapping[str, Any]], roles: set[str]) -> dict[str, Any]:
    for party in parties:
        role = clean_text(party.get("role")).lower()
        if role in roles:
            return dict(party)
    return {}


def _dmy(iso: Any) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", clean_text(iso))
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}" if match else clean_text(iso)


_TITLES = {"mr": "Mr", "mrs": "Mrs", "ms": "Ms", "miss": "Miss", "mx": "Mx", "dr": "Dr"}
_GENDER_TITLES = {"male": "Mr", "m": "Mr", "man": "Mr", "female": "Ms", "f": "Ms", "woman": "Ms"}


def person_title(title: Any = "", gender: Any = "") -> str:
    stated = clean_text(title).rstrip(".").lower()
    if stated in _TITLES:
        return _TITLES[stated]
    return _GENDER_TITLES.get(clean_text(gender).lower(), "")


def order_address(value: Any) -> str:
    text = re.sub(r",?\s*\b(?:UK|U\.K\.|United Kingdom)\.?\s*$", "", clean_text(value), flags=re.IGNORECASE).rstrip(", ")
    return ", ".join(fill_fl401_pdf.without_repeated_parts([part.strip() for part in text.split(",") if part.strip()]))


def sql_facts(details: Mapping[str, Any], parties: list[Mapping[str, Any]]) -> dict[str, str]:
    applicant = party_by_role(parties, {"applicant", "client"})
    respondent = party_by_role(parties, {"respondent", "respondant", "other party"})
    has_c8 = bool(details.get("has_c8"))
    facts = {
        "client_name": clean_text(details.get("client_name") or details.get("matter_name")),
        "client_dob": clean_text(details.get("dob_iso")),
        "applicant_dob": _dmy(applicant.get("dob_iso") or details.get("dob_iso")),
        "applicant_phone": "" if has_c8 else clean_text(details.get("phone_primary") or applicant.get("phone_primary")),
        "applicant_email": "" if has_c8 else clean_text(details.get("email_primary") or applicant.get("email_primary")),
        "applicant_address": "" if has_c8 else clean_text(applicant.get("address_text")),
        "respondent_name": clean_text(respondent.get("display_name") or details.get("respondent_name")),
        "respondent_dob": _dmy(respondent.get("dob_iso")),
        "respondent_address": clean_text(respondent.get("address_text")),
        "respondent_phone": clean_text(respondent.get("phone_primary") or respondent.get("phone_digits")),
        "respondent_email": clean_text(respondent.get("email_primary")),
        "applicant_title": person_title(applicant.get("title"), applicant.get("gender")),
        "respondent_title": person_title(respondent.get("title"), respondent.get("gender")),
        "relationship_start": clean_text(details.get("relationship_start")),
        "relationship_end": clean_text(details.get("relationship_end")),
        "has_c8": "yes" if details.get("has_c8") else "",
        "order_type": order_type_text(details),
    }
    return {key: value for key, value in facts.items() if clean_text(value)}


def direct_children(parent_path: str, item_type: str = "", access_token: str | None = None) -> list[dict[str, Any]]:
    return agwu_children.children_of(parent_path, item_type=item_type, allow_live_fallback=True, access_token=access_token, caller="draft_orders.direct_children")


def list_candidate_files(matter_path: str, children: list[Mapping[str, Any]], access_token: str | None = None) -> list[dict[str, Any]]:
    return agwu_children.list_candidate_files(matter_path, children, access_token=access_token, lister=direct_children)


choose_folder = agwu_children.choose_folder
candidate_source_folders = agwu_children.candidate_source_folders
_modified_key = agwu_children.modified_of



def is_fl403_source(source: Mapping[str, Any]) -> bool:
    return bool(re.search(r"\bfl403\b", clean_text(source.get("name")).lower()))


def choose_source_fl401(files: list[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = []
    for item in files:
        name = clean_text(item.get("name"))
        lower = name.lower()
        if not lower.endswith(".docx"):
            continue
        if any(token in lower for token in ("filled", "draft order", "legal aid", "laa", "ccms")):
            continue
        score = 0
        if re.search(r"\bfl401\b", lower):
            score = 30
        elif re.search(r"\bfl403\b", lower):
            score = 25
        elif "application" in lower and (
            "NMO" in order_codes_module.codes_in_text(lower) or re.search(r"injunction|domestic abuse", lower)
        ):
            score = 20
        elif SOURCE_FL401_RE.search(name):
            score = 10
        if score:
            candidates.append((score, _modified_key(item), dict(item)))
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return candidates[0][2] if candidates else {}


def choose_witness_statement(files: list[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = []
    for item in files:
        name = clean_text(item.get("name"))
        lower = name.lower()
        if not lower.endswith((".docx", ".pdf")):
            continue
        if WITNESS_RE.search(name) and not EXCLUDED_STATEMENT_RE.search(name):
            candidates.append(dict(item))
    candidates.sort(key=_modified_key, reverse=True)
    return candidates[0] if candidates else {}


def _download_item(item: Mapping[str, Any], output: Path, access_token: str | None = None) -> None:
    graph_files.download(clean_text(item.get("path")), output, access_token=access_token)


def _docx_text(path: Path) -> str:
    doc = Document(path)
    parts = [paragraph.text for paragraph in doc.paragraphs]
    w_p, w_t = qn("w:p"), qn("w:t")
    for table in doc.tables:
        for tr in table._tbl.tr_lst:
            for tc in tr.tc_lst:
                for para in tc.iter(w_p):
                    parts.append("".join(t.text or "" for t in para.iter(w_t)))
    return "\n".join(part for part in parts if clean_text(part))


def _pdf_text(path: Path) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_document_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return _docx_text(path)
    if path.suffix.lower() == ".pdf":
        return _pdf_text(path)
    return ""


def _parse_statement_date(value: str) -> dt.date | None:
    value = clean_text(value)
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d-%m-%y", "%d %B %Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _date_phrase(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            return clean_text(match.group(1).strip(" .,:;"))
    return ""


def parse_witness_statement_facts(text: str) -> dict[str, str]:
    compact = clean_text(text)
    facts: dict[str, str] = {}
    statement_date = _date_phrase(
        compact,
        [
            r"\bdated\s+(\d{1,2}[./-]\d{1,2}[./-](?:\d{2}|\d{4}))\b",
            r"\bdated\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})\b",
        ],
    )
    if statement_date:
        facts["statement_date"] = statement_date
    rel_start = _date_phrase(
        compact,
        [
            r"\brelationship\s+(?:started|began|commenced)\s+(?:in|on|around)?\s*([A-Za-z]+\s+20\d{2}|20\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"\bwe\s+(?:started|began)\s+(?:a\s+)?relationship\s+(?:in|on|around)?\s*([A-Za-z]+\s+20\d{2}|20\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ],
    )
    if rel_start:
        facts["relationship_start"] = rel_start
    rel_end = _date_phrase(
        compact,
        [
            r"\brelationship\s+(?:ended|broke down)\s+(?:in|on|around)?\s*([A-Za-z]+\s+20\d{2}|20\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"\brelationship\s+came\s+to\s+an\s+end\s+(?:in|on|around)?\s*([A-Za-z]+\s+20\d{2}|20\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"\b(?:we\s+)?(?:separated|split up)\s+(?:in|on|around)?\s*([A-Za-z]+\s+20\d{2}|20\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ],
    )
    if rel_end:
        facts["relationship_end"] = rel_end
    wedding = _date_phrase(
        compact,
        [
            r"\b(?:we\s+)?(?:got\s+married|were\s+married|married)\s+(?:on|in)\s+(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+(?:19|20)\d{2})",
            r"\b(?:wedding|marriage|civil\s+ceremony|civil\s+partnership)\s+(?:took\s+place\s+)?(?:was\s+)?(?:on|dated)\s+(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+(?:19|20)\d{2})",
            r"\b(?:we\s+)?(?:got\s+married|were\s+married|married)\s+(?:in|during)\s+((?:19|20)\d{2})\b",
        ],
    )
    if wedding:
        facts["marriage_date"] = wedding
    return facts


def fl401_facts_from_updates(updates: Mapping[str, Any]) -> dict[str, str]:
    facts = {
        "client_name": " ".join(
            part
            for part in [
                clean_text(updates.get("2.1 First name(s)")),
                clean_text(updates.get("2.1 Last name")),
            ]
            if part
        ),
        "client_dob": "/".join(
            part
            for part in [
                clean_text(updates.get("2.3 Your date of birth - DD")),
                clean_text(updates.get("2.3 Your date of birth - MM")),
                clean_text(updates.get("2.3 Your date of birth - YYYY")),
            ]
            if part
        ),
        "applicant_address": ", ".join(
            part
            for part in [
                clean_text(updates.get("2.5 Your full current address: building and street")),
                clean_text(updates.get("2.5 Your full current address: second line of address")),
                clean_text(updates.get("2.5 Your full current address: town or city")),
                clean_text(updates.get("2.5 Your full current address: postcode")),
            ]
            if part
        ),
        "applicant_phone": clean_text(updates.get("2.6 Your phone number")),
        "applicant_email": clean_text(updates.get("2.7 Your email address")),
        "respondent_name": " ".join(
            part
            for part in [
                clean_text(updates.get("3.1 First name(s)")),
                clean_text(updates.get("3.1 Last name")),
            ]
            if part
        ),
        "respondent_dob": "/".join(
            part
            for part in [
                clean_text(updates.get("3.3 The respondent's date of birth - DD")),
                clean_text(updates.get("3.3 The respondent's date of birth - MM")),
                clean_text(updates.get("3.3 The respondent's date of birth - YYYY")),
            ]
            if part
        ),
        "respondent_address": ", ".join(
            part
            for part in [
                clean_text(updates.get("3.5 Respondent's full current address: Building and street")),
                clean_text(updates.get("3.5 Respondent's full current address: Second line of address")),
                clean_text(updates.get("3.5 Respondent's full current address: Town or city")),
                clean_text(updates.get("3.5 Respondent's full current address: postcode")),
            ]
            if part
        ),
        "respondent_phone": clean_text(updates.get("3.6 The respondent's phone number (if you know it)")),
        "relationship_start": "/".join(
            part
            for part in [
                clean_text(updates.get("4.2 When did your relationship start and when did it end? Start - DD")),
                clean_text(updates.get("4.2 When did your relationship start and when did it end? Start - MM")),
                clean_text(updates.get("4.2 When did your relationship start and when did it end? Start - YYYY")),
            ]
            if part
        ),
        "relationship_end": "/".join(
            part
            for part in [
                clean_text(updates.get("4.2 When did your relationship start and when did it end? End - DD")),
                clean_text(updates.get("4.2 When did your relationship start and when did it end? End - MM")),
                clean_text(updates.get("4.2 When did your relationship start and when did it end? End - YYYY")),
            ]
            if part
        ),
    }
    return {key: value for key, value in facts.items() if clean_text(value)}


def cleaner_fallback(cleaner_result: Mapping[str, Any], details: Mapping[str, Any]) -> dict[str, str]:
    chosen = cleaner_result.get("chosen") if isinstance(cleaner_result.get("chosen"), dict) else {}
    values = {field: clean_text((fact or {}).get("value")) for field, fact in chosen.items() if isinstance(fact, dict)}
    values["name"] = values.get("client_name", "") or clean_text(details.get("client_name") or details.get("matter_name"))
    values["applicant_name"] = values["name"]
    values["order_type"] = values.get("order_type", "") or order_type_text(details)
    values["company_reference"] = clean_text(details.get("company_reference") or details.get("case_reference"))
    return {key: value for key, value in values.items() if clean_text(value)}


BARE_WORD_KEYS = ("Children", "Date", "WSDate")


_POSSESSIVE = {"Mr": "his", "Mrs": "her", "Ms": "her", "Miss": "her"}


CHILDREN_BLANK = "______________________"


def judge_order_data(order_data: Mapping[str, Any], *, children_required: bool = False) -> dict[str, Any]:
    data = {k: v for k, v in order_data.items() if k not in BARE_WORD_KEYS}
    data["ChildrenText"] = order_data.get("Children", "") or (CHILDREN_BLANK if children_required else "")
    data["StatementDate"] = order_data.get("WSDate", "")
    applicant_title = person_title(order_data.get("ApplicantTitle"))
    for key in ("ApplicantTitle", "RespondentTitle"):
        title = person_title(order_data.get(key))
        data[key] = f"{title} " if title else ""
    data["ApplicantPossessive"] = _POSSESSIVE.get(applicant_title, "their")
    for key in ("ApplicantAddress", "RespondentAddress"):
        if key in data:
            data[key] = order_address(data[key])
    return data


def children_lines(children: Sequence[Mapping[str, Any]], summary: str, as_of: dt.date) -> str:
    lines = []
    for child in children:
        name = clean_text(child.get("child_name"))
        if not name:
            continue
        iso = clean_text(child.get("dob_iso"))
        age = child_age.age_on(iso, as_of)
        match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso)
        if match and age is not None:
            lines.append(f"{name} (born {match.group(3)}/{match.group(2)}/{match.group(1)}, aged {age})")
        elif match:
            lines.append(f"{name} (born {match.group(3)}/{match.group(2)}/{match.group(1)})")
        else:
            lines.append(name)
    if lines:
        return "\n".join(lines)
    return "\n".join(part.strip() for part in child_age.with_live_ages(named_summary(summary), as_of).split(";") if part.strip())


_NOT_A_CHILD_NAME = {"child", "children", "pr", "son", "sons", "daughter", "daughters", "unnamed", "minor", "minors", "both", "na"}


def named_summary(summary: str) -> str:
    keep = []
    for part in str(summary or "").split(";"):
        words = re.findall(r"[A-Za-z][A-Za-z'’-]+", part)
        if any(w[0].isupper() and w.lower() not in _NOT_A_CHILD_NAME for w in words):
            keep.append(part.strip())
    return "; ".join(keep)


def _is_portal_court(matter_id: Any) -> bool:
    court = _recorded_court(matter_id)
    if not court:
        return False
    try:
        from onboarding.pipeline import portal_courts

        return bool(portal_courts.portal_court(court))
    except Exception:
        return False


def _recorded_court(matter_id: Any) -> str:
    mid = clean_text(matter_id)
    if not mid:
        return ""
    try:
        from documents.court_of_record import get_court

        return clean_text((get_court(mid) or {}).get("court"))
    except Exception:
        return ""


_SIGNED_DATE_RE = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+([A-Z][a-z]+)\s+(\d{1,2}),?\s+(20\d{2})\b"
)


def signed_statement_date(text: str) -> str:
    found = ""
    for month, day, year in _SIGNED_DATE_RE.findall(text or ""):
        try:
            found = dt.datetime.strptime(f"{day} {month} {year}", "%d %B %Y").strftime("%d/%m/%Y")
        except ValueError:
            continue
    return found


def _heading_children(children: Sequence[Mapping[str, Any]], details: Mapping[str, Any]) -> str:
    from onboarding.notice_of_acting import proper_child_name

    names = [proper_child_name(clean_text(c.get("child_name"))) for c in children if clean_text(c.get("child_name"))]
    return "; ".join(names) or named_summary(clean_text(known_value(details.get("children_summary"))))


def _order_matter_lines(codes: Iterable[str], children_summary: str) -> str:
    from documents.court_heading import matter_lines
    from onboarding.notice_of_acting import minors_line

    return "\n".join(matter_lines(codes, minors_line(children_summary)))


def order_template_data(
    facts: Mapping[str, Any],
    details: Mapping[str, Any],
    children: Sequence[Mapping[str, Any]] = (),
    order_codes_override: Iterable[str] | None = None,
) -> dict[str, str]:
    applicant_first, applicant_last = split_name(clean_text(facts.get("applicant_name") or facts.get("client_name") or facts.get("name")))
    respondent_first, respondent_last = split_name(clean_text(facts.get("respondent_name")))
    today_date = london_today()
    today = today_date.strftime("%d/%m/%Y")
    has_c8 = bool(details.get("has_c8"))
    statement_date_text = clean_text(facts.get("statement_date"))
    children_as_of = _parse_statement_date(statement_date_text) or today_date
    return {
        "CourtName": court_place(clean_text(details.get("court_name")) or _recorded_court(details.get("matter_id"))) or "[court]",
        "CaseReference": clean_text(details.get("company_reference") or details.get("case_reference")),
        "ApplicantFirstName": applicant_first,
        "ApplicantLastName": applicant_last,
        "RespondentFirstName": respondent_first,
        "RespondentLastName": respondent_last,
        "RespondentAddress": order_address(facts.get("respondent_address")) or fill_fl401_pdf.ADDRESS_UNKNOWN,
        "RespondentDOB": clean_text(facts.get("respondent_dob")),
        "ApplicantTitle": person_title(facts.get("applicant_title"), facts.get("applicant_gender")),
        "RespondentTitle": person_title(facts.get("respondent_title"), facts.get("respondent_gender")),
        "ApplicantAddress": "" if has_c8 else order_address(facts.get("applicant_address")),
        "Children": children_lines(children, clean_text(known_value(details.get("children_summary"))), children_as_of),
        "WSDate": statement_date_text or today,
        "FamilyMatters": _order_matter_lines(
            order_codes(details) if order_codes_override is None else order_codes_override, _heading_children(children, details)
        ),
        "Date": today,
    }


def record_runtime_event(status: str, details: Mapping[str, Any], *, files_read: Sequence[str], files_written: Sequence[str]) -> None:
    try:
        from telemetry_sqlite import record_runtime_event as _record, utc_now_z

        _record(
            {
                "timestamp": utc_now_z(),
                "event_name": "fl401_pack",
                "runtime_label": os.environ.get("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.environ.get("CASEFORGE_MODEL_LABEL", ""),
                "command": "tools.documents.draft_orders.make_fl401_pack_from_row",
                "files_read": list(files_read),
                "files_written": list(files_written),
                "metrics": {
                    "status": status,
                    "matter_id": clean_text(details.get("matter_id")),
                },
            }
        )
    except Exception:
        pass


def upload_file(
    local_path: Path, destination_folder_path: str, filename: str, access_token: str | None = None, *, conflict_behavior: str = "fail"
) -> dict[str, Any]:
    destination = f"{normalise_graph_path(destination_folder_path).rstrip('/')}/{filename}"
    uploaded = graph_files.upload(local_path, destination, access_token=access_token, conflict_behavior=conflict_behavior)
    return {
        "name": filename,
        "destination": destination,
        "webUrl": clean_text(uploaded.get("webUrl")),
        "id": clean_text(uploaded.get("id")),
    }


def address_warnings(matter_id: Any, fill_result: Any, order_data: Mapping[str, Any], has_c8: bool) -> list[str]:
    checks = (fill_result or {}).get("address_checks") if isinstance(fill_result, Mapping) else {}
    checks = checks or {}
    respondent = checks.get("respondent") or ""
    order_state = fill_fl401_pdf.address_state(clean_text(order_data.get("RespondentAddress")))
    lines: list[str] = []
    if "no_postcode" in (respondent, order_state):
        lines.append(f"Matter {matter_id}: respondent address has no postcode: find it.")
    if not has_c8 and checks.get("applicant") == "no_postcode":
        lines.append(f"Matter {matter_id}: applicant address has no postcode: find it.")
    if not has_c8 and checks.get("applicant") == "missing":
        lines.append(f"Matter {matter_id}: applicant address is missing: find it.")
    return lines


def relationship_warnings(matter_id: Any, fill_result: Any) -> list[str]:
    if not isinstance(fill_result, Mapping):
        return []
    return [
        f"Matter {matter_id}: {line}"
        for line in [*(fill_result.get("relationship_gaps") or []), *(fill_result.get("to_confirm") or [])]
    ]


def flag_address_check(matter_id: Any, client_name: str, warnings: Sequence[str]) -> None:
    if not warnings:
        return
    try:
        from vergil import client_edits

        for line in warnings:
            kind = "respondent" if "respondent" in line else "applicant"
            client_edits.flag_field_for_review(
                matter_id=str(matter_id), client_name=client_name, field_name=f"{kind}_address_check",
                field_label=f"{kind.title()} address to check", value_snapshot=line.split(": ", 1)[-1].rstrip("."),
                flagged_by="Court pack", note="A court form needs the address complete with its postcode, or written as Unknown.",
            )
    except Exception as exc:
        print(f"fl401: address check flag skipped: {type(exc).__name__}", file=sys.stderr)


def make_fl401_pack_from_row(
    row: Mapping[str, Any], *, query: str = "", access_token: str | None = None,
    live_matter_folder_override: str = "",
    no_overwrite: bool = True,
    fact_sheet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    matter_id = clean_text(row.get("matter_id"))
    if not matter_id:
        return {"ok": False, "message": "Matched client has no matter_id."}

    details = notice_of_acting.fetch_matter_details(matter_id, row)
    if live_matter_folder_override:
        details["live_matter_folder"] = live_matter_folder_override
    if not has_nmo_matter(details):
        return {"ok": False, "message": "This button is only available for NMO/FL401 matters."}
    parties = load_parties(matter_id)

    matter_path = normalise_graph_path(details.get("live_matter_folder"))
    if not matter_path:
        try:
            from agwu.client_rows import matter_path_for_row

            matter_path = normalise_graph_path(matter_path_for_row(details, query=query))
        except Exception:
            matter_path = ""
    if not matter_path:
        return {"ok": False, "message": "No live matter folder is recorded for this matter."}

    children = direct_children(matter_path, access_token=access_token)
    if not children:
        return {"ok": False, "message": "Could not list the live matter folder."}
    preliminary = choose_folder(children, "preliminary")
    if not preliminary:
        return {"ok": False, "message": "No Preliminary Docs folder found under the matter folder."}

    files = list_candidate_files(matter_path, children, access_token=access_token)
    source_fl401 = choose_source_fl401(files)
    witness = choose_witness_statement(files)

    client_name = clean_text(details.get("client_name") or details.get("matter_name") or query)
    surname = _surname(client_name)
    sql_source_facts = sql_facts(details, parties)

    with tempfile.TemporaryDirectory(prefix="caseforge-chat-fl401-") as tmp:
        tmp_path = Path(tmp)
        source_path = tmp_path / safe_filename(clean_text(source_fl401.get("name"))) if source_fl401 else None
        if source_fl401:
            _download_item(source_fl401, source_path, access_token=access_token)
        source_is_fl403 = is_fl403_source(source_fl401) if source_fl401 else False
        if source_is_fl403 or not source_fl401:
            source_updates: dict[str, str] = {}
        else:
            source_updates, _source_extracted = fill_fl401_pdf.updates_from_docx(source_path)
        sources = [
            {
                "source_kind": "referral",
                "source_label": "SQL intro/referral facts",
                "source_date": clean_text(details.get("source_email_sent_at") or details.get("referral_sent_at")),
                "facts": sql_source_facts,
            },
            *(
                [
                    {
                        "source_kind": "fl403" if source_is_fl403 else "fl401",
                        "source_label": clean_text(source_fl401.get("name")) or "Source FL401",
                        "source_date": clean_text(source_fl401.get("modified_utc") or source_fl401.get("modified")),
                        "facts": fl401_facts_from_updates(source_updates),
                    }
                ]
                if source_fl401
                else []
            ),
        ]
        ws_facts: dict[str, str] = {}
        ws_text = ""
        if witness:
            witness_path = tmp_path / safe_filename(clean_text(witness.get("name")))
            _download_item(witness, witness_path, access_token=access_token)
            ws_text = extract_document_text(witness_path)
            ws_facts = parse_witness_statement_facts(ws_text)
            if ws_facts:
                sources.insert(
                    0,
                    {
                        "source_kind": "witness_statement",
                        "source_label": clean_text(witness.get("name")) or "Witness statement",
                        "source_date": clean_text(witness.get("modified_utc") or witness.get("modified")),
                        "facts": ws_facts,
                    },
                )

        intro_text = ""
        intro_item = next(
            (f for f in files if clean_text(f.get("name")).lower().startswith("intro") and clean_text(f.get("name")).lower().endswith(".pdf")),
            None,
        )
        if intro_item:
            try:
                intro_path = tmp_path / safe_filename(clean_text(intro_item.get("name")))
                _download_item(intro_item, intro_path, access_token=access_token)
                intro_text = extract_document_text(intro_path)
            except Exception:
                intro_text = ""

        cleaner_result = client_info_cleaner.clean_client_info(
            {
                "sources": sources,
                "sql_current": sql_source_facts,
            }
        )
        if any(issue.get("severity") == "blocker" for issue in cleaner_result.get("issues") or []):
            return {
                "ok": False,
                "message": "FL401 pack blocked by client-info cleaner.",
                "issues": cleaner_result.get("issues") or [],
                "cleaner": cleaner_result,
            }

        fallback = cleaner_fallback(cleaner_result, details)
        facts_from_sheet = sheet_values(fact_sheet if fact_sheet is not None else stored_fact_sheet(matter_id))
        sheet_filled = fallback_with_sheet(fallback, facts_from_sheet)
        record_children = load_children(matter_id)
        child_rows = children_for_forms(record_children, facts_from_sheet.get("children") or [], ws_text)
        if child_rows is not record_children:
            try:
                import matter_fact_extraction

                matter_fact_extraction.fill_children_from_statement(clean_text(matter_id), child_rows)
            except Exception:
                pass
        involvement, child_confirm = (
            fill_fl401_pdf.child_involvement(child_rows, clean_text(known_value(details.get("children_summary"))))
            if has_children(details, child_rows)
            else ("no", [])
        )
        matter_updates = fill_fl401_pdf.sql_updates(
            codes=order_codes(details), children=[] if involvement == "no" else child_rows,
            has_children=involvement != "no", has_c8=bool(details.get("has_c8"))
        )
        if ws_facts.get("statement_date"):
            fallback["statement_date"] = ws_facts["statement_date"]
        wedding_date = clean_text(
            details.get("marriage_date") or details.get("wedding_date") or _sheet_date(facts_from_sheet.get("relationship.marriage_date"))
            or ws_facts.get("marriage_date")
        )
        if wedding_date:
            fallback["marriage_date"] = wedding_date
        has_c8 = bool(details.get("has_c8"))
        fl401_filename = safe_filename(soft_form_names.soft_name("FL401", surname, portal_only=_is_portal_court(matter_id)))
        fl401_output = tmp_path / fl401_filename
        fill_result = fill_fl401_pdf.fill_fl401(
            output=fl401_output,
            source=None if source_is_fl403 else source_path,
            fallback=fallback,
            flatten=False,
            fallback_overrides_source=True,
            redact_applicant_contact=has_c8,
            matter_updates=matter_updates,
            statement_text=ws_text,
            matter={**details, "tracker_notes": matter_tracker_notes(matter_id)},
            intro_text=intro_text,
            child_involved=False if involvement == "no" else None,
            child_confirm=child_confirm,
            bail=sheet_bail(facts_from_sheet),
        )
        if isinstance(fill_result, dict) and fill_result.get("redact_applicant_contact") and not has_c8:
            has_c8 = True
            details = {**details, "has_c8": True}

        def put(local: Path, filename: str, kind: str) -> dict[str, Any]:
            folder = clean_text(preliminary.get("path"))
            if not no_overwrite:
                return {**upload_file(local, folder, filename, access_token=access_token, conflict_behavior="replace"), "kind": kind}
            try:
                return {**upload_file(local, folder, filename, access_token=access_token, conflict_behavior="fail"), "kind": kind}
            except urllib.error.HTTPError as exc:
                if exc.code != 409:
                    raise
                return {"name": filename, "kind": kind, "status": "exists"}

        have = next((clean_text(f.get("name")) for f in files if soft_form_names.soft_on_file([clean_text(f.get("name"))], "FL401", surname)), "")
        if no_overwrite and have:
            uploaded_files = [{"name": have, "kind": "FL401", "status": "exists"}]
        else:
            uploaded_files = [put(fl401_output, fl401_filename, "FL401")]
        order_data = order_template_data(fallback, details, child_rows)
        codes = order_codes(details)
        if "NMO" in codes:
            nmo_filename = safe_filename(f"Draft-NMO-{surname}.docx")
            nmo_output = tmp_path / nmo_filename
            order_registry.fill_house_order("NMO", nmo_output, judge_order_data(order_data))
            uploaded_files.append(put(nmo_output, nmo_filename, "Draft NMO"))
        if "OO" in codes:
            oo_filename = safe_filename(f"Draft-OO-{surname}.docx")
            oo_output = tmp_path / oo_filename
            order_registry.fill_house_order("OO", oo_output, judge_order_data(order_data))
            uploaded_files.append(put(oo_output, oo_filename, "Draft OO"))
        if "PSO" in codes:
            pso_filename = safe_filename(f"Draft-PSO-{surname}.docx")
            pso_output = tmp_path / pso_filename
            order_registry.fill_house_order("PSO", pso_output, judge_order_data(order_data, children_required=True))
            uploaded_files.append(put(pso_output, pso_filename, "Draft PSO"))

    kept = [clean_text(f.get("name")) for f in uploaded_files if f.get("status") == "exists"]
    message = f"Created editable FL401 pack for {client_name}."
    if kept:
        message += (
            " NOT replaced, already in the folder (a signature or edits in it are safe): " + ", ".join(kept)
            + ". Delete or rename a file to have it made again."
        )
    warnings = address_warnings(matter_id, fill_result, order_data, has_c8)
    flag_address_check(matter_id, client_name, warnings)
    warnings = warnings + relationship_warnings(matter_id, fill_result)
    unsigned = sot_signature.unsigned_note(fill_result.get("signature")) if isinstance(fill_result, Mapping) else ""
    if unsigned:
        warnings = warnings + [f"Matter {matter_id}: FL401 {unsigned[0].lower()}{unsigned[1:]}"]
    if warnings:
        message += " " + " ".join(w.split(": ", 1)[-1] for w in warnings)
    if has_c8:
        message = (
            "C8: applicant contact details withheld from the FL401/draft order. "
            + message
            + " File the C8 form with the court separately."
        )

    files_read = [clean_text(source_fl401.get("path")) or clean_text(source_fl401.get("name"))] if source_fl401 else []
    if witness:
        files_read.append(clean_text(witness.get("path")) or clean_text(witness.get("name")))
    record_runtime_event(
        "created",
        details,
        files_read=files_read,
        files_written=[clean_text(f.get("webUrl") or f.get("destination")) for f in uploaded_files],
    )

    return {
        "ok": True,
        "message": message,
        "client_name": client_name,
        "matter_id": matter_id,
        "matter_path": matter_path,
        "has_c8": has_c8,
        "source_fl401": clean_text(source_fl401.get("name")),
        "witness_statement": clean_text(witness.get("name")) if witness else "",
        "files": uploaded_files,
        "issues": [*(cleaner_result.get("issues") or []), *({"severity": "warning", "field": "address", "message": w} for w in warnings)],
        "address_warnings": warnings,
        "updates": cleaner_result.get("updates") or [],
        "cleaner_summary": cleaner_result.get("summary") or {},
        "fill_summary": fill_result,
        "matter_vs_soft_copy": fill_result.get("matter_vs_soft_copy", []) if isinstance(fill_result, dict) else [],
        "built_from_record_only": not source_fl401,
        "fact_sheet": {"used": any(facts_from_sheet.values()), "filled": sheet_filled},
    }
