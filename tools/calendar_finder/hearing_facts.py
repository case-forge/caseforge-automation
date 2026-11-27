
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Callable

CASE_REF_RE = re.compile(r"\b[A-Z]{1,3}\d{2}[A-Z]\d{5}\b", re.IGNORECASE | re.ASCII)

_STRONG_WORDS = (
    r"hearings?", r"listed", r"listing", r"re-?listed", r"fhdra", r"fdra", r"dra", r"first appointment",
    r"directions appointment", r"dispute resolution appointment", r"pre-?trial review",
    r"case management (?:conference|hearing)", r"issues resolution hearing", r"fact[- ]finding",
    r"(?<!free\s)(?<!your\s)(?<!start\s)trial(?!\s+(?:period|run|offer|contact|separation|basis|version|subscription|and error|of\s+our))",
    r"fixed for", r"will be heard", r"to be heard", r"attend(?:ance)?(?: at)?(?: the)? court", r"committal",
    r"return date", r"court date", r"cmc", r"cmh", r"pta", r"ptr", r"irh", r"fdr", r"mention hearing", r"in the list",
    r"gwrandawiad(?:au)?", r"mention(?=\s+(?:is|will|on|at|listed|for|date))", r"appointment\s+at\s+court",
    r"(?:is|are|will\s+be|to\s+be)\s+before\s+(?:the\s+)?(?:district\s+judge|circuit\s+judge|judge|recorder|bench|magistrates|deputy)",
    r"will\s+(?:next\s+)?(?:consider|see\s+the\s+parties)", r"handed\s+down", r"to\s+be\s+considered",
)
_GATE_ONLY_WORDS = (
    r"directions", r"appointment", r"mention", r"conference", r"contested (?:hearing|application)", r"vacated", r"adjourned",
    r"cancell?ed", r"final hearing",
)
HEARING_WORD_RE = re.compile(r"\b(?:" + "|".join(_STRONG_WORDS) + r")\b", re.IGNORECASE | re.ASCII)
HEARING_GATE_RE = re.compile(r"\b(?:" + "|".join((*_STRONG_WORDS, *_GATE_ONLY_WORDS)) + r")\b", re.IGNORECASE | re.ASCII)

_NONHEARING_EVENT_RE = re.compile(
    r"\b(?:mediation|miam|meeting|call|consultation|our\s+office|catch[- ]?up|interview|assessment|home\s+visit|contact\s+(?:session|handover)|handover|"
    r"supervised\s+contact|spend\s+time|nursery|school|doctor|gp)\b",
    re.IGNORECASE,
)

_PURPOSE_BEFORE_RE = re.compile(
    r"(?:\bto\s+(?:prepare\s+for|discuss|talk\s+about|go\s+over|review)|\bprepare\s+for|\bpreparing\s+for|\bpreparation\s+for|"
    r"\bprior\s+to|\bahead\s+of|\bbefore|\bin\s+advance\s+of)\s+(?:the\s+|your\s+|our\s+|a\s+)?"
    r"(?:(?:forthcoming|upcoming|next|final|first|full|coming|proposed)\s+)*$",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_RE = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_ORD = r"(?:st|nd|rd|th)?"

_WEEKDAY = r"(?:(?:mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:day)?\.?,?\s+)?"
_RANGE_RE = re.compile(
    rf"\b{_WEEKDAY}(\d{{1,2}}){_ORD}((?:\s*(?:,|&|/|-|–|to|until|and|or)\s*{_WEEKDAY}\d{{1,2}}{_ORD})+)(?:\s+of)?\s+({_MONTH_RE})\b\.?,?(?:\s+(\d{{4}}))?",
    re.IGNORECASE | re.ASCII,
)
_LIST_SEP_RE = re.compile(r",|&|/|-|–|\bto\b|\buntil\b|\band\b|\bor\b", re.IGNORECASE)
_WEEKDAY_BEFORE_RE = re.compile(r"\b(mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)[a-z]*\.?,?\s+(?:the\s+)?$", re.IGNORECASE)
_WEEKDAY_INDEX = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "weds": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
_FROM_RESCHEDULE_BEFORE_RE = re.compile(
    r"\b(?:moved|changed|switched|adjourned|relisted|re-listed|rescheduled|postponed|transferred|put\s+back|brought\s+forward|deferred)\s+from\s+(?:the\s+)?(?:\w+day\s+)?$",
    re.IGNORECASE,
)
_MONTH_FIRST_RE = re.compile(rf"\b({_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)\b(?:,?\s+(\d{{4}}))?", re.IGNORECASE | re.ASCII)
_TEXT_DATE_RE = re.compile(rf"\b(\d{{1,2}}){_ORD}(?:\s+of)?\s+({_MONTH_RE})\b\.?,?(?:\s+(\d{{4}})\b)?", re.IGNORECASE | re.ASCII)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b", re.ASCII)
_NUM_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})\b", re.ASCII)

