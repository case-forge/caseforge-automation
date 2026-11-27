from __future__ import annotations

import dataclasses
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Mapping

CACHE_SECONDS = 5.0
STORE_TABLE = "pipeline_settings"
MAX_TEXT = 300
TYPES = ("string", "email", "path", "int", "bool", "enum", "people", "person_choice", "decimal")
_MONEY = re.compile(r"^\d{1,4}(\.\d{1,2})?$")
MAX_PEOPLE = 20
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")
SECRET_WORDS = ("secret", "token", "password", "passwd", "api_key", "apikey", "connection_string", "private_key")


class SettingError(ValueError):
    pass


class UnknownSetting(KeyError):
    pass


class SettingLocked(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Setting:
    key: str
    group: str
    type: str
    label: str
    help: str
    env: str
    default: Any = ""
    default_from: str = ""
    store_key: str = ""
    restart_required: bool = False
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()
    writable: bool = True
    consumer: str = ""
    derived: str = ""
    hidden: bool = False

    @property
    def stored_under(self) -> str:
        return self.store_key or f"app.{self.key}"

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key, "group": self.group, "type": self.type, "label": self.label, "help": self.help,
            "restart_required": self.restart_required, "minimum": self.minimum, "maximum": self.maximum,
            "choices": list(self.choices), "writable": self.writable, "env": self.env,
            "max_length": MAX_TEXT if self.type in ("string", "email", "path") else None,
        }

    def clean(self, raw: Any) -> Any:
        if self.type == "people":
            return self._people(raw)
        if self.type == "bool":
            if not isinstance(raw, bool):
                raise SettingError(f"{self.label} must be on or off")
            return raw
        if self.type == "int":
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise SettingError(f"{self.label} must be a whole number")
            return self._bounded(raw)
        if not isinstance(raw, str):
            raise SettingError(f"{self.label} must be text")
        text = " ".join(raw.split()) if self.type != "path" else raw.strip()
        if self.type == "decimal":
            return self._decimal(text)
        if self.type == "enum":
            if text not in self.choices:
                raise SettingError(f"{self.label} must be one of: {', '.join(self.choices)}")
            return text
        if len(text) > MAX_TEXT:
            raise SettingError(f"{self.label} is too long (at most {MAX_TEXT} characters)")
        if any(ord(c) < 32 for c in text):
            raise SettingError(f"{self.label} cannot contain control characters")
        if self.type == "email" and text and not _EMAIL.match(text):
            raise SettingError(f"{self.label} must be an email address")
        if self.type == "path" and text:
            text = text.strip("/")
            if "\\" in text or any(not p.strip() or p.strip() in (".", "..") for p in text.split("/")):
                raise SettingError(f"{self.label} must use forward slashes and no empty or relative parts")
        return text

    def _decimal(self, text: str) -> str:
        text = text.removeprefix("£").strip()
        if not _MONEY.match(text) or not (0 < float(text) < 2000):
            raise SettingError(f"{self.label} must be an amount in pounds above 0 and below 2,000, such as 250.00")
        return f"{float(text):.2f}"

    def _people(self, raw: Any) -> list[dict[str, str]]:
        if not isinstance(raw, list) or not raw or len(raw) > MAX_PEOPLE:
            raise SettingError(f"{self.label} needs between 1 and {MAX_PEOPLE} entries")
        out: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict) or not all(isinstance(item.get(k, ""), str) for k in ("name", "email", "role")):
                raise SettingError(f"{self.label} has an entry that is not name, email and role")
            name, email, role = (" ".join(str(item.get(k, "")).split()) for k in ("name", "email", "role"))
            if not name or len(name) > 120:
                raise SettingError(f"{self.label} has an entry with no name, or a name that is too long")
            if not _EMAIL.match(email) or len(email) > 200:
                raise SettingError(f"{self.label}: {name} needs a valid email address")
            if len(role) > 80 or any(ord(c) < 32 for c in name + email + role):
                raise SettingError(f"{self.label}: {name} has a role label that is too long")
            if name.lower() in {o["name"].lower() for o in out}:
                raise SettingError(f"{self.label} lists {name} more than once")
            out.append({"name": name, "email": email, "role": role})
        return out

    def parse_env(self, raw: str) -> Any:
        text = raw.strip()
        if self.type == "people":
            try:
                return self._people(json.loads(text))
            except ValueError as exc:
                if isinstance(exc, SettingError):
                    raise
                raise SettingError(f"{self.env} must be a JSON list") from None
        if self.type == "bool":
            if text.lower() in _TRUE:
                return True
            if text.lower() in _FALSE:
                return False
            raise SettingError(f"{self.env} must be true or false")
        if self.type == "int":
            try:
                return self._bounded(int(text))
            except ValueError as exc:
                if isinstance(exc, SettingError):
                    raise
                raise SettingError(f"{self.env} must be a whole number") from None
        return self.clean(text)

    def _bounded(self, value: int) -> int:
        if self.minimum is not None and value < self.minimum:
            raise SettingError(f"{self.label} must be at least {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise SettingError(f"{self.label} must be at most {self.maximum}")
        return value

    def encode(self, value: Any) -> str:
        if self.type == "people":
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        return ("1" if value else "0") if self.type == "bool" else str(value)

    def decode(self, text: str) -> Any:
        if self.type == "bool":
            if text in ("1", "0"):
                return text == "1"
            raise SettingError("stored value is not on or off")
        if self.type == "people":
            try:
                return self._people(json.loads(text))
            except ValueError as exc:
                if isinstance(exc, SettingError):
                    raise
                raise SettingError("stored value is not a list") from None
        if self.type == "int":
            try:
                return self._bounded(int(text.strip()))
            except ValueError as exc:
                if isinstance(exc, SettingError):
                    raise
                raise SettingError("stored value is not a whole number") from None
        return self.clean(text)


GROUPS: tuple[tuple[str, str, str], ...] = (
    ("firm", "Firm", "How the firm names and addresses itself on court documents and emails."),
    ("solicitor", "Instructing solicitor", "The solicitor who instructs the firm's work and signs it off."),
    ("folders", "Folders", "Where the system looks for scanned documents, stock documents and unsorted notes."),
    ("branding", "Branding", "How the CRM looks to everyone."),
    ("billing", "Billing", "Time and page rules for notes."),
    ("operations", "Operations", "Switches that stop automatic work. An administrator can hold or release each."),
)


def _s(key, group, type_, label, help_, env, **kw) -> Setting:
    return Setting(key=key, group=group, type=type_, label=label, help=help_, env=env, **kw)


SETTINGS: tuple[Setting, ...] = (
    _s("firm_name", "firm", "string", "Firm name", "The firm's full name, as court documents print it.", "CASEFORGE_SETTING_FIRM_NAME",
       default_from="profile:firm_name", restart_required=True, consumer="firm_profile.load_profile().firm_name"),
    _s("firm_trading_name", "firm", "string", "Trading name", "The short name used in letters, email labels and the chat assistant.",
       "CASEFORGE_SETTING_FIRM_TRADING_NAME", default_from="profile:firm_short_name", restart_required=True,
       consumer="firm_profile.load_profile().firm_short_name"),
    _s("office_street", "firm", "string", "Office street", "Building and street of the office on statements of service.",
       "CASEFORGE_SETTING_OFFICE_STREET", default_from="profile:office_street", restart_required=True,
       consumer="firm_profile.load_profile().office_street"),
    _s("office_town", "firm", "string", "Office town", "Town or city of the office.", "CASEFORGE_SETTING_OFFICE_TOWN",
       default_from="profile:office_town", restart_required=True, consumer="firm_profile.load_profile().office_town"),
    _s("office_postcode", "firm", "string", "Office postcode", "Postcode of the office.", "CASEFORGE_SETTING_OFFICE_POSTCODE",
       default_from="profile:office_postcode", restart_required=True, consumer="firm_profile.load_profile().office_postcode"),
    _s("firm_phone", "firm", "string", "Phone", "The firm's telephone number on court forms.", "CASEFORGE_SETTING_FIRM_PHONE",
       default_from="profile:legal_rep_phone", restart_required=True, consumer="firm_profile.load_profile().legal_rep_phone"),
    _s("email_heading", "firm", "string", "Email PDF heading", "The heading printed at the top of an email saved as a PDF.",
       "CASEFORGE_SETTING_EMAIL_HEADING", default_from="profile:email_heading", restart_required=True,
       consumer="firm_profile.load_profile().email_heading"),
    _s("solicitors", "solicitor", "people", "Instructing solicitors", "The firm's instructing solicitors: name, email and role label. Edit to add more.",
       "CASEFORGE_SETTING_SOLICITORS", default_from="profile:solicitors", restart_required=True, consumer="current_solicitor and the solicitor_* values below"),
    _s("current_solicitor", "solicitor", "person_choice", "Current instructing solicitor", "Who signs statements of truth and appears on court forms. Chosen from the list above.",
       "CASEFORGE_SETTING_CURRENT_SOLICITOR", default_from="solicitors:first", restart_required=True, consumer="solicitor_name, solicitor_email and solicitor_role_label"),
    _s("solicitor_name", "solicitor", "string", "Solicitor name", "The current instructing solicitor's name.", "CASEFORGE_SETTING_SOLICITOR_NAME",
       default_from="profile:statement_of_truth_signer", derived="name", hidden=True, writable=False,
       consumer="firm_profile.load_profile().statement_of_truth_signer"),
    _s("solicitor_role_label", "solicitor", "string", "Solicitor role label", "The current instructing solicitor's role label.",
       "CASEFORGE_SETTING_SOLICITOR_ROLE_LABEL", default_from="profile:statement_of_truth_position", derived="role", hidden=True, writable=False,
       consumer="firm_profile.load_profile().statement_of_truth_position"),
    _s("solicitor_email", "solicitor", "email", "Solicitor email", "The current instructing solicitor's email address.",
       "CASEFORGE_SETTING_SOLICITOR_EMAIL", default_from="profile:legal_rep_email", derived="email", hidden=True, writable=False,
       consumer="firm_profile.load_profile().legal_rep_email"),
    _s("scanned_docs_folder", "folders", "path", "Scanned Docs folder", "The OneDrive folder scanned documents wait in. Blank restores the default.",
       "CASEFORGE_SCANNED_DOCS_PATH", default_from="const:scanned_docs", store_key="scanned_docs_path",
       consumer="scanned_docs.scan_setting.scanned_docs_path"),
    _s("common_documents_folder", "folders", "path", "Stock documents folder", "The OneDrive folder of stock documents the virtual scanner compares against. Blank restores the default.",
       "CASEFORGE_COMMON_DOCUMENTS_PATH", default_from="const:common_docs", consumer="documents.virtual_scanner.common_docs_path"),
    _s("backup_retention_days", "folders", "int", "Backup retention (days)",
       "How many days of nightly backups to keep in the backup folder. Older files are deleted weekly, always keeping the newest copy of every kind of backup. The least allowed is 3.",
       "CASEFORGE_SETTING_BACKUP_RETENTION_DAYS", default=14, minimum=3, maximum=365, store_key="backup_retention_days",
       consumer="maintenance.backup_prune.retention_days"),
    _s("unsorted_notes_folder", "folders", "path", "Unsorted notes folder", "The OneDrive folder attendance notes go to when no client is found. Blank restores the default, Unsorted Attendance Notes. If the folder set here has been deleted, notes go to the default instead, and it is made again if it is missing.",
       "CASEFORGE_UNSORTED_AN_FOLDER", default_from="const:unsorted_an", consumer="documents.attendance_note_drafts.unsorted_path"),
    _s("statement_draft_cleanup", "folders", "bool", "Tidy spare statement drafts",
       "When on, once a witness statement is signed, the spare draft Word files for it in Preliminary Docs are moved into 000 Removed in the client's folder (never deleted; move one back to undo). Off (the default) only reports.",
       "CASEFORGE_SETTING_STATEMENT_DRAFT_CLEANUP", default=False, consumer="onboarding.pipeline.statement_draft_cleanup.auto_clean"),
    _s("referral_postcode_lookup", "folders", "bool", "Look up missing postcodes on a referral",
       "When on, a referral whose applicant or respondent address has no postcode gets one from a free address lookup (OpenStreetMap), only for the exact house, and the matter is marked for a person to check it. The address is sent to that service. Off (the default) sends nothing.",
       "CASEFORGE_SETTING_REFERRAL_POSTCODE_LOOKUP", default=False, consumer="documents.postcode_lookup.enabled"),
    _s("todo_show_automatic", "firm", "bool", "Show automatic to-dos", "Whether the to-do list shows the automatic chase tasks (Court, Bundle, Signing, Statements, Drafts). One switch for the whole firm.",
       "CASEFORGE_SETTING_TODO_SHOW_AUTOMATIC", default=True, hidden=True, consumer="todos.todo_store.automatic_settings"),
    _s("todo_hidden_categories", "firm", "string", "Hidden automatic to-do categories", "Comma-separated category keys switched off for the whole firm.",
       "CASEFORGE_SETTING_TODO_HIDDEN_CATEGORIES", default="", hidden=True, consumer="todos.todo_store.automatic_settings"),
    _s("theme_lock", "branding", "enum", "Theme", "Follow each person's system theme, or force light or dark for everyone.",
       "CASEFORGE_SETTING_THEME_LOCK", default="follow-system", choices=("follow-system", "force-light", "force-dark"),
       consumer="viewer app/layout.tsx"),
    _s("minutes_per_page", "billing", "int", "Minutes per page", "Perusal and preparation notes bill this many minutes for each page, and bundle, court form and received document pages are charged at the attendance and preparation rate for this many minutes. Notes already made keep their time.",
       "CASEFORGE_SETTING_MINUTES_PER_PAGE", default=2, minimum=1, maximum=60, store_key="minutes_per_page",
       consumer="billing.letter_notes.minutes_per_page"),
    _s("pipeline_auto_finish_court_pack", "billing", "bool", "Finish the court pack automatically",
       "When on, Case flow presses \"The forms are finished\" itself once every final form is on file, and bills the forms and draft orders by page count and the Notice of Acting as a letter out. Off (the default) leaves that press to a person.",
       "CASEFORGE_SETTING_PIPELINE_AUTO_FINISH_COURT_PACK", default=False,
       consumer="onboarding.pipeline.step_court_pack.auto_finish"),
    _s("private_hourly_rate", "billing", "decimal", "Private hourly rate (£, before VAT)",
       "The hourly rate for work on a privately billed matter, before VAT (20% is added on top). New billing lines use it; a line keeps the rate it was made at.",
       "CASEFORGE_SETTING_PRIVATE_HOURLY_RATE", default="250.00", consumer="billing.billing_items.rate_for"),
)

LEGAL_AID_RATES: tuple[tuple[str, str, str, str], ...] = (
    ("routine_letter_out", "Letter out", "each", "5.40"),
    ("routine_letter_in", "Routine letter in", "each", "2.70"),
    ("telephone", "Telephone", "each", "5.40"),
    ("attendance_preparation", "Attendance and preparation", "per hour", "59.40"),
    ("attendance_counsel_court", "Attendance on counsel or at court", "per hour", "32.40"),
    ("advocacy_court", "Advocacy at court", "per hour", "59.40"),
    ("travelling_waiting", "Travelling and waiting", "per hour", "28.80"),
)
LEGAL_AID_RATE_PREFIX = "legal_aid_rate_"

SETTINGS = SETTINGS + tuple(
    _s(f"{LEGAL_AID_RATE_PREFIX}{suffix}", "billing", "decimal", f"Legal aid rate: {label} (£ {unit})",
       "The legal aid rate for this work, before VAT. New billing lines use it; a line keeps the rate it was made at. "
       "Blank restores the standard rate.",
       f"CASEFORGE_SETTING_LEGAL_AID_RATE_{suffix.upper()}", default=standard, consumer="billing.billing_items.rate_for")
    for suffix, label, unit, standard in LEGAL_AID_RATES
)

BY_KEY: Mapping[str, Setting] = {s.key: s for s in SETTINGS}


def definition(key: str) -> Setting:
    try:
        return BY_KEY[key]
    except KeyError:
        raise UnknownSetting(key) from None


def _check_registry() -> None:
    groups = {g[0] for g in GROUPS}
    assert len(BY_KEY) == len(SETTINGS), "duplicate setting key"
    assert len({s.env for s in SETTINGS}) == len(SETTINGS), "duplicate env name"
    assert len({s.stored_under for s in SETTINGS}) == len(SETTINGS), "duplicate store key"
    for s in SETTINGS:
        assert s.group in groups and s.type in TYPES, s.key
        assert not any(w in f"{s.key} {s.env}".lower() for w in SECRET_WORDS), f"{s.key} looks like a secret"
        assert s.type != "enum" or s.default in s.choices, s.key


_check_registry()

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, tuple[str, str, str]]]] = {}


