#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple


WHITESPACE_RE = re.compile(r"\s+")
HEARING_TYPE_PATTERNS = [
    (
        re.compile(r"\b(first hearing dispute resolution appointment|fhdra)\b", re.IGNORECASE),
        ("FIRST HEARING DISPUTE RESOLUTION APPOINTMENT", "First Hearing Dispute Resolution Appointment"),
    ),
    (
        re.compile(r"\b(final dispute resolution appointment|fdra)\b", re.IGNORECASE),
        ("FINAL DISPUTE RESOLUTION APPOINTMENT", "Final Dispute Resolution Appointment"),
    ),
    (
        re.compile(r"\b(dispute resolution appointment|dra)\b", re.IGNORECASE),
        ("DISPUTE RESOLUTION APPOINTMENT", "Dispute Resolution Appointment"),
    ),
    (re.compile(r"\b(final hearing)\b", re.IGNORECASE), ("FINAL HEARING", "final hearing")),
    (re.compile(r"\b(directions hearing)\b", re.IGNORECASE), ("DIRECTIONS HEARING", "directions hearing")),
    (re.compile(r"\b(fact[- ]finding hearing)\b", re.IGNORECASE), ("FACT-FINDING HEARING", "fact-finding hearing")),
    (re.compile(r"\b(return hearing)\b", re.IGNORECASE), ("RETURN HEARING", "return hearing")),
]

HEARING_STAGE_PATTERNS = [
    (re.compile(r"\b(first hearing dispute resolution appointment|fhdra|first hearing)\b", re.IGNORECASE), "first hearing"),
    (re.compile(r"\b(final dispute resolution appointment|fdra|final hearing)\b", re.IGNORECASE), "final hearing"),
    (re.compile(r"\b(return hearing)\b", re.IGNORECASE), "return hearing"),
    (re.compile(r"\b(dispute resolution appointment|dra)\b", re.IGNORECASE), "return hearing"),
    (re.compile(r"\b(directions hearing)\b", re.IGNORECASE), "directions hearing"),
    (re.compile(r"\b(fact[- ]finding hearing)\b", re.IGNORECASE), "fact-finding hearing"),
]


def normalise_space(value: str) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "").strip())


def extract_hearing_type(*values: str) -> Tuple[str, str]:
    for value in values:
        text = str(value or "")
        for pattern, result in HEARING_TYPE_PATTERNS:
            if pattern.search(text):
                return result
    return "HEARING", "hearing"


def extract_hearing_stage(*values: str) -> str:
    for value in values:
        text = str(value or "")
        for pattern, result in HEARING_STAGE_PATTERNS:
            if pattern.search(text):
                return result
    return "hearing"


def resolve_pdftotext_path() -> Optional[Path]:
    candidates = []
    env_value = os.getenv("PDFTOTEXT_PATH", "").strip()
    if env_value:
        candidates.append(Path(env_value))
    which_value = shutil.which("pdftotext")
    if which_value:
        candidates.append(Path(which_value))
    candidates.extend(
        [
            Path("/usr/bin/pdftotext"),
            Path("/usr/local/bin/pdftotext"),
        ]
    )
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def extract_pdf_text(pdf_path: Path) -> str:
    pdftotext = resolve_pdftotext_path()
    if pdftotext is None or not pdf_path.exists():
        return ""
    try:
        result = subprocess.run(
            [str(pdftotext), "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            timeout=60,
        )
    except Exception:
        return ""
    if result.returncode != 0 and not result.stdout.strip():
        return ""
    return result.stdout or ""


def split_venue_components(venue_text: str) -> Tuple[str, str]:
    clean = normalise_space(re.sub(r"^\s*the Family Court at\s+", "", str(venue_text or ""), flags=re.IGNORECASE))
    if not clean:
        return "", ""
    parts = [part.strip() for part in clean.split(",") if part.strip()]
    if len(parts) >= 3 and parts[1].lower().startswith("the family court sitting at"):
        return ", ".join(parts[:2]), ", ".join(parts[2:])
    if len(parts) >= 2:
        return parts[0], ", ".join(parts[1:])
    return clean, ""


def parse_hearing_notice_text(text: str) -> Dict[str, object]:
    raw = str(text or "").replace("\r", "")
    flat = normalise_space(raw)
    hearing_heading, hearing_sentence = extract_hearing_type(raw, flat)
    hearing_stage = extract_hearing_stage(raw, flat)
    venue_match = re.search(r"\bat\s+the Family Court at\s+(.+?)\s+on\s+\d", flat, re.IGNORECASE)
    venue_text = normalise_space(venue_match.group(1)) if venue_match else ""
    court_name, court_address = split_venue_components(venue_text)
    mode_match = re.search(
        r"\bon\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}\s+at\s+[0-9:.apm ]+\s*-\s*([^.]+)",
        flat,
        re.IGNORECASE,
    )
    mode = normalise_space(mode_match.group(1)).title() if mode_match else ""
    mode_lower = mode.lower()
    if "face to face" in mode_lower or "in person" in mode_lower:
        mode = "In person"
    elif "remote" in mode_lower:
        mode = "Remote"
    elif "hybrid" in mode_lower:
        mode = "Hybrid"
    elif "telephone" in mode_lower:
        mode = "Telephone"
    elif "teams" in mode_lower:
        mode = "Teams"
    elif "cvp" in mode_lower:
        mode = "CVP"
    estimate_match = re.search(r"\btime estimate of\s+(\d+)\s*(hour|hours|minute|minutes|min|mins)\b", flat, re.IGNORECASE)
    duration_minutes = 0
    if estimate_match:
        amount = int(estimate_match.group(1))
        unit = estimate_match.group(2).lower()
        duration_minutes = amount * 60 if unit.startswith("hour") else amount
    return {
        "hearing_heading": hearing_heading,
        "hearing_sentence": hearing_sentence,
        "hearing_stage": hearing_stage,
        "venue_text": venue_text,
        "court_name": court_name,
        "court_address": court_address,
        "mode": mode,
        "duration_minutes": duration_minutes,
    }


def resolve_rootless_live_folder(one_drive_root: Optional[Path], rootless_path: str) -> Optional[Path]:
    if one_drive_root is None:
        return None
    clean = str(rootless_path or "").strip().strip("\\/")
    if not clean:
        return None
    return one_drive_root / Path(clean)


def find_hearing_notice_pdf(live_folder: Optional[Path], case_ref: str = "") -> Optional[Path]:
    if live_folder is None or not live_folder.exists():
        return None
    patterns = (
        "*HEARING NOTICE*.pdf",
        "*Notice of hearing*.pdf",
        "*notice of hearing*.pdf",
        "*C43*.pdf",
        "*order*.pdf",
        "*.pdf",
    )
    candidates = []
    case_key = str(case_ref or "").strip().upper()
    for pattern in patterns:
        candidates.extend(path for path in live_folder.rglob(pattern) if path.is_file())
    if not candidates:
        return None

    def rank(candidate: Path) -> tuple[int, int, float]:
        name_upper = candidate.name.upper()
        case_hit = 0 if case_key and case_key in name_upper else 1
        hearing_hit = 0 if ("HEARING" in name_upper or "NOTICE" in name_upper) else 1
        order_hit = 0 if ("C43" in name_upper or "ORDER" in name_upper) else 1
        return case_hit, hearing_hit + order_hit, -candidate.stat().st_mtime

    candidates = sorted(set(candidates), key=rank)
    return candidates[0]
