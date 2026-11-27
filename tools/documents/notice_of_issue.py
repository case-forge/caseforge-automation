#!/usr/bin/env python3
"Notice of Issue of Certificate (the Legal Aid Agency's NOTICE 1) maker: a prototype, on trial."
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

TEMPLATE = REPO_ROOT / "templates" / "PDF Templates" / "LAA Notice of Issue -.pdf"
TRIAL_DIR = REPO_ROOT / "tmp" / "notice-of-issue-trial"
TBC = "TBC"

CASE_NUMBER = "FillText9"
COURT = "FillText10"
DIVISION = "FillText11"
APPLICANT = "FillText12"
RESPONDENT = "FillText13"
CERTIFICATE_NUMBER = "FillText14"
DATED_DAY = "FillText19"
DATED_MONTH_YEAR = "FillText20"
ISSUED_TO = "FillText21"
EMERGENCY = "CheckBox1"
SUBSTANTIVE = "CheckBox2"
INVESTIGATIVE_HELP = "CheckBox3"
FULL_REPRESENTATION = "CheckBox4"
FAMILY_HELP_HIGHER = "CheckBox5"
SCOPE = "FillText22"
EXPIRES = "FillText23"
NOTICE_DATED = "FillText24"
SIGNER_FIRM = "FillText26"
SOLICITOR_FOR = "FillText27"
ADDRESSED_TO = "FillText28"

CERTIFICATE_TYPE, LEVEL_OF_SERVICE = "certificate_type", "level_of_service"
FIELD_LABELS: dict[str, str] = {
    CASE_NUMBER: "case number",
    COURT: "court",
    APPLICANT: "applicant",
    RESPONDENT: "respondent",
    CERTIFICATE_NUMBER: "certificate number",
    DATED_DAY: "certificate date (day)",
    DATED_MONTH_YEAR: "certificate date (month and year)",
    ISSUED_TO: "issued to",
    CERTIFICATE_TYPE: "emergency or substantive",
    LEVEL_OF_SERVICE: "level of service",
    SCOPE: "scope",
    EXPIRES: "emergency expiry",
    NOTICE_DATED: "notice dated",
    SIGNER_FIRM: "firm",
    SOLICITOR_FOR: "solicitor for",
    ADDRESSED_TO: "addressed to",
}
LEVEL_BOXES = {"investigative help": INVESTIGATIVE_HELP, "full representation": FULL_REPRESENTATION, "family help (higher)": FAMILY_HELP_HIGHER}
FORM_FIELDS = frozenset({*(k for k in FIELD_LABELS if k not in (CERTIFICATE_TYPE, LEVEL_OF_SERVICE)), DIVISION, EMERGENCY, SUBSTANTIVE, *LEVEL_BOXES.values()})
SCOPE_LINE_CHARS, SCOPE_LINES = 90, 3
CASE_NUMBER_CHARS = 25
MAX_CERTIFICATE_BYTES = 5_000_000

_DATE = r"(\d{2}/\d{2}/\d{4})"




@dataclasses.dataclass
class Proceeding:
    title: str = ""
    status: str = ""
    description: str = ""
    involvement: str = ""
    form_of_service: str = ""
    limitation_end_dates: tuple[str, ...] = ()


@dataclasses.dataclass
class Certificate:
    "What one certificate's text says. A field the text does not give for certain is empty."

    reference: str = ""
    letter_date: str = ""
    amended: bool = False
    client_name: str = ""
    kind: str = ""
    status: str = ""
    effective_date: str = ""
    end_date: str = ""
    proceedings: tuple[Proceeding, ...] = ()
    source: str = ""

    @property
    def live_proceedings(self) -> tuple[Proceeding, ...]:
        return tuple(p for p in self.proceedings if p.status.lower() == "live")


def pdf_text(pdf_bytes: bytes) -> str:
    "The PDF's own text layer in reading layout (``pdftotext -layout``), or \"\" when it has none or cannot be read."
    try:
        done = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf_bytes, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else ""


