#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import html
import math
import re
import unicodedata
from typing import Iterable, Sequence

from rapidfuzz.distance import OSA, JaroWinkler

MATCH = "MATCH"
WEAK = "WEAK"
NO_MATCH = "NO_MATCH"
UNKNOWN = "UNKNOWN"

ALLOW = "allow"
ALLOW_UNKNOWN = "allow_unknown"
NEEDS_CONFIRMATION = "needs_confirmation"
REFUSE = "refuse"

_TITLES = frozenset({"mr", "mrs", "ms", "miss", "mx", "dr", "sir", "dame", "lady", "lord", "prof", "rev", "master"})

GENERIC_LOCAL_PARTS = frozenset(
    {
        "info", "admin", "office", "enquiries", "enquiry", "contact", "hello", "mail", "email", "reception",
        "support", "team", "accounts", "account", "help", "noreply", "donotreply", "post", "general",
        "clerks", "clerk", "legal", "cases", "referrals", "referral", "family", "service", "services",
        "sales", "bookings", "booking", "court", "courts", "listing", "listings", "applications", "intake",
        "newclients", "client", "clients", "webmaster", "postmaster", "secretary", "inbox",
    }
)

_GENERIC_SALUTATION_WORDS = frozenset(
    {
        "sir", "sirs", "madam", "madams", "all", "colleague", "colleagues", "counsel", "team", "clerks",
        "clerk", "both", "everyone", "there", "you", "friend", "friends", "client", "member", "members",
        "whom", "it", "may", "concern", "to", "the", "customer", "applicant", "respondent", "partners",
        "judge", "court", "officer", "manager", "hon", "honourable", "learned",
    }
)

INSTITUTIONAL_DOMAIN_SUFFIXES = (
    ".gov.uk", ".police.uk", ".nhs.uk", "nhs.net", ".nhs.net", "hmcts.net", ".hmcts.net",
    ".sch.uk", ".ac.uk", ".parliament.uk", ".mod.uk", ".cjsm.net", ".cjsm.gov.uk",
)

_STRONG_FUZZY = 0.93
_WEAK_FUZZY = 0.88

OTHER_CLIENT_ADDRESS_DECISION = NEEDS_CONFIRMATION


@dataclasses.dataclass(frozen=True)
class NameMatch:
    verdict: str
    reason: str
    lone: bool = False


@dataclasses.dataclass(frozen=True)
class AddressFinding:
    address: str
    verdict: str
    reason: str
    lone: bool = False


@dataclasses.dataclass(frozen=True)
class RecordedOwner:

    address: str
    name: str
    matter_id: str = ""
    person_id: str = ""


@dataclasses.dataclass(frozen=True)
class OwnerLookup:

    owners: tuple[RecordedOwner, ...] = ()
    error: str = ""

    @classmethod
    def from_rows(cls, rows: Iterable[dict]) -> "OwnerLookup":
        clean = lambda v: "" if v is None else str(v).strip()
        return cls(
            tuple(
                RecordedOwner(clean(r.get("email")).lower(), clean(r.get("owner_name")), clean(r.get("matter_id")), clean(r.get("person_id")))
                for r in rows
                if clean(r.get("email"))
            )
        )


@dataclasses.dataclass(frozen=True)
class RecipientCheck:

    decision: str
    reason: str
    salutation: str
    salutation_verdict: str
    findings: tuple[AddressFinding, ...]
    other_client: bool = False

    def summary(self) -> dict:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "other_client": self.other_client,
            "salutation_verdict": self.salutation_verdict,
            "addresses": [{"address": f.address, "verdict": f.verdict} for f in self.findings],
        }