_AMPM = r"(?:\s*([ap])\.?m\.?)"
_TIME_COLON_RE = re.compile(rf"(?<![\d:.])(\d{{1,2}}):(\d{{2}})(?::\d{{2}})?(?!\d|:\d){_AMPM}?(?!\w)", re.IGNORECASE | re.ASCII)
_TIME_DOT_RE = re.compile(rf"(?<![\d:.£$])(\d{{1,2}})\.(\d{{2}})(?![\d:])(?!\.\d){_AMPM}?(?!\w)", re.IGNORECASE | re.ASCII)
_TIME_HOUR_AMPM_RE = re.compile(r"(?<![\d:.])(\d{1,2})\s*([ap])\.?m\b\.?", re.IGNORECASE | re.ASCII)
_TIME_24H_RE = re.compile(r"(?<![\d:.])([01]\d|2[0-3])([0-5]\d)\s*(?:hrs|hours|h)\b", re.IGNORECASE | re.ASCII)
_TIME_NOON_RE = re.compile(r"\b(?:12\s+noon|noon|midday)\b", re.IGNORECASE | re.ASCII)
_TIME_OCLOCK_RE = re.compile(r"\b(\d{1,2})\s*o'?\s*clock\b", re.IGNORECASE | re.ASCII)

_DOT_TIME_LEAD_RE = re.compile(r"(?:\bat|\bfor|\bfrom|@|\bstarting|\bcommencing|\blisted|\bhearing|\bprompt|\bon)\s*$", re.IGNORECASE)


_NONHEARING_DATE_BEFORE_RE = re.compile(
    r"(?:\b(?:born|dob|d\.o\.b\.?|date of birth|dated|issued|sealed|served|received|sent|called|phoned|spoke|emailed|met|filed)\s+(?:on\s+)?(?:the\s+)?"
    r"|\b(?:order|orders|letter|email|e-mail|message|call|statement|report|judgment|application|notice)\s+(?:of|dated|made on|made)\s+(?:the\s+)?"
    r"|\bmade\s+on\s+(?:the\s+)?"
    r"|\bwas\s+(?:heard|held|listed)\s+(?:on\s+)?(?:the\s+)?"
    r"|\b(?:was|were)\s+on\s+(?:the\s+)?"
    r"|\b(?:took\s+place|occurred|was\s+held)\s+on\s+(?:the\s+)?"
    r"|\b(?:yesterday|previously|earlier|last\s+(?:week|month))\s*(?:on\s+)?(?:the\s+)?"
    r"|\bat\s+the\s+hearing\s+(?:on\s+|held\s+on\s+)?(?:the\s+)?)$",
    re.IGNORECASE,
)
_DEADLINE_BEFORE_RE = re.compile(
    r"(?:\b(?:by|before|no\s+later\s+than|not\s+later\s+than|until|till|on\s+or\s+before|within|deadline(?:\s+(?:is|of))?|due(?:\s+(?:by|on))?)\s*(?:the\s+)?"
    r"(?:\d{1,2}(?:[:.]\d{2})?\s*[ap]\.?m\.?\s*(?:on\s+)?)?)$",
    re.IGNORECASE,
)
_RESCHEDULE_NEW_BEFORE_RE = re.compile(
    r"(?:\b(?:adjourned|moved|relisted|re-listed|rescheduled|postponed|transferred|deferred|put\s+back|brought\s+forward)\s+(?:to|until|for|on)\s+(?:the\s+)?"
    r"|\bnew\s+(?:hearing\s+)?date\s+(?:is|will\s+be|of)\s*(?:the\s+)?"
    r"|\bnow\s+(?:be\s+)?(?:listed|heard)\s+(?:on|for)\s+(?:the\s+)?"
    r"|\bre-?listed\s+(?:for|on)\s+(?:the\s+)?)$",
    re.IGNORECASE,
)
_RESCHEDULE_OLD_AFTER_RE = re.compile(
    r"^(?:(?!\b(?:and|but|while|whereas)\b)[^.\n,;]){0,40}?\b(?:is|has\s+been|was|will\s+be|are|have\s+been)?\s*(?:now\s+)?(?:adjourned|vacated|cancelled|canceled|postponed|moved|relisted|rescheduled|taken\s+out)\b",
    re.IGNORECASE,
)
_NOTBEFORE_BEFORE_RE = re.compile(r"\b(?:first\s+available\s+date\s+after|not\s+before|no\s+earlier\s+than|on\s+or\s+after|after)\s*(?:the\s+)?$", re.IGNORECASE)
_TIME_PREP_BEFORE_RE = re.compile(
    r"(?:\b(?:arrive|arriving|arrival|be\s+(?:present|there)|check[- ]?in|log(?:ging)?\s?in|dial\s?in|connect|doors?\s+open(?:ing)?|waiting\s+room)\b[^.\n\d]{0,25}"
    r"|\b(?:join|attend|be\s+at\s+court|come|report)\b[^.\n\d]{0,20}\b(?:by|no\s+later\s+than|before)"
    r"|\b(?:need\s+you|at\s+court\s+(?:from|by|at)|be\s+at\s+court|please\s+be)\b[^.\n\d]{0,25}"
    r"|\b(?:attend(?:\s+court)?|arrive|arriving|come|report|be\s+present|be\s+there|be\s+at\s+court)\s+(?:at|from|by)"
    r"|\b(?:meet(?:ing)?|witness(?:es)?|evidence|expected|interpreters?|will\s+be\s+at|outside(?:\s+the)?\s+court)\b[^.\n\d]{0,30})\s*$",
    re.IGNORECASE,
)
_TIME_BLOCK_WORD_RE = re.compile(
    r"\b(?:paras?|paragraphs?|rules?|court|courtroom|room|ref|reference|no|number|page|pages|section|item|clause|annex|appendix|schedule|cl|form)\.?\s*$",
    re.IGNORECASE,
)
_TIME_INTRO_BEFORE_RE = re.compile(
    r"(?:\bat|\bfor|\bfrom|@|\bstarting|\bstarts?|\bcommenc\w*|\bbeginning|\blisted(?:\s+for)?|\btime(?:\s+of\s+hearing)?\s*:|\bstart\s*time\s*:|\bhearing\s*:)\s*$",
    re.IGNORECASE,
)
_TIME_DEADLINE_BEFORE_RE = re.compile(r"\b(?:by|before|no\s+later\s+than|not\s+later\s+than|until|till)\s*$", re.IGNORECASE)

