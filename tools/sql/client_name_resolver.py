#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from fuzzyfinder import fuzzyfinder
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

import sys

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from telemetry_sqlite import record_client_search_event

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASE_REF_PATTERNS = [
    re.compile(r"\b[A-Z]{2}\d{2}[A-Z]\d{5}\b"),
    re.compile(r"\b[A-Z]{2}\d{2}P\d{5}\b"),
    re.compile(r"\b[A-Z]{2}\d{7}\b"),
    re.compile(r"\b\d{6}/\d{2}[A-Z]{2}\b"),
]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PARENS_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
_C8_BRACKETED = r"[(\[]\s*c8\s*[)\]]"
_C8_BARE = r"(?<!\w)c8(?!\w)"
_C8_TAG_RE = re.compile(
    rf"^\s*(?:{_C8_BRACKETED}\s*[-\u2013\u2014]?|{_C8_BARE}\s*[-\u2013\u2014])\s*"
    rf"|\s*(?:[-\u2013\u2014]\s*)?{_C8_BRACKETED}\s*$"
    rf"|\s*[-\u2013\u2014]\s*{_C8_BARE}\s*$"
    rf"|\s*(?:[-\u2013\u2014]\s*)?{_C8_BRACKETED}(?=\s*[-\u2013\u2014]\s)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AliasRow:
    alias: str
    canonical: str
    source: str
    note: str = ""
    root_card: str = ""


@dataclass
class CandidateRecord:
    canonical_name: str
    root_card_path: Path
    aliases: Dict[str, Set[str]] = field(default_factory=dict)
    query_forms: Dict[str, object] = field(default_factory=dict)
    identity_values: Dict[str, Set[str]] = field(default_factory=dict)
    is_live_bias_candidate: bool = False
    verified_name_middle: str = ""
    live_matter_folder: str = ""

    def add_alias(self, alias: str, source: str) -> None:
        alias = clean_text(alias)
        if not alias:
            return
        self.aliases.setdefault(alias, set()).add(source)


@dataclass
class RankedCandidate:
    canonical_name: str
    root_card: str
    score: int
    confidence_hint: str
    match_sources: List[str]
    live_bias: str
    auto_resolve_safe: bool
    support_signals: List[str]
    live_matter_folder: str = ""


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def normalise_name(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[-_/]", " ", text)
    text = re.sub(r"[^\w\s()]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_c8_tag(value: str) -> str:
    text = clean_text(value)
    while True:
        updated = _C8_TAG_RE.sub("", text, count=1).strip()
        if updated == text or not updated:
            return text if not updated else updated
        text = updated


def strip_matter_suffixes(value: str) -> str:
    text = strip_c8_tag(value)
    while True:
        updated = PARENS_SUFFIX_RE.sub("", text).strip()
        if updated == text:
            return updated
        text = updated


def tokenise_name(value: str) -> List[str]:
    return [token for token in normalise_name(value).split() if token]


def sorted_token_key(value: str) -> str:
    return " ".join(sorted(tokenise_name(strip_matter_suffixes(value))))


def compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalise_name(strip_matter_suffixes(value)))


def row_key(value: str) -> str:
    return normalise_name(value)


def repo_rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def split_csvish(value: str) -> List[str]:
    return [clean_text(part) for part in re.split(r"[;,]", value or "") if clean_text(part)]


def split_known_aliases(value: str) -> List[str]:
    return [clean_text(part) for part in (value or "").split(",") if clean_text(part)]


def normalise_phone_variants(value: str) -> Set[str]:
    digits = re.sub(r"\D+", "", value or "")
    variants: Set[str] = set()
    if not digits:
        return variants
    variants.add(digits)
    if digits.startswith("44") and len(digits) >= 11:
        variants.add("0" + digits[2:])
    if digits.startswith("0") and len(digits) >= 10:
        variants.add("44" + digits[1:])
    return variants


def normalise_email(value: str) -> str:
    return clean_text(value).lower()


def normalise_case_ref(value: str) -> str:
    return re.sub(r"\s+", "", clean_text(value).upper())


def extract_case_ref_variants(value: str) -> Set[str]:
    refs: Set[str] = set()
    for part in split_csvish(value):
        part_key = normalise_case_ref(part)
        if part_key:
            refs.add(part_key)
        for pattern in CASE_REF_PATTERNS:
            refs.update(normalise_case_ref(match.group(0)) for match in pattern.finditer(part.upper()))
    return refs


def normalise_dob(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        try:
            return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1))).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def parse_markdown_table(lines: Sequence[str]) -> Dict[str, str]:
    if len(lines) < 3:
        return {}
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines if line.strip().startswith("|")]
    if len(rows) < 3 or len(rows[0]) < 2:
        return {}
    if row_key(rows[0][0]) != "field" or row_key(rows[0][1]) != "value":
        return {}
    return {
        clean_text(row[0]): clean_text(row[1])
        for row in rows[2:]
        if len(row) >= 2 and clean_text(row[0])
    }


