#!/usr/bin/env python3
"Find missing matter references, hearings and counsel/chambers, then apply them."
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
import tempfile
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from london_time import london_today
import firm_profile
from hearing_calendar import hearing_dates

_PROFILE = firm_profile.load_profile()
LIBRARY_SEGMENTS = tuple(f"/{root.split('/')[-1]}/" for root in (_PROFILE.library_root, _PROFILE.closed_library_root))

LOG_TABLE = "clientdb_normalise_log"
LOG_MIGRATION = Path(__file__).resolve().parent / "migrations" / "0027_clientdb_normalise_log.sql"
ACTOR = "system:matter-gap-cleanup"
COLLECTION = "matter_documents_v1"
EARLIEST_DATE = dt.date(2022, 1, 1)
MIN_CONFIDENCE = {"high": 2, "medium": 1, "low": 0}


COMPANY_REF_RE = re.compile(r"(?<![\d/])(\d{6})/(\d{2})FL\b", re.IGNORECASE)
LEGACY_REF_RE = re.compile(r"(?<![A-Za-z0-9/])((?:[A-Z]{2}/){1,2})(\d{6})/(\d{2,3})\s*FL\b")
STD_SHAPE_RE = re.compile(r"^\d{6}/\d{2}FL$")
DATE_NEAR_DAYS = 14
COURT_NO_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2}\d{2}[A-Z]\d{5})(?![A-Za-z0-9])", re.ASCII)
REF_TYPE_BY_LETTER = {"F": "court_family", "P": "court_children"}
_REF_LABEL_RE = re.compile(r"(?:our|your|val|internal|company|case)\s*(?:ref|reference)|\bref\b", re.IGNORECASE)
_CASE_LABEL_RE = re.compile(r"(?:case|claim)\s*(?:no|number|ref)|\bcase\s*n", re.IGNORECASE)
_VACATED_RE = re.compile(r"vacat|cancel|adjourn|postpon", re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}

_DATE_FIRST_RE = re.compile(r"^\s*(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{4}|\d{2})(?!\d)[\s\-_.]*.*hearing", re.IGNORECASE)
_DATE_AFTER_RE = re.compile(r"hearing[\s\-_.]*(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{4}|\d{2})(?!\d)", re.IGNORECASE)
_DATE_WORD_RE = re.compile(r"hearing[\s\-_.]+(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})", re.IGNORECASE)

_NAME = r"(?:(?:Mr|Ms|Mrs|Miss|Dr)\.?\s+)?[A-Z][A-Za-z'\u2019\-]+(?:\s+[A-Z][A-Za-z'\u2019\-]+){0,3}"
_CHAMBERS = r"(?:\d{1,3}\s+)?(?:[A-Z][\w&'\u2019\-]*\s+){1,4}Chambers"
_COUNSEL_LABEL_RE = re.compile(
    rf"(?i:counsel|barrister)\s*(?i:instructed)?\s*[:\-\u2013]\s*({_NAME})\s*(?:[,(\-\u2013]|\bof\b|\bfrom\b|\bat\b)\s*({_CHAMBERS})"
)
_COUNSEL_FROM_RE = re.compile(rf"({_NAME})\s+(?:from|of|at)\s+({_CHAMBERS})")
_CUE_RE = re.compile(r"counsel|barrister|advocate|instruct|\bbrief", re.IGNORECASE)
_OTHER_SIDE_RE = re.compile(r"respondent|opponent|other side|other party|litigant|\bLIP\b", re.IGNORECASE)
_NAME_LEAD_STOP = {"dear", "hi", "hello", "kind", "best", "regards", "thanks", "thank", "you", "please", "re", "cc", "to", "from",
                   "the", "our", "with", "by", "counsel", "barrister", "advocate", "instructed", "and", "sent", "email", "attn"}
_TITLES = {"mr", "ms", "mrs", "miss", "dr"}


def valid_ref_date(yymmdd: str, today: dt.date | None = None) -> dt.date | None:
    today = today or london_today()
    try:
        d = dt.date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    except ValueError:
        return None
    return d if EARLIEST_DATE <= d <= today else None


def company_ref_candidates(text: str, today: dt.date | None = None) -> list[tuple[str, bool]]:
    "(reference, labelled) for each CaseForge-shaped reference with a real date."
    out = []
    for m in COMPANY_REF_RE.finditer(text or ""):
        if valid_ref_date(m.group(1), today) is None:
            continue
        window = text[max(0, m.start() - 60): m.start()]
        out.append((f"{m.group(1)}/{m.group(2)}FL", bool(_REF_LABEL_RE.search(window))))
    return out


def legacy_company_ref_candidates(text: str, today: dt.date | None = None) -> list[tuple[str, bool]]:
    "(reference, labelled) for each initials-prefixed reference with a real date."
    out = []
    for m in LEGACY_REF_RE.finditer(text or ""):
        if valid_ref_date(m.group(2), today) is None:
            continue
        window = text[max(0, m.start() - 60): m.start()]
        out.append((f"{m.group(1)}{m.group(2)}/{m.group(3)}FL", bool(_REF_LABEL_RE.search(window))))
    return out


def ref_date_of(ref: str) -> dt.date | None:
    "The date a reference encodes (its six digits), or None."
    m = re.search(r"(\d{6})/\d{2,3}FL$", ref or "", re.IGNORECASE)
    return valid_ref_date(m.group(1), dt.date.max) if m else None


def near_matter_date(ref: str, matter_dates: list[str], days: int = DATE_NEAR_DAYS) -> bool:
    rd = ref_date_of(ref)
    if rd is None:
        return False
    for iso in matter_dates or []:
        try:
            if abs((rd - dt.date.fromisoformat(str(iso)[:10])).days) <= days:
                return True
        except ValueError:
            continue
    return False


DOMINANT_MIN_DOCS = 3
DOMINANT_RATIO = 3


def dominant_reference(store: dict[str, dict], dates: list[str]) -> str | None:
    "The one candidate a matter's own papers overwhelmingly show: at least three documents"
    if len(store) < 2:
        return None
    ranked = sorted(store.items(), key=lambda kv: -len(kv[1]["docs"]))
    top_ref, top = ranked[0]
    if len(top["docs"]) < DOMINANT_MIN_DOCS or len(top["docs"]) < DOMINANT_RATIO * len(ranked[1][1]["docs"]):
        return None
    if dates and not near_matter_date(top_ref, dates) and any(near_matter_date(r, dates) for r in store if r != top_ref):
        return None
    return top_ref


def court_number_candidates(text: str) -> list[tuple[str, bool]]:
    out = []
    for m in COURT_NO_RE.finditer(text or ""):
        window = text[max(0, m.start() - 40): m.start()]
        out.append((m.group(1), bool(_CASE_LABEL_RE.search(window))))
    return out