_RESCHEDULE_VERB_RE = re.compile(
    r"\b(?:adjourned|moved|re-?listed|rescheduled|postponed|transferred|deferred|put\s+back|brought\s+forward|new\s+(?:hearing\s+)?date|no\s+longer)\b",
    re.IGNORECASE,
)

_LABEL_LINE_RE = re.compile(r"^\s*[A-Za-z][A-Za-z /]{1,30}:\s*\S")
_ABBREVIATIONS = ("mr", "mrs", "ms", "dr", "no", "ref", "approx", "st", "rd", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "e.g", "i.e", "etc", "v")

MAX_CANDIDATES = 6
FAR_FUTURE_DAYS = 730
FAR_PAST_DAYS = 3650


@dataclass
class DateTok:
    start: int
    end: int
    iso: str
    kind: str = "hearing"
    range_end: str = ""
    inferred_year: bool = False
    forced_kind: str = ""
    alternatives: bool = False
    weekday_mismatch: bool = False


@dataclass
class TimeTok:
    start: int
    end: int
    hhmm: str
    kind: str = "hearing"


@dataclass
class Candidate:
    date: str
    time: str
    case_ref: str
    statement: str
    weak: bool = False
    multi_day: bool = False
    inferred_year: bool = False
    rescheduled: bool = False
    alternatives: bool = False
    hedged: bool = False
    weekday_mismatch: bool = False
    untrusted_ref: bool = False
    ambiguous_time: bool = False


@dataclass
class Analysis:
    candidates: list[Candidate] = field(default_factory=list)
    needs_model: list[str] = field(default_factory=list)
    unsure: list[str] = field(default_factory=list)
    vacate_dates: list[str] = field(default_factory=list)
    vacate_items: list[tuple[str, str]] = field(default_factory=list)
    vacate_seen: bool = False
    reschedule_seen: bool = False
    retracted: bool = False
    message_case_refs: set[str] = field(default_factory=set)
    dates_seen: int = 0
    only_past_dates: bool = False
    echo_discards: int = 0



def _infer_year(day: int, month: int, ref: dt.date) -> int | None:
    for year in (ref.year, ref.year + 1):
        try:
            candidate = dt.date(year, month, day)
        except ValueError:
            continue
        if candidate >= ref - dt.timedelta(days=30):
            return year
    return None


def _weekday_mismatch(text: str, start: int, iso: str) -> bool:
    match = _WEEKDAY_BEFORE_RE.search(text[max(0, start - 16):start])
    if not match:
        return False
    try:
        return _WEEKDAY_INDEX[match.group(1).lower()] != dt.date.fromisoformat(iso).weekday()
    except (KeyError, ValueError):
        return False


def find_dates(text: str, ref: dt.date) -> list[DateTok]:
    text = str(text or "")
    toks: list[DateTok] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= a or start >= b for a, b in taken)

    for match in _RANGE_RE.finditer(text):
        first_text, rest, month_name, year = match.groups()
        month = _MONTHS.get(month_name.lower().rstrip("."))
        days = [int(first_text)] + [int(n) for n in re.findall(r"\d{1,2}", re.sub(r"(\d)(?:st|nd|rd|th)", r"\1", rest))]
        seps = [m.group(0).lower() for m in _LIST_SEP_RE.finditer(rest)]
        if not month or not all(1 <= d <= 31 for d in days) or days != sorted(set(days)):
            continue
        inferred = year is None
        y = int(year) if year else _infer_year(days[0], month, ref)
        if y is None:
            continue
        try:
            first, last = dt.date(y, month, days[0]), dt.date(y, month, days[-1])
        except ValueError:
            continue
        if not free(match.start(), match.end()):
            continue
        taken.append((match.start(), match.end()))
        if len(days) == 2 and seps == ["to"] and _FROM_RESCHEDULE_BEFORE_RE.search(text[max(0, match.start() - 60):match.start()]):
            toks.append(DateTok(match.start(), match.end(), first.isoformat(), inferred_year=inferred, forced_kind="reschedule_old"))
            toks.append(DateTok(match.start(), match.end(), last.isoformat(), inferred_year=inferred, forced_kind="reschedule_new"))
            continue
        toks.append(DateTok(
            match.start(), match.end(), first.isoformat(), range_end=last.isoformat(), inferred_year=inferred,
            alternatives="or" in seps,
        ))
    for match in _ISO_DATE_RE.finditer(text):
        if not free(match.start(), match.end()):
            continue
        try:
            iso = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            continue
        toks.append(DateTok(match.start(), match.end(), iso))
        taken.append((match.start(), match.end()))
    for match in _NUM_DATE_RE.finditer(text):
        if not free(match.start(), match.end()):
            continue
        d, m, y = int(match.group(1)), int(match.group(2)), match.group(3)
        year = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            iso = dt.date(year, m, d).isoformat()
        except ValueError:
            continue
        toks.append(DateTok(match.start(), match.end(), iso))
        taken.append((match.start(), match.end()))
    for match in _TEXT_DATE_RE.finditer(text):
        if not free(match.start(), match.end()):
            continue
        day, month_name, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if not month or not 1 <= int(day) <= 31:
            continue
        if month == 5 and month_name.lower() == "may" and year is None:
            continue
        inferred = year is None
        y = int(year) if year else _infer_year(int(day), month, ref)
        if y is None:
            continue
        try:
            iso = dt.date(y, month, int(day)).isoformat()
        except ValueError:
            continue
        toks.append(DateTok(match.start(), match.end(), iso, inferred_year=inferred))
        taken.append((match.start(), match.end()))
    for match in _MONTH_FIRST_RE.finditer(text):
        if not free(match.start(), match.end()):
            continue
        month_name, day, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if not month or (month == 5 and month_name.lower() == "may" and year is None):
            continue
        inferred = year is None
        y = int(year) if year else _infer_year(int(day), month, ref)
        try:
            iso = dt.date(y, month, int(day)).isoformat() if y else ""
        except ValueError:
            iso = ""
        if iso:
            toks.append(DateTok(match.start(), match.end(), iso, inferred_year=inferred))
            taken.append((match.start(), match.end()))
    toks.sort(key=lambda t: (t.start, t.forced_kind != "reschedule_old"))
    merged: list[DateTok] = []
    for tok in toks:
        if merged and not merged[-1].range_end and not merged[-1].forced_kind and re.fullmatch(r"\s*(?:to|until|-|–)\s*", text[merged[-1].end:tok.start], re.IGNORECASE) and tok.iso > merged[-1].iso:
            if _FROM_RESCHEDULE_BEFORE_RE.search(text[max(0, merged[-1].start - 60):merged[-1].start]):
                merged[-1].forced_kind, tok.forced_kind = "reschedule_old", "reschedule_new"
                merged.append(tok)
                continue
            merged[-1].range_end, merged[-1].end = tok.iso, tok.end
            continue
        merged.append(tok)
    for tok in merged:
        if not tok.range_end:
            tok.weekday_mismatch = _weekday_mismatch(text, tok.start, tok.iso)
    return merged


