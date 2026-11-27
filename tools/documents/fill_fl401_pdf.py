#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence
from zipfile import ZipFile

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from documents import c8_protection
from documents import sot_signature
from documents.pdf_acroform_fill import field_max_lengths

import firm_profile
import london_time
import matter_orders
from zip_safe import read_member

BLANK_FORM = ROOT / "templates" / "PDF Templates" / "FL401_0223 blank.pdf"

WITNESS_STATEMENT_LINE = "Please see Witness Statement attached."
HOUSE_TEXT = {
    "Why do you think one or more of the reasons you have chosen for question 1.3 may happen?": WITNESS_STATEMENT_LINE,
    "Is there anything else about your situation that you would like the court to know about or consider?": WITNESS_STATEMENT_LINE,
}
SPECIAL_MEASURES = (
    "a separate waiting room in the court building",
    "a separate entrance and exit from the court building",
    "to be shielded by a privacy screen in the courtroom",
    "to join the hearing by video link rather than in person",
)
SPECIAL_MEASURE_FIELDS = tuple(f"8.5 {option}" for option in SPECIAL_MEASURES)


def firm_fields(profile: firm_profile.FirmProfile) -> dict[str, str]:
    values = {
        "2.10 Do you have a legal representative? Yes": "/Yes",
        "2.11 Your legal representative’s name": profile.legal_rep_name,
        "2.12 Name of your legal representative’s firm": profile.legal_rep_firm,
        "2.13 Address of your legal representative’s firm: Building and street": profile.legal_rep_address_building,
        "2.13 Address of your legal representative’s firm: Second line of address": profile.legal_rep_address_line2,
        "2.13 Address of your legal representative’s firm: Town or city": profile.legal_rep_address_town,
        "2.13 Address of your legal representative’s firm: County (optional)": profile.legal_rep_address_county,
        "2.13 Address of your legal representative’s firm: postcode": profile.legal_rep_postcode.replace(" ", ""),
        "2.13 Your legal representative's DX number (if known)": profile.legal_rep_dx,
        "2.14 Your legal representative’s phone number": profile.legal_rep_phone,
        "2.15 Your legal representative’s address email address": profile.legal_rep_email,
        "The applicant believes that the facts stated in this form and any continuation sheets are true. "
        "I am authorised by the applicant to sign this statement": "/Yes",
        "Signed by - Applicant's legal representative": "/Applicant's legal representative",
        "Statement of truth signed by - Full name": profile.statement_of_truth_signer,
        "Statement of truth - Name of applicant’s legal representative’s firm": profile.statement_of_truth_firm,
        "Statement of truth - If signing on behalf of firm or company give position or office held": profile.statement_of_truth_position,
    }
    return {name: value for name, value in values.items() if clean_text(value)}

TEXT_STOPS = {
    "First name(s)",
    "Last name",
    "Day",
    "Month",
    "Year",
    "Building and street",
    "Second line of address",
    "Town or city",
    "County",
    "Postcode",
    "DX number (if known)",
    "Name of court",
    "Case number",
    "Type of case and any other details",
}


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\u200b", "").strip()
    text = re.sub(r"\s+", " ", text)
    if text in {"(optional)", "N/A", "n/a"}:
        return ""
    return text


