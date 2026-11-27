#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

NINO_RE = re.compile(r"^[A-Za-z]{2}\d{6}[A-Za-z]$")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_WHOLE_STRING_RE = re.compile(r"^[^@\s;<>]+@[^@\s;<>]+\.[^@\s;<>]+$")

UK_PHONE_RE = re.compile(r"(?:(?:\+|00)\d[\d\s-]{8,}\d|\b0\d{9,}\b)")

UK_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)

CASEFORGE_COMPANY_REF_RE = re.compile(r"^\d{6}/\d{2}FL$", re.IGNORECASE)

UNKNOWN_PLACEHOLDER_RE = re.compile(r"\[\s*unknown\b[^\]]*\]", re.IGNORECASE)
_DOB_PLACEHOLDER_RE = re.compile(r"\(\s*DOB\s*\[\s*unknown\b[^\]]*\]\s*\)", re.IGNORECASE)

_SHAPES: list[tuple[str, re.Pattern]] = [
    ("nino", NINO_RE),
    ("email", EMAIL_WHOLE_STRING_RE),
    ("uk_postcode", UK_POSTCODE_RE),
    ("caseforge_company_reference", CASEFORGE_COMPANY_REF_RE),
    ("uk_phone", UK_PHONE_RE),
]


def looks_like_nino(value: str) -> bool:
    return bool(NINO_RE.match((value or "").strip()))


def looks_like_email(value: str, *, whole_string: bool = True) -> bool:
    cleaned = (value or "").strip()
    pattern = EMAIL_WHOLE_STRING_RE if whole_string else EMAIL_RE
    return bool(pattern.search(cleaned)) if not whole_string else bool(pattern.match(cleaned))


def looks_like_uk_phone(value: str) -> bool:
    return bool(UK_PHONE_RE.search((value or "").strip()))


def looks_like_uk_postcode(value: str) -> bool:
    return bool(UK_POSTCODE_RE.search((value or "").strip()))


def looks_like_val_company_reference(value: str) -> bool:
    return bool(CASEFORGE_COMPANY_REF_RE.match((value or "").strip()))


def has_unknown_placeholder(value: object) -> bool:
    return bool(UNKNOWN_PLACEHOLDER_RE.search(str(value or "")))


def known_value(value: object) -> str:
    text = str(value or "")
    if not UNKNOWN_PLACEHOLDER_RE.search(text):
        return text.strip()
    text = _DOB_PLACEHOLDER_RE.sub(" ", text)
    text = UNKNOWN_PLACEHOLDER_RE.sub(" ", text)
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text).strip(" \t\r\n,;:-")
    return text if re.search(r"[A-Za-z0-9]", text) else ""


def is_unknown_placeholder(value: object) -> bool:
    return has_unknown_placeholder(value) and not known_value(value)


def classify(value: str) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    for name, pattern in _SHAPES:
        if pattern.match(cleaned) or (name in ("email", "uk_phone", "uk_postcode") and pattern.search(cleaned)):
            return name
    return None


def reject_if_wrong_shape(value: str, expected: str) -> bool:
    checkers = {
        "nino": looks_like_nino,
        "email": looks_like_email,
        "uk_phone": looks_like_uk_phone,
        "uk_postcode": looks_like_uk_postcode,
        "caseforge_company_reference": looks_like_val_company_reference,
    }
    checker = checkers.get(expected)
    if checker is None:
        return False
    if not checker(value):
        return True
    actual_shape = classify(value)
    return actual_shape is not None and actual_shape != expected



UK_POSTCODE_AREAS = frozenset("""
    AB AL B BA BB BD BF BH BL BN BR BS BT BX CA CB CF CH CM CO CR CT CV CW DA DD DE DG DH
    DL DN DT DY E EC EH EN EX FK FY G GL GU GY HA HD HG HP HR HS HU HX IG IM IP IV JE KA
    KT KW KY L LA LD LE LL LN LS LU M ME MK ML N NE NG NN NP NR NW OL OX PA PE PH PL PO
    PR RG RH RM S SA SE SG SK SL SM SN SO SP SR SS ST SW SY TA TD TF TN TQ TR TS TW UB W
    WA WC WD WF WN WR WS WV XX YO ZE
""".split())