def _to_24h(hour: int, minute: int, marker: str) -> str | None:
    if marker:
        if marker == "p" and 13 <= hour <= 23:
            marker = ""
        elif not 1 <= hour <= 12:
            return None
        if marker == "p" and hour != 12:
            hour += 12
        if marker == "a" and hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _near_a_date(start: int, end: int, dates: list[DateTok] | None, limit: int = 25) -> bool:
    return any(min(abs(start - d.end), abs(d.start - end)) <= limit for d in (dates or []))


def find_times(text: str, dates: list[DateTok] | None = None) -> list[TimeTok]:
    text = str(text or "")
    covered = [(d.start, d.end) for d in (dates or [])]
    toks: list[TimeTok] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= a or start >= b for a, b in covered + taken)

    def add(match: re.Match[str], hhmm: str | None) -> None:
        if not hhmm or not free(match.start(), match.end()):
            return
        if _TIME_BLOCK_WORD_RE.search(text[max(0, match.start() - 14):match.start()]):
            return
        toks.append(TimeTok(match.start(), match.end(), hhmm))
        taken.append((match.start(), match.end()))

    for match in _TIME_COLON_RE.finditer(text):
        add(match, _to_24h(int(match.group(1)), int(match.group(2)), (match.group(3) or "").lower()))
    for match in _TIME_HOUR_AMPM_RE.finditer(text):
        add(match, _to_24h(int(match.group(1)), 0, match.group(2).lower()))
    for match in _TIME_24H_RE.finditer(text):
        add(match, _to_24h(int(match.group(1)), int(match.group(2)), ""))
    for match in _TIME_NOON_RE.finditer(text):
        add(match, "12:00")
    for match in _TIME_OCLOCK_RE.finditer(text):
        hour = int(match.group(1))
        add(match, f"{hour:02d}:00" if 8 <= hour <= 12 else f"{hour + 12:02d}:00" if 1 <= hour <= 6 else None)
    for match in _TIME_DOT_RE.finditer(text):
        marker = (match.group(3) or "").lower()
        hour, minute = int(match.group(1)), int(match.group(2))
        lead = text[max(0, match.start() - 14):match.start()]
        if not (marker or _DOT_TIME_LEAD_RE.search(lead) or _near_a_date(match.start(), match.end(), dates)):
            continue
        add(match, _to_24h(hour, minute, marker))
    toks.sort(key=lambda t: t.start)
    return toks


_DEADLINE_VERB_RE = re.compile(
    r"\b(?:fil(?:e|ed|es|ing)|serv(?:e|ed|es|ing)|return(?:ed)?|respond\w*|submit\w*|lodg\w*|send|sent|sending|provid\w*|exchang\w*|"
    r"deliver\w*|upload\w*|disclos\w*|expir\w*|lapse\w*|comply|complied|complet\w*|pay|paid|payment|"
    r"position\s+statements?|skeleton\w*|bundles?|witness\s+statements?|statements?|reports?|documents?|evidence|letter|"
    r"in\s+force|effective|takes?\s+effect|comes?\s+into\s+(?:force|effect)|remains?|valid)\b",
    re.IGNORECASE,
)
_DEADLINE_BEFORE_WINDOW = 70
_VALIDITY_AFTER_RE = re.compile(r"^[^.\n]{0,25}\b(?:until|pending|till|up\s+to|to\s+remain\s+until)\s+(?:the\s+)?(?:\w+\s+){0,2}(?:hearing|trial|further\s+order)", re.IGNORECASE)