def hearing_folder_date(name: str, today: dt.date | None = None) -> tuple[dt.date | None, str]:
    "The date a hearing folder's own name states, or (None, reason)."
    today = today or london_today()
    if "hearing" not in (name or "").lower():
        return None, "not_a_hearing_folder"
    if _VACATED_RE.search(name):
        return None, "vacated_or_cancelled_wording"
    parts: tuple[int, int, int] | None = None
    multi = hearing_dates.label_start(name)
    if multi is not None:
        parts = (multi[0].year, multi[0].month, multi[0].day)
    m = None if parts else (_DATE_FIRST_RE.match(name) or _DATE_AFTER_RE.search(name))
    if m:
        year = int(m.group(3))
        parts = (year + 2000 if year < 100 else year, int(m.group(2)), int(m.group(1)))
    elif parts is None:
        w = _DATE_WORD_RE.search(name)
        if w and w.group(2).lower() in _MONTHS:
            parts = (int(w.group(3)), _MONTHS[w.group(2).lower()], int(w.group(1)))
    if parts is None:
        return None, "no_date_in_name"
    try:
        d = dt.date(*parts)
    except ValueError:
        return None, "invalid_date"
    if not (EARLIEST_DATE <= d <= today + dt.timedelta(days=400)):
        return None, "date_out_of_range"
    return d, ""


def _clean_counsel_name(raw: str) -> str:
    "Drop greeting/sign-off words the name pattern swept up; '' if no real"
    tokens = re.sub(r"\s+", " ", raw).strip().split(" ")
    while tokens and tokens[0].lower().rstrip(".") in _NAME_LEAD_STOP:
        tokens.pop(0)
    body = tokens[1:] if tokens and tokens[0].lower().rstrip(".") in _TITLES else tokens
    return " ".join(tokens) if len(body) >= 2 else ""


def counsel_candidates(text: str) -> list[tuple[str, str]]:
    "(counsel, chambers) pairs stated in the text, verbatim."
    text = text or ""
    out: list[tuple[str, str]] = []
    for m in _COUNSEL_LABEL_RE.finditer(text):
        name = _clean_counsel_name(m.group(1))
        if name:
            out.append((name, re.sub(r"\s+", " ", m.group(2)).strip()))
    for m in _COUNSEL_FROM_RE.finditer(text):
        window = text[max(0, m.start() - 250): m.end() + 250]
        if not _CUE_RE.search(window) or _OTHER_SIDE_RE.search(window):
            continue
        name = _clean_counsel_name(m.group(1))
        if name:
            out.append((name, re.sub(r"\s+", " ", m.group(2)).strip()))
    return list(dict.fromkeys(out))


def ref_type_for(case_no: str) -> str | None:
    return REF_TYPE_BY_LETTER.get(case_no[4:5])



def _prop(rule: str, op: str, confidence: str, args: dict, evidence: list[dict], **extra) -> dict:
    return {"rule": rule, "op": op, "confidence": confidence, "args": args, "evidence": evidence, **extra}