def is_certificate_text(text: str) -> bool:
    "The text is a civil legal aid certificate (not a marriage certificate or a certificate of service, which"
    return bool(re.search(r"CIVIL LEGAL AID CERTIFICATE", text) and re.search(r"Reference Number:\s*\d", text))


def _first(pattern: str, text: str) -> str:
    found = re.search(pattern, text, re.M)
    return " ".join(found.group(1).split()) if found and found.group(1) else ""


def _proceedings(text: str) -> tuple[Proceeding, ...]:
    "The proceedings in the certificate's Notice: each starts at a \"Current Status:\" line. The description is"
    _, _, notice = text.partition("Proceeding(s)")
    lines = notice.splitlines()
    starts = [i for i, line in enumerate(lines) if "Current Status:" in line]
    out: list[Proceeding] = []
    for n, start in enumerate(starts):
        block = lines[start:starts[n + 1] if n + 1 < len(starts) else len(lines)]
        head = re.match(r"\s*(.*?)\s*-?\s*Current Status:\s*(\S*)", block[0])
        body = "\n".join(block[1:])
        work = next((i for i, line in enumerate(block) if re.match(r"\s*Date work can", line)), 0)
        described = next((i for i, line in enumerate(block[:work]) if re.match(r"\s*to be\b", line, re.I)), 0)
        description = " ".join(" ".join(line.split()) for line in block[described:work]) if described else ""
        _, table, limits = body.partition("Effective Date")
        ends = re.findall(rf"{_DATE}\s+{_DATE}\s*$", limits, re.M) if table else []
        out.append(Proceeding(
            title=" ".join((head.group(1) if head else "").split()),
            status=(head.group(2) if head else "").strip(),
            description=description.strip(),
            involvement=_first(r"^\s*Client involvement type:[ \t]*(.+)$", body),
            form_of_service=_first(r"^\s*Form of Service:[ \t]*(.+)$", body),
            limitation_end_dates=tuple(dict.fromkeys(end for _start, end in ends)),
        ))
    return tuple(out)


def read_certificate(text: str, *, source: str = "") -> Certificate | None:
    "The certificate the text holds, or None when the text is not a civil legal aid certificate."
    if not is_certificate_text(text):
        return None
    letter, _, cert = text.partition("CIVIL LEGAL AID CERTIFICATE")
    summary = cert.partition("Certificate Summary")[2].partition("Proceeding(s)")[0]
    kind = re.search(r"^\s*(Emergency|Substantive)\s+Certificate\s+Status:[ \t]*(\S*)", summary, re.M)
    return Certificate(
        reference=_first(r"Reference Number:\s*(\d{6,})\b", cert),
        letter_date=_first(rf"^\s*Date:\s*{_DATE}\s*$", letter),
        amended=bool(re.search(r"application\s+to\s+amend", letter)),
        client_name=_first(r"^\s*Client Name[ \t]+(\S.*)$", cert),
        kind=kind.group(1) if kind else "",
        status=kind.group(2) if kind else "",
        effective_date=_first(rf"^\s*Effective Date:[ \t]*{_DATE}", summary),
        end_date=_first(rf"^\s*End Date:[ \t]*{_DATE}", summary),
        proceedings=_proceedings(cert),
        source=source,
    )


