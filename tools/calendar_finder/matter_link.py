
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

ORDER_CODES = ("NMO", "OO", "PSO", "CAO", "SIO")
_CACHE_SECONDS = 300.0
_match_cache: dict[str, tuple[float, tuple[int | None, str]]] = {}
_order_cache: dict[int, tuple[float, str]] = {}


def clear_caches() -> None:
    _match_cache.clear()
    _order_cache.clear()


def _default_resolver(query: str, *, caller: str):
    from agwu import resolve_client

    return resolve_client(query, caller=caller)


def _reference_confirms(matter_id: int, case_ref: str) -> bool | None:
    try:
        import clientdb_sql

        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ref_value, ref_value_normalised FROM matter_references WHERE matter_id = ?",
                (int(matter_id),),
            )
            rows = cursor.fetchall()
    except Exception:
        return None
    wanted = re.sub(r"[^A-Z0-9]", "", case_ref.upper())
    for row in rows:
        for value in row:
            if wanted and re.sub(r"[^A-Z0-9]", "", str(value or "").upper()) == wanted:
                return True
    return False


def resolve_matter(
    case_ref: str,
    *,
    resolver: Callable[..., Any] | None = None,
    caller: str = "calendar_finder.resolve_matter",
) -> tuple[int | None, str]:
    key = re.sub(r"[^A-Z0-9]", "", str(case_ref or "").upper())
    if not key:
        return None, "no_case_number"
    now = time.monotonic()
    cached = _match_cache.get(key)
    if cached and resolver is None and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    result = (resolver or _default_resolver)(key, caller=caller)
    top = getattr(result, "top", None)
    outcome: tuple[int | None, str]
    if getattr(result, "status", "") != "resolved" or top is None:
        outcome = (None, "ambiguous" if getattr(result, "status", "") == "ambiguous" else "not_found")
    elif "exact_search" not in list(getattr(top, "match_sources", []) or []):
        outcome = (None, "not_exact")
    else:
        try:
            matter_id = int((top.row or {}).get("matter_id"))
        except (TypeError, ValueError):
            matter_id = 0
        if not matter_id:
            outcome = (None, "no_matter_id")
        elif _reference_confirms(matter_id, key) is False:
            outcome = (None, "reference_mismatch")
        else:
            outcome = (matter_id, "exact_search")
    if resolver is None:
        _match_cache[key] = (now, outcome)
    return outcome


def resolve_matter_by_text(
    text: str,
    *,
    case_ref: str = "",
    resolver: Callable[..., Any] | None = None,
    caller: str = "calendar_finder.resolve_matter_by_text",
) -> tuple[int | None, str]:
    query = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(query) < 4:
        return None, "no_text"
    result = (resolver or _default_resolver)(query, caller=caller)
    top = getattr(result, "top", None)
    if getattr(result, "status", "") == "resolved" and top is not None and "exact_search" in list(getattr(top, "match_sources", []) or []):
        try:
            matter_id = int((top.row or {}).get("matter_id"))
        except (TypeError, ValueError):
            return None, "no_matter_id"
        if not matter_id:
            return None, "no_matter_id"
        if case_ref:
            confirmed = _reference_confirms(matter_id, re.sub(r"[^A-Z0-9]", "", case_ref.upper()))
            if confirmed is not True:
                return None, "reference_mismatch" if confirmed is False else "reference_unconfirmed"
        return matter_id, "exact_search"
    return None, "ambiguous" if getattr(result, "status", "") == "ambiguous" else "not_exact"


def _name_tokens(name: str) -> set[str]:
    return {token for token in re.split(r"[^a-z]+", str(name or "").lower()) if len(token) > 1}


def _matter_party_names(matter_id: int) -> list[str] | None:
    try:
        import clientdb_sql

        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT display_name FROM matter_parties WHERE matter_id = ?", (int(matter_id),))
            names = [str(row[0] or "") for row in cursor.fetchall()]
            try:
                cursor.execute("SELECT canonical_name FROM matters WHERE matter_id = ?", (int(matter_id),))
                row = cursor.fetchone()
                names.append(str(row[0] or "") if row else "")
            except Exception:
                pass
            return names
    except Exception:
        return None


def sql_parties(
    matter_id: int,
    *,
    reader: Callable[[int], list[tuple[str, str]] | None] | None = None,
) -> tuple[str, str]:
    rows: list[tuple[str, str]] | None
    if reader is not None:
        rows = reader(int(matter_id))
    else:
        try:
            import clientdb_sql

            with clientdb_sql.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT role, display_name FROM matter_parties WHERE matter_id = ?", (int(matter_id),))
                rows = [(str(r[0] or ""), str(r[1] or "")) for r in cursor.fetchall()]
        except Exception:
            rows = None
    applicant = respondent = ""
    for role, name in rows or []:
        kind, name = str(role or "").strip().lower(), str(name or "").strip()
        if not name:
            continue
        if kind == "respondent" and not respondent:
            respondent = name
        elif kind in ("client", "applicant") and not applicant:
            applicant = name
    return applicant, respondent


def resolve_matter_by_parties(
    applicant: str,
    respondent: str,
    *,
    resolver: Callable[..., Any] | None = None,
    parties_reader: Callable[[int], list[str] | None] | None = None,
) -> tuple[int | None, str]:
    if not (str(applicant or "").strip() and str(respondent or "").strip()):
        return None, "no_parties"
    matter_id, reason = resolve_matter_by_text(applicant, resolver=resolver, caller="calendar_finder.resolve_matter_by_parties")
    if matter_id is None:
        return None, reason
    names = (parties_reader or _matter_party_names)(matter_id)
    if names is None:
        return None, "parties_unreadable"
    tokens = [_name_tokens(name) for name in names]
    if all(any(_name_tokens(who) and _name_tokens(who) <= party for party in tokens) for who in (applicant, respondent)):
        return matter_id, "exact_search+parties"
    return None, "parties_mismatch"


def matter_order_types(matter_id: int, *, reader: Callable[[int], list[str]] | None = None) -> str:
    now = time.monotonic()
    cached = _order_cache.get(int(matter_id))
    if cached and reader is None and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    raw: list[str] = []
    try:
        if reader is not None:
            raw = list(reader(int(matter_id)))
        else:
            import matter_orders

            raw = list(matter_orders.resolve_matter_orders(int(matter_id)).codes)
    except Exception:
        raw = []
    found = {code for piece in raw for code in re.split(r"[^A-Za-z]+", piece.upper()) if code in ORDER_CODES}
    value = "/".join(code for code in ORDER_CODES if code in found)
    if reader is None:
        _order_cache[int(matter_id)] = (now, value)
    return value