def _classify_date(text: str, tok: DateTok) -> str:
    if tok.forced_kind:
        return tok.forced_kind
    before = text[max(0, tok.start - _DEADLINE_BEFORE_WINDOW):tok.start]
    after = text[tok.end:tok.end + 60]
    if _NONHEARING_DATE_BEFORE_RE.search(before):
        return "nonhearing"
    if _RESCHEDULE_NEW_BEFORE_RE.search(before):
        return "reschedule_new"
    if _FROM_RESCHEDULE_BEFORE_RE.search(before):
        return "reschedule_old"
    if _NOTBEFORE_BEFORE_RE.search(before):
        return "notbefore"
    if _DEADLINE_BEFORE_RE.search(before):
        return "deadline"
    hearing_spans = [(m.start(), m.end()) for m in HEARING_WORD_RE.finditer(before)]
    verbs = [
        m for m in _DEADLINE_VERB_RE.finditer(before)
        if not any(a <= m.start() and m.end() <= b for a, b in hearing_spans)
    ]
    if verbs and not HEARING_WORD_RE.search(before[verbs[-1].end():]):
        return "deadline"
    if _VALIDITY_AFTER_RE.search(after):
        return "deadline"
    if _RESCHEDULE_OLD_AFTER_RE.search(after):
        return "reschedule_old"
    return "hearing"


def _classify_time(text: str, tok: TimeTok) -> str:
    before = text[max(0, tok.start - 45):tok.start]
    if _TIME_PREP_BEFORE_RE.search(before):
        return "prep"
    if _TIME_DEADLINE_BEFORE_RE.search(before):
        return "deadline"
    return "hearing"


def _time_is_the_hearings(text: str, tok: TimeTok, dates: list[DateTok]) -> bool:
    return bool(_TIME_INTRO_BEFORE_RE.search(text[max(0, tok.start - 16):tok.start])) or _near_a_date(tok.start, tok.end, dates)



_HEDGE_PROSE_RE = re.compile(
    r"\b(?:incorrect(?:ly)?|wrong(?:ly)?|provisional(?:ly)?|proposed|draft|tbc|tbd|to\s+be\s+confirmed|subject\s+to|whether|not\s+yet|earliest|"
    r"may\s+be|might|awaiting|pending|i\s+think|we\s+think|probably|possibly|perhaps|suggest\w*|tentative(?:ly)?|hoping|unconfirmed|yet\s+to\s+be|"
    r"no\s+(?:further\s+)?(?:hearing|listing|trial)|not\s+(?:be\s+)?(?:listed|held|heard)|not\s+(?:a|the)\s+hearing|did\s+not|was\s+not|were\s+not|has\s+not|have\s+not|"
    r"cannot|can't|unable|unavailable|not\s+available|avoid(?:ing)?|abroad|"
    r"application\s+to\s+(?:adjourn|vary|vacate|relist)|to\s+adjourn|ask\s+the\s+court|no\s+decision|"
    r"week\s+(?:of|commencing|beginning)|w/c|fortnight|around|approximately|approx|circa|about|"
    r"was\s+(?:effective|concluded|held|heard|attended|listed|due)|had\s+been|has\s+been\s+(?:held|heard|concluded)|"
    r"yet\s+to\s+be|invoice[sd]?)\b|\bif\b|\?",
    re.IGNORECASE,
)
_HEDGE_LABEL_RE = re.compile(
    r"\b(?:provisional(?:ly)?|proposed|tbc|tbd|to\s+be\s+confirmed|tentative(?:ly)?|unconfirmed|draft|avoid(?:ing)?|unavailable|not\s+available|"
    r"cannot|unable|no\s+(?:further\s+)?hearing|week\s+(?:of|commencing|beginning)|approx(?:imately)?)\b|\?",
    re.IGNORECASE,
)
_RETRACT_RE = re.compile(
    r"\b(?:ignore|disregard)\s+(?:my|our|the|that|this)\s+(?:earlier|previous|last|prior|above|email|message|notice)\b|"
    r"\b(?:was|were|is|are)\s+(?:incorrect|wrong|in\s+error|mistaken|inaccurate)\b|\bincorrectly\s+(?:stated|given|listed|sent)\b|"
    r"\bplease\s+(?:ignore|disregard)\b|\b(?:sent|issued)\s+in\s+error\b|\bapologies\s+for\s+the\s+error\b|"
    r"\b(?:my|our)\s+mistake\b|\bfor\s+a\s+different\s+(?:client|case|matter|family)\b|\bwrong\s+(?:client|case|matter)\b",
    re.IGNORECASE,
)
_OTHER_MATTER_CI_RE = re.compile(
    r"\bseparately\b|\bother\s+(?:matter|case|proceedings?|client)s?\b|\bour\s+other\b|\banother\s+(?:matter|case|client)\b|"
    r"\bcrown\s+court\b|\btribunal\b|\bcourt\s+of\s+protection\b|\bcoroner\b|\bcriminal\b|\burn\b|\bbail\b|\bremand\b|"
    r"\bmagistrates['\u2019]?\s+court\s+(?:trial|sentenc\w+|bail)|"
    r"\b(?:case|claim|ref(?:erence)?|urn)\s*(?:no\.?|number|#)?\s*[:.]?\s*[A-Z0-9/-]*\d[A-Z0-9/-]{3,}\b",
    re.IGNORECASE,
)
_NAMED_MATTER_RE = re.compile(r"\b[Tt]he\s+[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\s+(?:matter|case|proceedings)\b|\bfor\s+(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]{2,}")