def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def name_tokens(name: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", str(name or ""))
    if text.count(",") == 1:
        last, first = text.split(",")
        text = f"{first} {last}"
    text = re.sub(r"['’]", "", _fold(text))
    return [t for t in re.split(r"[^a-z]+", text) if t and t not in _TITLES]


def local_part_pieces(address: str) -> tuple[list[str], str]:
    local = _fold(str(address or "").strip().split("@", 1)[0])
    local = local.split("+", 1)[0]
    pieces = [p for p in re.split(r"[^a-z]+", local) if p]
    return pieces, "".join(pieces)


def address_domain(address: str) -> str:
    text = str(address or "").strip().lower()
    return text.rsplit("@", 1)[-1] if "@" in text else ""


def is_institutional_address(address: str) -> bool:
    domain = address_domain(address)
    return bool(domain) and any(domain == s.lstrip(".") or domain.endswith(s) for s in INSTITUTIONAL_DOMAIN_SUFFIXES)


def is_generic_address(address: str) -> bool:
    pieces, compact = local_part_pieces(address)
    if len(compact) < 2:
        return True
    return compact in GENERIC_LOCAL_PARTS or (len(pieces) == 1 and pieces[0] in GENERIC_LOCAL_PARTS)




def _strip_once(text: str, token: str) -> str:
    idx = text.find(token)
    return text[:idx] + text[idx + len(token):]


def _contains(pieces: list[str], compact: str, token: str) -> bool:
    if len(token) < 2:
        return False
    return token in pieces or (len(token) >= 3 and token in compact)


def _squash(text: str) -> str:
    return re.sub(r"(.)\1+", r"\1", text)


def near_spelling(a: str, b: str) -> bool:
    if a == b:
        return True
    n = min(len(a), len(b))
    if n < 3 or abs(len(a) - len(b)) > 2 or a[0] != b[0]:
        return False
    if _squash(a) == _squash(b):
        return True
    distance = OSA.distance(a, b)
    if n <= 4:
        return distance <= 1 and sorted(a) == sorted(b)
    return distance <= (1 if n <= 6 else 2)


def _find_token(pieces: list[str], compact: str, token: str) -> str:
    if _contains(pieces, compact, token):
        return token
    if len(token) < 4:
        return ""
    for piece in pieces:
        if near_spelling(piece, token):
            return piece
    for size in (len(token), len(token) - 1, len(token) + 1):
        for start in range(0, len(compact) - size + 1):
            window = compact[start : start + size]
            if near_spelling(window, token):
                return window
    return ""


def _rest_names_given(rest: str, given: list[str]) -> bool:
    if not rest:
        return False
    initials = [g[0] for g in given]
    if len(rest) <= len(given) and all(ch in initials for ch in rest):
        return True
    for g in given:
        if len(g) >= 2 and g in rest:
            return True
        if len(rest) >= 3 and g.startswith(rest):
            return True
        if len(g) >= 3 and rest.startswith(g[:3]) and JaroWinkler.normalized_similarity(rest[: len(g)], g) >= 0.9:
            return True
        if len(g) >= 4 and near_spelling(rest, g):
            return True
    return False


def _rest_names_surname(rest: str, surnames: list[str]) -> bool:
    if not rest:
        return False
    initials = [s[0] for s in surnames]
    if len(rest) <= len(surnames) and all(ch in initials for ch in rest):
        return True
    return any(len(s) >= 3 and s.startswith(rest) and len(rest) >= 3 for s in surnames)


def score_address_against_name(address: str, name: str, *, fuzzy: bool = True) -> NameMatch:
    tokens = name_tokens(name)
    if not tokens:
        return NameMatch(UNKNOWN, "no name to compare the address with")
    if is_generic_address(address):
        return NameMatch(UNKNOWN, f"{address} is a shared or role mailbox, not a named person")
    pieces, compact = local_part_pieces(address)

    if len(tokens) == 1:
        token = tokens[0]
        if _contains(pieces, compact, token):
            return NameMatch(MATCH, f"{address} contains the name {token!r}")
        return NameMatch(NO_MATCH, f"{address} does not contain the name {token!r}")

    given, surnames = tokens[:-1], tokens[1:]
    best = NameMatch(NO_MATCH, f"{address} contains no part of the name {' '.join(tokens)!r}")

    for surname in surnames:
        found = _find_token(pieces, compact, surname)
        if not found:
            continue
        rest = _strip_once(compact, found)
        if _rest_names_given(rest, given):
            return NameMatch(MATCH, f"{address} contains the surname and the given name or its initial")
        if re.sub(r"[^a-z]", "", rest):
            best = NameMatch(WEAK, f"{address} contains the surname {surname!r} but also {rest!r}, which is not the given name")
        else:
            best = NameMatch(WEAK, f"{address} contains the surname {surname!r} only", lone=True)

    for g in given:
        short_forms = [p for p in pieces if len(p) >= 3 and g.startswith(p) and p != g]
        found_g = _find_token(pieces, compact, g)
        if found_g:
            rest = _strip_once(compact, found_g)
        elif short_forms:
            rest = _strip_once(compact, short_forms[0])
        else:
            continue
        if _rest_names_surname(rest, surnames):
            return NameMatch(MATCH, f"{address} contains the given name and the surname's initial")
        if best.verdict == NO_MATCH:
            best = NameMatch(WEAK, f"{address} contains the given name {g!r} only, not the surname", lone=not re.sub(r"[^a-z]", "", rest))

    if fuzzy and len(compact) >= 4:
        first, last = given[0], surnames[-1]
        forms = (first + last, last + first)
        ratio = max(JaroWinkler.normalized_similarity(compact, f) for f in forms)
        if ratio >= _STRONG_FUZZY:
            return NameMatch(MATCH, f"{address} is a close spelling of the name ({ratio:.2f})")
        if ratio >= _WEAK_FUZZY and best.verdict == NO_MATCH:
            best = NameMatch(WEAK, f"{address} is a loose spelling of the name ({ratio:.2f})")
    return best


def best_address_match(address: str, names: Iterable[str], *, fuzzy: bool = True) -> NameMatch:
    order = {MATCH: 0, WEAK: 1, NO_MATCH: 2, UNKNOWN: 3}
    results = [score_address_against_name(address, n, fuzzy=fuzzy) for n in names if name_tokens(n)]
    if not results:
        return NameMatch(UNKNOWN, "no name to compare the address with")
    if all(r.verdict == UNKNOWN for r in results):
        return results[0]
    return min((r for r in results if r.verdict != UNKNOWN), key=lambda r: order[r.verdict])



_HOMOGLYPHS = (("rn", "m"), ("vv", "w"), ("1", "l"), ("|", "l"), ("0", "o"), ("5", "s"), ("3", "e"))
_NEAR_MISS_EDITS = 2


def _fold_lookalikes(text: str) -> str:
    out = _fold(text)
    for old, new in _HOMOGLYPHS:
        out = out.replace(old, new)
    return out


_DOTLESS_DOMAINS = {"gmail.com": "gmail.com", "googlemail.com": "gmail.com"}


def canonical_address(address: str) -> str:
    text = str(address or "").strip().lower()
    if "@" not in text:
        return text
    local, domain = text.rsplit("@", 1)
    local = local.split("+", 1)[0]
    if domain in _DOTLESS_DOMAINS:
        local, domain = local.replace(".", ""), _DOTLESS_DOMAINS[domain]
    return f"{local}@{domain}"


def same_address(a: str, b: str) -> bool:
    ca, cb = canonical_address(a), canonical_address(b)
    return bool(ca) and ca == cb


def address_near_miss(address: str, recorded: str) -> str:
    a, r = canonical_address(address), canonical_address(recorded)
    if not a or not r or a == r:
        return ""
    if _fold_lookalikes(a) == _fold_lookalikes(r) or OSA.distance(a, r) <= _NEAR_MISS_EDITS:
        return f"{str(address).strip().lower()} looks like a typo or lookalike of the address on record ({str(recorded).strip().lower()})"
    return ""




def _token_matches(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
        return True
    return len(a) >= 4 and len(b) >= 4 and JaroWinkler.normalized_similarity(a, b) >= 0.9


def salutation_matches_name(salutation_name: str, name: str) -> bool:
    said, full = name_tokens(salutation_name), name_tokens(name)
    return bool(said) and bool(full) and all(any(_token_matches(s, f) for f in full) for s in said)


def names_refer_to_same_person(a: str, b: str) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return True
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(any(_token_matches(s, f) for f in long_) for s in short)



_SALUTATION_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:dear|hi|hello|hey|good[ \t]+(?:morning|afternoon|evening))\b[ \t]+([^\n,:;!]{1,80})",
    re.IGNORECASE,
)