def _db_key(db_path: Any) -> str:
    return str(db_path) if db_path is not None else os.environ.get("CASEFORGE_OPS_DB", "") or "(default)"


def invalidate() -> None:
    with _lock:
        _cache.clear()


def _rows(db_path: Any = None) -> dict[str, tuple[str, str, str]]:
    key = _db_key(db_path)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    rows: dict[str, tuple[str, str, str]] = {}
    try:
        import ops_db

        names = [s.stored_under for s in SETTINGS]
        with ops_db.connect(db_path) as conn:
            marks = ",".join("?" * len(names))
            for k, v, by, at in conn.execute(
                f"SELECT key, value, updated_by, updated_utc FROM {STORE_TABLE} WHERE key IN ({marks})", names
            ):
                rows[str(k)] = (str(v), str(by), str(at))
    except Exception:
        rows = {}
    with _lock:
        _cache[key] = (now, rows)
    return rows


def _default(setting: Setting, db_path: Any = None) -> Any:
    source = setting.default_from
    if source == "profile:solicitors":
        import firm_profile

        p = firm_profile.load_base_profile()
        return [{"name": p.statement_of_truth_signer, "email": p.legal_rep_email, "role": p.statement_of_truth_position}]
    if source == "solicitors:first":
        return resolve("solicitors", db_path=db_path).value[0]["name"]
    if source.startswith("profile:"):
        import firm_profile

        return getattr(firm_profile.load_base_profile(), source.split(":", 1)[1])
    if source.startswith("const:"):
        return _CONST_DEFAULTS[source.split(":", 1)[1]]()
    return setting.default