VACATED_WORD_RE = re.compile(
    r"\b(?:vacated|vacate|cancell?ed|cancel(?:l?ing)?\s+the\s+hearing|taken\s+out\s+of\s+the\s+(?:court\s+)?list|removed\s+from\s+the\s+(?:court\s+)?list|"
    r"(?:will|shall|does|do|did|is|are)\s+not\s+(?:now\s+)?(?:go\s+ahead|proceed|take\s+place)|not\s+going\s+ahead|dispensed\s+with|"
    r"no\s+longer\s+(?:needed|required|necessary|listed)|not\s+required)\b",
    re.IGNORECASE,
)
_VACATE_LOCAL_NEGATION_RE = re.compile(r"\b(?:not|never|no|nor|n't|refus\w*|declin\w*|reject\w*|denied|deny|dismiss\w*)\b[^.\n]{0,20}$", re.IGNORECASE)
_VACATE_MODALITY_RE = re.compile(
    r"\b(?:if|unless|whether|request\w*|ask|asks|asked|asking|apply|applied|applying|application|seek\w*|wish\w*|would\s+like|can\s+we|could|should|may|might|"
    r"propos\w*|consider\w*|hope|hoping|want\w*|intend\w*)\b|\?",
    re.IGNORECASE,
)


def vacate_words_in(statement: str) -> bool:
    for match in VACATED_WORD_RE.finditer(statement):
        before = statement[:match.start()]
        if _VACATE_LOCAL_NEGATION_RE.search(before[-40:]) or _VACATE_MODALITY_RE.search(before):
            continue
        if re.match(r"\s*(?:is|was|has\s+been|have\s+been|are)?\s*(?:not|refused|rejected|declined)\b", statement[match.end():], re.IGNORECASE):
            continue
        return True
    return False


_HEARING_THEN_DATE_GAP_RE = re.compile(
    r"^\s*(?:(?:is|are|was|will\s+be|to\s+be|being|shall\s+be)\s+)?(?:(?:listed|fixed|held|heard|taking\s+place|to\s+take\s+place)\s+)?(?:on|for|at|:|-|–)?\s*(?:the\s+)?(?:\w+day\s+)?$",
    re.IGNORECASE,
)


def hearing_attached_to_date(statement: str, tok_start: int) -> bool:
    window = statement[max(0, tok_start - 60):tok_start]
    for match in HEARING_WORD_RE.finditer(window):
        if _HEARING_THEN_DATE_GAP_RE.match(window[match.end():]):
            return True
    return False


_BIRTH_HEADER_RE = re.compile(r"\bdate\(?s?\)?\s+of\s+birth\b|\bdob\b", re.IGNORECASE)


_BIRTH_FLAT_HEADER_RE = re.compile(r"date\(?s?\)?\s+of\s+birth", re.IGNORECASE)
_BIRTH_FLAT_ROW_RE = re.compile(r"\s*[A-Za-z' -]{0,60}?\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}")


def _drop_flat_birth_rows(text: str) -> str:
    out, pos = [], 0
    for header in _BIRTH_FLAT_HEADER_RE.finditer(text):
        if header.start() < pos:
            continue
        end = header.end()
        while True:
            row = _BIRTH_FLAT_ROW_RE.match(text, end)
            if not row:
                break
            end = row.end()
        out.append(text[pos:header.start()])
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _drop_birth_tables(text: Any) -> str:
    text = _drop_flat_birth_rows(str(text or ""))
    kept: list[str] = []
    skipping = False
    rows_seen = False
    for line in str(text or "").splitlines():
        if skipping:
            if line.strip():
                rows_seen = True
                continue
            if not rows_seen:
                continue
            skipping = False
        if _BIRTH_HEADER_RE.search(line) and len(line.split()) >= 3 and "  " in line.strip():
            skipping, rows_seen = True, False
            continue
        kept.append(line)
    return "\n".join(kept)


def hearing_governs(statement: str) -> bool:
    return any(not _PURPOSE_BEFORE_RE.search(statement[max(0, m.start() - 45):m.start()]) for m in HEARING_WORD_RE.finditer(statement))



_BULLET_LINE_RE = re.compile(r"^\s*(?:(?:[*•·\-–]|\d{1,2}[.)])\s+\S|[A-Z]{1,3}\d{2}[A-Z]\d{5}\b)")
_MONTH_ABBREV = {"jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"}


def _join_soft_wraps(paragraph_lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in paragraph_lines:
        if _BULLET_LINE_RE.match(line):
            out.append(line)
        elif out and not _BULLET_LINE_RE.match(out[-1]) and not re.search(r"[.!?:;]\s*$", out[-1]) and not _LABEL_LINE_RE.match(line) and not _LABEL_LINE_RE.match(out[-1]):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out


def _ends_in_abbreviation(sentence: str) -> bool:
    match = re.search(r"(?:^|\s)([A-Za-z.]+)\.$", sentence)
    if not match or match.group(1).lower() not in {a.lower() for a in _ABBREVIATIONS}:
        return False
    if match.group(1).lower() in _MONTH_ABBREV and re.search(r"\d(?:st|nd|rd|th)?\s+" + re.escape(match.group(1)) + r"\.$", sentence, re.IGNORECASE):
        return False
    return True


def _split_sentences(line: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])", line)
    merged: list[str] = []
    for part in parts:
        if merged and _ends_in_abbreviation(merged[-1]):
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return [p.strip() for p in merged if p.strip()]


