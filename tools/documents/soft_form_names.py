
from __future__ import annotations

import re

FORMS = ("FL401", "C100", "C1A")
_FORM_RE = "|".join(FORMS)

_SOFT_PATTERNS = (
    re.compile(rf"(?P<form>{_FORM_RE})\.draft\.(?P<surname>.+)\.(?:pdf|docx)", re.I),
    re.compile(rf"(?P<form>{_FORM_RE})\.portal-only\.(?P<surname>.+)\.(?:pdf|docx)", re.I),
    re.compile(rf"draft-(?P<form>{_FORM_RE})-(?P<surname>.+)\.(?:pdf|docx)", re.I),
    re.compile(rf"draft\.(?P<form>{_FORM_RE})\.(?P<surname>.+)\.(?:pdf|docx)", re.I),
    re.compile(rf"(?P<form>{_FORM_RE})-draft-(?P<surname>.+)\.(?:pdf|docx)", re.I),
)
_PORTAL_PATTERN = re.compile(rf"(?:{_FORM_RE})\.portal-only\..+\.(?:pdf|docx)", re.I)


def soft_name(form: str, surname: str, *, portal_only: bool = False) -> str:
    return f"{form.upper()}.{'portal-only' if portal_only else 'draft'}.{surname}.pdf"


def parse_soft_name(filename: str) -> tuple[str, str] | None:
    name = str(filename or "").strip().rsplit("/", 1)[-1]
    for pattern in _SOFT_PATTERNS:
        match = pattern.fullmatch(name)
        if match:
            return match.group("form").upper(), match.group("surname")
    return None


def is_soft_copy(filename: str) -> bool:
    return parse_soft_name(filename) is not None


_NEVER_AN_APPLICATION = re.compile(
    rf"(?:{_FORM_RE})\.(?:draft|portal-only)\..+|draft\.(?:{_FORM_RE})\..+", re.I
)


def is_never_an_application(filename: str) -> bool:
    return bool(_NEVER_AN_APPLICATION.fullmatch(str(filename or "").strip().rsplit("/", 1)[-1]))


def is_portal_only(filename: str) -> bool:
    return bool(_PORTAL_PATTERN.fullmatch(str(filename or "").strip().rsplit("/", 1)[-1]))


def soft_name_aliases(form: str, surname: str) -> tuple[str, ...]:
    form, low = form.upper(), surname.lower()
    f = form.lower()
    return (
        f"{f}.draft.{low}.pdf",
        f"{f}.portal-only.{low}.pdf",
        f"draft-{f}-{low}.pdf",
        f"draft.{f}.{low}.pdf",
        f"{f}-draft-{low}.pdf",
    )


def soft_on_file(names, form: str, surname: str) -> bool:
    have = {str(n).lower() for n in names}
    return any(alias in have for alias in soft_name_aliases(form, surname))
