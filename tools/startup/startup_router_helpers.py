#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import firm_profile
except ModuleNotFoundError:
    from tools import firm_profile

_PROFILE = firm_profile.load_profile()
ONEDRIVE_ROOT_NAME = _PROFILE.onedrive_root_name
FIRM_MAIL_DOMAINS = tuple(domain.lower() for domain in _PROFILE.mail_domains)


CASE_NO_RE = re.compile(r"\b[A-Z]{1,4}\d{2}[A-Z]?\d{4,6}\b")

BUCKETS = {
    "A-D": set("ABCD"),
    "E-H": set("EFGH"),
    "I-L": set("IJKL"),
    "M-P": set("MNOP"),
    "Q-T": set("QRST"),
    "U-Z": set("UVWXYZ"),
}


@dataclass
class Client:
    name: str
    first: str
    surname: str
    bucket: str
    norm_full: str
    path: Path
    summary_path: Optional[Path]


def normalise(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def bucket_for_first_name(first_name: str) -> str:
    initial = (first_name[:1] or "").upper()
    for bucket, letters in BUCKETS.items():
        if initial in letters:
            return bucket
    return "U-Z"


def clean_filename_subject(name: str) -> str:
    name = re.sub(r"_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.md$", "", str(name or ""))
    return name.strip()


def parse_date(raw: str, fallback: dt.datetime) -> dt.datetime:
    if not raw:
        return fallback
    raw = raw.strip()
    try:
        return dt.datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return fallback


def safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return -1.0


def resolve_onedrive_root(cli_value: str = "") -> Optional[Path]:
    candidates: List[Path] = []
    if cli_value:
        candidates.append(Path(cli_value))

    for env_name in ("CASEFORGE_ONEDRIVE_ROOT", "OneDriveCommercial", "OneDrive"):
        val = os.getenv(env_name, "")
        if val:
            candidates.append(Path(val))

    home = Path.home()
    candidates.append(home / ONEDRIVE_ROOT_NAME)

    users_root = Path("C:/Users")
    if users_root.exists():
        for path in users_root.glob(f"*/{ONEDRIVE_ROOT_NAME}"):
            candidates.append(path)

    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def extract_case_numbers(text: str) -> List[str]:
    return sorted({match.group(0).upper() for match in CASE_NO_RE.finditer(str(text or ""))})


def parse_meta(raw: str, filename: str, fallback_time: dt.datetime) -> Dict[str, object]:
    def line(pattern: str) -> str:
        match = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else ""

    from_ = line(r"^FROM:\s*(.+)$") or line(r"^\*\*From:\*\*\s*([^\r\n]+)")
    to_ = line(r"^TO:\s*(.+)$")
    subject = line(r"^SUBJECT:\s*(.+)$") or line(r"^#\s*(.+)$") or clean_filename_subject(filename)
    received = line(r"^RECEIVED:\s*([^\r\n]+)") or line(r"^\*\*Sent:\*\*\s*([^\r\n]+)")
    when = parse_date(received, fallback_time)

    return {
        "from": from_,
        "to": to_,
        "subject": subject,
        "received_raw": received,
        "when": when,
    }


def parse_summary_fields(summary_path: Optional[Path]) -> Dict[str, str]:
    fields = {
        "Court": "TBC",
        "Case No": "TBC",
        "Matter": "TBC",
        "Respondent": "TBC",
    }
    if not summary_path or not summary_path.exists():
        return fields

    text = summary_path.read_text(encoding="utf-8", errors="ignore")
    mapping = {
        "Court": r"\|\s*\*\*Court\*\*\s*\|\s*([^|\r\n]+)\|",
        "Case No": r"\|\s*\*\*Case No\*\*\s*\|\s*([^|\r\n]+)\|",
        "Matter": r"\|\s*\*\*Order Type\*\*\s*\|\s*([^|\r\n]+)\|",
        "Respondent": r"\|\s*\*\*Respondent\*\*\s*\|\s*([^|\r\n]+)\|",
    }
    for key, pattern in mapping.items():
        match = re.search(pattern, text)
        if match and not re.search(r"\[\s*unknown\b[^\]]*\]", match.group(1), re.IGNORECASE):
            fields[key] = match.group(1).strip() or "TBC"
    return fields


def choose_direction(from_: str, to_: str) -> str:
    from_text = str(from_ or "").lower()
    to_text = str(to_ or "").lower()
    if any(domain in from_text for domain in FIRM_MAIL_DOMAINS) or "/o=exchangelabs/" in from_text:
        return "OUT"
    if any(domain in to_text for domain in FIRM_MAIL_DOMAINS):
        return "IN"
    return "IN"


def build_client_index(clients_root: Path) -> Tuple[List[Client], Dict[str, List[Client]], Dict[str, List[Client]]]:
    result = _build_client_index_from_sql(clients_root)
    if result[0]:
        return result
    print("  [client-index] SQL returned no clients - falling back to local folder scan", flush=True)

    return _build_client_index_from_folders(clients_root)


def _build_client_index_from_sql(
    clients_root: Path,
) -> Tuple[List[Client], Dict[str, List[Client]], Dict[str, List[Client]]]:
    try:
        import clientdb_sql

        with clientdb_sql.get_connection() as conn:
            cur = conn.cursor()

            cur.execute("SELECT DISTINCT canonical_name FROM dbo.matters WHERE canonical_name IS NOT NULL")
            name_rows = [row[0] for row in cur.fetchall()]

            cur.execute(
                "SELECT m.canonical_name, r.ref_value "
                "FROM dbo.matter_references r "
                "JOIN dbo.matters m ON r.matter_id = m.matter_id "
                "WHERE r.ref_value IS NOT NULL"
            )
            name_to_refs: Dict[str, List[str]] = {}
            for canonical, ref in cur.fetchall():
                name_to_refs.setdefault(canonical, []).append(ref)
    except Exception as exc:
        print(f"  [client-index] SQL unavailable: {exc}", flush=True)
        return [], {}, {}

    clients: List[Client] = []
    surname_index: Dict[str, List[Client]] = {}
    case_index: Dict[str, List[Client]] = {}

    for canonical in name_rows:
        parts = str(canonical or "").strip().split()
        if len(parts) < 2:
            continue
        first = parts[0]
        surname = parts[-1]
        synthetic_path = clients_root / bucket_for_first_name(first) / f"{canonical} - AI GEN"
        client = Client(
            name=canonical,
            first=first,
            surname=surname,
            bucket=bucket_for_first_name(first),
            norm_full=normalise(canonical),
            path=synthetic_path,
            summary_path=None,
        )
        clients.append(client)
        surname_index.setdefault(normalise(surname), []).append(client)
        for ref in name_to_refs.get(canonical, []):
            for case_no in extract_case_numbers(ref):
                case_index.setdefault(case_no, []).append(client)

    print(f"  [client-index] SQL: {len(clients)} clients, {len(case_index)} case refs", flush=True)
    return clients, surname_index, case_index


def _build_client_index_from_folders(
    clients_root: Path,
) -> Tuple[List[Client], Dict[str, List[Client]], Dict[str, List[Client]]]:
    clients: List[Client] = []
    surname_index: Dict[str, List[Client]] = {}
    case_index: Dict[str, List[Client]] = {}

    for folder in clients_root.rglob("* - AI GEN"):
        if not folder.is_dir():
            continue
        name = folder.name.replace(" - AI GEN", "").strip()
        parts = name.split()
        if len(parts) < 2:
            continue
        if not any(folder.rglob("*.md")):
            continue
        first = parts[0]
        surname = parts[-1]
        summaries = sorted(folder.glob("*-Case-Summary-*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
        summary = summaries[0] if summaries else None
        client = Client(
            name=name,
            first=first,
            surname=surname,
            bucket=bucket_for_first_name(first),
            norm_full=normalise(name),
            path=folder,
            summary_path=summary,
        )
        clients.append(client)
        surname_index.setdefault(normalise(surname), []).append(client)
        if summary and summary.exists():
            text = summary.read_text(encoding="utf-8", errors="ignore")
            for case_no in extract_case_numbers(text):
                case_index.setdefault(case_no, []).append(client)

    return clients, surname_index, case_index


def match_client(
    filename: str,
    subject: str,
    snippet: str,
    clients: List[Client],
    surname_index: Dict[str, List[Client]],
    case_index: Dict[str, List[Client]],
) -> Optional[Client]:
    combined = f"{filename} {subject} {snippet}"

    candidates: List[Client] = []
    for case_no in extract_case_numbers(combined):
        candidates.extend(case_index.get(case_no, []))
    candidates = list({client.path: client for client in candidates}.values())
    if len(candidates) == 1:
        return candidates[0]

    search = normalise(combined)

    full_hits = [client for client in clients if client.norm_full and re.search(rf"\b{re.escape(client.norm_full)}\b", search)]
    full_hits = list({client.path: client for client in full_hits}.values())
    if len(full_hits) == 1:
        return full_hits[0]

    matched_surnames: List[Client] = []
    for surname_key, matched_clients in surname_index.items():
        if not surname_key:
            continue
        if re.search(rf"\b{re.escape(surname_key)}\b", search) and len(matched_clients) == 1:
            matched_surnames.append(matched_clients[0])

    matched_surnames = list({client.path: client for client in matched_surnames}.values())
    if len(matched_surnames) == 1:
        return matched_surnames[0]

    return None