def build_proposals(state: dict, today: dt.date | None = None) -> tuple[list[dict], list[dict], dict]:
    "``state`` keys (all plain data):"
    today = today or london_today()
    matters = state["matters"]
    props: list[dict] = []
    conflicts: list[dict] = []

    refs_by_matter: dict[int, list[dict]] = defaultdict(list)
    owners: dict[str, set[int]] = defaultdict(set)
    for r in state["refs"]:
        refs_by_matter[r["matter_id"]].append(r)
        if r["ref_type"].startswith("court"):
            owners[r["value"].upper()].add(r["matter_id"])
    company_owner: dict[str, set[int]] = defaultdict(set)
    for mid, m in matters.items():
        if m["company_reference"]:
            company_owner[m["company_reference"].upper()].add(mid)
    for r in state["refs"]:
        if r["ref_type"] in ("company_ref", "company"):
            company_owner[r["value"].upper()].add(r["matter_id"])

    proposed_company: dict[str, list[int]] = defaultdict(list)
    legacy_mined = state.get("mined_company_legacy", {})
    for mid, m in matters.items():
        have_ref_rows = {r["value"].upper() for r in refs_by_matter[mid] if r["ref_type"] in ("company_ref", "company")}
        col = (m["company_reference"] or "").upper()
        would_reconcile = bool(col and col not in have_ref_rows) or (not col and len(have_ref_rows) == 1)
        if would_reconcile and any(company_owner.get(v, set()) - {mid} for v in ({col} - {""}) | have_ref_rows):
            conflicts.append({"rule": "company_ref_reconcile", "matter_id": mid, "reason": "value_held_by_another_matter"})
            continue
        if col and col not in have_ref_rows:
            props.append(_prop("company_ref_reconcile_to_references", "insert_reference", "high",
                               {"matter_id": mid, "ref_type": "company_ref", "value": col, "source": "reconcile:matters.company_reference"}, [],
                               style="standard" if STD_SHAPE_RE.match(col) else "legacy"))
        elif not col and len(have_ref_rows) == 1:
            only = next(iter(have_ref_rows))
            props.append(_prop("company_ref_reconcile_to_matters", "set_company_reference", "high",
                               {"matter_id": mid, "value": only}, [], style="standard" if STD_SHAPE_RE.match(only) else "legacy"))
        elif not col and len(have_ref_rows) > 1:
            conflicts.append({"rule": "company_ref_reconcile_to_matters", "matter_id": mid, "reason": "several_reference_rows"})
        if col or have_ref_rows:
            continue
        cands = state["mined_company"].get(mid, {})
        lcands = legacy_mined.get(mid, {})
        if not cands and not lcands:
            continue
        dates = m.get("dates") or []
        for store, rule, style in ((cands, "company_ref_from_documents", "standard"), (lcands, "company_ref_legacy_from_documents", "legacy")):
            if not store:
                continue
            pick, how = None, ""
            if len(store) == 1:
                pick, how = next(iter(store)), "only_candidate"
            else:
                near = [r for r in store if near_matter_date(r, dates)] if dates else []
                if len(near) == 1:
                    pick, how = near[0], "referral_date"
                elif dominant_reference(store, dates):
                    pick, how = dominant_reference(store, dates), "document_count"
                else:
                    conflicts.append({"rule": rule, "matter_id": mid, "reason": "several_candidates" if not dates or not near else "several_near_referral_date",
                                      "candidates": len(store), "near_referral_date": len(near),
                                      "labelled": len([r for r, i in store.items() if i["labelled"]])})
            if pick is None:
                continue
            info = store[pick]
            near_pick = near_matter_date(pick, dates) if dates else None
            conf = "high" if (info["labelled"] and info["docs"]) or len(info["docs"]) >= 2 or (how == "referral_date" and info["labelled"]) else "medium"
            if (near_pick is False and conf == "high") or how == "document_count":
                conf = "medium"
            proposed_company[pick].append(mid)
            props.append(_prop(rule, "set_company_reference", conf,
                               {"matter_id": mid, "value": pick, "also_reference_row": True},
                               [{"item_id": i} for i in sorted(info["docs"])[:5]], style=style, chosen_by=how, date_match=near_pick))
            break
    drop: set[tuple[str, int]] = set()
    for ref, mids in proposed_company.items():
        holders = company_owner.get(ref.upper(), set())
        if len(mids) > 1 or holders:
            for mid in mids:
                drop.add((ref, mid))
                conflicts.append({"rule": "company_ref_from_documents", "matter_id": mid,
                                  "reason": "held_by_another_matter" if holders else "proposed_for_several_matters"})
    doc_rules = ("company_ref_from_documents", "company_ref_legacy_from_documents")
    props = [p for p in props if not (p["rule"] in doc_rules and (p["args"]["value"], p["args"]["matter_id"]) in drop)]

    for ref, holders in sorted(company_owner.items()):
        if len(holders) < 2:
            continue
        holders = {h for h in holders if h in matters}
        in_docs = {h for h in holders if ref in state["mined_company"].get(h, {}) or ref in legacy_mined.get(h, {})}
        date_ok = {h for h in holders if near_matter_date(ref, matters[h].get("dates") or [])}
        both = in_docs & date_ok
        genuine = in_docs if len(in_docs) == 1 else both if len(both) == 1 else (date_ok if not in_docs and len(date_ok) == 1 else set())
        if len(genuine) != 1:
            conflicts.append({"rule": "company_ref_collision", "reason": "cannot_tell_which_matter_holds_it",
                              "matters": sorted(holders), "in_own_documents": sorted(in_docs), "date_matches": sorted(date_ok)})
            continue
        keep = next(iter(genuine))
        for other in sorted(holders - {keep}):
            alt_store = {r: i for r, i in {**state["mined_company"].get(other, {}), **legacy_mined.get(other, {})}.items() if r != ref}
            other_dates = matters[other].get("dates") or []
            alt_near = [r for r in alt_store if near_matter_date(r, other_dates)]
            new, how = None, ""
            if len(alt_near) == 1:
                new, how = alt_near[0], "referral_date"
            elif len(alt_store) == 1:
                new, how = next(iter(alt_store)), "only_candidate"
            elif dominant_reference(alt_store, other_dates):
                new, how = dominant_reference(alt_store, other_dates), "document_count"
            if new and (company_owner.get(new.upper(), set()) - {other}):
                new = None
            if new:
                info = alt_store[new]
                props.append(_prop("company_ref_collision_replace", "replace_company_reference", "medium",
                                   {"matter_id": other, "old": ref, "new": new},
                                   [{"item_id": i} for i in sorted(info["docs"])[:5]],
                                   style="standard" if STD_SHAPE_RE.match(new) else "legacy", genuine_matter=keep, chosen_by=how,
                                   date_match=near_matter_date(new, other_dates) if other_dates else None))
            else:
                conflicts.append({"rule": "company_ref_collision", "reason": "wrong_holder_has_no_other_reference_in_its_documents",
                                  "matter_id": other, "genuine_matter": keep})

    generated = [mid for mid, m in matters.items()
                 if m["open"] and not m["company_reference"]
                 and not any(r["ref_type"] in ("company_ref", "company") for r in refs_by_matter[mid])
                 and not any(p["args"].get("matter_id") == mid and p["op"] == "set_company_reference" for p in props)]
    with_date = [mid for mid in generated if matters[mid].get("ref_date")]

    hearing_case_refs: dict[int, set[str]] = defaultdict(set)
    for h in state["hearings"]:
        if h["matter_id"] and h["case_ref"]:
            hearing_case_refs[h["matter_id"]].add(h["case_ref"].upper())
    proposed_court: list[tuple[int, str, str]] = []
    for mid, cands in state["mined_court"].items():
        by_type: dict[str, dict[str, dict]] = defaultdict(dict)
        unmapped: dict[str, dict] = {}
        for no, info in cands.items():
            rt = ref_type_for(no)
            if rt is None:
                conflicts.append({"rule": "court_number_from_documents", "matter_id": mid, "reason": "unmapped_case_letter", "letter": no[4:5]})
                unmapped[no] = info
                continue
            by_type[rt][no] = info
        existing = {(r["ref_type"], r["value"].upper()) for r in refs_by_matter[mid]}
        if len(unmapped) == 1 and not any(t == "court_ref" for (t, _v) in existing) and not by_type:
            no, info = next(iter(unmapped.items()))
            if not (owners.get(no.upper(), set()) - {mid}):
                props.append(_prop("court_number_unmapped_letter_as_court_ref", "insert_reference", "medium",
                                   {"matter_id": mid, "ref_type": "court_ref", "value": no, "source": "document-index", "letter": no[4:5]},
                                   [{"item_id": i} for i in sorted(info["docs"])[:5]], style="court_ref"))
        for rt, found in by_type.items():
            have = [v for (t, v) in existing if t == rt]
            if have:
                differing = [n for n, i in found.items() if n.upper() not in have and len(i["docs"]) >= 2]
                if differing:
                    conflicts.append({"rule": "court_number_from_documents", "matter_id": mid, "reason": "differs_from_existing", "ref_type": rt})
                continue
            pick = None
            if len(found) == 1:
                pick = next(iter(found))
            else:
                matching = [n for n in found if n in hearing_case_refs.get(mid, set())]
                if len(matching) == 1:
                    pick = matching[0]
                else:
                    conflicts.append({"rule": "court_number_from_documents", "matter_id": mid, "reason": "several_candidates", "ref_type": rt, "candidates": len(found)})
                    continue
            info = found[pick]
            other = owners.get(pick.upper(), set()) - {mid}
            if other:
                conflicts.append({"rule": "court_number_from_documents", "matter_id": mid, "reason": "held_by_another_matter", "ref_type": rt})
                continue
            matches_hearing = any(h["case_ref"].upper() == pick for h in state["hearings"])
            conf = "high" if (info["order_docs"] or len(info["docs"]) >= 2 or matches_hearing) else "medium"
            proposed_court.append((mid, rt, pick))
            props.append(_prop("court_number_from_documents", "insert_reference", conf,
                               {"matter_id": mid, "ref_type": rt, "value": pick, "source": "document-index"},
                               [{"item_id": i} for i in sorted(info["docs"])[:5]], matches_hearing=matches_hearing))
    dup: dict[str, set[int]] = defaultdict(set)
    for mid, _rt, no in proposed_court:
        dup[no].add(mid)
    bad = {no for no, mids in dup.items() if len(mids) > 1}
    if bad:
        for p in props:
            if p["rule"] == "court_number_from_documents" and p["args"]["value"] in bad:
                conflicts.append({"rule": "court_number_from_documents", "matter_id": p["args"]["matter_id"], "reason": "proposed_for_several_matters"})
        props = [p for p in props if not (p["rule"] == "court_number_from_documents" and p["args"]["value"] in bad)]

    ref_owner = {k: set(v) for k, v in owners.items()}
    for p in props:
        if p["rule"] == "court_number_from_documents":
            ref_owner.setdefault(p["args"]["value"].upper(), set()).add(p["args"]["matter_id"])
    effective: dict[int, int | None] = {}
    for h in state["hearings"]:
        effective[h["hearing_id"]] = h["matter_id"]
        if h["matter_id"] or not h["case_ref"]:
            continue
        found = ref_owner.get(h["case_ref"].upper(), set())
        if len(found) == 1:
            mid = next(iter(found))
            effective[h["hearing_id"]] = mid
            existing_ref = h["case_ref"].upper() in owners
            props.append(_prop("hearing_link_by_case_number", "link_hearing", "high" if existing_ref else "medium",
                               {"hearing_id": h["hearing_id"], "matter_id": mid}, []))
        elif len(found) > 1:
            conflicts.append({"rule": "hearing_link_by_case_number", "hearing_id": h["hearing_id"], "reason": "several_matters_hold_the_number"})

    have_dates: dict[int, set[str]] = defaultdict(set)
    for h in state["hearings"]:
        mid = effective.get(h["hearing_id"])
        if mid:
            have_dates[mid].add(h["date"])
    folder_dates: dict[tuple[int, str], dict] = {}
    for f in state["folders"]:
        folder_dates.setdefault((f["matter_id"], f["date"]), f)
    for h in state["hearings"]:
        mid = effective.get(h["hearing_id"])
        f = folder_dates.get((mid, h["date"])) if mid else None
        if f and h["review_state"] == "needs_review" and "weekend" not in (h["review_reason"] or "").lower():
            props.append(_prop("hearing_confirmed_by_folder", "confirm_hearing", "high",
                               {"hearing_id": h["hearing_id"]}, [{"item_id": f["item_id"]}]))
    today_iso = today.isoformat()
    for (mid, date), f in sorted(folder_dates.items()):
        m = matters.get(mid)
        if not m or not m["open"] or date in have_dates.get(mid, set()):
            continue
        cases = sorted(hearing_case_refs.get(mid, set()) | {r["value"].upper() for r in refs_by_matter[mid] if r["ref_type"].startswith("court")}
                       | {p["args"]["value"] for p in props if p["rule"] == "court_number_from_documents" and p["args"]["matter_id"] == mid})
        case_ref = cases[0] if len(cases) == 1 else ""
        future = date >= today_iso
        props.append(_prop("hearing_from_folder_name", "insert_hearing", "medium",
                           {"matter_id": mid, "hearing_date": date, "case_ref": case_ref,
                            "review_state": "needs_review" if future else "ok",
                            "review_reason": "from a hearing folder name: time and type not stated" + ("" if case_ref else "; case number ambiguous"),
                            "source_kind": "folder"},
                           [{"item_id": f["item_id"]}]))

    for h in state["hearings"]:
        if h["counsel"] or h["chambers"]:
            continue
        own = counsel_candidates(h.get("text", ""))
        pairs = sorted(set(own))
        evidence: list[dict] = [{"hearing_id": h["hearing_id"]}] if pairs else []
        conf = "high"
        if not pairs:
            mid = effective.get(h["hearing_id"])
            docs = state["mined_counsel"].get(mid, []) if mid else []
            distinct = sorted({tuple(d["pair"]) for d in docs})
            conf = "medium"
            if len(distinct) == 1:
                pairs = [distinct[0]]
                evidence = [{"item_id": d["item_id"]} for d in docs[:5]]
            elif len(distinct) > 1:
                near = [d for d in docs if d.get("modified") and abs((dt.date.fromisoformat(d["modified"][:10]) - dt.date.fromisoformat(h["date"])).days) <= 45]
                near_pairs = sorted({tuple(d["pair"]) for d in near})
                if len(near_pairs) == 1:
                    pairs = [near_pairs[0]]
                    evidence = [{"item_id": d["item_id"]} for d in near[:5]]
                else:
                    conflicts.append({"rule": "counsel_from_documents", "hearing_id": h["hearing_id"], "reason": "several_counsel_in_matter"})
                    continue
        if len(pairs) == 1:
            props.append(_prop("counsel_from_hearing_text" if evidence and "hearing_id" in evidence[0] else "counsel_from_documents",
                               "set_counsel", conf, {"hearing_id": h["hearing_id"], "counsel": pairs[0][0], "chambers": pairs[0][1]}, evidence))
        elif len(pairs) > 1:
            conflicts.append({"rule": "counsel_from_hearing_text", "hearing_id": h["hearing_id"], "reason": "several_counsel_in_text"})

    summary: dict[str, Any] = {"by_rule": defaultdict(lambda: defaultdict(int)), "conflicts": defaultdict(int)}
    for p in props:
        summary["by_rule"][p["rule"]][p["confidence"]] += 1
    for c in conflicts:
        summary["conflicts"][f"{c['rule']}:{c['reason']}"] += 1
    summary["by_rule"] = {k: dict(v) for k, v in summary["by_rule"].items()}
    summary["conflicts"] = dict(summary["conflicts"])
    open_ids = [mid for mid, m in matters.items() if m["open"]]
    has_company_now = {mid for mid in open_ids if matters[mid]["company_reference"] or any(r["ref_type"] in ("company_ref", "company") for r in refs_by_matter[mid])}
    has_company_after = has_company_now | {p["args"]["matter_id"] for p in props if p["op"] == "set_company_reference" and p["args"]["matter_id"] in matters and matters[p["args"]["matter_id"]]["open"]}
    has_court_now = {mid for mid in open_ids if any(r["ref_type"].startswith("court") for r in refs_by_matter[mid])}
    has_court_after = has_court_now | {p["args"]["matter_id"] for p in props if p["rule"] == "court_number_from_documents" and matters[p["args"]["matter_id"]]["open"]}
    linked_after = {h["hearing_id"] for h in state["hearings"] if effective.get(h["hearing_id"])}
    summary["coverage_if_high_and_medium_applied"] = {
        "open_matters": len(open_ids),
        "open_with_company_reference": {"now": len(has_company_now), "after": len(has_company_after)},
        "open_with_a_court_number": {"now": len(has_court_now), "after": len(has_court_after)},
        "hearings": len(state["hearings"]),
        "hearings_linked_to_a_matter": {"now": sum(1 for h in state["hearings"] if h["matter_id"]), "after": len(linked_after)},
        "hearings_with_counsel": {"now": sum(1 for h in state["hearings"] if h["counsel"]),
                                  "after": sum(1 for h in state["hearings"] if h["counsel"]) + sum(1 for p in props if p["op"] == "set_counsel")},
        "hearings_new_from_folders": sum(1 for p in props if p["op"] == "insert_hearing"),
    }
    summary["company_reference_generation_candidates"] = {"open_matters_without_any": len(generated), "of_which_with_a_referral_date": len(with_date)}
    return props, conflicts, summary



