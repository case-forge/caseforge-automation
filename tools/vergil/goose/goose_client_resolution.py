from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _add_to_sys_path(directory: Path) -> None:
    entry = str(directory)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _load_name_extractor():
    _add_to_sys_path(REPO_ROOT / "tools")
    import name_extractor

    return name_extractor


def _load_client_name_resolver():
    _add_to_sys_path(REPO_ROOT / "tools")
    _add_to_sys_path(REPO_ROOT / "tools" / "sql")
    from sql import client_name_resolver

    return client_name_resolver


name_extractor = _load_name_extractor()
client_name_resolver = _load_client_name_resolver()
extract_candidate_names = name_extractor.extract_candidate_names



def _unresolved_no_candidate() -> Dict[str, object]:
    return {
        "query": "",
        "query_normalised": "",
        "query_kind": "none",
        "confidence": "none",
        "resolved": False,
        "reason": "no candidate name found in message",
        "candidates": [],
    }


def _top_score(result: Dict[str, object]) -> int:
    candidates = result.get("candidates") or []
    return candidates[0]["score"] if candidates else -1


def _candidate_to_dict(candidate) -> Dict[str, object]:
    row = candidate.row
    canonical_name = str(row.get("client_name") or row.get("matter_name") or "").strip()
    return {
        "canonical_name": canonical_name,
        "score": candidate.score,
        "confidence_hint": "/".join(candidate.match_sources) if candidate.match_sources else "unknown",
        "live_matter_folder": str(row.get("live_matter_folder") or ""),
    }


def _resolution_to_result(query: str, resolution) -> Dict[str, object]:
    candidates_out = [_candidate_to_dict(c) for c in resolution.matches]
    resolved = resolution.status == "resolved"
    result: Dict[str, object] = {
        "query": query,
        "query_kind": client_name_resolver.classify_query_kind(query),
        "resolved": resolved,
        "candidates": candidates_out,
    }
    if resolved and candidates_out:
        result["resolved_candidate"] = candidates_out[0]
    return result


def resolve_client_from_message(
    message: str,
    *,
    limit: int = 3,
    candidate_pool: Optional[
        Tuple[Dict[str, object], Dict[str, Set[str]]]
    ] = None,
) -> Dict[str, object]:
    names = extract_candidate_names(message)
    if not names:
        return _unresolved_no_candidate()

    import agwu

    results = []
    for name in names:
        resolution = agwu.resolve_client(
            name, limit=limit, caller="goose_client_resolution.resolve_client_from_message"
        )
        result = _resolution_to_result(name, resolution)
        results.append(result)
        if result["resolved"]:
            return result
    return max(results, key=_top_score)
