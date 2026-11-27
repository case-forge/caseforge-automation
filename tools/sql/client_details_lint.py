#!/usr/bin/env python3
"Read-only quality linter for client/matter details in caseforge-clientdb."
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)

PLACEHOLDER_RE = re.compile(r"\[unknown[^\]]*\]|\bunknown\b|\bn/?a\b|\btbc\b", re.IGNORECASE)

THIRD_PARTY_RE = re.compile(
    r"\b(MUM|MUMS|DAD|DADS|MOTHER|FATHER|PRISON|HMP|NAN|GRAN|SISTER|BROTHER|"
    r"FRIEND|WORK|C/?O|CARE OF)\b",
    re.IGNORECASE,
)

ROLE_ARTEFACT_RE = re.compile(r"\(\s*[RrAa]\s*\)")

MIN_ADDRESS_CHARS = 20
LONG_NAME_WORDS = 5


@dataclass
class Finding:
    code: str
    severity: str
    matter_id: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "matter_id": self.matter_id,
            "detail": self.detail,
        }


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, code: str, severity: str, matter_id: Any, detail: str) -> None:
        self.findings.append(Finding(code, severity, str(matter_id), detail))

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    def by_code(self) -> dict[str, int]:
        return dict(Counter(f.code for f in self.findings).most_common())


CODES: dict[str, str] = {
    "N001": "canonical_name holds an [unknown ...] placeholder",
    "N002": "canonical_name holds a role artefact such as (R)",
    "N003": "canonical_name has a parenthetical suffix — classify before splitting",
    "N004": "canonical_name is a single word — cannot split into first/last",
    "N005": f"canonical_name is {LONG_NAME_WORDS}+ words — may hold two names in one field",
    "N006": "canonical_name is ALL CAPS — casing lost, cannot infer the intended form",
    "N007": "canonical_name contains a comma — may be 'Surname, Forename' order",
    "A001": "address has no recognisable postcode",
    "A002": "address holds a placeholder value",
    "A003": "address has no separator — nothing to split into lines",
    "A004": "address names a third party (MUM/PRISON/etc) — may not be the client's",
    "A005": f"address is under {MIN_ADDRESS_CHARS} chars and a single token",
    "A006": "address has content after the postcode — strip before extracting it",
    "A007": "address contains more than one postcode — two addresses in one field",
    "P001": "phone holds a placeholder value",
    "P002": "phone names a third party",
    "E001": "email holds a placeholder value",
    "R001": "client_role conflicts with this matter's own matter_parties rows",
    "R002": "name carries an (R) artefact but client_role is not Respondent",
    "R003": "matter has no matter_parties row at all",
    "R004": "no address on record for the client in people or a client-side matter_parties row",
    "C001": "client_role is implausibly one-sided across the whole corpus",
    "C002": "client_role values differ only by casing — breaks case-sensitive equality (Postgres, SQLite, Python)",
}


def _words(value: str) -> list[str]:
    return [w for w in re.split(r"\s+", value.strip()) if w]


def check_name(matter_id: Any, name: str, report: Report) -> None:
    if not name or not name.strip():
        return
    if PLACEHOLDER_RE.search(name):
        report.add("N001", "error", matter_id, "placeholder in name")
    if ROLE_ARTEFACT_RE.search(name):
        report.add("N002", "warning", matter_id, "role artefact in name")
    elif "(" in name:
        inner = re.findall(r"\(([^)]*)\)", name)
        shape = "digits" if any(re.search(r"\d", i) for i in inner) else "text"
        report.add("N003", "warning", matter_id, f"parenthetical ({shape})")
    count = len(_words(name))
    if count == 1:
        report.add("N004", "error", matter_id, "1 word")
    elif count >= LONG_NAME_WORDS:
        report.add("N005", "warning", matter_id, f"{count} words")
    if name.isupper() and re.search(r"[A-Z]{2}", name):
        report.add("N006", "warning", matter_id, "all caps")
    if "," in name:
        report.add("N007", "info", matter_id, "comma present")


def _severity(is_client: bool, client_level: str, opponent_level: str) -> str:
    "Rate a missing or junk detail by whose detail it is."
    return client_level if is_client else opponent_level