def _qdrant(path: str, body: dict) -> dict:
    key = os.environ.get("CASEFORGE_QDRANT_READONLY_API_KEY") or os.environ.get("CASEFORGE_QDRANT_API_KEY", "")
    base = os.environ.get("CASEFORGE_QDRANT_URL", "http://127.0.0.1:6333")
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "api-key": key}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def iter_chunks() -> Iterator[dict]:
    offset = None
    while True:
        body: dict[str, Any] = {"limit": 500, "with_vector": False,
                                "with_payload": ["matter_id", "item_id", "doc_type", "c8_protected", "modified_utc", "text"]}
        if offset:
            body["offset"] = offset
        res = _qdrant(f"/collections/{COLLECTION}/points/scroll", body)["result"]
        for point in res["points"]:
            yield point["payload"]
        offset = res.get("next_page_offset")
        if not offset:
            return


def mine_text(mid: int, item: str, text: str, company: dict, court: dict, legacy: dict | None, today: dt.date | None = None,
              doc_type: str = "") -> None:
    "One document's worth of references into the maps ``mine_chunks`` builds."
    for ref, labelled in company_ref_candidates(text, today):
        info = company[mid].setdefault(ref, {"docs": set(), "labelled": 0})
        info["docs"].add(item)
        info["labelled"] += 1 if labelled else 0
    if legacy is not None:
        for ref, labelled in legacy_company_ref_candidates(text, today):
            info = legacy[mid].setdefault(ref, {"docs": set(), "labelled": 0})
            info["docs"].add(item)
            info["labelled"] += 1 if labelled else 0
    for no, labelled in court_number_candidates(text):
        info = court[mid].setdefault(no, {"docs": set(), "labelled": 0, "order_docs": 0})
        info["docs"].add(item)
        info["labelled"] += 1 if labelled else 0
        info["order_docs"] += 1 if doc_type == "order" else 0