def _date(value: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def _name_words(name: str) -> set[str]:
    return set(re.findall(r"[a-z]+", re.sub(r"\([^)]*\)", " ", str(name or "").lower().replace("'", ""))))


def same_person(a: str, b: str) -> bool:
    "Two names are one person when one name's words are all in the other (a middle name may be missing), and at"
    one, two = _name_words(a), _name_words(b)
    return len(one & two) >= 2 and (one <= two or two <= one)


def choose_certificates(found: Iterable[Certificate]) -> list[Certificate]:
    "One certificate per reference number: the newest by its letter's date, a substantive one before an"
    def rank(cert: Certificate) -> tuple[dt.date, bool]:
        return (_date(cert.letter_date) or dt.date.min, cert.kind == "Substantive")

    best: dict[str, Certificate] = {}
    for cert in found:
        if cert.reference not in best or rank(cert) > rank(best[cert.reference]):
            best[cert.reference] = cert
    return [best[ref] for ref in sorted(best)]




@dataclasses.dataclass
class MatterFacts:
    "What the matter record holds. Read, never re-parsed from papers."

    matter_id: str
    client_name: str = ""
    client_role: str = "Applicant"
    other_party: str = ""
    court: str = ""
    court_from_hearings: bool = False
    case_numbers: tuple[str, ...] = ()
    folder_path: str = ""


def load_matter_facts(matter_id: str) -> MatterFacts:
    "The parties, the court and the case numbers from the client database (read only)."
    import clientdb_sql
    from documents.court_of_record import hearing_courts_for_matters, recorded_court_name
    from onboarding import notice_of_acting as noa
    from onboarding.pipeline import load_context

    ctx = load_context(matter_id)
    role, _warning = noa.client_party_role(noa.fetch_matter_details(ctx.matter_id))
    court, from_hearings = recorded_court_name(ctx.matter_id), False
    if not court:
        named = hearing_courts_for_matters([ctx.matter_id]).get(ctx.matter_id, set())
        if len({court_place(name).lower() for name in named}) == 1:
            court, from_hearings = sorted(named)[0], True
    return MatterFacts(
        matter_id=ctx.matter_id,
        client_name=re.sub(r"(?:\s*\([^)]*\))+\s*$", "", ctx.client_name).strip(),
        client_role=role,
        other_party=ctx.respondent,
        court=court,
        court_from_hearings=from_hearings,
        case_numbers=tuple(dict.fromkeys(clientdb_sql.get_court_references(ctx.matter_id))),
        folder_path=ctx.folder_path,
    )


def court_place(court: str) -> str:
    "The court as the form's \"IN THE ____ [FAMILY COURT]\" line takes it: the place the firm's court heading"
    from documents.court_heading import court_line

    if not str(court or "").strip():
        return ""
    return re.sub(r"(?i)^in the (?:family court sitting at )?", "", court_line(court)).strip()




def _scope(cert: Certificate) -> tuple[str, str]:
    "``(scope, why not)``: each live proceeding's own description, once each. The limitations are not copied:"
    live = cert.live_proceedings
    if not live:
        return "", "the certificate lists no live proceeding"
    if any(not p.description for p in live):
        return "", "a proceeding's description could not be read"
    parts = dict.fromkeys(p.description if p.description.endswith(".") else p.description + "." for p in live)
    return " ".join(part[0].upper() + part[1:] for part in parts), ""


def _lines_needed(text: str) -> int:
    lines, used = 1, 0
    for word in text.split():
        if used and used + 1 + len(word) > SCOPE_LINE_CHARS:
            lines, used = lines + 1, len(word)
        else:
            used += (1 if used else 0) + len(word)
    return lines


def build_fields(facts: MatterFacts, cert: Certificate | None, *, today: dt.date, firm_name: str) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    "``(the form's fields, what is TBC and why, notes)``. A field is filled only from the matter record or from"
    fields: dict[str, Any] = {}
    tbc: dict[str, str] = {}
    notes: list[str] = []

    def put(key: str, value: str, why: str) -> None:
        if str(value or "").strip():
            fields[key] = str(value).strip()
        else:
            tbc[FIELD_LABELS[key]] = why

    client_is_applicant = facts.client_role != "Respondent"
    no_client, no_other = "no client name on the matter record", "no other party on the matter record"
    put(CASE_NUMBER, " / ".join(facts.case_numbers), "no court case number on the matter record")
    if len(" / ".join(facts.case_numbers)) > CASE_NUMBER_CHARS:
        notes.append("the matter's case numbers are longer than the box: check how they print")
    put(COURT, court_place(facts.court), "no court on the matter record, and its hearings do not name one court")
    if facts.court and facts.court_from_hearings:
        notes.append("the matter has no court of record: the court is the one its hearings name")
    put(APPLICANT, facts.client_name if client_is_applicant else facts.other_party, no_client if client_is_applicant else no_other)
    put(RESPONDENT, facts.other_party if client_is_applicant else facts.client_name, no_other if client_is_applicant else no_client)
    put(ISSUED_TO, facts.client_name, no_client)
    put(SOLICITOR_FOR, facts.client_role, "the client's side is not recorded")
    put(SIGNER_FIRM, firm_name, "no firm name in the firm profile")
    fields[NOTICE_DATED] = today.strftime("%d/%m/%Y")
    tbc[FIELD_LABELS[ADDRESSED_TO]] = "who the notice is served on (the court, the other party or their solicitors) is not on the matter record"

    no_cert = "no certificate could be read"
    put(CERTIFICATE_NUMBER, cert.reference if cert else "", "no reference number in the certificate" if cert else no_cert)
    issued = _date(cert.letter_date) if cert else None
    if issued:
        fields[DATED_DAY] = str(issued.day)
        fields[DATED_MONTH_YEAR] = f"{issued:%b %Y}"
        if cert.amended:
            notes.append("the certificate on file is an amended one: the date is its covering letter's, the day the amendment was granted")
    else:
        tbc[FIELD_LABELS[DATED_DAY]] = tbc[FIELD_LABELS[DATED_MONTH_YEAR]] = "no date on the certificate's covering letter" if cert else no_cert

    kind = cert.kind if cert else ""
    if kind == "Emergency":
        fields[EMERGENCY] = True
    elif kind == "Substantive":
        fields[SUBSTANTIVE] = True
    else:
        tbc[FIELD_LABELS[CERTIFICATE_TYPE]] = "the certificate summary names neither Emergency nor Substantive" if cert else no_cert
    if kind and cert.status.lower() != "live":
        notes.append(f"the certificate's status reads {cert.status or 'nothing'!r}, not Live: check it before this notice is used")

    levels = list(dict.fromkeys(p.form_of_service for p in cert.live_proceedings)) if cert else []
    unknown = [level for level in levels if level.lower() not in LEVEL_BOXES]
    if not cert:
        tbc[FIELD_LABELS[LEVEL_OF_SERVICE]] = no_cert
    elif not levels or unknown:
        tbc[FIELD_LABELS[LEVEL_OF_SERVICE]] = f"a form of service the form has no box for: {', '.join(repr(u) for u in unknown)}" if levels else "no form of service on a live proceeding"
    else:
        for level in levels:
            fields[LEVEL_BOXES[level.lower()]] = True
        if len(levels) > 1:
            notes.append("the proceedings have different levels of service, so more than one box is ticked: " + ", ".join(levels))

    scope, why = _scope(cert) if cert else ("", no_cert)
    put(SCOPE, scope, why)
    if scope and _lines_needed(scope) > SCOPE_LINES:
        notes.append("the scope is longer than the box's three lines: check how it prints")

    if kind == "Emergency":
        if cert.end_date:
            fields[EXPIRES] = cert.end_date
        else:
            ends = sorted({end for p in cert.live_proceedings for end in p.limitation_end_dates}, key=lambda d: _date(d) or dt.date.max)
            seen = f" (a limitation ends on {', '.join(ends)}: not taken as the expiry)" if ends else ""
            tbc[FIELD_LABELS[EXPIRES]] = "the certificate summary gives no end date" + seen
    elif not cert:
        tbc[FIELD_LABELS[EXPIRES]] = no_cert
    return fields, tbc, notes


def filled_labels(fields: dict[str, Any]) -> list[str]:
    "The report's words for what was filled, in the form's order."
    have = {key for key in FIELD_LABELS if key in fields}
    if fields.get(EMERGENCY) or fields.get(SUBSTANTIVE):
        have.add(CERTIFICATE_TYPE)
    if any(fields.get(box) for box in LEVEL_BOXES.values()):
        have.add(LEVEL_OF_SERVICE)
    return [label for key, label in FIELD_LABELS.items() if key in have]


def fill_notice(*, output: Path, fields: dict[str, Any], template: Path = TEMPLATE) -> dict[str, Any]:
    "Fill a copy of the form at ``output`` (a path on this machine)."
    from documents.pdf_acroform_fill import fill_acroform

    return fill_acroform(template=template, output=output, facts=fields)




def notice_state(pdf_bytes: bytes, *, firm_name: str = "", template: Path = TEMPLATE) -> str:
    "What a file named as a Notice of Issue really is. Every new client folder is made with a blank copy of the"
    if hashlib.sha256(pdf_bytes).digest() == hashlib.sha256(template.read_bytes()).digest():
        return "blank"
    try:
        from pypdf import PdfReader

        got = PdfReader(io.BytesIO(pdf_bytes)).get_fields() or {}
    except Exception:
        return "unreadable"
    values = {key: str(got[key].get("/V") or "").strip() for key in got if key in FORM_FIELDS}
    if not values:
        return "flat"
    if not any(v and v != "/Off" for v in values.values()):
        return "blank"
    of = re.sub(r"[^a-z]", "", values.get(SIGNER_FIRM, "").lower())
    firm = re.sub(r"[^a-z]", "", firm_name.lower())
    if firm and of and not (of[:10] in firm or firm[:10] in of):
        return "other firm"
    return "filled"


def is_notice_name(name: str) -> bool:
    "A file name that reads as a Notice of Issue (PDF only)."
    low = re.sub(r"[^a-z0-9.]+", " ", str(name or "").lower())
    return low.endswith(".pdf") and bool(re.search(r"notice ?of ?issue", low))


def notices_on_file(
    folder_path: str,
    *,
    firm_name: str,
    indexed: Callable[[str], list[tuple[str, int]]] | None = None,
    download: Callable[[str], bytes] | None = None,
    template: Path = TEMPLATE,
) -> dict[str, int]:
    "How many files named as a Notice of Issue the matter folder holds, by what each really is"
    blank_size = template.stat().st_size
    counts: dict[str, int] = {}
    for path, size in (indexed or _indexed_notices)(folder_path):
        if size == blank_size:
            state = "blank"
        else:
            try:
                state = notice_state((download or _download)(path), firm_name=firm_name, template=template)
            except Exception:
                state = "unreadable"
        counts[state] = counts.get(state, 0) + 1
    return counts




def _firm_name() -> str:
    import firm_profile

    return firm_profile.load_profile().legal_rep_firm


def _today() -> dt.date:
    import london_time

    return london_time.london_today()


def _root_listing(folder_path: str) -> list[dict[str, Any]]:
    import graph_files

    return list(graph_files.list_children(folder_path).get("value", []))


def _download(path: str) -> bytes:
    from onboarding.pipeline import court_common

    return court_common.download(path)


def _like(path: str) -> str:
    return path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _indexed_files(folder_path: str, *, root_only: bool = False) -> list[tuple[str, int]]:
    "``(path, size)`` of the files under a folder, from the OneDrive index the system keeps (no Graph call)."
    import ops_db

    query = "SELECT path, size_bytes FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'file' AND path LIKE ? ESCAPE '\\'"
    params = [_like(folder_path) + "/%"]
    if root_only:
        query += " AND path NOT LIKE ? ESCAPE '\\'"
        params.append(_like(folder_path) + "/%/%")
    with ops_db.connect() as conn:
        return [(str(path), int(size or 0)) for path, size in conn.execute(query, params).fetchall()]


def _indexed_notices(folder_path: str) -> list[tuple[str, int]]:
    return [(path, size) for path, size in _indexed_files(folder_path) if is_notice_name(path.rsplit("/", 1)[-1])]


def is_certificate_name(name: str) -> bool:
    "A PDF the certificate detector names (``milestones._certificate_milestone``, the one detector)."
    from onboarding.pipeline import milestones

    return str(name or "").lower().endswith(".pdf") and bool(milestones._certificate_milestone(str(name or "")))


def make_for_matter(
    matter_id: str,
    *,
    out_dir: Path = TRIAL_DIR,
    skip_if_filled: bool = False,
    facts: MatterFacts | None = None,
    listing: Callable[[str], list[dict[str, Any]]] | None = None,
    download: Callable[[str], bytes] | None = None,
    indexed: Callable[[str], list[tuple[str, int]]] | None = None,
    today: dt.date | None = None,
    firm_name: str | None = None,
    template: Path = TEMPLATE,
) -> dict[str, Any]:
    "Make the matter's Notice of Issue into ``out_dir`` and say what was filled and what is TBC. The report"
    facts = facts or load_matter_facts(matter_id)
    firm = firm_name if firm_name is not None else _firm_name()
    download = download or _download
    report: dict[str, Any] = {"matter_id": facts.matter_id, "status": "", "outputs": [], "skipped": [], "certificates": 0}
    if not facts.folder_path:
        return {**report, "status": "no folder", "why": "the matter has no recorded folder"}
    report["notices_on_file"] = notices_on_file(facts.folder_path, firm_name=firm, indexed=indexed, download=download, template=template)
    if skip_if_filled and report["notices_on_file"].get("filled"):
        return {**report, "status": "already has a filled notice", "why": "the folder holds a notice this firm filled"}

    read: list[Certificate] = []
    for item in (listing or _root_listing)(facts.folder_path):
        name = str(item.get("name") or "")
        if "file" not in item or not is_certificate_name(name):
            continue
        if int(item.get("size") or 0) > MAX_CERTIFICATE_BYTES:
            report["skipped"].append("a file named as a certificate is too large to be one (a scan or another paper)")
            continue
        text = pdf_text(download(f"{facts.folder_path}/{name}"))
        cert = read_certificate(text, source=name)
        if not text.strip():
            report["skipped"].append("a file named as a certificate has no text layer (a scan): it would need OCR, which this does not do")
        elif cert is None:
            report["skipped"].append("a file named as a certificate is not a legal aid certificate")
        elif not same_person(cert.client_name, facts.client_name):
            report["skipped"].append("a certificate names somebody other than the client on the matter record")
        else:
            read.append(cert)
    report["skipped"] = list(dict.fromkeys(report["skipped"]))
    chosen = choose_certificates(read)
    report["certificates"] = len(chosen)
    if not chosen:
        return {**report, "status": "no certificate", "why": "no certificate in the matter folder could be read"}
    if len(chosen) > 1:
        report["skipped"].append("the folder holds certificates with different reference numbers: one notice was made for each")

    out_dir.mkdir(parents=True, exist_ok=True)
    for n, cert in enumerate(chosen, start=1):
        fields, tbc, notes = build_fields(facts, cert, today=today or _today(), firm_name=firm)
        output = out_dir / (f"{facts.matter_id}.pdf" if n == 1 else f"{facts.matter_id}-{n}.pdf")
        filled = fill_notice(output=output, fields=fields, template=template)
        if filled["missing_fields"] or filled["overlong_fields"]:
            notes.append("the form refused a field: " + ", ".join([*filled["missing_fields"], *filled["overlong_fields"]]))
        report["outputs"].append({
            "file": output.name,
            "certificate_type": cert.kind or TBC,
            "filled": filled_labels(fields),
            "tbc": tbc,
            "notes": notes,
        })
    return {**report, "status": "made"}




def trial_candidates() -> list[str]:
    "Open matters with a recorded folder that, in the OneDrive index, holds a PDF the certificate detector names"
    from onboarding.pipeline import load_context, open_matter_ids

    out: list[str] = []
    for mid in open_matter_ids():
        folder = load_context(mid).folder_path
        if folder and any(is_certificate_name(path.rsplit("/", 1)[-1]) for path, _size in _indexed_files(folder, root_only=True)):
            out.append(mid)
    return out


def run_trial(*, out_dir: Path = TRIAL_DIR, limit: int | None = None, candidates: list[str] | None = None, make: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    "Run the maker on every candidate, leaving alone a matter whose folder already holds a notice the firm"
    make = make or make_for_matter
    rows: list[dict[str, Any]] = []
    for mid in candidates if candidates is not None else trial_candidates():
        if limit is not None and sum(1 for r in rows if r.get("status") == "made") >= limit:
            break
        try:
            rows.append(make(mid, out_dir=out_dir, skip_if_filled=True))
        except Exception as exc:
            rows.append({"matter_id": mid, "status": "failed", "why": type(exc).__name__, "outputs": []})
    return {"matters": rows, "summary": summarise(rows)}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    "Counts by status and, for each field, how often it was filled out of the notices it applies to (the"
    statuses: dict[str, int] = {}
    hits = {label: [0, 0] for label in FIELD_LABELS.values()}
    made = 0
    for row in rows:
        statuses[row.get("status", "")] = statuses.get(row.get("status", ""), 0) + 1
        for output in row.get("outputs", []):
            made += 1
            for label in hits:
                if label in output["filled"] or label in output["tbc"]:
                    hits[label][1] += 1
                hits[label][0] += label in output["filled"]
    return {"statuses": statuses, "notices_made": made, "field_hits": {label: {"filled": got, "of": of} for label, (got, of) in hits.items()}}


def table(result: dict[str, Any]) -> str:
    "The trial as a Markdown table: one line per notice made, matter numbers and field names only."
    lines = ["| Matter | File | Type | Filled | TBC (why) | Notes |", "| --- | --- | --- | --- | --- | --- |"]
    for row in result["matters"]:
        extra = "; ".join(row.get("skipped", []))
        if not row.get("outputs"):
            lines.append(f"| {row['matter_id']} | - | - | - | - | {row.get('status', '')}: {'; '.join(x for x in (row.get('why', ''), extra) if x)} |")
        for made in row.get("outputs", []):
            tbc = "; ".join(f"{k} ({v})" for k, v in made["tbc"].items()) or "-"
            notes = "; ".join([*made["notes"], *([extra] if extra else [])]) or "-"
            lines.append(f"| {row['matter_id']} | {made['file']} | {made['certificate_type']} | {len(made['filled'])} of {len(made['filled']) + len(made['tbc'])} | {tbc} | {notes} |")
    summary = result["summary"]
    lines += ["", f"Notices made: {summary['notices_made']}. By status: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["statuses"].items())) + ".", ""]
    lines += ["| Field | Filled |", "| --- | --- |"]
    lines += [f"| {label} | {hit['filled']} of {hit['of']} |" for label, hit in summary["field_hits"].items()]
    return "\n".join(lines) + "\n"




def _scratch(path: str) -> Path:
    "The output path, which must be on this machine: a OneDrive or web address is refused."
    if re.match(r"(?i)^\s*(https?:|company_data/|onedrive)", path):
        raise SystemExit("The notice is made to a scratch folder on this machine only, never to a client's folder.")
    return Path(path).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("make", help="make one matter's notice into the scratch folder")
    one.add_argument("--matter-id", required=True)
    one.add_argument("--out-dir", default=str(TRIAL_DIR))
    many = sub.add_parser("trial", help="make a notice for every open matter with a certificate and no filled notice")
    many.add_argument("--limit", type=int, default=None, help="stop after this many matters have had a notice made")
    many.add_argument("--out-dir", default=str(TRIAL_DIR))
    bare = sub.add_parser("fill", help="fill the form from a JSON file of field names and values (no matter is read)")
    bare.add_argument("--facts-json", required=True)
    bare.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    if args.command == "fill":
        report = fill_notice(output=_scratch(args.output), fields=json.loads(Path(args.facts_json).read_text(encoding="utf-8")))
        print(json.dumps(report, indent=2))
        return 1 if report["missing_fields"] else 0
    out_dir = _scratch(args.out_dir)
    if args.command == "make":
        report = make_for_matter(args.matter_id, out_dir=out_dir)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "made" else 1
    result = run_trial(out_dir=out_dir, limit=args.limit)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trial.md").write_text(table(result), encoding="utf-8")
    import atomic_json

    atomic_json.atomic_write_json(out_dir / "trial.json", result)
    print(table(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