def check_address(
    matter_id: Any, address: str, report: Report, *, is_client: bool = False
) -> None:
    if not address or not address.strip():
        return
    text = address.strip()
    if PLACEHOLDER_RE.search(text):
        report.add(
            "A002",
            _severity(is_client, "error", "info"),
            matter_id,
            f"placeholder in {'client' if is_client else 'opponent'} address",
        )
    matches = list(POSTCODE_RE.finditer(text))
    if not matches:
        report.add(
            "A001",
            _severity(is_client, "error", "info"),
            matter_id,
            f"no postcode ({'client' if is_client else 'opponent'})",
        )
    elif len(matches) > 1:
        report.add("A007", "error", matter_id, f"{len(matches)} postcodes")
    if matches:
        tail = text[matches[-1].end():].strip(" ,.;")
        if tail:
            report.add("A006", "info", matter_id, f"{len(_words(tail))} word(s) after postcode")
    if not any(sep in text for sep in (",", ";", "\n", " - ")):
        report.add("A003", _severity(is_client, "warning", "info"), matter_id, "no separator")
    if THIRD_PARTY_RE.search(text):
        report.add("A004", "warning", matter_id, "third-party marker")
    if len(text) < MIN_ADDRESS_CHARS and len(_words(text)) <= 1:
        report.add(
            "A005",
            _severity(is_client, "warning", "info"),
            matter_id,
            f"{len(text)} chars, 1 token",
        )


def check_contact(
    matter_id: Any, phone: str, email: str, report: Report, *, is_client: bool = False
) -> None:
    if phone and PLACEHOLDER_RE.search(phone):
        report.add("P001", _severity(is_client, "error", "info"), matter_id, "placeholder in phone")
    if phone and THIRD_PARTY_RE.search(phone):
        report.add("P002", "warning", matter_id, "third-party marker in phone")
    if email and PLACEHOLDER_RE.search(email):
        report.add("E001", _severity(is_client, "error", "info"), matter_id, "placeholder in email")


def check_roles(
    matter_id: Any,
    name: str,
    client_role: str,
    party_roles: list[str],
    report: Report,
) -> None:
    "Roles are the one place a wrong value is worse than a missing one."
    role = (client_role or "").strip().lower()
    if not party_roles:
        report.add("R003", "warning", matter_id, "no matter_parties row")
        return
    lowered = {r.strip().lower() for r in party_roles if r}
    if role == "applicant" and "applicant" in lowered and "respondent" not in lowered:
        report.add("R001", "error", matter_id, "applicant matter, applicant-only parties")
    if role == "respondent" and "respondent" in lowered and "applicant" not in lowered:
        report.add("R001", "error", matter_id, "respondent matter, respondent-only parties")
    if ROLE_ARTEFACT_RE.search(name or "") and role != "respondent":
        report.add("R002", "error", matter_id, f"(R) in name, client_role={role or 'empty'}")


def check_client_address_exists(
    matter_id: Any,
    party_rows: list[tuple],
    client_role: str,
    report: Report,
    person_address: str = "",
) -> None:
    "Is the client's own address recorded anywhere in the client DB for this matter?"
    if (person_address or "").strip():
        return
    role = (client_role or "").strip().lower()
    for party_role, address, _phone, _email in party_rows:
        if (party_role or "").strip().lower() == role and (address or "").strip():
            return
    report.add("R004", "warning", matter_id, "client address not in SQL")


def check_corpus(role_counts: Counter, report: Report) -> None:
    "One-sidedness is invisible per record and obvious in aggregate."
    total = sum(role_counts.values())
    if not total:
        return

    by_fold: dict[str, set[str]] = {}
    for value in role_counts:
        by_fold.setdefault(value.strip().lower(), set()).add(value)
    for folded, variants in sorted(by_fold.items()):
        if len(variants) > 1:
            shape = ", ".join(f"{v!r}={role_counts[v]}" for v in sorted(variants))
            report.add(
                "C002",
                "error",
                "-",
                f"{folded!r} stored as {len(variants)} different casings: {shape} — "
                "any WHERE client_role = 'Applicant' silently misses the others",
            )

    folded_counts = Counter()
    for value, count in role_counts.items():
        folded_counts[value.strip().lower()] += count
    role_counts = folded_counts
    minority = min(role_counts.values()) if len(role_counts) > 1 else 0
    if len(role_counts) < 2 or (minority / total) < 0.01:
        shape = ", ".join(f"{k or 'empty'}={v}" for k, v in role_counts.most_common())
        report.add(
            "C001",
            "error",
            "-",
            f"{shape} across {total} matters — a firm acting on both sides cannot "
            "look like this; see the archived STATUS §M item 3",
        )