def mine_chunks(chunks: Iterable[dict], numeric_matters: set[int], today: dt.date | None = None,
                legacy: dict | None = None) -> tuple[dict, dict, dict]:
    company: dict[int, dict[str, dict]] = defaultdict(dict)
    court: dict[int, dict[str, dict]] = defaultdict(dict)
    counsel: dict[int, list[dict]] = defaultdict(list)
    for c in chunks:
        try:
            mid = int(str(c.get("matter_id")))
        except ValueError:
            continue
        if mid not in numeric_matters or c.get("c8_protected"):
            continue
        text, item = str(c.get("text") or ""), str(c.get("item_id") or "")
        mine_text(mid, item, text, company, court, legacy, today, str(c.get("doc_type") or ""))
        for pair in counsel_candidates(text):
            counsel[mid].append({"pair": list(pair), "item_id": item, "modified": str(c.get("modified_utc") or "")})
    return company, court, counsel



COMPANY_DOC_KINDS = (
    ("ccl", re.compile(r"care letter|\bccl\b", re.IGNORECASE)),
    ("noa", re.compile(r"notice of acting|\bnoa\b", re.IGNORECASE)),
    ("invoice", re.compile(r"invoice|fee note|bill of costs", re.IGNORECASE)),
    ("loa", re.compile(r"letter of (?:authority|engagement)", re.IGNORECASE)),
)
COURT_DOC_KINDS = (
    ("order", re.compile(r"\border\b|sealed|\bnmo\b|\bpso\b|\bcao\b", re.IGNORECASE)),
    ("notice", re.compile(r"notice of hearing|\bnoh\b|listing|directions", re.IGNORECASE)),
    ("form", re.compile(r"fl401|\bc100\b|fl403|fl404|\bc2\b|\bc1a\b", re.IGNORECASE)),
)
READABLE_SUFFIXES = (".docx", ".pdf")
MAX_FILE_BYTES = 15 * 1024 * 1024


def plan_file_reads(items: Iterable[dict], roots: list[tuple[str, int]], company_targets: set[int], court_targets: set[int],
                    per_matter: int = 4) -> dict[int, list[dict]]:
    "Which indexed files to read for each matter, most likely to carry the number first."
    ordered = sorted(roots, key=lambda t: -len(t[0]))
    by_matter: dict[int, list[tuple[int, str, dict]]] = defaultdict(list)
    for it in items:
        name = str(it.get("name") or "")
        if not name.lower().endswith(READABLE_SUFFIXES) or int(it.get("size") or 0) > MAX_FILE_BYTES:
            continue
        path = str(it.get("path") or "") + "/"
        mid = next((m for prefix, m in ordered if path.startswith(prefix)), None)
        if mid is None:
            continue
        if mid in company_targets:
            for rank, (kind, rx) in enumerate(COMPANY_DOC_KINDS):
                if rx.search(name):
                    by_matter[mid].append((rank, "company:" + kind, it))
                    break
        if mid in court_targets:
            for rank, (kind, rx) in enumerate(COURT_DOC_KINDS):
                if rx.search(name):
                    by_matter[mid].append((10 + rank, "court:" + kind, it))
                    break
    plan: dict[int, list[dict]] = {}
    for mid, rows in by_matter.items():
        seen: set[str] = set()
        chosen: list[dict] = []
        for _rank, purpose, it in sorted(rows, key=lambda t: (t[0], str(t[2].get("name")))):
            key = str(it.get("name")).lower()
            if key in seen:
                continue
            seen.add(key)
            chosen.append({"item_id": str(it["item_id"]), "path": str(it["path"]), "name": str(it["name"]), "purpose": purpose})
            if len(chosen) >= per_matter:
                break
        plan[mid] = chosen
    return plan


def read_targets(matters: dict[int, dict], refs: list[dict]) -> tuple[set[int], set[int]]:
    "(matters to read for a company reference, matters to read for a court number)."
    open_ids = {mid for mid, m in matters.items() if m["open"]}
    holders: dict[str, set[int]] = defaultdict(set)
    for mid, m in matters.items():
        if m["company_reference"]:
            holders[m["company_reference"].upper()].add(mid)
    for r in refs:
        if r["ref_type"] in ("company_ref", "company"):
            holders[r["value"].upper()].add(r["matter_id"])
    has_company = {mid for s in holders.values() for mid in s}
    has_court = {r["matter_id"] for r in refs if r["ref_type"].startswith("court")}
    shared = {mid for s in holders.values() if len(s) > 1 for mid in s}
    return (open_ids - has_company) | shared, open_ids - has_court


def docx_text_with_headers(path: Path) -> str:
    "Body, tables, headers and footers: a letter's 'Our ref' often sits in a header."
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    for section in doc.sections:
        for part in (section.header, section.first_page_header, section.even_page_header,
                     section.footer, section.first_page_footer, section.even_page_footer):
            try:
                parts.extend(p.text for p in part.paragraphs)
                for table in part.tables:
                    for row in table.rows:
                        parts.extend(cell.text for cell in row.cells)
            except Exception:
                continue
    return "\n".join(t for t in parts if t and t.strip())


def pdf_text(path: Path, max_pages: int = 12) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])


def read_planned_files(plan: dict[int, list[dict]], company: dict, court: dict, legacy: dict, tmp_dir: Path,
                       today: dt.date | None = None, pause: float = 0.2) -> dict[str, int]:
    "Download each planned file, mine it, delete it. Read only: GET on the drive, no write."
    import time

    import graph_files

    tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = graph_files.token()
    stats: dict[str, int] = defaultdict(int)
    for mid, files in plan.items():
        for f in files:
            stats["files_planned"] += 1
            target = tmp_dir / f"{uuid.uuid4().hex}{Path(f['name']).suffix.lower()}"
            try:
                graph_files.download(f["path"], target, token)
                text = docx_text_with_headers(target) if target.suffix == ".docx" else pdf_text(target)
            except Exception as exc:
                stats["unreadable_" + type(exc).__name__] += 1
                continue
            finally:
                try:
                    target.unlink()
                except OSError:
                    pass
            if not text.strip():
                stats["no_text_layer"] += 1
                continue
            stats["files_read"] += 1
            mine_text(mid, f["item_id"], text, company, court, legacy, today, "order" if f["purpose"] == "court:order" else "")
            time.sleep(pause)
    return dict(stats)