def parse_quick_lookup(text: str) -> Dict[str, str]:
    lines = text.splitlines()
    in_section = False
    table_lines: List[str] = []
    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("## Quick Lookup"):
            in_section = True
            continue
        if not in_section:
            continue
        if table_lines and (stripped.startswith("## ") or stripped == "---"):
            break
        if stripped.startswith("|"):
            table_lines.append(stripped)
    return parse_markdown_table(table_lines)


def parse_table_lines(lines: Sequence[str], minimum_cells: int) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [clean_text(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) >= minimum_cells:
            rows.append(cells)
    return rows


def parse_alias_rows(path: Path) -> List[AliasRow]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    rows: List[AliasRow] = []

    start_marker = "<!-- MANUAL-ALIASES-START -->"
    end_marker = "<!-- MANUAL-ALIASES-END -->"
    if start_marker in text and end_marker in text:
        block = text.split(start_marker, 1)[1].split(end_marker, 1)[0]
        manual_lines = [line for line in block.splitlines() if line.strip().startswith("|")]
        for cells in parse_table_lines(manual_lines[2:], 4):
            rows.append(AliasRow(alias=cells[0], canonical=cells[1], source="manual", note=cells[2]))

    generated_start = None
    for index, line in enumerate(lines):
        if line.strip() == "## Generated Lookup Entries":
            generated_start = index + 1
            break
    if generated_start is not None:
        generated_lines: List[str] = []
        for line in lines[generated_start:]:
            if generated_lines and not line.strip().startswith("|"):
                break
            if line.strip().startswith("|"):
                generated_lines.append(line)
        for cells in parse_table_lines(generated_lines[2:], 4):
            rows.append(
                AliasRow(
                    alias=cells[0],
                    canonical=cells[1],
                    source=f"generated:{cells[2]}",
                    root_card=cells[3],
                )
            )
    return rows


_PERSON_COLUMNS = """
                    p.person_id,
                    p.canonical_name AS person_name,
                    p.name_first,
                    p.name_middle,
                    p.name_last,
                    p.dob_iso,
                    p.phone_primary,
                    p.phone_digits,
                    p.email_primary,
                    m.matter_id,
                    m.canonical_name AS matter_name,
                    m.company_reference,
                    m.live_matter_folder,
                    m.repo_client_folder"""

_CANDIDATE_QUERIES = (
    f"""
                SELECT DISTINCT {{top}} {_PERSON_COLUMNS}
                FROM people p
                LEFT JOIN matters m ON m.primary_person_id = p.person_id
                ORDER BY p.canonical_name, m.canonical_name
    """,
    f"""
                SELECT DISTINCT {{top}} {_PERSON_COLUMNS},
                    pa.alias_text
                FROM people p
                LEFT JOIN matters m ON m.primary_person_id = p.person_id
                JOIN person_aliases pa ON pa.person_id = p.person_id
                ORDER BY p.canonical_name, m.canonical_name
    """,
    f"""
                SELECT DISTINCT {{top}} {_PERSON_COLUMNS},
                    mr.ref_value,
                    mr.ref_value_normalised
                FROM people p
                JOIN matters m ON m.primary_person_id = p.person_id
                JOIN matter_references mr ON mr.matter_id = m.matter_id
                ORDER BY p.canonical_name, m.canonical_name
    """,
    f"""
                SELECT DISTINCT {{top}} {_PERSON_COLUMNS},
                    mp.display_name AS party_name,
                    mp.email_primary AS party_email,
                    mp.phone_digits AS party_phone_digits,
                    mp.dob_iso AS party_dob
                FROM people p
                JOIN matters m ON m.primary_person_id = p.person_id
                JOIN matter_parties mp ON mp.matter_id = m.matter_id
                ORDER BY p.canonical_name, m.canonical_name
    """,
)


def load_sql_candidate_rows(limit: int | None = None) -> List[dict]:
    try:
        import sys
        tools_dir = str(REPO_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from clientdb_sql import get_connection

        top = f"TOP ({max(1, min(int(limit), 10000))})" if limit else ""
        rows: List[dict] = []
        with get_connection() as conn:
            for template in _CANDIDATE_QUERIES:
                cursor = conn.cursor()
                cursor.execute(template.replace("{top}", top))
                cols = [col[0] for col in cursor.description]
                rows.extend(dict(zip(cols, row)) for row in cursor.fetchall())
        return rows
    except Exception:
        return []


def _add_identity(candidate: CandidateRecord, kind: str, value: str) -> None:
    cleaned = clean_text(str(value or ""))
    if not cleaned:
        return
    values = candidate.identity_values.setdefault(kind, set())
    if kind == "email":
        normalised = normalise_email(cleaned)
        if normalised:
            values.add(normalised)
    elif kind == "phone":
        values.update(normalise_phone_variants(cleaned))
    elif kind == "dob":
        normalised = normalise_dob(cleaned)
        if normalised:
            values.add(normalised)
    elif kind == "case_ref":
        values.update(extract_case_ref_variants(cleaned))


_CANDIDATE_CACHE: Dict[str, object] = {"built_at": 0.0, "candidates": None, "alias_conflicts": None}
CANDIDATE_CACHE_TTL_SECONDS = 30


def build_candidates(*, use_cache: bool = True) -> Tuple[Dict[str, CandidateRecord], Dict[str, Set[str]]]:
    if use_cache:
        cached = _CANDIDATE_CACHE
        if cached["candidates"] is not None and (time.time() - float(cached["built_at"])) < CANDIDATE_CACHE_TTL_SECONDS:
            return cached["candidates"], cached["alias_conflicts"]

    candidates: Dict[str, CandidateRecord] = {}
    alias_conflicts: Dict[str, Set[str]] = {}

    for row in load_sql_candidate_rows():
        canonical = clean_text(str(row.get("matter_name") or row.get("person_name") or ""))
        person_name = clean_text(str(row.get("person_name") or ""))
        if not canonical:
            continue
        candidate = candidates.get(row_key(canonical))
        if candidate is None:
            root = clean_text(str(row.get("repo_client_folder") or ""))
            root_path = REPO_ROOT / root if root else REPO_ROOT
            candidate = CandidateRecord(canonical_name=canonical, root_card_path=root_path)
            candidate.add_alias(canonical, "canonical")
            candidates[row_key(canonical)] = candidate
        candidate.is_live_bias_candidate = True
        if not candidate.verified_name_middle:
            middle = clean_text(str(row.get("name_middle") or ""))
            if middle:
                candidate.verified_name_middle = middle
        if not candidate.live_matter_folder:
            folder = clean_text(str(row.get("live_matter_folder") or ""))
            if folder:
                candidate.live_matter_folder = folder
        for alias, source in (
            (person_name, "sql:person"),
            (clean_text(str(row.get("alias_text") or "")), "sql:person_alias"),
            (clean_text(str(row.get("party_name") or "")), "sql:party"),
            (clean_text(str(row.get("live_matter_folder") or "")), "sql:live_folder"),
        ):
            if alias:
                candidate.add_alias(alias, source)
                alias_conflicts.setdefault(row_key(alias), set()).add(candidate.canonical_name)
        for kind, field in (
            ("email", "email_primary"),
            ("email", "party_email"),
            ("phone", "phone_primary"),
            ("phone", "phone_digits"),
            ("phone", "party_phone_digits"),
            ("dob", "dob_iso"),
            ("dob", "party_dob"),
            ("case_ref", "company_reference"),
            ("case_ref", "ref_value"),
            ("case_ref", "ref_value_normalised"),
        ):
            _add_identity(candidate, kind, str(row.get(field) or ""))

    for candidate in candidates.values():
        candidate.query_forms = build_query_forms(candidate.canonical_name)
        for alias in list(candidate.aliases):
            alias_conflicts.setdefault(row_key(alias), set()).add(candidate.canonical_name)

    if use_cache:
        _CANDIDATE_CACHE["candidates"] = candidates
        _CANDIDATE_CACHE["alias_conflicts"] = alias_conflicts
        _CANDIDATE_CACHE["built_at"] = time.time()

    return candidates, alias_conflicts


def build_query_forms(value: str) -> Dict[str, object]:
    stripped = strip_matter_suffixes(value)
    tokens = tokenise_name(stripped)
    first = tokens[0] if tokens else ""
    last = tokens[-1] if tokens else ""
    return {
        "raw": clean_text(value),
        "normalised": normalise_name(value),
        "normalised_stripped": normalise_name(stripped),
        "compact": compact_key(value),
        "sorted_tokens": sorted_token_key(value),
        "tokens": tokens,
        "first": first,
        "last": last,
    }


def looks_like_email(query: str) -> bool:
    return bool(EMAIL_RE.match(clean_text(query)))


def looks_like_phone(query: str) -> bool:
    digits = re.sub(r"\D+", "", query or "")
    return 10 <= len(digits) <= 15


def looks_like_dob(query: str) -> bool:
    return bool(normalise_dob(query))


def looks_like_case_ref(query: str) -> bool:
    query_upper = clean_text(query).upper()
    return any(pattern.search(query_upper) for pattern in CASE_REF_PATTERNS)


def classify_query_kind(query: str) -> str:
    if looks_like_email(query):
        return "email"
    if looks_like_case_ref(query):
        return "case_ref"
    if looks_like_dob(query):
        return "dob"
    if looks_like_phone(query):
        return "phone"
    return "name"


def full_string_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return fuzz.ratio(left, right) / 100.0


def similarity_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return Levenshtein.normalized_similarity(left, right)


def surname_matches_within_one_edit(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < 5 or abs(len(left) - len(right)) > 1:
        return False
    return Levenshtein.distance(left, right, score_cutoff=1) <= 1


def add_signal(score_parts: List[int], match_sources: List[str], support_signals: List[str], source: str, points: int, support: Optional[str] = None) -> None:
    if points <= 0:
        return
    score_parts.append(points)
    match_sources.append(source)
    support_signals.append(support or source)


def best_confidence_hint(match_sources: Sequence[str]) -> str:
    for prefix in (
        "identity:",
        "manual_alias_exact",
        "canonical_exact",
        "normalised_exact",
        "generated_alias_exact",
        "sorted_token_exact",
        "token:",
    ):
        for source in match_sources:
            if source.startswith(prefix):
                return source
    return match_sources[0] if match_sources else "no-match"


def score_identity(query_kind: str, query: str, candidate: CandidateRecord, score_parts: List[int], match_sources: List[str], support_signals: List[str]) -> None:
    if query_kind == "email":
        email = normalise_email(query)
        if email and email in candidate.identity_values.get("email", set()):
            add_signal(score_parts, match_sources, support_signals, "identity:email_exact", 130)
    elif query_kind == "phone":
        phone_hits = normalise_phone_variants(query)
        if phone_hits and phone_hits & candidate.identity_values.get("phone", set()):
            add_signal(score_parts, match_sources, support_signals, "identity:phone_exact", 130)
    elif query_kind == "dob":
        dob = normalise_dob(query)
        if dob and dob in candidate.identity_values.get("dob", set()):
            add_signal(score_parts, match_sources, support_signals, "identity:dob_exact", 128)
    elif query_kind == "case_ref":
        case_keys = extract_case_ref_variants(query)
        if case_keys and case_keys & candidate.identity_values.get("case_ref", set()):
            add_signal(score_parts, match_sources, support_signals, "identity:case_ref_exact", 129)


def score_aliases(
    query_forms: Dict[str, object],
    candidate: CandidateRecord,
    alias_conflicts: Dict[str, Set[str]],
    score_parts: List[int],
    match_sources: List[str],
    support_signals: List[str],
) -> None:
    query_key = query_forms["normalised"]
    query_compact = query_forms["compact"]
    query_stripped = query_forms["normalised_stripped"]
    for alias, sources in candidate.aliases.items():
        alias_norm = normalise_name(alias)
        alias_compact = compact_key(alias)
        alias_stripped = normalise_name(strip_matter_suffixes(alias))
        conflict_count = len(alias_conflicts.get(alias_norm, {candidate.canonical_name}))
        is_manual = "manual" in sources
        is_generated = any(source.startswith("generated:") for source in sources)
        conflicted_suffix = "_conflicted" if (conflict_count > 1 and not is_manual) else ""
        if query_key and alias_norm == query_key:
            if is_manual:
                add_signal(score_parts, match_sources, support_signals, "manual_alias_exact", 100)
            elif is_generated:
                points = 85 if conflict_count == 1 else 72
                add_signal(score_parts, match_sources, support_signals, f"generated_alias_exact{conflicted_suffix}", points)
            else:
                add_signal(score_parts, match_sources, support_signals, f"alias_exact{conflicted_suffix}", 80)
        elif query_compact and alias_compact == query_compact:
            if is_manual:
                source = "manual_alias_compact_exact"
                points = 92
            else:
                source = f"alias_compact_exact{conflicted_suffix}"
                points = 78
            add_signal(score_parts, match_sources, support_signals, source, points)
        elif query_stripped and alias_stripped == query_stripped:
            if is_manual:
                source = "manual_alias_suffixless_exact"
                points = 88
            else:
                source = f"alias_suffixless_exact{conflicted_suffix}"
                points = 74
            add_signal(score_parts, match_sources, support_signals, source, points)


def score_canonical(query_forms: Dict[str, object], candidate: CandidateRecord, score_parts: List[int], match_sources: List[str], support_signals: List[str]) -> None:
    candidate_forms = candidate.query_forms
    if query_forms["normalised"] == candidate_forms["normalised"]:
        add_signal(score_parts, match_sources, support_signals, "canonical_exact", 95)
    elif query_forms["compact"] and query_forms["compact"] == candidate_forms["compact"]:
        add_signal(score_parts, match_sources, support_signals, "normalised_exact", 90)
    elif query_forms["normalised_stripped"] and query_forms["normalised_stripped"] == candidate_forms["normalised_stripped"]:
        add_signal(score_parts, match_sources, support_signals, "canonical_suffixless_exact", 86)
    elif query_forms["sorted_tokens"] and query_forms["sorted_tokens"] == candidate_forms["sorted_tokens"]:
        add_signal(score_parts, match_sources, support_signals, "sorted_token_exact", 75)


def score_tokens(query_forms: Dict[str, object], candidate: CandidateRecord, score_parts: List[int], match_sources: List[str], support_signals: List[str]) -> None:
    query_tokens = query_forms["tokens"]
    candidate_tokens = candidate.query_forms["tokens"]
    if not query_tokens or not candidate_tokens:
        return

    query_first = query_tokens[0]
    query_last = query_tokens[-1]

    if len(query_tokens) == 1:
        if query_first == candidate_tokens[0]:
            add_signal(score_parts, match_sources, support_signals, "token:first_name_exact_single", 24)
        if query_last == candidate_tokens[-1]:
            add_signal(score_parts, match_sources, support_signals, "token:surname_exact_single", 14)
        return



def score_fuzzy(query_forms: Dict[str, object], candidate: CandidateRecord, score_parts: List[int], match_sources: List[str], support_signals: List[str]) -> None:
    candidate_forms = candidate.query_forms
    full_similarity = full_string_similarity(query_forms["normalised_stripped"], candidate_forms["normalised_stripped"])
    if full_similarity >= 0.94:
        add_signal(score_parts, match_sources, support_signals, "fuzzy:full_very_strong", 30, support="fuzzy:full")
    elif full_similarity >= 0.88:
        add_signal(score_parts, match_sources, support_signals, "fuzzy:full_strong", 20, support="fuzzy:full")
    elif full_similarity >= 0.82:
        add_signal(score_parts, match_sources, support_signals, "fuzzy:full_mid", 12, support="fuzzy:full")

    query_first = query_forms["first"]
    candidate_first = candidate_forms["first"]
    query_last = query_forms["last"]
    candidate_last = candidate_forms["last"]
    first_similarity = similarity_score(query_first, candidate_first)
    last_similarity = similarity_score(query_last, candidate_last)
    if query_last and query_last == candidate_last and first_similarity >= 0.75:
        add_signal(score_parts, match_sources, support_signals, "fuzzy:first_name_under_exact_surname", 10, support="fuzzy:first")
    elif last_similarity >= 0.8 and query_first != candidate_first:
        add_signal(score_parts, match_sources, support_signals, "fuzzy:surname_only", 8, support="fuzzy:surname")


def score_subsequence(query_forms: Dict[str, object], candidate: CandidateRecord, score_parts: List[int], match_sources: List[str], support_signals: List[str]) -> None:
    query_text = str(query_forms["normalised_stripped"])
    candidate_text = str(candidate.query_forms["normalised_stripped"])
    if len(query_text) < 2 or not candidate_text:
        return
    if len(query_text) >= len(candidate_text) * 0.6:
        return
    if list(fuzzyfinder(query_text, [candidate_text])):
        add_signal(score_parts, match_sources, support_signals, "subsequence:abbreviation", 6, support="fuzzy:subsequence")


def score_verified_full_name(query_forms: Dict[str, object], candidate: CandidateRecord, score_parts: List[int], match_sources: List[str], support_signals: List[str]) -> None:
    if not candidate.verified_name_middle:
        return
    query_tokens = query_forms["tokens"]
    if len(query_tokens) < 3:
        return
    candidate_first = candidate.query_forms["first"]
    candidate_last = candidate.query_forms["last"]
    if query_tokens[0] != candidate_first or query_tokens[-1] != candidate_last:
        return
    query_middle = normalise_name(" ".join(query_tokens[1:-1]))
    verified_middle = normalise_name(candidate.verified_name_middle)
    if full_string_similarity(query_middle, verified_middle) >= 0.8:
        add_signal(score_parts, match_sources, support_signals, "verified_full_name:middle_match", 40, support="verified_full_name")


def apply_penalties(query_forms: Dict[str, object], candidate: CandidateRecord, score_parts: List[int], match_sources: List[str]) -> None:
    query_tokens = query_forms["tokens"]
    candidate_tokens = candidate.query_forms["tokens"]
    if not query_tokens or not candidate_tokens:
        return

    if len(query_tokens) == 1 and query_tokens[0] == candidate.query_forms["last"]:
        score_parts.append(-20)
        match_sources.append("penalty:surname_only")
    elif len(query_tokens) > 1 and query_forms["first"] != candidate.query_forms["first"]:
        first_similarity = full_string_similarity(query_forms["first"], candidate.query_forms["first"])
        if first_similarity < 0.7:
            full_similarity = full_string_similarity(query_forms["normalised_stripped"], candidate.query_forms["normalised_stripped"])
            if full_similarity < 0.9:
                score_parts.append(-15)
                match_sources.append("penalty:first_token_mismatch")

    if candidate.is_live_bias_candidate:
        score_parts.append(3)
        match_sources.append("tie_break:live_bias")


def score_candidate(query: str, query_kind: str, candidate: CandidateRecord, alias_conflicts: Dict[str, Set[str]]) -> RankedCandidate:
    query_forms = build_query_forms(query)
    score_parts: List[int] = []
    match_sources: List[str] = []
    support_signals: List[str] = []

    score_identity(query_kind, query, candidate, score_parts, match_sources, support_signals)
    if query_kind == "name":
        score_aliases(query_forms, candidate, alias_conflicts, score_parts, match_sources, support_signals)
        score_canonical(query_forms, candidate, score_parts, match_sources, support_signals)
        score_tokens(query_forms, candidate, score_parts, match_sources, support_signals)
        score_fuzzy(query_forms, candidate, score_parts, match_sources, support_signals)
        score_subsequence(query_forms, candidate, score_parts, match_sources, support_signals)
        score_verified_full_name(query_forms, candidate, score_parts, match_sources, support_signals)
        apply_penalties(query_forms, candidate, score_parts, match_sources)
    elif candidate.is_live_bias_candidate and score_parts:
        score_parts.append(3)
        match_sources.append("tie_break:live_bias")

    score = sum(score_parts)
    if query_kind != "name" and not any(source.startswith("identity:") for source in match_sources):
        score = min(score, 0)

    match_sources = dedupe_list(match_sources)
    support_signals = dedupe_list(support_signals)
    return RankedCandidate(
        canonical_name=candidate.canonical_name,
        root_card=repo_rel(candidate.root_card_path),
        score=score,
        confidence_hint=best_confidence_hint(match_sources),
        match_sources=match_sources,
        live_bias="live" if candidate.is_live_bias_candidate else "neutral",
        auto_resolve_safe=any(
            not signal.startswith("fuzzy:") and not signal.endswith("_conflicted")
            for signal in support_signals
        ),
        support_signals=support_signals,
        live_matter_folder=candidate.live_matter_folder,
    )


def dedupe_list(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def classify_confidence(query: str, query_kind: str, ranked: Sequence[RankedCandidate]) -> Tuple[str, bool, str]:
    if not ranked or ranked[0].score <= 0:
        return "low", False, "no plausible client match"

    top = ranked[0]
    second_score = ranked[1].score if len(ranked) > 1 else -999
    margin = top.score - second_score
    query_tokens = tokenise_name(query)
    single_token_query = query_kind == "name" and len(query_tokens) == 1

    if single_token_query and margin <= 5:
        if any(source in {"token:first_name_exact_single", "token:surname_exact_single"} for source in top.match_sources):
            return "low", False, "single-token name query is ambiguous"

    if any(source.startswith("identity:") for source in top.match_sources):
        return "high", True, top.confidence_hint
    if "manual_alias_exact" in top.match_sources or "canonical_exact" in top.match_sources or "normalised_exact" in top.match_sources:
        return "high", True, top.confidence_hint
    if "generated_alias_exact" in top.match_sources and margin >= 15:
        return "high", True, top.confidence_hint
    if top.score >= 85 and margin >= 15 and top.auto_resolve_safe:
        return "high", True, top.confidence_hint
    if top.score >= 45 and margin >= 15 and top.auto_resolve_safe and not single_token_query:
        return "mid", True, f"{top.confidence_hint} with clear margin"
    if top.score >= 25:
        return "mid", False, "multiple plausible candidates"
    return "low", False, "weak or ambiguous match"


def rank_candidates(query: str, query_kind: str, candidates: Dict[str, CandidateRecord], alias_conflicts: Dict[str, Set[str]]) -> List[RankedCandidate]:
    ranked = [score_candidate(query, query_kind, candidate, alias_conflicts) for candidate in candidates.values()]
    ranked = [candidate for candidate in ranked if candidate.score > 0 and candidate.support_signals]
    ranked.sort(
        key=lambda item: (
            item.score,
            any(source.startswith("identity:") for source in item.match_sources),
            item.auto_resolve_safe,
            item.canonical_name.lower(),
        ),
        reverse=True,
    )
    return ranked


def candidate_to_dict(candidate: RankedCandidate) -> Dict[str, object]:
    return {
        "canonical_name": candidate.canonical_name,
        "root_card": candidate.root_card,
        "score": candidate.score,
        "confidence_hint": candidate.confidence_hint,
        "match_sources": candidate.match_sources,
        "live_bias": candidate.live_bias,
        "live_matter_folder": candidate.live_matter_folder,
    }


def build_result(query: str, query_kind: str, ranked: Sequence[RankedCandidate], limit: int) -> Dict[str, object]:
    query_forms = build_query_forms(query)
    confidence, resolved, reason = classify_confidence(query, query_kind, ranked)
    candidates_out = [candidate_to_dict(candidate) for candidate in ranked[:limit]]
    result: Dict[str, object] = {
        "query": query,
        "query_normalised": query_forms["normalised_stripped"],
        "query_kind": query_kind,
        "confidence": confidence,
        "resolved": resolved,
        "reason": reason,
        "candidates": candidates_out,
    }
    if resolved and candidates_out:
        result["resolved_candidate"] = candidates_out[0]
    return result


def maybe_record_search_learning(args: argparse.Namespace, result: Dict[str, object]) -> None:
    selected_canonical = clean_text(args.confirm_canonical)
    if not selected_canonical and result.get("resolved_candidate"):
        selected_canonical = clean_text(str(result["resolved_candidate"].get("canonical_name", "")))

    should_record_event = bool(args.record_event or args.confirm_canonical)
    if not should_record_event:
        return

    top_candidates = [
        {
            "canonical_name": str(candidate.get("canonical_name", "")),
            "score": int(candidate.get("score", 0) or 0),
            "confidence_hint": str(candidate.get("confidence_hint", "")),
        }
        for candidate in result.get("candidates", [])
    ]
    event_payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "query_raw": str(result.get("query", "")),
        "query_normalised": str(result.get("query_normalised", "")),
        "query_kind": str(result.get("query_kind", "")),
        "resolver_confidence": str(result.get("confidence", "")),
        "resolver_resolved": bool(result.get("resolved", False)),
        "selected_canonical": selected_canonical,
        "selection_source": clean_text(args.selection_source),
        "confirmed": bool(args.confirm_canonical),
        "top_candidates": top_candidates,
    }
    record_client_search_event(event_payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve a client name or exact client identity field against telemetry-backed aliases.")
    parser.add_argument("--query", required=True, help="Client query to resolve.")
    parser.add_argument("--limit", type=int, default=3, help="How many ranked candidates to return.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON result.")
    parser.add_argument("--record-event", action="store_true", help="Record the resolver attempt in telemetry SQL.")
    parser.add_argument("--confirm-canonical", default="", help="Confirmed canonical client name for learning / event logging.")
    parser.add_argument("--selection-source", default="user_confirmed", help="Why the canonical client was selected.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidates, alias_conflicts = build_candidates()
    query = clean_text(args.query)
    query_kind = classify_query_kind(query)
    ranked = rank_candidates(query, query_kind, candidates, alias_conflicts)
    payload = build_result(query, query_kind, ranked, max(1, args.limit))
    maybe_record_search_learning(args, payload)
    print(json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