_POSTCODE_STRICT_RE = re.compile(r"^([A-Z]{1,2})(\d[A-Z\d]?)(\d[ABD-HJLNP-UW-Z]{2})$")
_POSTCODE_CANDIDATE_RE = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{2,4})\s*([0-9OI][A-Z]{2})(?![A-Z0-9])", re.IGNORECASE)
_SLIPS = {"O": "0", "0": "O", "I": "1", "1": "I"}

POSTCODE_OK = "ok"
POSTCODE_REPAIRED = "repaired"
POSTCODE_INVALID = "invalid"
POSTCODE_EMPTY = "empty"


@dataclass(frozen=True)
class PostcodeCheck:

    given: str
    postcode: str
    status: str
    reason: str = ""


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _real(compact: str) -> bool:
    match = _POSTCODE_STRICT_RE.match(compact)
    return bool(match) and match.group(1) in UK_POSTCODE_AREAS


def format_postcode(value: str) -> str:
    compact = _compact(value)
    return f"{compact[:-3]} {compact[-3:]}" if len(compact) > 3 else compact


def check_uk_postcode(value: str) -> PostcodeCheck:
    given = str(value or "").strip()
    compact = _compact(given)
    if not compact:
        return PostcodeCheck(given, "", POSTCODE_EMPTY)
    if not 5 <= len(compact) <= 7:
        return PostcodeCheck(given, "", POSTCODE_INVALID, f"'{given}' is not the length of a UK postcode.")
    if _real(compact):
        return PostcodeCheck(given, format_postcode(compact), POSTCODE_OK)
    slip_positions = [i for i, ch in enumerate(compact) if ch in _SLIPS]
    readings: set[str] = set()
    for mask in range(1, 1 << len(slip_positions)):
        chars = list(compact)
        for bit, pos in enumerate(slip_positions):
            if mask >> bit & 1:
                chars[pos] = _SLIPS[chars[pos]]
        candidate = "".join(chars)
        if _real(candidate):
            readings.add(format_postcode(candidate))
    if len(readings) == 1:
        fixed = readings.pop()
        return PostcodeCheck(given, fixed, POSTCODE_REPAIRED, f"'{given}' was read as {fixed} (a letter O or I typed as a digit 0 or 1, or the other way round).")
    if readings:
        return PostcodeCheck(given, "", POSTCODE_INVALID, f"'{given}' could be read as more than one postcode ({', '.join(sorted(readings))}).")
    return PostcodeCheck(given, "", POSTCODE_INVALID, f"'{given}' is not a UK postcode.")


def postcodes_in_text(text: str) -> list[PostcodeCheck]:
    found: list[PostcodeCheck] = []
    for match in _POSTCODE_CANDIDATE_RE.finditer(str(text or "")):
        check = check_uk_postcode(match.group(1) + match.group(2))
        if check.postcode and all(f.postcode != check.postcode for f in found):
            found.append(check)
    return found


def _fold(value: str) -> str:
    return _compact(value).replace("O", "0").replace("I", "1")


def postcode_in_text(value: str, text: str) -> bool:
    needle = _fold(value)
    return len(needle) >= 5 and needle in _fold(text)