def load_state(today: dt.date | None = None, read_files: bool = False, per_matter: int = 4,
               find_folders: bool = True, tmp_dir: Path | None = None) -> dict:
    import ops_db
    import clientdb_sql

    today = today or london_today()
    with clientdb_sql._pg_get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT matter_id, closed_at, company_reference, referral_sent_at, source_email_sent_at, created_utc, canonical_name FROM matters")
        matters = {}
        names: dict[int, str] = {}
        for r in cur.fetchall():
            ref_date = next((str(v)[:10] for v in (r[3], r[4], r[5]) if v), "")
            dates = sorted({str(v)[:10] for v in (r[3], r[4], r[5]) if v})
            matters[int(r[0])] = {"open": r[1] is None, "company_reference": (r[2] or "").strip(), "ref_date": ref_date, "dates": dates}
            names[int(r[0])] = str(r[6] or "")
        cur.execute("SELECT matter_id, ref_type, ref_value FROM matter_references")
        refs = [{"matter_id": int(r[0]), "ref_type": r[1], "value": r[2] or ""} for r in cur.fetchall()]
        cur.execute("SELECT hearing_id, matter_id, case_ref, hearing_date, review_state, review_reason, counsel, chambers, source_subject, notes FROM matter_hearings")
        hearings = [{"hearing_id": int(r[0]), "matter_id": int(r[1]) if r[1] is not None else None, "case_ref": r[2] or "", "date": r[3],
                     "review_state": r[4], "review_reason": r[5] or "", "counsel": r[6] or "", "chambers": r[7] or "",
                     "text": f"{r[8] or ''}\n{r[9] or ''}"} for r in cur.fetchall()]
    legacy: dict[int, dict[str, dict]] = defaultdict(dict)
    company, court, counsel = mine_chunks(iter_chunks(), set(matters), today, legacy)

    folders: list[dict] = []
    file_reading: dict[str, Any] = {}
    with ops_db.connect() as c:
        roots = [(str(r[1]).rstrip("/") + "/", int(r[0])) for r in c.execute(
            "SELECT matter_id, folder_path FROM matter_onedrive_roots WHERE folder_path IS NOT NULL AND matter_id GLOB '[0-9]*'")]
        roots.sort(key=lambda t: -len(t[0]))
        if read_files:
            company_targets, court_targets = read_targets(matters, refs)
            rooted = {m for _p, m in roots}
            plan_roots = list(roots)
            by_name_found = 0
            if find_folders:
                wanted: dict[str, list[int]] = defaultdict(list)
                for mid in (company_targets | court_targets) - rooted:
                    key = re.sub(r"[^a-z]+", " ", names.get(mid, "").lower()).strip()
                    if key:
                        wanted[key].append(mid)
                by_name: dict[str, list[str]] = defaultdict(list)
                for path, name in c.execute("SELECT path, name FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'folder'"):
                    key = re.sub(r"[^a-z]+", " ", str(name).split(" - ")[0].lower()).strip()
                    if key in wanted and any(segment in str(path) for segment in LIBRARY_SEGMENTS):
                        by_name[key].append(str(path))
                for key, mids in wanted.items():
                    if len(mids) == 1 and len(by_name.get(key, [])) == 1:
                        plan_roots.append((by_name[key][0].rstrip("/") + "/", mids[0]))
                        by_name_found += 1
            rows = c.execute(
                "SELECT item_id, path, name, size_bytes FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'file' AND ("
                + " OR ".join(f"lower(name) LIKE '%{w}%'" for w in ("care letter", "ccl", "notice of acting", "noa", "invoice", "fee note", "bill of costs",
                                                                   "letter of", "order", "sealed", "nmo", "pso", "cao", "notice of hearing", "noh",
                                                                   "listing", "directions", "fl401", "c100", "fl403", "fl404", "c2", "c1a")) + ")")
            items = [{"item_id": r[0], "path": r[1], "name": r[2], "size": r[3]} for r in rows]
            plan = plan_file_reads(items, plan_roots, company_targets, court_targets, per_matter)
            file_reading = {"matters_targeted": len(company_targets | court_targets), "matters_with_a_folder_found_by_exact_name": by_name_found,
                            "matters_with_files_planned": len(plan), "matters_with_no_folder_or_no_candidate_file": len(company_targets | court_targets) - len(plan)}
            file_reading.update(read_planned_files(plan, company, court, legacy, tmp_dir or Path(tempfile.mkdtemp(prefix="matter-gap-")), today))
        for r in c.execute("SELECT item_id, path, name FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'folder' AND name LIKE '%earing%'"):
            d, _why = hearing_folder_date(str(r[2]), today)
            if d is None:
                continue
            path = str(r[1]) + "/"
            mid = next((m for prefix, m in roots if path.startswith(prefix)), None)
            if mid is not None and mid in matters:
                folders.append({"matter_id": mid, "date": d.isoformat(), "item_id": str(r[0])})
    return {"matters": matters, "refs": refs, "hearings": hearings, "mined_company": company, "mined_court": court,
            "mined_counsel": counsel, "folders": folders, "mined_company_legacy": legacy, "file_reading": file_reading}


def _jsonable(o: Any):
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(type(o))


def split_proposal_files(props: list[dict]) -> dict[str, list[dict]]:
    "The main file is what one apply command takes; the others are for the owner to look at first."
    return {
        "proposals.json": [p for p in props if p.get("style", "standard") == "standard"],
        "proposals-legacy.json": [p for p in props if p.get("style") == "legacy"],
        "proposals-review.json": [p for p in props if p.get("style") == "court_ref"],
    }