def _scanned_default() -> str:
    from scanned_docs.intake_facts import DEFAULT_SCANNED_DOCS_PATH

    return DEFAULT_SCANNED_DOCS_PATH


def _common_default() -> str:
    from documents import virtual_scanner

    return virtual_scanner.DEFAULT_COMMON_DOCS_PATH


def _unsorted_default() -> str:
    from documents import attendance_note_drafts

    return attendance_note_drafts.DEFAULT_UNSORTED_PATH


_CONST_DEFAULTS = {"scanned_docs": _scanned_default, "common_docs": _common_default, "unsorted_an": _unsorted_default}


@dataclasses.dataclass(frozen=True)
class Resolved:
    setting: Setting
    value: Any
    source: str
    env_invalid: bool = False
    updated_by: str = ""
    updated_at: str = ""

    @property
    def locked(self) -> bool:
        return self.source == "env"


def resolve(key: str, *, db_path: Any = None, env: Mapping[str, str] | None = None) -> Resolved:
    setting = definition(key)
    env = os.environ if env is None else env
    invalid = False
    raw_env = env.get(setting.env)
    if raw_env is not None and raw_env.strip():
        try:
            return Resolved(setting, setting.parse_env(raw_env), "env")
        except SettingError:
            invalid = True
    if setting.derived:
        return _derived(setting, db_path, env, invalid)
    row = _rows(db_path).get(setting.stored_under)
    if row is not None:
        try:
            return Resolved(setting, setting.decode(row[0]), "database", invalid, row[1], row[2])
        except SettingError:
            pass
    return Resolved(setting, _default(setting, db_path), "default", invalid)