def statements(text: str) -> list[tuple[str, int, bool]]:
    out: list[tuple[str, int, bool]] = []
    paragraphs = re.split(r"\n\s*\n", str(text or "").replace("\r\n", "\n"))
    for index, paragraph in enumerate(paragraphs):
        lines = [ln.strip() for ln in paragraph.split("\n") if ln.strip()]
        block: list[str] = []
        prose: list[str] = []

        def flush_block() -> None:
            if block:
                out.append(("; ".join(block), index, True))
                block.clear()

        def flush_prose() -> None:
            for joined in _join_soft_wraps(prose):
                for sentence in _split_sentences(joined):
                    out.append((sentence, index, False))
            prose.clear()

        for line in lines:
            if _LABEL_LINE_RE.match(line) and len(_split_sentences(line)) == 1:
                flush_prose()
                block.append(line)
            else:
                flush_block()
                prose.append(line)
        flush_prose()
        flush_block()
    return out



MAX_HEARING_STATEMENT_CHARS = 600

def analyse(
    subject: str,
    body: str,
    *,
    ref_date: dt.date,
    today: dt.date,
    extra_text: str = "",
    reject: Callable[[str, str, str], bool] | None = None,
    exclude_refs: frozenset[str] = frozenset(),
) -> Analysis:
    result = Analysis()
    subject, body, extra_text = str(subject or ""), _drop_birth_tables(body), _drop_birth_tables(extra_text)
    result.message_case_refs = {m.group(0).upper() for m in CASE_REF_RE.finditer(f"{subject}\n{body}")} - set(exclude_refs)
    if not result.message_case_refs:
        attached = {m.group(0).upper() for m in CASE_REF_RE.finditer(extra_text)} - set(exclude_refs)
        if len(attached) == 1:
            result.message_case_refs = attached
    subject_signal = bool(HEARING_WORD_RE.search(subject)) and hearing_governs(subject)
    full = "\n\n".join(part for part in (subject, body, extra_text) if part)
    if _RETRACT_RE.search(f"{subject}\n{body}"):
        result.retracted = True
        result.unsure.append("the message corrects or retracts something said earlier; check which listing stands")
    para_signals: dict[int, bool] = {}
    stmts = statements(full)
    for statement, para, _label in stmts:
        if hearing_governs(statement):
            para_signals[para] = True

    seen: set[tuple[str, str, str]] = set()
    dates_total: list[str] = []
    for statement, para, is_label in stmts:
        vacating = vacate_words_in(statement)
        if vacating:
            result.vacate_seen = True
        dates = find_dates(statement, ref_date)
        if not dates:
            continue
        for tok in dates:
            tok.kind = _classify_date(statement, tok)
        times = find_times(statement, dates)
        for tok in times:
            tok.kind = _classify_time(statement, tok)
        result.dates_seen += len(dates)
        dates_total.extend(d.iso for d in dates)
        refs = {m.group(0).upper() for m in CASE_REF_RE.finditer(statement)}
        own_ref = next(iter(refs)) if len(refs) == 1 else ""
        run_on = len(statement) > MAX_HEARING_STATEMENT_CHARS
        if run_on:
            strong = any(hearing_attached_to_date(statement, d.start) for d in dates)
        else:
            strong = hearing_governs(statement) or any(hearing_attached_to_date(statement, d.start) for d in dates)
        if is_label and not strong and not run_on:
            strong = (subject_signal or para_signals.get(para, False)) and not _NONHEARING_EVENT_RE.search(statement)
        weak = False
        if not strong:
            if not run_on and not _BULLET_LINE_RE.match(statement) and (subject_signal or para_signals.get(para, False)):
                weak = True
            else:
                if vacating:
                    result.vacate_items.extend((d.iso, own_ref) for d in dates if d.kind in ("hearing", "reschedule_old"))
                continue
        if vacating:
            for tok in dates:
                if tok.kind in ("hearing", "reschedule_old"):
                    result.vacate_dates.append(tok.iso)
                    result.vacate_items.append((tok.iso, own_ref))
        if _RESCHEDULE_VERB_RE.search(statement):
            result.reschedule_seen = True
        usable = [d for d in dates if d.kind in ("hearing", "reschedule_new")]
        if run_on:
            usable = [d for d in usable if hearing_attached_to_date(statement, d.start)]
        hearing_times = [t for t in times if t.kind == "hearing" and _time_is_the_hearings(statement, t, dates)]
        if not usable:
            continue
        assigned: dict[int, list[TimeTok]] = {i: [] for i in range(len(dates))}
        for t in hearing_times:
            nearest = min(range(len(dates)), key=lambda i: min(abs(t.start - dates[i].end), abs(dates[i].start - t.end)))
            assigned[nearest].append(t)
        if len(refs) > 1:
            result.needs_model.append("several case numbers in one statement")
        hedge_re = _HEDGE_LABEL_RE if is_label else _HEDGE_PROSE_RE
        hedged = bool(hedge_re.search(statement)) and not vacating
        other_matter = (not refs) and bool(_OTHER_MATTER_CI_RE.search(statement) or _NAMED_MATTER_RE.search(statement))
        for index, tok in enumerate(dates):
            if tok not in usable:
                continue
            slot = assigned[index]
            ambiguous_time = len(slot) > 1
            if ambiguous_time:
                result.needs_model.append("several times for one date")
            time_value = slot[0].hhmm if slot and not ambiguous_time else ""
            case_ref = own_ref
            try:
                gap = (dt.date.fromisoformat(tok.iso) - today).days
            except ValueError:
                continue
            if gap > FAR_FUTURE_DAYS or gap < -FAR_PAST_DAYS:
                result.needs_model.append("date is implausibly far from today")
                continue
            if reject is not None and time_value and reject(tok.iso, time_value, statement):
                result.echo_discards += 1
                continue
            if (
                not time_value and not is_label and tok.iso == ref_date.isoformat()
                and not hearing_attached_to_date(statement, tok.start)
            ):
                continue
            if tok.alternatives:
                result.needs_model.append("the message offers alternative dates")
            key = (tok.iso, time_value, case_ref)
            if key in seen:
                continue
            seen.add(key)
            result.candidates.append(Candidate(
                date=tok.iso, time=time_value, case_ref=case_ref, statement=statement, weak=weak,
                multi_day=bool(tok.range_end), inferred_year=tok.inferred_year, rescheduled=tok.kind == "reschedule_new",
                alternatives=tok.alternatives, hedged=hedged, weekday_mismatch=tok.weekday_mismatch,
                untrusted_ref=other_matter and not case_ref, ambiguous_time=ambiguous_time,
            ))
    _finalise(result, dates_total, today)
    return result


