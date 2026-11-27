#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

WITHHELD = "Withheld - see C8"
WITHHELD_WORDS_RE = re.compile(r"(?i)\b(?:withheld|confidential|protected|see\s+c8|form\s+c8|c8\s+form|c8|w/h)\b")
_ADDRESS_WITHHELD_RE = re.compile(
    r"(?i)(?:address|lives?\s+at|living\s+at|residing\s+at|resides\s+at)[^.\n]{0,60}?\b(?:withheld|confidential|see\s+c8|c8)\b"
    r"|\b(?:withheld|confidential)\b[^.\n]{0,20}\baddress\b"
)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+\s?44\s?(?:\(0\)\s?)?|\b0)(?:[\s-]?\d){9,10}\b")
MATTER_FLAGS = ("has_c8", "c8_flag", "c8_address", "c8_phone", "c8_email")
MATTER_CONTACT_KEYS = {
    "address": ("client_address", "applicant_address", "address_text", "address"),
    "phone": ("applicant_phone", "phone_primary", "phone"),
    "email": ("applicant_email", "email_primary", "email"),
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "c8", "withheld", "confidential", "protected"}


_WH_PREFIX_RE = re.compile(r"^\s*W\s*/?\s*H(?:OLD)?\b[\s,:-]*", re.IGNORECASE)
_FURTHER_INFO_RE = re.compile(r"FURTHER INFO\s*:?\s*(.{0,80}?)\s+(?:APPROPRIATE ADULT|NAME\b)", re.IGNORECASE)
_FURTHER_INFO_C8_RE = re.compile(r"\bW/?H\s+ADDRESS\b|\bC8\b", re.IGNORECASE)


def strip_wh_prefix(address: str | None) -> str:
    return _WH_PREFIX_RE.sub("", str(address or "")).strip()


def intro_shows_withheld(text: str | None, address: str | None = "") -> bool:
    if _WH_PREFIX_RE.match(str(address or "")):
        return True
    info = _FURTHER_INFO_RE.search(re.sub(r"\s+", " ", str(text or "")))
    return bool(info and _FURTHER_INFO_C8_RE.search(info.group(1)))


def statement_shows_withheld(text: str | None) -> bool:
    return bool(_ADDRESS_WITHHELD_RE.search(str(text or "")))


def fl401_shows_c8(fl401: Mapping[str, Any] | str | None) -> bool:
    if not fl401:
        return False
    if isinstance(fl401, str):
        return statement_shows_withheld(fl401) or bool(re.search(r"(?i)\b2\.[567]\b[^\n]{0,80}\b(?:withheld|see\s+c8)\b", fl401))
    for name, value in fl401.items():
        key = str(name).lower()
        on = value not in (None, "", False, "/Off", "Off")
        if key.startswith("2.4") and key.rstrip().endswith("no") and on:
            return True
        if key.startswith(("2.5", "2.6", "2.7")) and isinstance(value, str) and WITHHELD_WORDS_RE.search(value):
            return True
    return False


def detect(
    *,
    c8_text: str | None = None,
    matter: Mapping[str, Any] | None = None,
    fl401: Mapping[str, Any] | str | None = None,
    statement: str | None = None,
    intro: str | None = None,
) -> dict[str, Any]:
    matter = matter or {}
    routes: list[str] = []
    if str(c8_text or "").strip():
        routes.append("c8_document")
    if any(_truthy(matter.get(flag)) for flag in MATTER_FLAGS) or str(matter.get("withheld_fields") or "").strip():
        routes.append("matter_c8_flag")
    if fl401_shows_c8(fl401):
        routes.append("fl401")
    if statement_shows_withheld(statement):
        routes.append("statement")
    if intro_shows_withheld(intro, matter.get("client_address") or matter.get("address_text") or ""):
        routes.append("intro")
    return {"c8": bool(routes), "route": routes[0] if routes else None, "routes": routes}


def _digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return "0" + digits[2:] if digits.startswith("44") else digits


def protected_values(*sources: Any, c8_text: str | None = None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"address": set(), "postcode": set(), "phone": set(), "email": set()}

    def add_address(text: str) -> None:
        whole = " ".join(text.replace("\n", ", ").split())
        if len(whole) >= 6 and re.search(r"\d", whole):
            out["address"].add(whole.lower())
        for match in POSTCODE_RE.finditer(text):
            out["postcode"].add(re.sub(r"\s+", "", match.group(0).upper()))
        for part in re.split(r"[,\n]", POSTCODE_RE.sub("", text)):
            part = " ".join(part.split())
            if len(part) >= 6 and re.search(r"\d", part):
                out["address"].add(part.lower())

    for source in sources:
        if not source:
            continue
        if isinstance(source, str):
            add_address(source)
            continue
        if not isinstance(source, Mapping):
            continue
        for kind, keys in MATTER_CONTACT_KEYS.items():
            for key in keys:
                value = str(source.get(key) or "").strip()
                if not value or WITHHELD_WORDS_RE.fullmatch(value):
                    continue
                if kind == "address":
                    add_address(value)
                elif kind == "phone":
                    if len(_digits(value)) >= 10:
                        out["phone"].add(_digits(value))
                else:
                    out["email"].add(value.lower())
    text = str(c8_text or "")
    for match in POSTCODE_RE.finditer(text):
        out["postcode"].add(re.sub(r"\s+", "", match.group(0).upper()))
    out["email"] |= {m.group(0).lower() for m in EMAIL_RE.finditer(text)}
    out["phone"] |= {_digits(m.group(0)) for m in PHONE_RE.finditer(text)}
    return out


def redact_text(value: str, protected: Mapping[str, set[str]]) -> str:
    text = value
    for line in sorted(protected.get("address", ()), key=len, reverse=True):
        words = [word for word in re.split(r"[\s,]+", line) if word]
        if words:
            text = re.sub(r"[\s,]+".join(re.escape(word) for word in words), WITHHELD, text, flags=re.I)
    for email in protected.get("email", ()):
        text = re.sub(re.escape(email), WITHHELD, text, flags=re.I)
    phones = protected.get("phone", set())
    if phones:
        text = PHONE_RE.sub(lambda m: WITHHELD if _digits(m.group(0)) in phones else m.group(0), text)
    postcodes = protected.get("postcode", set())
    if postcodes:
        text = POSTCODE_RE.sub(lambda m: WITHHELD if re.sub(r"\s+", "", m.group(0).upper()) in postcodes else m.group(0), text)
    return text


def protect(
    values: dict[str, Any],
    protected: Mapping[str, set[str]],
    *,
    contact_fields: Iterable[str] = (),
    max_lengths: Mapping[str, int] | None = None,
) -> dict[str, list[str]]:
    withheld = sorted(name for name in contact_fields if values.pop(name, None) not in (None, "", False))
    redacted: list[str] = []
    for name, value in list(values.items()):
        if not isinstance(value, str) or not value.strip():
            continue
        new = redact_text(value, protected)
        if new == value:
            continue
        limit = (max_lengths or {}).get(name)
        if limit and len(new) > limit:
            values.pop(name)
            withheld.append(name)
        else:
            values[name] = new
            redacted.append(name)
    return {"withheld": sorted(withheld), "redacted": sorted(redacted)}