def reconcile_postcode(record: str, proposed: str, *, proposed_from: str = "the address") -> dict:
    rec, prop = check_uk_postcode(record), check_uk_postcode(proposed)
    flags: list[str] = []
    for check, label in ((rec, "The client record's postcode"), (prop, f"The postcode in {proposed_from}")):
        if check.status in (POSTCODE_REPAIRED, POSTCODE_INVALID):
            flags.append(f"{label}: {check.reason}")
    if rec.status == POSTCODE_EMPTY and prop.status == POSTCODE_EMPTY:
        return {"postcode": "", "status": "none", "flags": flags}
    if rec.postcode and prop.postcode and rec.postcode != prop.postcode:
        flags.append(f"The client record says {rec.postcode} but {proposed_from} says {prop.postcode}: the record's is used until a person decides.")
        return {"postcode": rec.postcode, "status": "mismatch", "flags": flags}
    if rec.status == POSTCODE_INVALID and prop.postcode:
        flags.append(f"{proposed_from[:1].upper()}{proposed_from[1:]} says {prop.postcode}: it is not used while the record's postcode is wrong.")
        return {"postcode": "", "status": "mismatch", "flags": flags}
    chosen = rec if rec.postcode else prop
    if not chosen.postcode:
        return {"postcode": "", "status": "invalid", "flags": flags}
    repaired = POSTCODE_REPAIRED in (rec.status, prop.status)
    return {"postcode": chosen.postcode, "status": "repaired" if repaired else "ok", "flags": flags}


_DOB_ORDINAL_RE = re.compile(r"(?<=\d)(?:st|nd|rd|th)\b", re.IGNORECASE)
_DOB_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %m %Y", "%d%m%Y", "%Y-%m-%d", "%Y/%m/%d",
    "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%d%m%y",
    "%d %B %y", "%d %b %y",
)
_DOB_MONTH_SEPARATOR_RE = re.compile(r"(?<=\d)[/.\-](?=[A-Za-z])|(?<=[A-Za-z])[/.\-](?=\d)")
MAX_AGE_YEARS = 120


def parse_dob(value: object, *, today: dt.date | None = None) -> str:
    text = _DOB_ORDINAL_RE.sub("", str(value or "")).replace(",", " ")
    text = " ".join(_DOB_MONTH_SEPARATOR_RE.sub(" ", text).split())
    if not text or (text.isdigit() and len(text) not in (6, 8)):
        return ""
    from london_time import london_today

    today = today or london_today()
    for fmt in _DOB_FORMATS:
        try:
            parsed = dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if "%y" in fmt and parsed > today:
            parsed = parsed.replace(year=parsed.year - 100)
        if parsed > today or parsed.year < today.year - MAX_AGE_YEARS:
            continue
        return parsed.isoformat()
    return ""


FEMALE_WORDS = frozenset({"female", "f", "woman", "mrs", "ms", "miss"})
MALE_WORDS = frozenset({"male", "m", "man", "mr"})
SEX_VALUES = ("Male", "Female", "Other")
SEX_OTHER_MAX = 60


def sex_word(raw: object) -> str:
    word = re.sub(r"[^a-z]", "", str(raw or "").lower())
    return "female" if word in FEMALE_WORDS else "male" if word in MALE_WORDS else ""


def normalise_sex(raw: object) -> tuple[str, str]:
    text = " ".join(str(raw if raw is not None else "").split())
    if not text:
        return "", ""
    found = sex_word(text)
    if found:
        return found.capitalize(), ""
    return "Other", text[:SEX_OTHER_MAX]


SEX_TITLES = frozenset({"mr", "mrs", "ms", "miss", "mx"})


def sex_from_details(sex: object = None, title: object = None) -> tuple[str, str]:
    got = normalise_sex(sex)
    if got[0]:
        return got
    word = re.sub(r"[^a-z]", "", str(title or "").lower())
    return normalise_sex(word.capitalize()) if word in SEX_TITLES else ("", "")


def clean_sex_pair(sex: object, sex_other: object = "") -> tuple[str, str]:
    value = " ".join(str(sex or "").split()).capitalize()
    if value and value not in SEX_VALUES:
        raise ValueError("sex must be blank, Male, Female or Other")
    other = " ".join(str(sex_other or "").split())
    if len(other) > SEX_OTHER_MAX:
        raise ValueError(f"sex (other) is at most {SEX_OTHER_MAX} characters")
    return value, (other if value == "Other" else "")


def stored_sex_word(sex: object) -> str:
    value = str(sex or "").strip().lower()
    return value if value in ("male", "female") else ""