def run(limit: int = 0) -> Report:
    import clientdb_sql

    report = Report()
    role_counts: Counter = Counter()

    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.matter_id, m.canonical_name, m.client_role,
                   p.address_text, p.address_line1, p.address_postcode
            FROM matters m
            LEFT JOIN people p ON p.person_id = m.primary_person_id
            ORDER BY m.matter_id
            """
        )
        matters = cur.fetchall()
        if limit:
            matters = matters[:limit]

        cur.execute(
            """
            SELECT matter_id, role, address_text, phone_primary, email_primary
            FROM matter_parties
            """
        )
        parties: dict[str, list[tuple]] = {}
        for row in cur.fetchall():
            parties.setdefault(str(row[0]), []).append(row)

    report.counts["matters"] = len(matters)
    report.counts["parties"] = sum(len(v) for v in parties.values())

    for matter_id, name, client_role, *person_address_parts in matters:
        role_counts[(client_role or "").strip()] += 1
        check_name(matter_id, name or "", report)
        rows = parties.get(str(matter_id), [])
        check_roles(matter_id, name or "", client_role or "", [r[1] for r in rows], report)
        party_rows = [tuple(r[1:]) for r in rows]
        person_address = " ".join(str(v or "").strip() for v in person_address_parts)
        check_client_address_exists(
            matter_id, party_rows, client_role or "", report, person_address=person_address
        )
        client_side = (client_role or "").strip().lower()
        for party_role, address, phone, email in party_rows:
            is_client = (party_role or "").strip().lower() == client_side
            check_address(matter_id, address or "", report, is_client=is_client)
            check_contact(matter_id, phone or "", email or "", report, is_client=is_client)

    check_corpus(role_counts, report)
    report.counts["addresses_present"] = sum(
        1 for rows in parties.values() for r in rows if (r[2] or "").strip()
    )
    return report


def sample(matter_id: str) -> int:
    "Print the raw values for exactly one matter."
    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT matter_id, canonical_name, client_role FROM matters WHERE matter_id = ?",
            (matter_id,),
        )
        row = cur.fetchone()
        if not row:
            print(f"no matter {matter_id}", file=sys.stderr)
            return 1
        print(f"matter_id     : {row[0]}")
        print(f"canonical_name: {row[1]!r}")
        print(f"client_role   : {row[2]!r}")
        cur.execute(
            "SELECT role, display_name, address_text, phone_primary, email_primary "
            "FROM matter_parties WHERE matter_id = ?",
            (matter_id,),
        )
        for party in cur.fetchall():
            print(f"  party role  : {party[0]!r}")
            print(f"    name      : {party[1]!r}")
            print(f"    address   : {party[2]!r}")
            print(f"    phone     : {party[3]!r}")
            print(f"    email     : {party[4]!r}")
    return 0


def print_human(report: Report) -> None:
    print(
        f"matters {report.counts.get('matters', 0)}, "
        f"parties {report.counts.get('parties', 0)}, "
        f"addresses present {report.counts.get('addresses_present', 0)}"
    )
    print(f"findings {len(report.findings)} ({report.errors} error)")
    print()
    by_code = report.by_code()
    width = max((len(c) for c in by_code), default=4)
    for code, count in by_code.items():
        severity = next(f.severity for f in report.findings if f.code == code)
        print(f"  {code:<{width}}  {severity:<7} {count:>4}  {CODES.get(code, '')}")
    corpus = [f for f in report.findings if f.code == "C001"]
    for finding in corpus:
        print(f"\n  C001: {finding.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="Full findings as JSON (PII-safe).")
    parser.add_argument("--code", default="", help="Show matter ids for one finding code.")
    parser.add_argument("--limit", type=int, default=0, help="Check only the first N matters.")
    parser.add_argument(
        "--sample",
        default="",
        help="Print raw values for ONE matter id. The deliberate PII exception.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit 1 when any error-severity finding exists (for CI use).",
    )
    args = parser.parse_args(argv)

    if args.sample:
        if len(args.sample.split(",")) > 1:
            print("--sample takes one matter id, not a list.", file=sys.stderr)
            return 2
        return sample(args.sample.strip())

    report = run(limit=args.limit)

    if args.code:
        code = args.code.upper()
        ids = [f.matter_id for f in report.findings if f.code == code]
        print(f"{code}: {len(ids)} matter(s) — {CODES.get(code, 'unknown code')}")
        print(" ".join(ids))
    elif args.json:
        print(
            json.dumps(
                {
                    "schema": "caseforge.client-details-lint.v1",
                    "generated_utc": dt.datetime.now(dt.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "counts": report.counts,
                    "by_code": report.by_code(),
                    "codes": CODES,
                    "findings": [f.as_dict() for f in report.findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_human(report)

    return 1 if (args.fail_on_error and report.errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