def _collapse_repeats(cands: list[Candidate]) -> list[Candidate]:
    _DOUBTS = ("multi_day", "inferred_year", "rescheduled", "alternatives", "hedged", "weekday_mismatch", "untrusted_ref", "ambiguous_time")
    timed = {(c.date, c.case_ref) for c in cands if c.time}
    kept: dict[tuple[str, str, str], Candidate] = {}
    absorbed: list[Candidate] = []
    for cand in cands:
        if not cand.time and (cand.date, cand.case_ref) in timed:
            absorbed.append(cand)
            continue
        key = (cand.date, cand.time, cand.case_ref)
        first = kept.get(key)
        if first is None:
            kept[key] = cand
            continue
        first.weak = first.weak and cand.weak
        for flag in _DOUBTS:
            setattr(first, flag, getattr(first, flag) or getattr(cand, flag))
    for cand in absorbed:
        for target in kept.values():
            if target.time and (target.date, target.case_ref) == (cand.date, cand.case_ref):
                for flag in _DOUBTS:
                    setattr(target, flag, getattr(target, flag) or getattr(cand, flag))
    return list(kept.values())


def _finalise(result: Analysis, dates_total: list[str], today: dt.date) -> None:
    if not result.message_case_refs:
        result.candidates = [c for c in result.candidates if not c.weak]
    for cand in result.candidates:
        if not cand.case_ref and not cand.untrusted_ref and len(result.message_case_refs) == 1:
            cand.case_ref = next(iter(result.message_case_refs))
    result.candidates = _collapse_repeats(result.candidates)
    cands = result.candidates
    if len(cands) > MAX_CANDIDATES:
        result.needs_model.append(f"more than {MAX_CANDIDATES} hearing dates in one message")
    if len({(c.date, c.time, c.case_ref) for c in cands}) > 1:
        result.needs_model.append("several hearing dates or times in one message")
    if len(result.message_case_refs) > 1:
        result.needs_model.append("several case numbers in one message")
    if result.reschedule_seen:
        result.unsure.append("message mentions an adjournment or change: check whether an earlier hearing of this case should be vacated")
    for cand in cands:
        if cand.multi_day or cand.alternatives:
            result.unsure.append("several days are named, so only the first is recorded (a multi-day listing, or alternatives to choose between)")
        if cand.inferred_year:
            result.unsure.append("no year was given; the year was assumed")
        if cand.weak:
            result.unsure.append("the hearing wording is not in the same sentence as the date")
        if cand.hedged:
            result.unsure.append("the wording is hedged, provisional or a question")
        if cand.weekday_mismatch:
            result.unsure.append("the weekday written does not match the date")
        if cand.ambiguous_time:
            result.unsure.append("several times are named for this hearing, so no time was recorded")
        if cand.untrusted_ref:
            result.unsure.append("the sentence names another matter or proceeding, so the message's case number was not applied")
        elif not cand.case_ref and len(result.message_case_refs) > 1:
            result.needs_model.append("the date could not be tied to one case number")
    result.unsure = list(dict.fromkeys(result.unsure))
    result.needs_model = list(dict.fromkeys(result.needs_model))
    if dates_total and not cands:
        try:
            parsed = [dt.date.fromisoformat(d) for d in dates_total]
        except ValueError:
            parsed = []
        result.only_past_dates = bool(parsed) and all(d < today for d in parsed)



def verify_in_source(extraction: dict, text: str, ref_date: dt.date) -> list[str]:
    problems: list[str] = []
    text = str(text or "")
    dates = find_dates(text, ref_date)
    date_set = {d.iso for d in dates} | {d.range_end for d in dates if d.range_end}
    hearing_date = str(extraction.get("hearing_date") or "")
    if hearing_date and hearing_date not in date_set:
        problems.append("the date is not written in the message")
    hearing_time = str(extraction.get("hearing_time") or "")
    if hearing_time and hearing_time not in {t.hhmm for t in find_times(text, dates)}:
        problems.append("the time is not written in the message")
    case_ref = re.sub(r"[^A-Z0-9]", "", str(extraction.get("case_ref") or "").upper())
    if case_ref and case_ref not in re.sub(r"[^A-Z0-9]", "", text.upper()):
        problems.append("the case number is not written in the message")
    return problems