def norm_key(value: str) -> str:
    text = str(value or "").replace("ï¿½", "").replace("�", "")
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def is_on(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    if text in {"", "/Off", "Off", "False", "false"}:
        return False
    return True


def broken_join(tokens: list[str]) -> str:
    parts: list[str] = []
    for raw in tokens:
        token = clean_text(raw).strip(" ,")
        if not token:
            continue
        if parts and token.isalpha() and (len(token) <= 2 or len(parts[-1]) == 1):
            parts[-1] += token
        else:
            parts.append(token)
    return " ".join(parts).strip()


def split_name(full_name: str) -> tuple[str, str]:
    from documents.form_names import first_and_last

    return first_and_last(clean_text(full_name))


MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")


def two_digit_month(value: str) -> str:
    text = clean_text(value).lower().rstrip(".")
    if text.isdigit():
        return text.zfill(2) if 1 <= int(text) <= 12 else ""
    if len(text) >= 3:
        for number, name in enumerate(MONTH_NAMES, 1):
            if name.startswith(text):
                return f"{number:02d}"
    return ""


def two_digit_day(value: str) -> str:
    text = re.sub(r"(?<=\d)(st|nd|rd|th)$", "", clean_text(value).lower())
    return text.zfill(2) if text.isdigit() and 1 <= int(text) <= 31 else ""


def split_date(value: str) -> tuple[str, str, str]:
    text = clean_text(value)
    bits = re.split(r"[./\-\s,]+", text)
    if len(bits) >= 3:
        day, month, year = bits[0], bits[1], bits[2]
        if len(year) == 2 and year.isdigit():
            year = f"20{year}" if int(year) < 40 else f"19{year}"
        return two_digit_day(day), two_digit_month(month), year
    return "", "", ""


def split_loose_date(value: str) -> tuple[str, str, str]:
    day, month, year = split_date(value)
    if year:
        return day, month, year
    text = clean_text(value)
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if not match:
        return "", "", ""
    named = next((two_digit_month(word) for word in re.findall(r"[A-Za-z]{3,}", text) if two_digit_month(word)), "")
    return "", named, match.group(1)


def full_date(value: str) -> tuple[str, str, str]:
    import datetime as _dt

    text = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", clean_text(value), flags=re.I)
    day, month, year = split_date(text)
    if year and month.isdigit():
        return day, month, year
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            when = _dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
        return f"{when.day:02d}", f"{when.month:02d}", str(when.year)
    return "", "", ""


def wedding_parts(value: str) -> tuple[str, str, str]:
    day, month, year = full_date(value)
    if year:
        return day, month, year
    bare = re.fullmatch(r"\s*((?:19|20)\d{2})\s*", clean_text(value))
    return ("", "", bare.group(1)) if bare else ("", "", "")


def fl401_relationship_gaps(facts: dict[str, Any], filled: dict[str, Any]) -> dict[str, list[str]]:
    gaps: list[str] = []
    to_confirm: list[str] = []
    end_d, end_m, end_y = split_loose_date(clean_text(facts.get("relationship_end")))
    if end_y and not clean_text(filled.get(RELATIONSHIP_END_FIELDS[2])):
        gaps.append(f"The statement says the relationship ended in {end_y} but 4.2 End is blank.")
    wed_text = clean_text(facts.get("marriage_date") or facts.get("wedding_date"))
    wed_d, wed_m, wed_y = wedding_parts(wed_text)
    if not wed_y:
        found = re.search(r"\b((?:19|20)\d{2})\b", wed_text)
        wed_y = found.group(1) if found else ""
    if wed_y and not clean_text(filled.get(f"{WEDDING_PREFIX} YYYY")):
        gaps.append(f"The statement says married in {wed_y} but 4.3 is blank.")
    elif wed_y and not (clean_text(filled.get(f"{WEDDING_PREFIX} DD")) and clean_text(filled.get(f"{WEDDING_PREFIX} MM"))):
        to_confirm.append(f"4.3 holds the year {wed_y} only: the full wedding date is needed.")
    return {"gaps": gaps, "to_confirm": to_confirm}


ADDRESS_LINE_WORDS = re.compile(
    r"\b(house|court|road|street|lane|close|way|avenue|drive|place|gardens|mews|terrace|square|flats?|building|buildings|"
    r"lodge|tower|towers|park|hall|crescent|grove|walk|row|hill|rise|view|apartments?|villas?|cottages?|farm)\b",
    re.IGNORECASE,
)


def without_repeated_parts(parts: list[str]) -> list[str]:
    def key(part: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", part.lower())

    return [part for i, part in enumerate(parts) if not key(part) or key(part) not in {key(later) for later in parts[i + 1 :]}]


_BARE_NUMBER = re.compile(r"\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?")


def _join_number_and_street(parts: list[str]) -> list[str]:
    out = list(parts)
    for index in (0, 1):
        if index + 1 < len(out) and _BARE_NUMBER.fullmatch(out[index]):
            out[index : index + 2] = [f"{out[index]} {out[index + 1]}"]
    return out


def split_address(value: str) -> dict[str, str]:
    text = clean_text(value)
    text = re.sub(r"\bUK\b\.?", "", text, flags=re.IGNORECASE).strip(" ,")
    postcode = ""
    match = re.search(r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})$", text, re.IGNORECASE)
    if match:
        postcode = match.group(1).upper().replace(" ", "")
        text = text[: match.start()].strip(" ,")
    parts = without_repeated_parts([part.strip() for part in text.split(",") if part.strip()])
    parts = _join_number_and_street(parts)
    line2 = ", ".join(parts[1:-1]) if len(parts) > 2 else ""
    town = parts[-1] if len(parts) > 1 else ""
    if len(parts) == 2 and ADDRESS_LINE_WORDS.search(parts[1]):
        line2, town = parts[1], ""
    return {
        "building": parts[0] if parts else text,
        "line2": line2,
        "town": town,
        "postcode": postcode,
    }


def docx_tokens(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        root = ET.fromstring(read_member(archive, "word/document.xml"))
    texts: list[str] = []
    for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
        cleaned = clean_text(node.text)
        if cleaned:
            texts.append(cleaned)
    return texts


def section(tokens: list[str], start: str, end: str | None = None, after: int = 0) -> list[str]:
    start_index = next((i for i, token in enumerate(tokens[after:], start=after) if token == start), -1)
    if start_index < 0:
        return []
    if end is None:
        end_index = len(tokens)
    else:
        end_index = next(
            (i for i, token in enumerate(tokens[start_index + 1 :], start=start_index + 1) if token == end),
            len(tokens),
        )
    return tokens[start_index:end_index]


def after_label(
    tokens: list[str],
    label: str,
    *,
    join_postcode: bool = False,
    collect: bool = False,
    max_tokens: int = 10,
) -> str:
    try:
        idx = tokens.index(label)
    except ValueError:
        return ""
    values: list[str] = []
    for token in tokens[idx + 1 :]:
        cleaned = clean_text(token)
        if (
            re.fullmatch(r"\d+(?:\.\d+)+", cleaned)
            or cleaned in TEXT_STOPS
            or cleaned.startswith("Note ")
            or cleaned.startswith("Go to ")
            or cleaned in {"☐", "☒"}
            or (cleaned in {"X", "x"} and not join_postcode)
        ):
            break
        if cleaned.startswith("(") and cleaned.endswith(")"):
            continue
        if cleaned:
            values.append(cleaned)
        if not collect and values:
            break
        if len(values) >= max_tokens:
            break
    if join_postcode and values:
        return "".join(values).upper().replace(" ", "")
    return broken_join(values) if collect else " ".join(values).strip(" ,")


def checked_option(tokens: list[str], options: list[str]) -> str:
    for i, token in enumerate(tokens[:-1]):
        if token not in {"☒", "X", "x"}:
            continue
        following = " ".join(tokens[i + 1 : i + 7])
        for option in options:
            if following.lower().startswith(option.lower()):
                return option
    return ""


def checked_options(tokens: list[str], options: list[str]) -> set[str]:
    chosen: set[str] = set()
    for i, token in enumerate(tokens[:-1]):
        if token not in {"☒", "X", "x"}:
            continue
        following = " ".join(tokens[i + 1 : i + 8])
        for option in options:
            if following.lower().startswith(option.lower()):
                chosen.add(option)
    return chosen


def date_from_fragments(values: list[str]) -> tuple[str, str, str]:
    import datetime as _dt

    runs = [v for v in values if re.fullmatch(r"\d{1,4}", v)]
    digits = "".join(runs)
    if len(digits) >= 4 and digits[-4:].startswith(("19", "20")):
        year, rest, year_len = digits[-4:], digits[:-4], 4
    elif len(digits) >= 3 and re.fullmatch(r"\d{2}", digits[-2:]) and len(digits) > 4:
        year = (f"20{digits[-2:]}" if int(digits[-2:]) < 40 else f"19{digits[-2:]}")
        rest, year_len = digits[:-2], 2
    else:
        return "", "", ""
    if not rest:
        return "", "", year
    boundaries, running = set(), 0
    for run in runs:
        running += len(run)
        boundaries.add(running)
    if len(rest) <= 2 and not any(0 < b < len(rest) for b in boundaries):
        return ("", rest.zfill(2), year) if 1 <= int(rest) <= 12 else ("", "", "")
    found = []
    for cut in range(1, len(rest)):
        day, month = rest[:cut], rest[cut:]
        if len(day) > 2 or len(month) > 2:
            continue
        try:
            _dt.date(int(year), int(month), int(day))
        except ValueError:
            continue
        found.append((cut, day.zfill(2), month.zfill(2)))
    inner = {b for b in boundaries if 0 < b < len(rest)}
    if inner:
        found = [f for f in found if f[0] in inner]
    if len(found) != 1:
        return "", "", ""
    return found[0][1], found[0][2], year


def loose_date_to_fields(prefix: str, values: list[str]) -> dict[str, str]:
    joined = " ".join(values)
    if not joined:
        return {}
    if all(re.fullmatch(r"\d{1,4}", v) for v in values):
        day, month, year = date_from_fragments(values)
        return {f"{prefix} - {part}": value for part, value in (("DD", day), ("MM", month), ("YYYY", year)) if value}
    match = re.search(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", joined)
    if match:
        day, month, year = match.groups()
        updates = {f"{prefix} - DD": day.zfill(2), f"{prefix} - MM": month.zfill(2)}
        if year:
            updates[f"{prefix} - YYYY"] = f"20{year}" if len(year) == 2 else year
        elif len(values) > 1 and re.fullmatch(r"\d{4}", values[1]):
            updates[f"{prefix} - YYYY"] = values[1]
        return updates
    nums = [v for v in values if re.fullmatch(r"\d{1,4}", v)]
    if len(nums) == 1 and len(nums[0]) == 4:
        return {f"{prefix} - YYYY": nums[0]}
    if len(nums) == 2 and len(nums[1]) == 4:
        return {f"{prefix} - MM": nums[0].zfill(2), f"{prefix} - YYYY": nums[1]}
    if len(nums) >= 3:
        return {
            f"{prefix} - DD": nums[0].zfill(2),
            f"{prefix} - MM": nums[1].zfill(2),
            f"{prefix} - YYYY": nums[2],
        }
    return {}


def date_values_after(sec: list[str], marker: str, stop_markers: set[str]) -> list[str]:
    try:
        idx = sec.index(marker)
    except ValueError:
        return []
    year_idx = next((i for i, token in enumerate(sec[idx + 1 :], start=idx + 1) if token == "Year"), idx)
    values: list[str] = []
    for token in sec[year_idx + 1 :]:
        if token in stop_markers or re.fullmatch(r"\d+\.", token):
            break
        if re.fullmatch(r"\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?", token) or re.fullmatch(r"\d{1,4}", token):
            values.append(token)
    return join_split_year(values)


def join_split_year(values: list[str]) -> list[str]:
    joined: list[str] = []
    for value in values:
        if joined and re.fullmatch(r"\d{1,3}", joined[-1]) and re.fullmatch(r"\d{1,3}", value) and len(joined[-1]) + len(value) == 4 and (joined[-1] + value).startswith(("19", "20")):
            joined[-1] += value
        else:
            joined.append(value)
    return joined


def answer_after_note(sec: list[str], note_start: str, note_end: str, *, skip_after: int = 0) -> str:
    start = next((i for i, token in enumerate(sec) if token.startswith(note_start)), -1)
    if start < 0:
        return ""
    end = next((i for i in range(start, len(sec)) if note_end in sec[i]), -1)
    if end < 0:
        return ""
    bits: list[str] = []
    for token in sec[end + 1 + skip_after :]:
        if re.fullmatch(r"\d\.\d", token) or re.fullmatch(r"\d\.", token):
            break
        if token not in {".", ":"} and not token.startswith("Note "):
            bits.append(token)
    return rejoin_split_words(clean_text(" ".join(bits)).replace(" .", "."))


def rejoin_split_words(text: str) -> str:
    return re.sub(r"(?<![’'])\b([b-hj-z]) (?=[a-z]{3,})", r"\1", text)


WEDDING_PREFIX = (
    "4.3 If you are or were previously married or in a civil partnership with the respondent, "
    "what date was your wedding or civil ceremony?"
)
MARRIED_TICK = "4.1 Married or in a civil partnership"
RELATIONSHIP_END_FIELDS = tuple(
    f"4.2 When did your relationship start and when did it end? End - {part}" for part in ("DD", "MM", "YYYY")
)
CHILD_DATE_RE = r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
CHILD_FIELD_STEMS = (
    "5.2 Child's full name",
    "5.2 Child's date of birth",
    "5.2 Your relationship to the child",
    "Do you and the respondent both have parental responsibility for this child?",
    "Respondent’s relationship to the child",
)


def extract_child_rows(sec52: list[str]) -> dict[str, str]:
    start = -1
    for i, token in enumerate(sec52):
        if token == "Respondent’s" and "relationship" in " ".join(sec52[i : i + 5]):
            start = i + 3
            break
    if start < 0:
        return {}
    row = [clean_text(t) for t in sec52[start:] if clean_text(t)]
    row = [t for t in row if not re.fullmatch(r"5\.\d+", t)]
    dates = [i for i, token in enumerate(row) if re.fullmatch(CHILD_DATE_RE, token)]
    if not dates or dates[0] <= 0:
        return {}
    out: dict[str, str] = {}
    name_start = 0
    for number, date_idx in enumerate(dates[:4], 1):
        name = broken_join(row[name_start:date_idx])
        if not name:
            break
        day, month, year = split_date(row[date_idx].replace(".", "/").replace("-", "/"))
        next_date = dates[number] if number < len(dates) else len(row)
        answers = row[date_idx + 1 : min(date_idx + 4, next_date)]
        answers += [""] * (3 - len(answers))
        relation, responsibility, respondent_relation = answers[:3]
        if "i do" in responsibility.lower() and "respondent does not" in responsibility.lower():
            responsibility = "Applicant only"
        name_start = date_idx + 4
        for stem, value in zip(
            CHILD_FIELD_STEMS,
            (name, "/".join(part for part in (day, month, year) if part), relation, responsibility, respondent_relation),
        ):
            out[f"{stem} {number}"] = value
    return out


def _child_key(name: str) -> str:
    return re.sub(r"[^a-z]+", " ", clean_text(name).lower()).strip()


def _child_dob(value: str) -> str:
    day, month, year = split_date(clean_text(value))
    return f"{day}/{month}/{year}" if year else ""


def _same_child(a_name: str, a_dob: str, b_name: str, b_dob: str) -> bool:
    a_key, b_key = _child_key(a_name), _child_key(b_name)
    a_words, b_words = set(a_key.split()), set(b_key.split())
    if a_dob and b_dob and a_dob == b_dob:
        return not (a_words and b_words) or a_key == b_key or a_words <= b_words or b_words <= a_words
    if a_key and a_key == b_key:
        return True
    if a_dob and b_dob and a_dob != b_dob:
        return False
    return bool(a_words and b_words and (a_words <= b_words or b_words <= a_words))


def _child_rows_from(updates: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for number in range(1, 5):
        row = {stem: clean_text(updates.get(f"{stem} {number}")) for stem in CHILD_FIELD_STEMS}
        if row[CHILD_FIELD_STEMS[0]]:
            rows.append(row)
    return rows


def merge_child_updates(
    matter_updates: dict[str, Any], source_updates: dict[str, Any]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    merged = _child_rows_from(matter_updates)
    differences: list[dict[str, str]] = []
    taken: set[int] = set()
    for soft in _child_rows_from(source_updates):
        name_f, dob_f = CHILD_FIELD_STEMS[0], CHILD_FIELD_STEMS[1]
        soft_dob = _child_dob(soft[dob_f])
        match = next(
            (m for m in merged if id(m) not in taken and _same_child(m[name_f], _child_dob(m[dob_f]), soft[name_f], soft_dob)),
            None,
        )
        if match is not None:
            taken.add(id(match))
        if match is None:
            merged.append(soft)
            continue
        if _child_dob(match[dob_f]) and soft_dob and _child_dob(match[dob_f]) != soft_dob:
            differences.append(
                {"field": f"{name_f} ({match[name_f]})", "matter_record": match[dob_f], "soft_copy": soft[dob_f]}
            )
        for stem in CHILD_FIELD_STEMS:
            if not match[stem] and soft[stem]:
                match[stem] = soft[stem]
    out: dict[str, str] = {}
    for number, row in enumerate(merged[:4], 1):
        for stem in CHILD_FIELD_STEMS:
            if row[stem]:
                out[f"{stem} {number}"] = row[stem]
    return out, differences


def is_child_field(name: str) -> bool:
    return any(norm_key(name).startswith(norm_key(stem)) for stem in CHILD_FIELD_STEMS)


CHILD_ORDER_PREFIX = "6.3 What do you want to stop the respondent from doing to your child or children (if applicable)?"
CHILD_ORDER_OPTIONS = (
    "Being violent towards my children or threatening my children",
    "Harassing or intimidating my children",
    "Posting or publishing anything about my children in print, or digitally",
    "Contacting my children directly without my consent",
    "Going to or near my children’s school or nursery",
)


NMO_BOX = "Non-molestation order – to stop abusive behaviour"
OO_BOX = "Occupation order – to decide who lives in or can return to a property"
CHILDREN_Q = "4.5 Do you have any children, have parental responsibility for any children or need to protect other children with this application?"


_CHILD_WORDS = re.compile(r"\b(son|sons|daughter|daughters|child|children|boy|boys|girl|girls|kids?|baby|toddler|stepson|stepdaughter)\b", re.I)
_ADULT_MARK = re.compile(r"\b(?:over|above)\s+18\b|\b18\s+or\s+(?:over|older)\b|\badults?\b|\bgrown[- ]?up\b|\bover\s+eighteen\b", re.I)
_AGE = re.compile(r"\b(?:aged?|age of)\s+(\d{1,2})\b|\b(\d{1,2})[- ]years?[- ]old\b", re.I)


def _under_18_by_dob(iso: str, today: Any) -> bool | None:
    import datetime as _dt

    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", clean_text(iso))
    if not match:
        return None
    try:
        born = _dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        eighteenth = born.replace(year=born.year + 18)
    except ValueError:
        return None
    return today < eighteenth


def child_involvement(children: Sequence[dict[str, Any]], summary: str = "", today: Any = None) -> tuple[str, list[str]]:
    import datetime as _dt

    today = today or london_time.london_today()
    confirm = ["A child is mentioned with no age or date of birth: confirm the child is under 18 (5.1, 6.3, 4.5, 7.3 are ticked for a child)."]
    states: list[bool | None] = []
    for row in children:
        state = _under_18_by_dob(clean_text(row.get("dob_iso")), today)
        if state is None:
            age = re.fullmatch(r"\s*(\d{1,2})\s*", clean_text(row.get("age") or row.get("child_age")))
            state = int(age.group(1)) < 18 if age else None
        states.append(state)
    if states:
        if any(state is True for state in states):
            return "yes", []
        if any(state is None for state in states):
            return "unconfirmed", confirm
        return "no", []
    text = clean_text(summary)
    if text.lower() in {"", "none", "no", "n/a", "nil"} or not _CHILD_WORDS.search(text):
        return "no", []
    ages = [int(a or b) for a, b in _AGE.findall(text)]
    if any(age < 18 for age in ages):
        return "yes", []
    adults = len(_ADULT_MARK.findall(text)) + sum(1 for age in ages if age >= 18)
    if adults and adults >= len(_CHILD_WORDS.findall(text)):
        return "no", []
    return "unconfirmed", confirm


_APPLICANT_OUT = re.compile(
    r"\bI\s+(?:fled|left\s+the\s+(?:family\s+)?(?:home|house|property|address)|moved\s+out|am\s+(?:now\s+)?(?:staying|living)\s+with|have\s+been\s+(?:staying|living)\s+with)\b", re.I)
_RESPONDENT_OUT = re.compile(
    r"\b(?:he|she|they|the\s+respondent)\s+(?:has\s+|have\s+)?(?:moved\s+out|left\s+the\s+(?:family\s+)?(?:home|house|property|address))\b", re.I)
_BOTH_LIVE = re.compile(r"\b(?:we\s+(?:both\s+|still\s+|currently\s+)*live\s+(?:together|at|in)|we\s+(?:both\s+)?(?:still\s+)?(?:share|cohabit)|living\s+together\s+(?:at|in))\b", re.I)
_RESPONDENT_NEVER = re.compile(r"\b(?:the\s+respondent|he|she)\s+has\s+never\s+lived\b", re.I)
_APPLICANT_NEVER = re.compile(r"\bI\s+(?:have\s+)?never\s+lived\b", re.I)


def home_history(statement: str, ticked_now: set[str]) -> dict[str, bool | None]:
    text = clean_text(statement)
    both = bool(_BOTH_LIVE.search(text))
    out = {
        "applicant_now": True if ("Me" in ticked_now or both) else None,
        "respondent_now": True if ("The respondent" in ticked_now or both) else None,
        "applicant_out": True if _APPLICANT_OUT.search(text) else None,
        "respondent_out": True if _RESPONDENT_OUT.search(text) else None,
        "applicant_never": True if _APPLICANT_NEVER.search(text) else None,
        "respondent_never": True if _RESPONDENT_NEVER.search(text) else None,
    }
    if out["applicant_out"]:
        out["applicant_now"] = None
    if out["respondent_out"]:
        out["respondent_now"] = None
    return out


def section7_answers(statement: str, ticked_now: set[str]) -> tuple[dict[str, str], list[str]]:
    h = home_history(statement, ticked_now)
    a_lived = bool(h["applicant_now"] or h["applicant_out"])
    r_lived = bool(h["respondent_now"] or h["respondent_out"])
    answers: dict[str, str] = {}
    confirm: list[str] = []
    moved = [who for who, key in (("myself", "applicant_out"), ("the respondent", "respondent_out")) if h[key]]
    if len(moved) == 2:
        answers[S7_EVER_LIVED] = "Yes, both of us"
    elif moved:
        answers[S7_EVER_LIVED] = f"Yes, {moved[0]}"
    elif h["applicant_now"] and h["respondent_now"]:
        answers[S7_EVER_LIVED] = "No"
    if a_lived and r_lived:
        answers[S7_INTENDED] = "Yes, both of us"
    elif a_lived and h["respondent_never"]:
        answers[S7_INTENDED] = "Yes, myself"
    elif r_lived and h["applicant_never"]:
        answers[S7_INTENDED] = "Yes, the respondent"
    if S7_EVER_LIVED not in answers or S7_INTENDED not in answers:
        confirm.append("7.4 and 7.5: the statement does not settle who lives, or has lived, at the address: a person completes them.")
    return answers, confirm


def sql_updates(*, codes: set[str], children: list[dict[str, Any]], has_children: bool, has_c8: bool = False) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "NMO" in codes:
        updates[NMO_BOX] = "/Non-molestation order"
        updates["6.1 Are you applying for a non-molestation order? Yes"] = "/Yes"
    elif codes:
        updates["6.1 Are you applying for a non-molestation order? No"] = "/No"
    if "OO" in codes:
        updates[OO_BOX] = "/Occupation order"
        updates["7.1 Are you applying for an occupation order? Yes"] = "/Yes"
    elif codes:
        updates["7.1 Are you applying for an occupation order? No"] = "/No"
    if has_c8:
        updates["2.4 Can your contact details be shared with the respondent? No"] = "/No"
    if has_children:
        updates[f"{CHILDREN_Q} Yes"] = "/Yes"
        updates["5.1 Who is this application for? You and your child/children"] = "/You and your child/children"
        for option in CHILD_ORDER_OPTIONS:
            updates[f"{CHILD_ORDER_PREFIX} {option}"] = f"/{option}"
    from onboarding import intro_children

    children = intro_children.tidy_children([dict(c) for c in children])
    for number, child in enumerate([c for c in children if clean_text(c.get("child_name"))][:4], 1):
        updates[f"5.2 Child's full name {number}"] = clean_text(child.get("child_name"))
        iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", clean_text(child.get("dob_iso")))
        if iso:
            updates[f"5.2 Child's date of birth {number}"] = f"{iso.group(3)}/{iso.group(2)}/{iso.group(1)}"
    return updates


def sql_disagreements(sql: dict[str, Any], source: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for name, value in sql.items():
        word = source.get(name)
        if str(value).startswith("/") or str(word).startswith("/") or not clean_text(word):
            continue
        if re.sub(r"\W+", "", str(word)).lower() != re.sub(r"\W+", "", str(value)).lower():
            out.append({"field": name, "matter_record": clean_text(value), "soft_copy": clean_text(word)})
    return out


def bail_end_from_tokens(sec15: list[str]) -> dict[str, str]:
    start = next((i for i, t in enumerate(sec15) if t == "1.6" or "bail conditions end" in t.lower()), -1)
    if start < 0:
        return {}
    values = date_values_after(sec15[start:], sec15[start], {"1.7"})
    parts = loose_date_to_fields("bail", values)
    day, month, year = (parts.get(f"bail - {p}", "") for p in BAIL_END_FIELDS)
    try:
        import datetime as _dt

        _dt.date(int(year), int(month), int(day))
    except ValueError:
        return {}
    return {f"When do the bail conditions end? {p}": v for p, v in zip(BAIL_END_FIELDS, (day, month, year))}


def updates_from_docx(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    tokens = docx_tokens(path)
    updates: dict[str, Any] = {}
    extracted: dict[str, str] = {}

    sec11 = section(tokens, "1.1", "1.2")
    if checked_option(sec11, ["Non-molestation order"]):
        updates["Non-molestation order – to stop abusive behaviour"] = "/Non-molestation order"
    if checked_option(sec11, ["Occupation order"]):
        updates["Occupation order – to decide who lives in or can return to a property"] = "/Occupation order"

    sec12 = section(tokens, "1.2", "1.3")
    without_notice = checked_option(sec12, ["Yes", "No"])
    if without_notice:
        updates[f"Do you want to apply for the order without giving notice to the respondent? {without_notice}"] = (
            f"/{without_notice}"
        )
    sec13 = section(tokens, "1.3", "1.5")
    for reason in checked_options(sec13, ["a)", "b)", "c)"]):
        updates[f"Why do you want to apply without giving notice to the respondent? {reason}"] = f"/{reason}"
    if "1.4" in sec13:
        text = answer_after_note(sec13, "This could include things", "done in the past")
        if text:
            updates["Why do you think one or more of the reasons you have chosen for question 1.3 may happen?"] = text

    sec15 = section(tokens, "1.5", "1.7")
    bail = checked_option(sec15, ["Yes", "No"])
    if bail:
        updates[
            f"As far as you know, are there any bail conditions stopping the respondent from contacting or coming near you? {bail}"
        ] = f"/{bail}"
    if bail != "No":
        updates.update(bail_end_from_tokens(sec15))
    sec17 = section(tokens, "1.7", "2. Your details")
    answer17 = answer_after_note(sec17, "It is important for", "supporting witness", skip_after=1)
    if answer17:
        updates["Is there anything else about your situation that you would like the court to know about or consider?"] = answer17
    elif "Please see Witness Statement" in " ".join(sec17):
        updates["Is there anything else about your situation that you would like the court to know about or consider?"] = (
            "Please see Witness Statement attached."
        )

    sec21 = section(tokens, "2.1", "2.2")
    if sec21 and "Last name" in sec21:
        last_idx = sec21.index("Last name")
        first = after_label(sec21[: last_idx + 1], "First name(s)", collect=True, max_tokens=4)
        last = after_label(sec21[last_idx - 1 :], "Last name", collect=True, max_tokens=4)
        updates["2.1 First name(s)"] = first
        updates["2.1 Last name"] = last
        extracted["applicant_name"] = f"{first} {last}".strip()

    other_names = clean_text(" ".join(section(tokens, "2.2", "2.3")[2:]))
    if other_names and not other_names.startswith("2.3"):
        updates["2.2 Any other names you have been known by"] = other_names

    sec23 = section(tokens, "2.3", "2.4")
    day, month, year = date_from_fragments(date_values_after(sec23, "2.3", {"2.4"}))
    if year and month and day:
        updates["2.3 Your date of birth - DD"] = day
        updates["2.3 Your date of birth - MM"] = month
        updates["2.3 Your date of birth - YYYY"] = year

    sec24 = section(tokens, "2.4", "2.5")
    share = checked_option(sec24, ["Yes", "No"])
    if share:
        updates[f"2.4 Can your contact details be shared with the respondent? {share}"] = f"/{share}"
        extracted["contact_share"] = share

    sec25 = section(tokens, "2.5", "2.6")
    updates["2.5 Your full current address: building and street"] = after_label(sec25, "Building and street", collect=True)
    updates["2.5 Your full current address: second line of address"] = after_label(sec25, "Second line of address", collect=True)
    updates["2.5 Your full current address: town or city"] = after_label(sec25, "Town or city", collect=True)
    updates["2.5 Your full current address: postcode"] = after_label(sec25, "Postcode", join_postcode=True, collect=True)

    sec26 = section(tokens, "2.6", "2.7")
    updates["2.6 Your phone number"] = after_label(sec26, "Your phone number", collect=True, max_tokens=3)
    sec27 = section(tokens, "2.7", "2.8")
    updates["2.7 Your email address"] = after_label(sec27, "Your email address", collect=True, max_tokens=3)
    sec31 = section(tokens, "3.1", "3.2")
    if sec31 and "Last name" in sec31:
        last_idx = sec31.index("Last name")
        first_candidates = [clean_text(t) for t in sec31[:last_idx] if clean_text(t)]
        first = next(
            (
                t
                for t in reversed(first_candidates)
                if not t.startswith("Note ") and t not in {"3.1", "Their name", "First name(s)", "applicant’."}
            ),
            "",
        )
        last = after_label(sec31[last_idx - 1 :], "Last name", collect=True, max_tokens=4)
        updates["3.1 First name(s)"] = first
        updates["3.1 Last name"] = last
        extracted["respondent_name"] = f"{first} {last}".strip()

    sec33 = section(tokens, "3.3", "3.4")
    day, month, year = date_from_fragments(date_values_after(sec33, "3.3", {"3.4"}))
    if year and month and day:
        updates["3.3 The respondent's date of birth - DD"] = day
        updates["3.3 The respondent's date of birth - MM"] = month
        updates["3.3 The respondent's date of birth - YYYY"] = year

    sec34 = section(tokens, "3.4", "3.5")
    lives = checked_option(sec34, ["Yes", "No"])
    if lives:
        updates[f"3.4 Does the respondent live with you? {lives}"] = f"/{lives}"

    sec35 = section(tokens, "3.5", "3.6")
    updates["3.5 Respondent's full current address: Building and street"] = after_label(
        sec35, "Building and street", collect=True
    )
    updates["3.5 Respondent's full current address: Second line of address"] = after_label(
        sec35, "Second line of address", collect=True
    )
    updates["3.5 Respondent's full current address: Town or city"] = after_label(sec35, "Town or city", collect=True)
    updates["3.5 Respondent's full current address: postcode"] = after_label(
        sec35, "Postcode", join_postcode=True, collect=True
    )
    sec36 = section(tokens, "3.6", "3.7")
    updates["3.6 The respondent's phone number (if you know it)"] = after_label(
        sec36, "Their phone number (if you know it)", collect=True, max_tokens=3
    )
    sec37 = section(tokens, "3.7", "4. Your relationship with the respondent")
    respondent_email = after_label(sec37, "email address", collect=True, max_tokens=3)
    if respondent_email:
        updates["3.7 The respondent's email address (if you know it)"] = respondent_email

    sec41 = section(tokens, "4.1", "4.2")
    relationship_options = [
        "Married or in a civil partnership",
        "Formerly married or in a civil partnership",
        "Engaged or proposed civil partnership",
        "Formerly engaged or proposed civil partnership",
        "Live together as a couple",
        "Formerly lived together as a couple",
        "Boyfriend, girlfriend or partner who does not live with me",
        "Former boyfriend, girlfriend or partner who does not live with me",
        "Former boyfriend, girlfriend or partner who did not live with me",
    ]
    rel = checked_option(sec41, relationship_options)
    if rel:
        pdf_rel = rel.replace("did not", "does not")
        updates[f"4.1 {pdf_rel}"] = "/Yes"
        extracted["relationship"] = pdf_rel

    sec42 = section(tokens, "4.2", "4.3")
    end_marker = next((t for t in sec42 if re.match(r"End\b", t)), "End (if applicable)")
    updates.update(
        loose_date_to_fields(
            "4.2 When did your relationship start and when did it end? Start",
            date_values_after(sec42, "Start", {end_marker}),
        )
    )
    updates.update(
        loose_date_to_fields(
            "4.2 When did your relationship start and when did it end? End",
            date_values_after(sec42, end_marker, {"4.", "4.3"}),
        )
    )
    sec43 = section(tokens, "4.3", "4.4")
    updates.update(
        loose_date_to_fields(
            WEDDING_PREFIX,
            date_values_after(sec43, "Year", {"4.", "4.4"}) if "Year" in sec43 else [],
        )
    )

    sec45 = section(tokens, "4.5", "5.1")
    children = checked_option(sec45, ["Yes", "No"])
    if children:
        updates[
            f"4.5 Do you have any children, have parental responsibility for any children or need to protect other children with this application? {children}"
        ] = f"/{children}"
        extracted["has_children"] = children

    sec51 = section(tokens, "5.1", "5.2")
    who = checked_option(sec51, ["You only", "You and your child/children"])
    if who:
        if who == "You only":
            updates["5.1 Who is this application for? You only"] = "/You only"
            extracted["protect_children"] = "No"
        else:
            updates["5.1 Who is this application for? You and your child/children"] = "/You and your child/children"
            updates[
                "4.5 Do you have any children, have parental responsibility for any children or need to protect other children with this application? Yes"
            ] = "/Yes"
            extracted["protect_children"] = "Yes"
    updates.update(extract_child_rows(section(tokens, "5.2", "5.3")))

    sec53 = section(tokens, "5.3", "5.4")
    proceedings = checked_option(sec53, ["Yes", "No"])
    if proceedings:
        updates[f"5.3 Are there any ongoing family court proceedings involving both of you? {proceedings}"] = (
            f"/{proceedings}"
        )

    sec61 = section(tokens, "6.1", "6.2")
    non_mol = checked_option(sec61, ["Yes", "No"])
    if non_mol:
        updates[f"6.1 Are you applying for a non-molestation order? {non_mol}"] = f"/{non_mol}"
    sec62 = section(tokens, "6.2", "6.3")
    for option in checked_options(
        sec62,
        [
            "Being violent towards me or threatening me",
            "Harassing or intimidating me",
            "Posting or publishing about me either in print or digitally",
            "Contacting me directly",
            "Causing damage to my possessions",
            "Causing damage to my home",
            "Coming into my home",
            "Coming near my home",
            "Coming near my place of work",
        ],
    ):
        updates[f"6.2 What do you want to stop the respondent from doing? {option}"] = f"/{option}"
    if extracted.get("protect_children") == "Yes":
        for option in CHILD_ORDER_OPTIONS:
            updates[f"{CHILD_ORDER_PREFIX} {option}"] = f"/{option}"

    sec71 = section(tokens, "7.1", "8. Going to court")
    occupation = checked_option(sec71, ["Yes", "No"])
    if occupation:
        updates[f"7.1 Are you applying for an occupation order? {occupation}"] = f"/{occupation}"
    if occupation == "Yes":
        updates.update(section7_updates(tokens))

    sec85 = section(tokens, "8.5")
    sec85 = sec85[: next((i for i, t in enumerate(sec85) if re.match(r"9\.?$|9\. |Statement of truth", t)), len(sec85))]
    updates.update(special_measures_from_tokens(sec85))

    return {k: v for k, v in updates.items() if clean_text(v) or is_on(v)}, extracted


SPECIAL_MEASURES_NONE = {"no", "none", "not needed", "no special measures", "none needed"}


def special_measures_from_tokens(sec85: list[str]) -> dict[str, str]:
    marks = {"☒", "X", "x"}
    declined_all = any(
        token in marks and clean_text(tokens_next).strip(" .").lower() in SPECIAL_MEASURES_NONE
        for token, tokens_next in zip(sec85, sec85[1:])
    )
    if declined_all:
        return {name: "/Off" for name in SPECIAL_MEASURE_FIELDS}
    ticked = checked_options(sec85, list(SPECIAL_MEASURES))
    if not ticked:
        return {}
    stated = {f"8.5 {option}": f"/{option}" for option in ticked}
    for i, token in enumerate(sec85[:-1]):
        if token != "☐":
            continue
        following = " ".join(sec85[i + 1 : i + 8]).lower()
        for option in SPECIAL_MEASURES:
            if option not in ticked and following.startswith(option.lower()):
                stated[f"8.5 {option}"] = "/Off"
    return stated


S7_ADDRESS_LABELS = (
    ("Building and street", "Building and street", False),
    ("Second line of address", "Second line of address", False),
    ("Town or city", "Town or city", False),
    ("County", "County (optional)", False),
    ("Postcode", "Postcode", True),
)
S7_EVER_LIVED = "7.4 Have you or the respondent ever lived at the address but don\u2019t live there currently?"
S7_INTENDED = "7.5 If neither you nor the respondent have lived at the address, did you intent to live at the address?"
S7_WHO_OPTIONS = ("Yes, both of us", "Yes, myself", "Yes, the respondent", "No")
S7_YES_NO = (
    ("7.7", "7.8", "7.7 Is the property specially adapted in any way for you, your children or anyone else living there?"),
    ("7.9", "7.10", "7.9 Is there a mortgage on the property?"),
    ("7.13", "7.14", "7.13 Is the property rented?"),
    ("7.16", "7.17", "7.16 Do you have any home rights?"),
)
S7_LIVING = {
    "I want to be able to stay in my home": "7.17 I want to be able to stay in my home",
    "I want to be able to return to my home": "7.17 I want to be able to return to my home",
    "I don\u2019t want the respondent to be able to enter my home": "7.17 I don\u2019t want the respondent to be able to enter my home",
    "I want to keep the respondent away from the area surrounding": "7.17 I want to keep the respondent away from the area surrounding my home",
    "I want to limit where in the home the respondent can go": "7.17 I want to limit where in the home the respondent can go",
}
S7_HOME = {
    "I need the respondent to pay for or contribute to repairs": "7.18 Is there anything else you want to happen with the family home?",
    "I need the respondent to pay for or contribute to the rent": "7.18 I need the respondent to pay for or contribute to the rent or mortgage",
    "I need the use of the furniture": "7.18 I need the use of the furniture or other household contents",
}


def merge_split_numbers(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for token in tokens:
        if out and re.fullmatch(r"\d{1,2}", token) and re.fullmatch(r"7\.\d?", out[-1]):
            joined = out[-1] + token
            if re.fullmatch(r"7\.1\d", joined):
                out[-1] = joined
                continue
        out.append(token)
    return out


def _s7_address(sec: list[str], prefix: str) -> dict[str, str]:
    out = {}
    for label, field_label, postcode in S7_ADDRESS_LABELS:
        value = after_label(sec, label, join_postcode=postcode, collect=True)
        if value:
            out[f"{prefix} {field_label}"] = value
    return out


def _s7_children(sec76: list[str]) -> dict[str, str]:
    try:
        start = next(i for i, t in enumerate(sec76) if t.replace("\u2019", "'").lower() == "child's age") + 1
    except StopIteration:
        return {}
    rows: list[list[str]] = []
    for token in sec76[start:]:
        cleaned = clean_text(token)
        if cleaned.lower().startswith("other children"):
            break
        if re.fullmatch(r"\d{1,2}", cleaned) and rows:
            rows[-1].append(cleaned)
        elif cleaned:
            rows.append([cleaned])
    out = {}
    for number, row in enumerate(rows[:4], 1):
        out[f"7.6 a) Child's name {number}"] = row[0]
        if len(row) > 1:
            out[f"7.6 a) Child's age {number}"] = row[1]
    return out


def section7_updates(tokens: list[str]) -> dict[str, Any]:
    tokens = merge_split_numbers(tokens)
    updates: dict[str, Any] = {}
    updates.update(_s7_address(section(tokens, "7.2", "7.3"), "7.2 To what address do you want the occupation order to apply?"))
    sec73 = section(tokens, "7.3", "7.4")
    for option in checked_options(sec73, ["Me", "The respondent", "My child or children", "Someone else"]):
        updates[f"7.3 Who currently lives at the address? {option}"] = f"/{option}"
    for number, end, name in (("7.4", "7.5", S7_EVER_LIVED), ("7.5", "7.6", S7_INTENDED)):
        chosen = checked_option(section(tokens, number, end), list(S7_WHO_OPTIONS))
        if chosen:
            updates[f"{name} {chosen}"] = f"/{chosen}"
    updates.update(_s7_children(section(tokens, "7.6", "7.7")))
    for number, end, name in S7_YES_NO:
        chosen = checked_option(section(tokens, number, end), ["Yes", "No"])
        if chosen:
            updates[f"{name} {chosen}"] = f"/{chosen}"
    for number, end, label in (("7.10", "7.11", "7.10 Who is named on the mortgage?"), ("7.14", "7.15", "7.14 Who is named on the rental agreement?")):
        for option in checked_options(section(tokens, number, end), ["Me", "The respondent", "Someone else"]):
            updates[f"{label} {option}"] = f"/{option}"
    updates.update(_s7_address(section(tokens, "7.12", "7.13"), "7.12 What is the name and address of the mortgage lender?"))
    updates.update(_s7_address(section(tokens, "7.15", "7.16"), "7.15 What is the name and address of the landlord?"))
    for number, end, options in (("7.17", "7.18", S7_LIVING), ("7.18", "7.19", S7_HOME)):
        for option in checked_options(section(tokens, number, end), list(options)):
            updates[options[option]] = "/On"
    return updates


def single_choice_groups(field_names: Any) -> list[list[str]]:
    names = set(field_names)
    groups = [[f"{q} Yes", f"{q} No"] for q in sorted({n[:-4] for n in names if n.endswith(" Yes")}) if f"{q} No" in names]
    groups.append(["5.1 Who is this application for? You only", "5.1 Who is this application for? You and your child/children"])
    for name in (S7_EVER_LIVED, S7_INTENDED):
        groups.append([f"{name} {option}" for option in S7_WHO_OPTIONS])
    return [[n for n in group if n in names] for group in groups]


def keep_one_answer(final: dict[str, Any], layers: list[set[str]], fields: dict[str, Any]) -> list[str]:
    cleared: list[str] = []
    for group in single_choice_groups(fields):
        on = [n for n in group if is_on(final.get(n))]
        if len(on) < 2:
            continue
        keep = next((n for layer in layers for n in on if n in layer), on[0])
        for name in on:
            if name != keep:
                final[name] = "/Off"
                cleared.append(name)
    return cleared


def pdf_values(path: Path) -> dict[str, Any]:
    reader = PdfReader(path)
    values: dict[str, Any] = {}
    for name, info in (reader.get_fields() or {}).items():
        value = info.get("/V")
        if not is_on(value):
            continue
        if str(value) == "/Off":
            continue
        if clean_text(value):
            values[name] = value
    return values


def fallback_updates(data: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    applicant = clean_text(data.get("name") or data.get("applicant_name"))
    respondent = clean_text(data.get("respondent_name"))
    first, last = split_name(applicant)
    r_first, r_last = split_name(respondent)
    dob_d, dob_m, dob_y = split_date(clean_text(data.get("applicant_dob")))
    rdob_d, rdob_m, rdob_y = split_date(clean_text(data.get("respondent_dob")))
    applicant_address = split_address(clean_text(data.get("applicant_address")))
    respondent_address = split_address(clean_text(data.get("respondent_address")))
    rel_start_d, rel_start_m, rel_start_y = split_loose_date(clean_text(data.get("relationship_start")))
    rel_end_d, rel_end_m, rel_end_y = split_loose_date(clean_text(data.get("relationship_end")))
    wed_d, wed_m, wed_y = wedding_parts(clean_text(data.get("marriage_date") or data.get("wedding_date")))
    updates.update(
        {
            f"{WEDDING_PREFIX} DD": wed_d,
            f"{WEDDING_PREFIX} MM": wed_m,
            f"{WEDDING_PREFIX} YYYY": wed_y,
            "2.1 First name(s)": first,
            "2.1 Last name": last,
            "2.16 Your legal representative’s reference": clean_text(data.get("company_reference") or data.get("legal_rep_reference")),
            "2.3 Your date of birth - DD": dob_d,
            "2.3 Your date of birth - MM": dob_m,
            "2.3 Your date of birth - YYYY": dob_y,
            "2.5 Your full current address: building and street": applicant_address["building"],
            "2.5 Your full current address: second line of address": applicant_address["line2"],
            "2.5 Your full current address: town or city": applicant_address["town"],
            "2.5 Your full current address: postcode": applicant_address["postcode"],
            "2.6 Your phone number": data.get("applicant_phone", ""),
            "2.7 Your email address": data.get("applicant_email", ""),
            "3.1 First name(s)": r_first,
            "3.1 Last name": r_last,
            "3.3 The respondent's date of birth - DD": rdob_d,
            "3.3 The respondent's date of birth - MM": rdob_m,
            "3.3 The respondent's date of birth - YYYY": rdob_y,
            "3.5 Respondent's full current address: Building and street": respondent_address["building"],
            "3.5 Respondent's full current address: Second line of address": respondent_address["line2"],
            "3.5 Respondent's full current address: Town or city": respondent_address["town"],
            "3.5 Respondent's full current address: postcode": respondent_address["postcode"],
            "3.6 The respondent's phone number (if you know it)": data.get("respondent_phone", ""),
            "4.2 When did your relationship start and when did it end? Start - DD": rel_start_d,
            "4.2 When did your relationship start and when did it end? Start - MM": rel_start_m,
            "4.2 When did your relationship start and when did it end? Start - YYYY": rel_start_y,
            "4.2 When did your relationship start and when did it end? End - DD": rel_end_d,
            "4.2 When did your relationship start and when did it end? End - MM": rel_end_m,
            "4.2 When did your relationship start and when did it end? End - YYYY": rel_end_y,
        }
    )
    return {k: v for k, v in updates.items() if clean_text(v)}


def on_value(field_info: dict[str, Any]) -> str:
    for state in field_info.get("/_States_", []):
        state = str(state)
        if state != "/Off":
            return state
    return "/Yes"


def checked_value(fields: dict[str, Any], name: str) -> str:
    return on_value(fields[name])


def default_checked_fields(fallback: dict[str, Any]) -> set[str]:
    fields = {
        "How old are you - 18 years old or older",
        "Do you want to apply for the order without giving notice to the respondent? Yes",
        "Why do you want to apply without giving notice to the respondent? a)",
        "Why do you want to apply without giving notice to the respondent? b)",
        "As far as you know, are there any bail conditions stopping the respondent from contacting or coming near you? No",
        "2.4 Can your contact details be shared with the respondent? Yes",
        "3.4 Does the respondent live with you? No",
        "5.3 Are there any ongoing family court proceedings involving both of you? No",
        "8.1 Do you need an interpreter at court? No",
        "8.3 Do we need to provide something different in court or when we contact you, because of a disability? No",
    }
    codes = set(matter_orders.resolve_row(fallback).codes)
    if "NMO" in codes:
        fields.add("Non-molestation order – to stop abusive behaviour")
        fields.add("6.1 Are you applying for a non-molestation order? Yes")
    elif codes:
        fields.add("6.1 Are you applying for a non-molestation order? No")
    if "OO" in codes:
        fields.add("Occupation order – to decide who lives in or can return to a property")
        fields.add("7.1 Are you applying for an occupation order? Yes")
    elif codes:
        fields.add("7.1 Are you applying for an occupation order? No")
    return fields


def drop_overlong_values(
    updates: dict[str, Any], limits: dict[str, int]
) -> dict[str, dict[str, int]]:
    dropped: dict[str, dict[str, int]] = {}
    for name in list(updates):
        value = updates[name]
        limit = limits.get(name)
        if limit is not None and isinstance(value, str) and len(value) > limit:
            dropped[name] = {"length": len(value), "max_length": limit}
            del updates[name]
    return dropped


def strip_form_widgets(writer: PdfWriter) -> None:
    from pypdf.generic import ArrayObject, NameObject

    for page in writer.pages:
        annots = page.get("/Annots")
        if annots is None:
            continue
        kept = ArrayObject(a for a in annots if a.get_object().get("/Subtype") != "/Widget")
        if kept:
            page[NameObject("/Annots")] = kept
        else:
            del page["/Annots"]
    if "/AcroForm" in writer._root_object:
        del writer._root_object["/AcroForm"]


SIGNATURE_BOX_FIELD = "Statement of truth - signature"


def draw_outline(writer: PdfWriter, page: Any, rect: tuple[float, float, float, float]) -> None:
    from pypdf.generic import ContentStream, FloatObject

    x0, y0, x1, y1 = min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])
    content = ContentStream(page.get_contents(), writer)
    content.operations.extend([
        ([], b"q"),
        ([FloatObject(0.75)], b"w"),
        ([FloatObject(0), FloatObject(0), FloatObject(0)], b"RG"),
        ([FloatObject(x0), FloatObject(y0), FloatObject(x1 - x0), FloatObject(y1 - y0)], b"re"),
        ([], b"S"),
        ([], b"Q"),
    ])
    page.replace_contents(content)


def strip_signature_box(writer: PdfWriter) -> int:
    from pypdf.generic import ArrayObject, NameObject

    def is_box(ref: Any) -> bool:
        obj = ref.get_object()
        parent = obj.get("/Parent")
        name = obj.get("/T") or (parent.get_object().get("/T") if parent else None)
        return obj.get("/Subtype") == "/Widget" and str(name or "") == SIGNATURE_BOX_FIELD

    removed = 0
    for page in writer.pages:
        annots = page.get("/Annots")
        if annots is None:
            continue
        outlines = [tuple(float(x) for x in a.get_object()["/Rect"]) for a in annots if is_box(a) and a.get_object().get("/Rect") is not None]
        kept = ArrayObject(a for a in annots if not is_box(a))
        removed += len(annots) - len(kept)
        page[NameObject("/Annots")] = kept
        for rect in outlines:
            draw_outline(writer, page, rect)
    acro = writer._root_object.get("/AcroForm")
    acro = acro.get_object() if acro is not None else None
    if acro is not None and acro.get("/Fields") is not None:
        acro[NameObject("/Fields")] = ArrayObject(f for f in acro["/Fields"].get_object() if not is_box(f))
    return removed


def use_real_on_states(updates: dict[str, Any], fields: dict[str, Any]) -> None:
    for name, value in list(updates.items()):
        info = fields.get(name)
        if not info or info.get("/FT") != "/Btn" or not isinstance(value, str) or not value.startswith("/"):
            continue
        states = [str(state) for state in info.get("/_States_", [])]
        if states and value not in states:
            updates[name] = on_value(info)


MULTILINE_FONT_SIZES = (12, 11, 10, 9, 8, 7)
AVERAGE_CHAR_WIDTH_EM = 0.52
LINE_HEIGHT_EM = 1.17


def _field_name(annot: Any) -> str:
    parts: list[str] = []
    node = annot
    while node is not None:
        if node.get("/T") is not None:
            parts.append(str(node["/T"]))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return ".".join(reversed(parts))


def fit_multiline_text(reader: PdfReader, updates: dict[str, Any]) -> list[str]:
    import textwrap

    from pypdf.generic import NameObject, TextStringObject

    unfit: list[str] = []
    for page in reader.pages:
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            name = _field_name(annot)
            value = updates.get(name)
            parent = annot["/Parent"].get_object() if annot.get("/Parent") is not None else {}
            field_type = annot.get("/FT") or parent.get("/FT")
            flags = int(annot.get("/Ff") or parent.get("/Ff") or 0)
            if not isinstance(value, str) or field_type != "/Tx" or not flags & (1 << 12):
                continue
            x0, y0, x1, y1 = (float(v) for v in annot["/Rect"])
            width, height = abs(x1 - x0) - 6, abs(y1 - y0) - 4
            chosen = None
            for size in MULTILINE_FONT_SIZES:
                per_line = max(8, int(width / (size * AVERAGE_CHAR_WIDTH_EM)))
                lines = [row for para in value.split("\n") for row in (textwrap.wrap(para, per_line) or [""])]
                if len(lines) * size * LINE_HEIGHT_EM <= height:
                    chosen = (size, lines)
                    break
            if chosen is None:
                size = MULTILINE_FONT_SIZES[-1]
                per_line = max(8, int(width / (size * AVERAGE_CHAR_WIDTH_EM)))
                chosen = (size, [row for para in value.split("\n") for row in (textwrap.wrap(para, per_line) or [""])])
                unfit.append(name)
            size, lines = chosen
            updates[name] = "\n".join(lines)
            da = str(annot.get("/DA") or "/ArialMT 12 Tf 0 g")
            annot[NameObject("/DA")] = TextStringObject(re.sub(r"\d+(?:\.\d+)?(\s+Tf)", rf"{size}\1", da))
    return unfit


def map_updates_to_template(updates: dict[str, Any], fields: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    by_key = {norm_key(name): name for name in fields}
    mapped: dict[str, Any] = {}
    missing: list[str] = []
    for source_name, value in updates.items():
        if not is_on(value) and not clean_text(value):
            continue
        target_name = by_key.get(norm_key(source_name))
        if not target_name:
            missing.append(source_name)
            continue
        mapped[target_name] = value
    return mapped, sorted(set(missing))


C8_APPLICANT_CONTACT_FIELDS = (
    "2.5 Your full current address: building and street",
    "2.5 Your full current address: second line of address",
    "2.5 Your full current address: town or city",
    "2.5 Your full current address: postcode",
    "2.6 Your phone number",
    "2.7 Your email address",
)

BAIL_YES_FIELD = "As far as you know, are there any bail conditions stopping the respondent from contacting or coming near you? Yes"
BAIL_NO_FIELD = "As far as you know, are there any bail conditions stopping the respondent from contacting or coming near you? No"
BAIL_END_FIELDS = ("DD", "MM", "YYYY")
_BAIL_ENTRY_RE = re.compile(r"(?i)\b(bail[a-z/ ]{0,30}?)\s*:\s*([^;\n]{0,200})")
_BAIL_NEGATIVE_RE = re.compile(r"(?i)\W*(?:n/?a|no|none|nil|not\s+(?:known|applicable)|unknown|-)?\W*")
_BAIL_DATE_RE = re.compile(
    r"(?i)\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2,4})\b"
    r"|\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(\d{2,4})\b"
)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _bail_date(value: str) -> tuple[str, str, str] | None:
    import datetime as _dt

    for m in _BAIL_DATE_RE.finditer(value):
        if m.group(1):
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            day, month, year = int(m.group(4)), _MONTHS.index(m.group(5).lower()) + 1, int(m.group(6))
        year += 2000 if year < 100 else 0
        try:
            _dt.date(year, month, day)
        except ValueError:
            continue
        return f"{day:02d}", f"{month:02d}", f"{year:04d}"
    return None


def bail_conditions(*texts: Any) -> tuple[bool, tuple[str, str, str] | None]:
    found = False
    end = None
    for text in texts:
        for m in _BAIL_ENTRY_RE.finditer(str(text or "")):
            label, value = m.group(1).lower(), m.group(2).strip()
            date = _bail_date(value)
            if date:
                return True, date
            if "conditions" in label and not _BAIL_NEGATIVE_RE.fullmatch(value):
                found = True
    return found, end


CONTACT_INSTRUCTIONS_FIELD = "2.9 Contact instructions, including safe call times"
CONTACT_PREFERENCE_FIELDS = ("2.8 How do you prefer to be contacted? Phone", "2.8 How do you prefer to be contacted? Email")

COURT_ONLY_PREFIX = "To be completed by the court"


def is_court_only(field_name: str) -> bool:
    return norm_key(field_name).startswith(norm_key(COURT_ONLY_PREFIX))

C8_APPLICANT_CONTACT_CHECKBOXES = (
    "2.4 Can your contact details be shared with the respondent? Yes",
    "2.8 How do you prefer to be contacted? Phone",
    "2.8 How do you prefer to be contacted? Email",
)


ADDRESS_UNKNOWN = "Unknown"
_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
RESPONDENT_ADDRESS_BOXES = (
    "3.5 Respondent's full current address: Building and street",
    "3.5 Respondent's full current address: Second line of address",
    "3.5 Respondent's full current address: Town or city",
    "3.5 Respondent's full current address: County",
    "3.5 Respondent's full current address: postcode",
)
APPLICANT_ADDRESS_BOXES = (
    "2.5 Your full current address: building and street",
    "2.5 Your full current address: second line of address",
    "2.5 Your full current address: town or city",
    "2.5 Your full current address: county",
    "2.5 Your full current address: postcode",
)


def address_state(text: str) -> str:
    joined = " ".join(clean_text(text).split())
    if not joined or joined.lower() == ADDRESS_UNKNOWN.lower():
        return "unknown"
    return "ok" if _POSTCODE_RE.search(joined) else "no_postcode"


_NO_MORTGAGE = re.compile(
    r"\bno\s+mortg\w*|\bmortgage[\s-]*free\b|\bunencumbered\b|\bowned\s+outright\b"
    r"|\bmortg\w*\s*(?:o/?s|outstanding)?\s*[:=\-]?\s*(?:nil|n/?a|none|0|£\s*0)\b",
    re.IGNORECASE,
)


def _age_on(dob: str, today: Any) -> str:
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", clean_text(dob))
    if not match:
        return ""
    day, month, year = (int(g) for g in match.groups())
    years = today.year - year - ((today.month, today.day) < (month, day))
    return str(years) if 0 <= years < 120 else ""


def owner_section7_rules(final_updates: dict[str, Any], fields: Any, *, intro_text: str | None = None, today: Any = None) -> None:
    by = {norm_key(name): name for name in fields}

    def real(semantic: str) -> str | None:
        return by.get(norm_key(semantic))

    def is_ticked(semantic: str) -> bool:
        name = real(semantic)
        return bool(name) and is_on(final_updates.get(name, ""))

    def tick(semantic: str) -> None:
        name = real(semantic)
        if name:
            final_updates[name] = checked_value(fields, name)

    def untick(semantic: str) -> None:
        name = real(semantic)
        if name:
            final_updates[name] = "/Off"

    if not is_ticked("7.1 Are you applying for an occupation order? Yes"):
        return
    if intro_text and _NO_MORTGAGE.search(clean_text(intro_text)):
        tick("7.9 Is there a mortgage on the property? No")
        untick("7.9 Is there a mortgage on the property? Yes")
        for name in [n for n in final_updates if n.startswith(("7.10", "7.11", "7.12"))]:
            final_updates.pop(name)
    if is_ticked("7.3 Who currently lives at the address? Me"):
        untick("7.17 I want to be able to return to my home")
        tick("7.17 I want to be able to stay in my home")
    tick("7.18 Is there anything else you want to happen with the family home?")
    if is_ticked("7.9 Is there a mortgage on the property? Yes") or is_ticked("7.13 Is the property rented? Yes"):
        tick("7.18 I need the respondent to pay for or contribute to the rent or mortgage")
    today = today or london_time.london_today()
    named = []
    for number in range(1, 5):
        name = clean_text(final_updates.get(real(f"5.2 Child's full name {number}") or "", ""))
        if name:
            named.append((name, clean_text(final_updates.get(real(f"5.2 Child's date of birth {number}") or "", ""))))
    live_there = is_ticked("7.3 Who currently lives at the address? My child or children")
    rows = []
    for number in range(1, 5):
        name_field, age_field = real(f"7.6 a) Child's name {number}"), real(f"7.6 a) Child's age {number}")
        if name_field and age_field:
            rows.append((name_field, age_field))
    if live_there and rows and not any(clean_text(final_updates.get(n, "")) for n, _a in rows):
        for (name_field, _age), (name, _dob) in zip(rows, named):
            final_updates[name_field] = name
    for name_field, age_field in rows:
        name = clean_text(final_updates.get(name_field, ""))
        if not name or clean_text(final_updates.get(age_field, "")):
            continue
        dob = next((d for n, d in named if compact_name(n) == compact_name(name)), "")
        age = _age_on(dob, today)
        if age:
            final_updates[age_field] = age


def compact_name(value: str) -> str:
    return re.sub(r"[^a-z]", "", clean_text(value).lower())


def date_statement_of_truth(final_updates: dict[str, Any], fields: Any, *, today: Any = None) -> None:
    today = today or london_time.london_today()
    values = {"DD": f"{today.day:02d}", "MM": f"{today.month:02d}", "YYYY": str(today.year)}
    names = {part: f"Statement of truth signed date - {part}" for part in values}
    if not all(name in fields for name in names.values()):
        return
    if any(clean_text(final_updates.get(name, "")) for name in names.values()):
        return
    for part, name in names.items():
        final_updates[name] = values[part]


def fill_fl401(
    *,
    template: Path = BLANK_FORM,
    output: Path,
    source: Path | None = None,
    profile: firm_profile.FirmProfile | None = None,
    fallback: dict[str, Any] | None = None,
    flatten: bool = False,
    fallback_overrides_source: bool = False,
    redact_applicant_contact: bool = False,
    matter_updates: dict[str, Any] | None = None,
    c8_text: str | None = None,
    statement_text: str | None = None,
    matter: dict[str, Any] | None = None,
    intro_text: str | None = None,
    child_involved: bool | None = None,
    child_confirm: Sequence[str] = (),
    bail: tuple[bool | None, tuple[str, str, str] | None] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}
    profile = profile or firm_profile.load_profile()
    source_updates: dict[str, Any] = {}
    extracted: dict[str, str] = {}
    if source:
        if source.suffix.lower() == ".docx":
            source_updates, extracted = updates_from_docx(source)
        elif source.suffix.lower() == ".pdf":
            source_updates = pdf_values(source)
            if any(name in source_updates for name in SPECIAL_MEASURE_FIELDS):
                for name in SPECIAL_MEASURE_FIELDS:
                    source_updates.setdefault(name, "/Off")
        else:
            raise ValueError(f"Unsupported FL401 source type: {source}")
    special_measures_stated = {
        name: is_on(value)
        for layer in (source_updates, matter_updates or {})
        for name, value in layer.items()
        if name in SPECIAL_MEASURE_FIELDS
    }

    reader = PdfReader(template)
    fields = reader.get_fields() or {}

    fixed_raw = {**HOUSE_TEXT, **firm_fields(profile)}
    fixed_raw = {name: value for name, value in fixed_raw.items() if name not in SPECIAL_MEASURE_FIELDS}
    fixed_updates, fixed_missing = map_updates_to_template(fixed_raw, fields)
    fixed_field_names = set(fixed_updates)

    fallback_field_values = fallback_updates(fallback)
    merged_source = (
        {**source_updates, **fallback_field_values}
        if fallback_overrides_source
        else {**fallback_field_values, **source_updates}
    )
    matter_updates = dict(matter_updates or {})
    merged_children, child_differences = merge_child_updates(matter_updates, source_updates)
    matter_updates = {k: v for k, v in matter_updates.items() if not is_child_field(k)}
    source_updates = {k: v for k, v in source_updates.items() if not is_child_field(k)}
    matter_updates.update(merged_children)
    disagreements = sql_disagreements(matter_updates, source_updates) + child_differences
    merged_source = {**merged_source, **matter_updates}
    if source:
        fact_updates = {
            key: value
            for key, value in fallback_field_values.items()
            if key in merged_source and clean_text(value)
        }
        merged_source = {
            "Why do you think one or more of the reasons you have chosen for question 1.3 may happen?": (
                "Please see Witness Statement attached."
            ),
            "Is there anything else about your situation that you would like the court to know about or consider?": (
                "Please see Witness Statement attached."
            ),
            **merged_source,
        }
        if fallback_overrides_source:
            merged_source.update(fact_updates)
    applicant_building = clean_text(merged_source.get("2.5 Your full current address: building and street", ""))
    applicant_postcode = clean_text(merged_source.get("2.5 Your full current address: postcode", ""))
    fallback_postcode = clean_text(fallback_field_values.get("2.5 Your full current address: postcode", ""))
    if fallback_postcode and (
        len(applicant_postcode) < 5
        or fallback_postcode in applicant_building.replace(" ", "").upper()
        or "UK" in applicant_building.upper()
    ):
        for field_name in (
            "2.5 Your full current address: building and street",
            "2.5 Your full current address: second line of address",
            "2.5 Your full current address: town or city",
            "2.5 Your full current address: postcode",
        ):
            merged_source[field_name] = fallback_field_values.get(field_name, "")
    source_mapped, source_missing = map_updates_to_template(merged_source, fields)
    for fixed_name in fixed_field_names:
        source_mapped.pop(fixed_name, None)

    checked_updates: dict[str, Any] = {}
    for source_name in (default_checked_fields(fallback) if source else set()):
        mapped, missing = map_updates_to_template({source_name: True}, fields)
        source_missing.extend(missing)
        for target_name in mapped:
            if target_name not in fixed_field_names:
                checked_updates[target_name] = checked_value(fields, target_name)

    final_updates = {**fixed_updates, **source_mapped, **checked_updates}
    end_stated = bool(split_loose_date(clean_text(fallback.get("relationship_end")))[2]) or any(
        clean_text(source_updates.get(name)) for name in RELATIONSHIP_END_FIELDS
    )
    if is_on(final_updates.get(MARRIED_TICK)) and not end_stated:
        for name in RELATIONSHIP_END_FIELDS:
            final_updates.pop(name, None)
    relationship_checks = fl401_relationship_gaps(fallback, final_updates)
    section7_confirm: list[str] = []
    if statement_text and is_on(final_updates.get("7.1 Are you applying for an occupation order? Yes")):
        by_seven = {norm_key(name): name for name in fields}
        ticked_now = {
            option
            for option in ("Me", "The respondent")
            if is_on(final_updates.get(by_seven.get(norm_key(f"7.3 Who currently lives at the address? {option}"), ""), ""))
        }
        answers, section7_confirm = section7_answers(statement_text, ticked_now)
        for question in (S7_EVER_LIVED, S7_INTENDED):
            group = [by_seven.get(norm_key(f"{question} {option}")) for option in S7_WHO_OPTIONS]
            if any(name and is_on(final_updates.get(name)) for name in group):
                continue
            real = by_seven.get(norm_key(f"{question} {answers[question]}")) if question in answers else None
            if real:
                final_updates[real] = checked_value(fields, real)
    if child_involved is False:
        by_name = {norm_key(name): name for name in fields}
        for name in list(final_updates):
            if is_child_field(name):
                final_updates.pop(name)
        for semantic, value in (
            ("5.1 Who is this application for? You and your child/children", None),
            (f"{CHILDREN_Q} Yes", None),
            ("7.3 Who currently lives at the address? My child or children", None),
            *((f"{CHILD_ORDER_PREFIX} {option}", None) for option in CHILD_ORDER_OPTIONS),
        ):
            real = by_name.get(norm_key(semantic))
            if real:
                final_updates[real] = "/Off"
        real = by_name.get(norm_key(f"{CHILDREN_Q} No"))
        if real:
            final_updates[real] = checked_value(fields, real)
        for name, info in fields.items():
            if name.startswith("5."):
                final_updates[name] = "/Off" if (info or {}).get("/FT") == "/Btn" else ""
    if bail is not None and bail[0] is not None:
        bail_yes, bail_end = bool(bail[0]), bail[1]
    else:
        bail_yes, bail_end = bail_conditions(intro_text, (matter or {}).get("tracker_notes"), (matter or {}).get("intake_notes"))
    if bail_yes and BAIL_YES_FIELD in fields and BAIL_NO_FIELD in fields:
        final_updates[BAIL_YES_FIELD] = checked_value(fields, BAIL_YES_FIELD)
        final_updates[BAIL_NO_FIELD] = "/Off"
        for part, value in zip(BAIL_END_FIELDS, bail_end or ("", "", "")):
            name = f"When do the bail conditions end? {part}"
            if value and name in fields:
                final_updates[name] = value
    elif bail is not None and bail[0] is False and BAIL_NO_FIELD in fields and BAIL_YES_FIELD in fields:
        final_updates[BAIL_NO_FIELD] = checked_value(fields, BAIL_NO_FIELD)
        final_updates[BAIL_YES_FIELD] = "/Off"
        for part in BAIL_END_FIELDS:
            final_updates.pop(f"When do the bail conditions end? {part}", None)
    elif BAIL_NO_FIELD in fields and BAIL_YES_FIELD in fields:
        said_yes = final_updates.get(BAIL_YES_FIELD) not in (None, "", "/Off")
        if not said_yes:
            final_updates[BAIL_NO_FIELD] = checked_value(fields, BAIL_NO_FIELD)
            final_updates[BAIL_YES_FIELD] = "/Off"
    for name in CONTACT_PREFERENCE_FIELDS:
        if name in fields:
            final_updates[name] = "/Off"
    if CONTACT_INSTRUCTIONS_FIELD in fields:
        final_updates[CONTACT_INSTRUCTIONS_FIELD] = ""
    special_measures: list[str] = []
    special_measures_declined: list[str] = []
    for name in SPECIAL_MEASURE_FIELDS:
        if name not in fields:
            continue
        if special_measures_stated.get(name, True):
            final_updates[name] = checked_value(fields, name)
            special_measures.append(name)
        else:
            final_updates[name] = "/Off"
            special_measures_declined.append(name)
    special_measures.sort()
    special_measures_declined.sort()
    court_only_cleared = sorted(name for name in final_updates if is_court_only(name))
    for name in court_only_cleared:
        del final_updates[name]
    matter_mapped, _ = map_updates_to_template(matter_updates, fields)
    soft_mapped, _ = map_updates_to_template(source_updates, fields)
    keep_one_answer(final_updates, [set(matter_mapped), set(soft_mapped), set(source_mapped)], fields)

    c8 = c8_protection.detect(
        c8_text=c8_text,
        matter={**(matter or {}), **({"has_c8": True} if redact_applicant_contact else {})},
        fl401={**source_updates, **merged_source},
        statement=statement_text,
        intro=intro_text,
    )
    redacted_fields: list[str] = []
    c8_redacted: list[str] = []
    if c8["c8"]:
        by_key = {norm_key(name): name for name in fields}

        def target(semantic: str) -> str | None:
            return by_key.get(norm_key(semantic))

        given = {name: clean_text(final_updates.get(target(name) or "", "")) for name in C8_APPLICANT_CONTACT_FIELDS}
        own = {
            "address": ", ".join(v for k, v in given.items() if k.startswith("2.5") and v),
            "phone": given.get("2.6 Your phone number", ""),
            "email": given.get("2.7 Your email address", ""),
        }
        protected = c8_protection.protected_values(own, fallback, matter, c8_text=c8_text)
        for semantic_name in (*C8_APPLICANT_CONTACT_FIELDS, *C8_APPLICANT_CONTACT_CHECKBOXES):
            target_name = target(semantic_name)
            if target_name and target_name in final_updates:
                final_updates.pop(target_name, None)
                redacted_fields.append(target_name)
        no_box = target("2.4 Can your contact details be shared with the respondent? No")
        if no_box:
            final_updates[no_box] = checked_value(fields, no_box)
        c8_redacted = c8_protection.protect(final_updates, protected, max_lengths=field_max_lengths(reader))["redacted"]

    keys = {norm_key(name): name for name in fields}

    def box_text(names: Sequence[str]) -> str:
        return " ".join(clean_text(final_updates.get(keys.get(norm_key(n)) or "", "")) for n in names if keys.get(norm_key(n)))

    address_checks = {"respondent": address_state(box_text(RESPONDENT_ADDRESS_BOXES)), "applicant": "withheld"}
    if address_checks["respondent"] == "unknown":
        building = keys.get(norm_key(RESPONDENT_ADDRESS_BOXES[0]))
        if building:
            final_updates[building] = ADDRESS_UNKNOWN
    if not c8["c8"]:
        applicant_state = address_state(box_text(APPLICANT_ADDRESS_BOXES))
        address_checks["applicant"] = "missing" if applicant_state == "unknown" else applicant_state

    overlong_fields = drop_overlong_values(final_updates, field_max_lengths(reader))
    if overlong_fields:
        print(
            "fill_fl401: left blank, value longer than the field allows: "
            + ", ".join(
                f"{name} ({info['length']} > {info['max_length']})"
                for name, info in sorted(overlong_fields.items())
            ),
            file=sys.stderr,
        )

    owner_section7_rules(final_updates, fields, intro_text=intro_text)
    date_statement_of_truth(final_updates, fields)
    use_real_on_states(final_updates, reader.get_fields() or {})
    overflow = fit_multiline_text(reader, final_updates)
    if overflow:
        print("fill_fl401: text does not fit its box even at the smallest size: " + ", ".join(overflow), file=sys.stderr)
    writer = PdfWriter()
    writer.append(reader)
    writer.update_page_form_field_values(None, final_updates, auto_regenerate=False, flatten=flatten)
    if flatten:
        strip_form_widgets(writer)
    else:
        strip_signature_box(writer)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)
    signature = sot_signature.sign_file(output, "fl401")

    return {
        "signature": signature,
        "court_only_cleared": court_only_cleared,
        "overlong_fields": overlong_fields,
        "matter_vs_soft_copy": disagreements,
        "text_overflow": overflow,
        "template": str(template),
        "firm_profile": profile.source,
        "special_measures": special_measures,
        "special_measures_declined": special_measures_declined,
        "source": str(source) if source else "",
        "output": str(output),
        "fixed_fields": len(fixed_updates),
        "source_fields": len(source_mapped),
        "checked_fields": len(checked_updates),
        "total_fields": len(final_updates),
        "missing_fields": sorted(set(fixed_missing + source_missing)),
        "extracted": extracted,
        "flattened": flatten,
        "fallback_overrides_source": fallback_overrides_source,
        "redact_applicant_contact": bool(c8["c8"]),
        "c8": c8,
        "redacted_fields": sorted(redacted_fields),
        "c8_redacted": c8_redacted,
        "address_checks": address_checks,
        "relationship_gaps": relationship_checks["gaps"],
        "to_confirm": relationship_checks["to_confirm"] + list(child_confirm) + section7_confirm,
        "child_involved": child_involved,
    }


def load_fallback(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill an FL401 PDF AcroForm using pypdf.")
    parser.add_argument("--source", type=Path, help="referrer soft-copy FL401 (.docx or .pdf)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=BLANK_FORM, help="Form to fill (default: the blank official FL401 02/23)")
    parser.add_argument("--profile", type=Path, help="Firm profile YAML (default: firm_profile.load_profile())")
    parser.add_argument("--fallback-json", type=Path, help="Optional fallback facts JSON")
    parser.add_argument("--flatten", action="store_true", help="Flatten the form (off by default: the form stays editable and is printed to PDF by hand)")
    parser.add_argument("--prefer-fallback", action="store_true", help="Let fallback facts override source FL401 values")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = fill_fl401(
        template=args.template,
        output=args.output,
        source=args.source,
        profile=firm_profile.load_profile(args.profile),
        fallback=load_fallback(args.fallback_json),
        flatten=args.flatten,
        fallback_overrides_source=args.prefer_fallback,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