def _plain_text(body: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</li>|</tr>", "\n", str(body or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def salutation_names(body: str) -> tuple[str, list[str]]:
    match = _SALUTATION_RE.search(_plain_text(body))
    if not match:
        return "", []
    raw = match.group(1).strip()
    if "{{" in raw or "}}" in raw:
        return raw, []
    people = []
    for part in re.split(r"\s*(?:&|/|\band\b)\s*", raw, flags=re.IGNORECASE):
        words = name_tokens(part)
        if words and not all(w in _GENERIC_SALUTATION_WORDS for w in words):
            people.append(" ".join(words))
    return raw, people


def salutation_verdict(body: str, expected_names: Sequence[str]) -> str:
    _raw, people = salutation_names(body)
    names = [n for n in expected_names if name_tokens(n)]
    if not people or not names:
        return UNKNOWN
    if any(salutation_matches_name(p, n) for p in people for n in names):
        return MATCH
    return NO_MATCH




def _same_full_name(a: str, b: str) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    return len(ta) >= 2 and sorted(ta) == sorted(tb)


def _owner_is_expected(owner: RecordedOwner, names: Sequence[str], matter_id: str) -> bool:
    if matter_id:
        return owner.matter_id == matter_id
    return any(_same_full_name(owner.name, n) for n in names)


def other_client_owners(
    addresses: Sequence[str],
    lookup: OwnerLookup,
    *,
    expected_names: Sequence[str],
    expected_matter_id: str = "",
) -> dict[str, list[RecordedOwner]]:
    names = [n for n in expected_names if name_tokens(n)]
    matter_id = str(expected_matter_id or "").strip()
    if not (names or matter_id):
        return {}
    found: dict[str, list[RecordedOwner]] = {}
    for address in addresses:
        records = [o for o in lookup.owners if same_address(o.address, address)]
        if records and not any(_owner_is_expected(o, names, matter_id) for o in records):
            found[address] = records
    return found


def _other_client_reason(address: str, records: Sequence[RecordedOwner]) -> str:
    matters = sorted({o.matter_id for o in records if o.matter_id})
    where = f" (matter {', '.join(matters)})" if matters else ""
    return f"{address}: this address belongs to a different client on record{where}"




def respondent_name_in(address: str, respondent_names: Sequence[str], client_names: Sequence[str]) -> str:
    pieces, compact = local_part_pieces(address)
    own = {t for n in client_names for t in name_tokens(n)}
    for name in respondent_names:
        tokens = name_tokens(name)
        first = tokens[0] if tokens else ""
        if len(first) >= 3 and first not in own and _contains(pieces, compact, first):
            return first
    return ""


def _only_a_shared_surname(address: str, respondent_names: Sequence[str], client_names: Sequence[str]) -> bool:
    own = {t for n in client_names for t in name_tokens(n)}
    client_initials = {t[0] for n in client_names for t in name_tokens(n)[:-1]}
    _pieces, compact = local_part_pieces(address)
    for name in respondent_names:
        tokens = name_tokens(name)
        for surname in tokens[1:]:
            if len(surname) >= 3 and surname in own and surname in compact:
                rest = _strip_once(compact, surname)
                if not rest:
                    return True
                if len(rest) == 1 and not (rest == tokens[0][0] and rest not in client_initials):
                    return True
    return False


def respondent_lookalike(
    address: str,
    respondent_names: Sequence[str],
    client_names: Sequence[str],
    respondent_addresses: Sequence[str] = (),
) -> str:
    wanted = str(address or "").strip()
    if not wanted:
        return ""
    if any(same_address(wanted, r) for r in respondent_addresses if str(r or "").strip()):
        return f"{wanted} is an email recorded for the respondent"
    clients = [n for n in client_names if name_tokens(n)]
    own_match = bool(clients) and best_address_match(wanted, clients).verdict == MATCH
    if not own_match and not _only_a_shared_surname(wanted, respondent_names, clients):
        for name in respondent_names:
            if name_tokens(name) and score_address_against_name(wanted, name).verdict == MATCH:
                return f"{wanted} looks like the respondent's (name on record)"
    if respondent_name_in(wanted, respondent_names, client_names):
        return f"{wanted} looks like the respondent's (name on record)"
    return ""



OK = "OK"
REVIEW = "REVIEW"

FILLER_WORDS = frozenset(
    {"uk", "london", "official", "mail", "email", "real", "the", "xx", "family", "me", "my", "its", "iam", "im", "mr", "mrs", "ms", "miss"}
)

_ODD_MIN_LETTERS = 3
_ODD_MIN_SHARE = 0.3
_VOWELS = frozenset("aeiouy")
_RARE_LETTERS = frozenset("qxzjwkv")


@dataclasses.dataclass(frozen=True)
class EmailOddness:

    verdict: str
    code: str
    reason: str


def shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = {ch: text.count(ch) for ch in set(text)}
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def _random_looking(text: str) -> bool:
    if len(text) < 5:
        return False
    vowels = sum(ch in _VOWELS for ch in text)
    if vowels == 0 or re.search(r"[^aeiouy]{5,}", text):
        return True
    if sum(ch in _RARE_LETTERS for ch in text) / len(text) >= 0.5:
        return True
    return shannon_entropy(text) >= 2.8 and vowels / len(text) < 0.25


def _name_unit_ends(compact: str, start: int, token: str) -> list[tuple[int, bool]]:
    out: list[tuple[int, bool]] = []
    for end in range(start + 1, min(len(compact), start + len(token) + 2) + 1):
        span = compact[start:end]
        if span == token or (len(token) >= 4 and near_spelling(span, token)):
            out.append((end, False))
        elif len(span) >= 3 and len(token) >= 4 and len(span) < len(token) and token.startswith(span):
            out.append((end, True))
    return out


def _explain_local(compact: str, tokens: Sequence[str]) -> tuple[int, int, str]:
    n = len(compact)
    units: list[list[tuple[int, int, bool]]] = []
    for i in range(n):
        options: list[tuple[int, int, bool]] = []
        for tok in tokens:
            options += [(e, 0, short) for e, short in _name_unit_ends(compact, i, tok)]
        for word in FILLER_WORDS:
            if compact.startswith(word, i):
                options.append((i + len(word), len(word), False))
        units.append(options)
    best: dict[tuple[int, int, bool], tuple[int, int, str]] = {(0, 0, False): (0, 0, "")}

    def offer(key: tuple[int, int, bool], value: tuple[int, int, str]) -> None:
        if key not in best or value[:2] < best[key][:2]:
            best[key] = value

    for i in range(n):
        for (pos, mask, short), (u, f, residue) in [(k, v) for k, v in best.items() if k[0] == i]:
            if not short:
                offer((i + 1, mask, False), (u + 1, f, residue + compact[i]))
            for k, tok in enumerate(tokens):
                if compact[i] == tok[0] and not mask & (1 << k):
                    offer((i + 1, mask | (1 << k), False), (u, f, residue))
            for end, fill, is_short in units[i]:
                offer((end, mask, is_short), (u, f - fill, residue))
    finals = [v for (pos, _mask, _short), v in best.items() if pos == n]
    u, f, residue = min(finals, key=lambda v: v[:2])
    return u, -f, residue


def email_oddness(address: str, client_names: Sequence[str], respondent_names: Sequence[str] = ()) -> EmailOddness:
    if is_generic_address(address):
        return EmailOddness(OK, "generic", "a shared or role mailbox, not a named person")
    tokens = list(dict.fromkeys(t for n in client_names for t in name_tokens(n)))
    pieces, compact = local_part_pieces(address)
    compact = compact[:64]
    own = set(tokens)
    initials = {t[0] for t in tokens}
    for name in respondent_names:
        rtokens = name_tokens(name)
        if not rtokens:
            continue
        first, last = rtokens[0], rtokens[-1]
        if len(first) >= 3 and first not in own and _contains(pieces, compact, first):
            return EmailOddness(REVIEW, "respondent_name", "it contains the other party's first name, so it may not be the client's")
        if len(rtokens) > 1 and last not in own and len(last) >= 4 and _contains(pieces, compact, last):
            return EmailOddness(REVIEW, "respondent_name", "it contains the other party's surname, so it may not be the client's")
        if len(rtokens) > 1 and last in own and first[0] not in initials and compact in (first[0] + last, last + first[0]):
            return EmailOddness(REVIEW, "respondent_name", "it reads as the other party's initial and surname, so it may not be the client's")
    if not tokens:
        return EmailOddness(OK, "no_client_name", "no client name to compare the address with")
    if not compact:
        return EmailOddness(REVIEW, "no_name_found", "it has no letters from the client's name")
    unexplained, filler, residue = _explain_local(compact, tokens)
    effective = len(compact) - filler
    explained = effective - unexplained
    if effective <= 0 or explained <= 1:
        if _random_looking(residue or compact):
            return EmailOddness(REVIEW, "random_looking", "it looks like a random string of letters, not the client's name")
        return EmailOddness(REVIEW, "no_name_found", "it does not look like the client's name")
    if unexplained >= _ODD_MIN_LETTERS and unexplained / effective >= _ODD_MIN_SHARE:
        if _random_looking(residue):
            return EmailOddness(REVIEW, "random_looking", "part of it looks like a random string of letters, not the client's name")
        return EmailOddness(REVIEW, "unexplained_letters", "a large part of it does not come from the client's name")
    return EmailOddness(OK, "explained", "the client's name accounts for the address")


def check_client_recipient(
    *,
    expected_names: Sequence[str],
    addresses: Sequence[str],
    body: str = "",
    recorded_addresses: Sequence[str] = (),
    owner_lookup: OwnerLookup | None = None,
    expected_matter_id: str = "",
    respondent_names: Sequence[str] = (),
    confirmed_addresses: Sequence[str] = (),
    respondent_addresses: Sequence[str] = (),
) -> RecipientCheck:
    names = [n for n in expected_names if name_tokens(n)]
    raw, people = salutation_names(body)
    sal = salutation_verdict(body, names)
    compare_names = names or people
    recorded = [str(r or "").strip().lower() for r in recorded_addresses if str(r or "").strip()]
    wanted = list(dict.fromkeys(str(x or "").strip().lower() for x in addresses if str(x or "").strip()))
    findings = tuple(
        AddressFinding(a, m.verdict, m.reason, m.lone)
        for a in wanted
        for m in [best_address_match(a, compare_names, fuzzy=not recorded)]
    )

    near = [reason for a in wanted for r in recorded if (reason := address_near_miss(a, r))]
    if near:
        return RecipientCheck(
            REFUSE,
            "; ".join(near)
            + ". Use the address on record. If this is the client's correct address, "
            "update the email on their record first.",
            raw, sal, findings,
        )

    other = (
        other_client_owners(
            wanted,
            owner_lookup,
            expected_names=names,
            expected_matter_id=expected_matter_id,
        )
        if owner_lookup is not None
        else {}
    )
    unchecked = (
        [f"whether {', '.join(wanted)} belongs to another client could not be checked ({owner_lookup.error})"]
        if owner_lookup is not None and owner_lookup.error and wanted and (names or expected_matter_id)
        else []
    )
    confirmed = [str(c or "").strip().lower() for c in confirmed_addresses if str(c or "").strip()]
    is_confirmed = lambda a: any(same_address(a, c) for c in confirmed)
    other_reasons = [_other_client_reason(a, records) for a, records in other.items() if not is_confirmed(a)]
    if unchecked and all(is_confirmed(a) for a in wanted):
        unchecked = []

    if sal == NO_MATCH:
        return RecipientCheck(
            REFUSE,
            f"The greeting {raw!r} names someone other than the client on record ({names[0]}). "
            "A client-facing draft must greet the client it is going to.",
            raw, sal, findings,
        )
    if other_reasons and OTHER_CLIENT_ADDRESS_DECISION == REFUSE:
        return RecipientCheck(
            REFUSE,
            "; ".join(other_reasons) + ". If it is also this client's address, record it on their record first.",
            raw, sal, findings,
            other_client=True,
        )
    off_record = [
        f"{a} is not the address on record ({recorded[0]})"
        for a in wanted
        if recorded and not any(same_address(a, r) for r in recorded) and not is_confirmed(a)
    ]
    lookalikes = [
        reason
        for a in wanted
        if not is_confirmed(a)
        for reason in [respondent_lookalike(a, respondent_names, names, respondent_addresses)]
        if reason
    ]
    if other_reasons or unchecked or off_record or lookalikes:
        return RecipientCheck(
            NEEDS_CONFIRMATION,
            "; ".join(other_reasons + unchecked + off_record + lookalikes) + ".",
            raw, sal, findings,
            other_client=bool(other_reasons),
        )
    if wanted and all(is_confirmed(a) for a in wanted):
        return RecipientCheck(ALLOW, "A person has confirmed this address as the client's.", raw, sal, findings)
    if not names and not people:
        return RecipientCheck(ALLOW_UNKNOWN, "No client name was available to check the address against.", raw, sal, findings)
    if any(f.verdict == UNKNOWN for f in findings):
        return RecipientCheck(
            ALLOW_UNKNOWN,
            "A shared or role mailbox is not judged: " + "; ".join(f.reason for f in findings if f.verdict == UNKNOWN),
            raw, sal, findings,
        )
    return RecipientCheck(ALLOW, "Nothing to flag: the address is not the respondent's and is not another client's.", raw, sal, findings)