def selected_person(db_path: Any = None, env: Mapping[str, str] | None = None) -> tuple[dict[str, str], str]:
    people = resolve("solicitors", db_path=db_path, env=env)
    chosen = resolve("current_solicitor", db_path=db_path, env=env)
    entry = next((p for p in people.value if p["name"] == chosen.value), people.value[0])
    sources = {people.source, chosen.source}
    return entry, "env" if "env" in sources else "database" if "database" in sources else "default"


def _derived(setting: Setting, db_path: Any, env: Mapping[str, str], invalid: bool) -> Resolved:
    entry, source = selected_person(db_path, env)
    return Resolved(setting, entry[setting.derived], source, invalid)


def get_setting(key: str, *, db_path: Any = None) -> Any:
    return resolve(key, db_path=db_path).value


def resolve_all(*, db_path: Any = None) -> list[Resolved]:
    return [resolve(s.key, db_path=db_path) for s in SETTINGS]


def apply_changes(actor: str, values: Mapping[str, Any], *, db_path: Any = None, env: Mapping[str, str] | None = None) -> list[str]:
    import ops_db

    env = os.environ if env is None else env
    actor = " ".join(str(actor or "").split())[:200]
    if not actor:
        raise SettingError("a change needs a named person")
    plan: list[tuple[Setting, Any]] = []
    for key, raw in values.items():
        setting = definition(key)
        if not setting.writable:
            raise SettingError(f"{setting.label} is changed on its own, not with the other settings")
        if raw is None or (isinstance(raw, str) and not raw.strip() and setting.type not in ("enum",)):
            plan.append((setting, None))
        else:
            plan.append((setting, setting.clean(raw)))
        if (env.get(setting.env) or "").strip():
            raise SettingLocked(f"{setting.label} is set by the environment ({setting.env}) and cannot be changed here")
    planned = {st.key: v for st, v in plan}
    if "solicitors" in planned or "current_solicitor" in planned:
        if "solicitors" in planned:
            people = planned["solicitors"] if planned["solicitors"] is not None else _default(definition("solicitors"))
        else:
            people = resolve("solicitors", db_path=db_path, env=env).value
        if "current_solicitor" in planned:
            current = planned["current_solicitor"]
        else:
            stored = _rows(db_path).get(definition("current_solicitor").stored_under)
            current = stored[0] if stored else None
        if current is not None and current not in [p["name"] for p in people]:
            raise SettingError("Current instructing solicitor must be one of the instructing solicitors listed")
    changed: list[str] = []
    now = ops_db.utc_now_z()
    with ops_db.acting_as(actor), ops_db.connect(db_path) as conn:
        for setting, value in plan:
            row = conn.execute(f"SELECT value FROM {STORE_TABLE} WHERE key = ?", (setting.stored_under,)).fetchone()
            if value is None:
                if row is None:
                    continue
                conn.execute(f"DELETE FROM {STORE_TABLE} WHERE key = ?", (setting.stored_under,))
            else:
                text = setting.encode(value)
                if row is not None and str(row[0]) == text:
                    continue
                conn.execute(
                    f"INSERT INTO {STORE_TABLE} (key, value, updated_by, updated_utc) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, updated_utc = excluded.updated_utc",
                    (setting.stored_under, text, actor[:80], now),
                )
            changed.append(setting.key)
    invalidate()
    return changed


def data_dir(db_path: Any = None) -> Path:
    import ops_db

    return Path(ops_db.resolve_ops_db_path(db_path)).parent