def cmd_discover(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(out, 0o700)
    state = load_state(read_files=args.read_files, per_matter=args.per_matter, tmp_dir=out / "tmp")
    props, conflicts, summary = build_proposals(state)
    summary["file_reading"] = state.get("file_reading", {})
    files = split_proposal_files(props)
    have_company = {mid for mid, m in state["matters"].items() if m["company_reference"]} | {
        r["matter_id"] for r in state["refs"] if r["ref_type"] in ("company_ref", "company")}
    proposed = {p["args"]["matter_id"] for p in props if p["op"] == "set_company_reference"}
    still = sorted(mid for mid, m in state["matters"].items() if m["open"] and mid not in have_company and mid not in proposed)
    summary["files"] = {name: len(rows) for name, rows in files.items()}
    summary["company_reference_still_missing_on_open_matters"] = {"count": len(still), "ids": still}
    for name, payload in (*files.items(), ("conflicts.json", conflicts), ("summary.json", summary)):
        path = out / name
        path.write_text(json.dumps(payload, indent=2, default=_jsonable), encoding="utf-8")
        os.chmod(path, 0o600)
    print(json.dumps({k: v for k, v in summary.items() if k != "company_reference_still_missing_on_open_matters"}, indent=2, default=_jsonable))
    return 0



REVERTIBLE = {
    ("matter_references", "reference_id"), ("matters", "matter_id"), ("matter_hearings", "hearing_id"),
}
UPDATE_COLUMNS = {"matters": {"company_reference"}, "matter_hearings": {"matter_id", "counsel", "chambers", "review_state"},
                  "matter_references": {"ref_value", "ref_value_normalised"}}


def _ph(cur, sql: str) -> str:
    return sql.replace("?", "%s") if "psycopg2" in type(cur).__module__ else sql


def _x(cur, sql: str, params: tuple = ()):
    cur.execute(_ph(cur, sql), params)
    return cur


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(cur, run_tag: str, table: str, pk_col: str, pk: Any, column: str, old: Any, new: Any) -> None:
    _x(cur, f"INSERT INTO {LOG_TABLE} (run_tag, table_name, pk_column, pk_value, column_name, old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
       (run_tag, table, pk_col, str(pk), column, None if old is None else str(old), None if new is None else str(new)))


def _event(cur, hearing_id: int, before: dict, after: dict) -> None:
    _x(cur, "INSERT INTO matter_hearing_events (hearing_id, at_utc, actor, action, before_json, after_json, source_message_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
       (hearing_id, _now(), ACTOR, "updated", json.dumps(before), json.dumps(after), ""))


REFUSALS = frozenset({"value_held_by_another_matter", "new_value_held_by_another_matter"})
COMPANY_REF_TYPES = ("company_ref", "company")


def _company_reference_held_elsewhere(cur, matter_id: Any, value: str) -> bool:
    "True when a matter other than ``matter_id`` already holds ``value`` as its"
    norm = value.strip().upper()
    return bool(
        _x(cur, "SELECT 1 FROM matters WHERE matter_id <> ? AND upper(trim(company_reference)) = ?", (matter_id, norm)).fetchone()
        or _x(cur, "SELECT 1 FROM matter_references WHERE matter_id <> ? AND ref_type IN ('company_ref', 'company') AND ref_value_normalised = ?",
              (matter_id, norm)).fetchone()
    )


def _insert_reference(cur, run_tag: str, a: dict) -> str:
    norm = a["value"].upper()
    if _x(cur, "SELECT 1 FROM matter_references WHERE matter_id = ? AND ref_type = ? AND ref_value_normalised = ?", (a["matter_id"], a["ref_type"], norm)).fetchone():
        return "already_present"
    if a["ref_type"] in COMPANY_REF_TYPES and _company_reference_held_elsewhere(cur, a["matter_id"], a["value"]):
        return "value_held_by_another_matter"
    now = _now()
    row = _x(cur, "INSERT INTO matter_references (matter_id, ref_type, ref_value, ref_value_normalised, source, notes, is_primary, created_utc, updated_utc) "
                  "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?) RETURNING reference_id",
             (a["matter_id"], a["ref_type"], a["value"], norm, a.get("source", "matter-gap-cleanup"), f"run {run_tag}", now, now)).fetchone()
    _log(cur, run_tag, "matter_references", "reference_id", row[0], "(insert)", None, now)
    return "applied"


def _set_company_reference(cur, run_tag: str, a: dict) -> str:
    "Fill an empty ``matters.company_reference``. Refuses, with"
    row = _x(cur, "SELECT company_reference FROM matters WHERE matter_id = ?", (a["matter_id"],)).fetchone()
    if row is None:
        return "matter_missing"
    if (row[0] or "").strip():
        return "already_present"
    if _company_reference_held_elsewhere(cur, a["matter_id"], a["value"]):
        return "value_held_by_another_matter"
    _x(cur, "UPDATE matters SET company_reference = ? WHERE matter_id = ? AND COALESCE(company_reference, '') = ''", (a["value"], a["matter_id"]))
    _log(cur, run_tag, "matters", "matter_id", a["matter_id"], "company_reference", row[0], a["value"])
    if a.get("also_reference_row"):
        _insert_reference(cur, run_tag, {"matter_id": a["matter_id"], "ref_type": "company_ref", "value": a["value"], "source": "document-index"})
    return "applied"


def _replace_company_reference(cur, run_tag: str, a: dict) -> str:
    "Correct a reference two matters share: change ``old`` to ``new`` on the matter that"
    mid, old, new = a["matter_id"], a["old"].upper(), a["new"]
    row = _x(cur, "SELECT company_reference FROM matters WHERE matter_id = ?", (mid,)).fetchone()
    if row is None:
        return "matter_missing"
    holds_column = (row[0] or "").strip().upper() == old
    ref_rows = _x(cur, "SELECT reference_id, ref_value FROM matter_references WHERE matter_id = ? AND ref_type IN ('company_ref', 'company') "
                       "AND ref_value_normalised = ?", (mid, old)).fetchall()
    if not holds_column and not ref_rows:
        return "old_value_not_present"
    if _company_reference_held_elsewhere(cur, mid, new):
        return "new_value_held_by_another_matter"
    if _x(cur, "SELECT 1 FROM matter_references WHERE matter_id = ? AND ref_type IN ('company_ref', 'company') AND ref_value_normalised = ?",
          (mid, new.upper())).fetchone():
        return "new_row_already_exists"
    if holds_column:
        _x(cur, "UPDATE matters SET company_reference = ? WHERE matter_id = ? AND upper(company_reference) = ?", (new, mid, old))
        _log(cur, run_tag, "matters", "matter_id", mid, "company_reference", row[0], new)
    now = _now()
    for ref_id, value in ref_rows:
        _x(cur, "UPDATE matter_references SET ref_value = ?, ref_value_normalised = ?, updated_utc = ? WHERE reference_id = ?", (new, new.upper(), now, ref_id))
        _log(cur, run_tag, "matter_references", "reference_id", ref_id, "ref_value", value, new)
        _log(cur, run_tag, "matter_references", "reference_id", ref_id, "ref_value_normalised", old, new.upper())
    return "applied"


def _update_hearing(cur, run_tag: str, hid: int, changes: dict, only_if_empty: tuple[str, ...] = ()) -> str:
    row = _x(cur, "SELECT matter_id, counsel, chambers, review_state, review_reason FROM matter_hearings WHERE hearing_id = ?", (hid,)).fetchone()
    if row is None:
        return "hearing_missing"
    current = dict(zip(("matter_id", "counsel", "chambers", "review_state", "review_reason"), row))
    if any(current[c] not in (None, "") for c in only_if_empty):
        return "already_present"
    changes = {k: v for k, v in changes.items() if current.get(k) != v}
    if not changes:
        return "already_present"
    assert set(changes) <= UPDATE_COLUMNS["matter_hearings"]
    _x(cur, f"UPDATE matter_hearings SET {', '.join(f'{k} = ?' for k in changes)}, updated_utc = ?, updated_by = ? WHERE hearing_id = ?",
       (*changes.values(), _now(), ACTOR, hid))
    for k, v in changes.items():
        _log(cur, run_tag, "matter_hearings", "hearing_id", hid, k, current.get(k), v)
    _event(cur, hid, {k: current.get(k) for k in changes}, changes)
    return "applied"


def _insert_hearing(cur, run_tag: str, a: dict, evidence: list[dict]) -> str:
    case_ref = a.get("case_ref", "")
    where, params = (("case_ref = ? AND hearing_date = ?", (case_ref, a["hearing_date"])) if case_ref
                     else ("matter_id = ? AND hearing_date = ?", (a["matter_id"], a["hearing_date"])))
    if _x(cur, f"SELECT 1 FROM matter_hearings WHERE {where}", params).fetchone():
        return "already_present"
    now = _now()
    pointer = ", ".join(e["item_id"] for e in evidence if "item_id" in e)[:300]
    minutes = a.get("duration_minutes")
    duration, stated = (int(minutes), 1) if minutes else (60, 0)
    row = _x(cur, "INSERT INTO matter_hearings (hearing_uid, matter_id, case_ref, hearing_date, duration_minutes, duration_stated, review_state, "
                  "review_reason, confidence, source_kind, source_subject, created_utc, updated_utc, updated_by) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING hearing_id",
             (uuid.uuid4().hex, a["matter_id"], case_ref, a["hearing_date"], duration, stated, a["review_state"], a["review_reason"], 0.7,
              a.get("source_kind", "folder"), f"hearing folder {pointer}", now, now, ACTOR)).fetchone()
    _log(cur, run_tag, "matter_hearings", "hearing_id", row[0], "(insert)", None, now)
    return "applied"


def apply_proposals(cur, proposals: list[dict], run_tag: str, min_confidence: str = "medium",
                    refused: list[dict] | None = None) -> dict:
    "Apply each proposal; return result counts per rule. A refused write (see"
    floor = MIN_CONFIDENCE[min_confidence]
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    order = ["replace_company_reference", "insert_reference", "set_company_reference", "link_hearing", "insert_hearing", "confirm_hearing", "set_counsel"]
    for p in sorted(proposals, key=lambda p: order.index(p["op"]) if p["op"] in order else 99):
        if MIN_CONFIDENCE.get(p["confidence"], -1) < floor:
            counts[p["rule"]]["skipped_low_confidence"] += 1
            continue
        a, op = p["args"], p["op"]
        if op == "insert_reference":
            result = _insert_reference(cur, run_tag, a)
        elif op == "set_company_reference":
            result = _set_company_reference(cur, run_tag, a)
        elif op == "replace_company_reference":
            result = _replace_company_reference(cur, run_tag, a)
        elif op == "link_hearing":
            result = _update_hearing(cur, run_tag, a["hearing_id"], {"matter_id": a["matter_id"]}, only_if_empty=("matter_id",))
        elif op == "insert_hearing":
            result = _insert_hearing(cur, run_tag, a, p.get("evidence", []))
        elif op == "confirm_hearing":
            result = _update_hearing(cur, run_tag, a["hearing_id"], {"review_state": "ok"})
        elif op == "set_counsel":
            result = _update_hearing(cur, run_tag, a["hearing_id"], {"counsel": a["counsel"], "chambers": a["chambers"]}, only_if_empty=("counsel", "chambers"))
        else:
            result = "unknown_op"
        counts[p["rule"]][result] += 1
        if result in REFUSALS and refused is not None:
            refused.append({"rule": p["rule"], "op": op, "matter_id": a.get("matter_id"), "reason": result})
    return {rule: dict(v) for rule, v in counts.items()}


def revert_run(cur, run_tag: str, apply: bool) -> dict:
    "Undo a run, newest change first, only where a row still holds what the run wrote."
    entries = _x(cur, f"SELECT log_id, table_name, pk_column, pk_value, column_name, old_value, new_value FROM {LOG_TABLE} "
                      "WHERE run_tag = ? AND reverted_utc IS NULL ORDER BY log_id DESC", (run_tag,)).fetchall()
    out = {"run_tag": run_tag, "mode": "apply" if apply else "dry-run", "entries": len(entries), "restored": 0, "changed_since": 0}
    for log_id, table, pk_col, pk, column, old, new in entries:
        if (table, pk_col) not in REVERTIBLE:
            raise ValueError(f"refusing to revert unexpected log row {log_id}")
        if column == "(insert)":
            if table == "matter_hearings":
                still = _x(cur, "SELECT 1 FROM matter_hearings WHERE hearing_id = ? AND updated_utc = ? AND human_edited = 0", (pk, new)).fetchone()
            else:
                still = _x(cur, "SELECT 1 FROM matter_references WHERE reference_id = ? AND updated_utc = ?", (pk, new)).fetchone()
            if not still:
                out["changed_since"] += 1
                continue
            out["restored"] += 1
            if apply:
                if table == "matter_hearings":
                    _x(cur, "DELETE FROM matter_hearing_events WHERE hearing_id = ?", (pk,))
                _x(cur, f"DELETE FROM {table} WHERE {pk_col} = ?", (pk,))
        else:
            if column not in UPDATE_COLUMNS.get(table, set()):
                raise ValueError(f"refusing to revert unexpected log row {log_id}")
            current = _x(cur, f"SELECT {column} FROM {table} WHERE {pk_col} = ?", (pk,)).fetchone()
            if current is None or (None if current[0] is None else str(current[0])) != new:
                out["changed_since"] += 1
                continue
            out["restored"] += 1
            if apply:
                _x(cur, f"UPDATE {table} SET {column} = ? WHERE {pk_col} = ?", (old, pk))
        if apply:
            _x(cur, f"UPDATE {LOG_TABLE} SET reverted_utc = ? WHERE log_id = ?", (_now(), log_id))
    return out


_SHADOWED = (
    ("matter_references", "reference_id"), ("matters", None), ("matter_hearings", "hearing_id"),
    ("matter_hearing_events", "event_id"), (LOG_TABLE, "log_id"),
)


def _shadow_with_temp_tables(cur) -> None:
    "Shadow each table with a temporary copy (same columns and indexes) so"
    for table, serial in _SHADOWED:
        cur.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        cur.execute(f"INSERT INTO {table} SELECT * FROM public.{table}")
        if not serial:
            continue
        cur.execute("SELECT attidentity FROM pg_attribute WHERE attrelid = %s::regclass AND attname = %s", (f"pg_temp.{table}", serial))
        kind = (cur.fetchone() or [""])[0]
        if kind:
            cur.execute(f"ALTER TABLE pg_temp.{table} ALTER COLUMN {serial} RESTART WITH 1000000")
        else:
            cur.execute(f"CREATE TEMP SEQUENCE seq_{table} START 1000000")
            cur.execute(f"ALTER TABLE pg_temp.{table} ALTER COLUMN {serial} SET DEFAULT nextval('seq_{table}')")


def cmd_apply(args: argparse.Namespace) -> int:
    import psycopg2

    proposals = json.loads(Path(args.proposals).read_text(encoding="utf-8"))
    dsn = os.environ.get("CASEFORGE_CLIENTDB_PG_URL")
    if not dsn:
        print("CASEFORGE_CLIENTDB_PG_URL not set", file=sys.stderr)
        return 1
    run_tag = args.run_tag or "gap-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    conn = psycopg2.connect(dsn, connect_timeout=15, application_name="caseforge:sql/matter_gap_proposals.py")
    try:
        cur = conn.cursor()
        if args.apply:
            cur.execute(LOG_MIGRATION.read_text(encoding="utf-8"))
        else:
            _shadow_with_temp_tables(cur)
        refused: list[dict] = []
        result = apply_proposals(cur, proposals, run_tag, args.min_confidence, refused=refused)
        revert_check = revert_run(cur, run_tag, apply=False)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    mode = "apply" if args.apply else "dry-run (statements ran against temporary copies, rolled back)"
    print(json.dumps({"mode": mode, "run_tag": run_tag, "min_confidence": args.min_confidence, "result": result,
                      "refused": refused, "revert_dry_run": revert_check}, indent=2))
    if refused:
        print(f"REFUSED {len(refused)} write(s): the reference is already held by another matter; "
              "see \"refused\" above (matter numbers only).", file=sys.stderr)
    return 0


def cmd_revert(args: argparse.Namespace) -> int:
    import psycopg2

    dsn = os.environ.get("CASEFORGE_CLIENTDB_PG_URL")
    if not dsn:
        print("CASEFORGE_CLIENTDB_PG_URL not set", file=sys.stderr)
        return 1
    conn = psycopg2.connect(dsn, connect_timeout=15, application_name="caseforge:sql/matter_gap_proposals.py")
    try:
        cur = conn.cursor()
        result = revert_run(cur, args.run_tag, args.apply)
        conn.commit() if args.apply else conn.rollback()
    finally:
        conn.close()
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover", help="Read-only: write proposals, conflicts and a summary")
    d.add_argument("--out", required=True)
    d.add_argument("--read-files", action="store_true", help="Also read firm papers (care letters, notices of acting, invoices, orders) straight from the drive for matters still lacking a reference; read only")
    d.add_argument("--per-matter", type=int, default=4, help="With --read-files: most files read per matter")
    a = sub.add_parser("apply", help="Apply proposals (dry run unless --apply)")
    a.add_argument("--proposals", required=True)
    a.add_argument("--apply", action="store_true", help="Commit the writes")
    a.add_argument("--run-tag", default="")
    a.add_argument("--min-confidence", choices=["high", "medium"], default="medium")
    r = sub.add_parser("revert", help="Undo a run (dry run unless --apply)")
    r.add_argument("--run-tag", required=True)
    r.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    return {"discover": cmd_discover, "apply": cmd_apply, "revert": cmd_revert}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
