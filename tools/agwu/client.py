#!/usr/bin/env python3
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from clientdb_sql import search_clients
from sql.client_name_resolver import (
    build_candidates,
    classify_confidence,
    classify_query_kind,
    rank_candidates,
)


@dataclass
class Candidate:
    row: dict[str, Any]
    score: int
    margin: int
    match_sources: list[str] = field(default_factory=list)
    support_signals: list[str] = field(default_factory=list)


@dataclass
class ClientResolution:
    status: str
    matches: list[Candidate]
    display_query: str

    @property
    def top(self) -> Candidate | None:
        return self.matches[0] if self.matches else None


def _classify(query: str, query_kind: str, ranked) -> str:
    confidence, auto_resolve_safe, _hint = classify_confidence(query, query_kind, ranked)

    if auto_resolve_safe:
        return "resolved"
    if auto_resolve_safe is False and confidence != "low":
        return "ambiguous"
    return "not_found"


def _row_named(rows: list[dict], name: str) -> dict:

    def _norm(value: object) -> str:
        return " ".join(str(value or "").lower().split())

    wanted = _norm(name)
    for row in rows:
        if _norm(row.get("client_name")) == wanted:
            return row
    return rows[0]


def _finish(status: str, matches: list[Candidate], display_query: str, clean_query: str, caller: str) -> ClientResolution:
    if matches:
        from onboarding import client_removal

        kept = client_removal.visible_rows(matches, matter_id_of=lambda c: c.row.get("matter_id"))
        if len(kept) != len(matches):
            top_removed = not kept or kept[0] is not matches[0]
            matches = kept
            if not matches:
                status = "not_found"
            elif status == "resolved" and top_removed:
                status = "ambiguous"
    resolution = ClientResolution(status=status, matches=matches, display_query=display_query)
    from agwu.telemetry import log_client_resolution

    log_client_resolution(clean_query, resolution, caller=caller)
    return resolution


def _ranked_candidates(clean_query: str, query_kind: str) -> list:
    if query_kind != "name":
        return []
    try:
        candidates, alias_conflicts = build_candidates()
        return rank_candidates(clean_query, query_kind, candidates, alias_conflicts)
    except Exception:
        return []


def _reorder_rows_by_ranking(rows: list[dict], ranked: list) -> list[dict]:
    if not rows or not ranked:
        return list(rows)
    rank_index: dict[str, int] = {}
    for position, candidate in enumerate(ranked):
        name = str(getattr(candidate, "canonical_name", "") or "").strip().lower()
        if name and name not in rank_index:
            rank_index[name] = position
    if not rank_index:
        return list(rows)
    unranked = len(rank_index)
    return sorted(
        rows,
        key=lambda row: rank_index.get(
            str(row.get("client_name") or row.get("matter_name") or "").strip().lower(),
            unranked,
        ),
    )


def _court_reference_key(query: str) -> str:
    try:
        from vergil.client_search import court_reference_from_query

        return str(court_reference_from_query(query) or "").strip()
    except Exception:
        return ""


def _startup_cache_rows(query: str, limit: int) -> tuple[list[dict], str]:
    try:
        from vergil.client_search import search_clients_from_cache

        rows, display = search_clients_from_cache(query, search_clients, limit)
        return list(rows or []), str(display or "")
    except Exception:
        return [], ""


def resolve_client(query: str, *, limit: int = 6, caller: str = "") -> ClientResolution:
    clean_query = str(query or "").strip()
    if not clean_query:
        return _finish("not_found", [], clean_query, clean_query, caller)

    probe_limit = max(int(limit or 0), 2)
    exact_rows = search_clients(clean_query, limit=probe_limit)

    if len(exact_rows) == 1:
        matches = [
            Candidate(row=exact_rows[0], score=100, margin=100, match_sources=["exact_search"], support_signals=[])
        ]
        return _finish("resolved", matches, clean_query, clean_query, caller)

    query_kind = classify_query_kind(clean_query)
    ranked = _ranked_candidates(clean_query, query_kind)

    if exact_rows:
        ordered = _reorder_rows_by_ranking(exact_rows, ranked)
        matches = [
            Candidate(row=row, score=0, margin=0, match_sources=["exact_search_multiple"], support_signals=[])
            for row in ordered[:limit]
        ]
        return _finish("ambiguous", matches, clean_query, clean_query, caller)

    status = _classify(clean_query, query_kind, ranked)

    matches = []
    seen_matter_ids: set[str] = set()
    top_ranked_survived = False
    for position, candidate in enumerate(ranked):
        rows = search_clients(candidate.canonical_name, limit=4)
        if not rows:
            continue
        row = _row_named(rows, candidate.canonical_name)
        matter_key = "" if row.get("matter_id") is None else str(row.get("matter_id"))
        if matter_key and matter_key in seen_matter_ids:
            continue
        if matter_key:
            seen_matter_ids.add(matter_key)
        next_score = ranked[position + 1].score if position + 1 < len(ranked) else -999
        matches.append(
            Candidate(
                row=row,
                score=candidate.score,
                margin=candidate.score - next_score,
                match_sources=list(getattr(candidate, "match_sources", [])),
                support_signals=list(getattr(candidate, "support_signals", [])),
            )
        )
        if position == 0:
            top_ranked_survived = True
        if len(matches) >= limit:
            break

    if matches:
        if status == "resolved" and not top_ranked_survived:
            status = "ambiguous"
        return _finish(status, matches, clean_query, clean_query, caller)

    ref_query = _court_reference_key(clean_query)
    if ref_query and ref_query != clean_query:
        ref_rows = search_clients(ref_query, limit=probe_limit)
        if ref_rows:
            display = f"{clean_query} -> {ref_query}"
            if len(ref_rows) == 1:
                matches = [
                    Candidate(
                        row=ref_rows[0],
                        score=100,
                        margin=100,
                        match_sources=["exact_search", "court_reference"],
                        support_signals=[],
                    )
                ]
                return _finish("resolved", matches, display, clean_query, caller)
            matches = [
                Candidate(
                    row=row,
                    score=0,
                    margin=0,
                    match_sources=["exact_search_multiple", "court_reference"],
                    support_signals=[],
                )
                for row in ref_rows[:limit]
            ]
            return _finish("ambiguous", matches, display, clean_query, caller)

    cache_rows, cache_display = _startup_cache_rows(clean_query, limit)
    if cache_rows:
        matches = [
            Candidate(row=row, score=0, margin=0, match_sources=["startup_cache"], support_signals=[])
            for row in cache_rows[:limit]
        ]
        return _finish("ambiguous", matches, cache_display or clean_query, clean_query, caller)

    return _finish("not_found", [], clean_query, clean_query, caller)
