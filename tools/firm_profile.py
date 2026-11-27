from __future__ import annotations

import dataclasses
import functools
import importlib.util
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "profile" / "schema.json"
DEFAULT_PROFILE_PATH = REPO_ROOT / "profile" / "firm.yaml"
DEFAULTS_MODULE_PATH = Path(__file__).resolve().parent / "firm_profile_defaults.py"
ENV_VAR = "CASEFORGE_FIRM_PROFILE"

COURT_FORM_FIELDS = (
    "legal_rep_name",
    "legal_rep_firm",
    "legal_rep_address_building",
    "legal_rep_address_line2",
    "legal_rep_address_town",
    "legal_rep_address_county",
    "legal_rep_postcode",
    "legal_rep_dx",
    "legal_rep_phone",
    "legal_rep_email",
    "statement_of_truth_signer",
    "statement_of_truth_firm",
    "statement_of_truth_position",
)


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class FirmProfile:
    firm_name: str
    firm_short_name: str
    mail_domains: tuple[str, ...]
    web_domains: tuple[str, ...]
    workers: tuple[str, ...]
    legal_aid_worker: str
    folder_books: tuple[str, ...]
    worker_books: Mapping[str, str]
    shared_books: tuple[str, ...]
    auto_books: tuple[str, ...]
    casework_books: tuple[str, ...]
    protective_orders_book: str
    common_documents_book: str
    unsorted_attendance_book: str
    library_root: str
    closed_library_root: str
    onedrive_root_name: str
    sharepoint_site_id: str
    key_vault_name: str
    access_team_domain: str
    hostnames: Mapping[str, str]
    legal_rep_name: str
    legal_rep_firm: str
    legal_rep_address_building: str
    legal_rep_address_line2: str
    legal_rep_address_town: str
    legal_rep_address_county: str
    legal_rep_postcode: str
    legal_rep_dx: str
    legal_rep_phone: str
    legal_rep_email: str
    statement_of_truth_signer: str
    statement_of_truth_firm: str
    statement_of_truth_position: str
    pba_number: str
    local_model_url: str
    backup_folder: str
    office_street: str
    office_town: str
    office_postcode: str
    email_heading: str
    source: str

    @property
    def firm_domains(self) -> tuple[str, ...]:
        return self.mail_domains + tuple(d for d in self.web_domains if d not in self.mail_domains)

    @property
    def key_vault_url(self) -> str:
        return f"https://{self.key_vault_name}.vault.azure.net"


def check_books(data: Mapping[str, Any]) -> None:
    workers, books, worker_books = set(data["workers"]), set(data["folder_books"]), dict(data["worker_books"])
    problems = [f"worker_books: {w!r} is not in workers" for w in worker_books if w not in workers]
    problems += [f"worker_books: {w!r} has book {b!r}, which is not in folder_books" for w, b in worker_books.items() if b not in books]
    problems += [f"shared_books: {b!r} is not in folder_books" for b in data["shared_books"] if b not in books]
    for field in ("auto_books", "casework_books"):
        problems += [f"{field}: {w!r} is not a key of worker_books" for w in data[field] if w not in worker_books]
    if problems:
        more = f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""
        raise ProfileError(f"invalid firm profile: {problems[0]}{more}")


def _from_mapping(data: Mapping[str, Any], source: str) -> FirmProfile:
    check_books(data)
    return FirmProfile(
        firm_name=data["firm_name"],
        firm_short_name=data["firm_short_name"],
        mail_domains=tuple(data["mail_domains"]),
        web_domains=tuple(data["web_domains"]),
        workers=tuple(data["workers"]),
        legal_aid_worker=data["legal_aid_worker"],
        folder_books=tuple(data["folder_books"]),
        worker_books=MappingProxyType(dict(data["worker_books"])),
        shared_books=tuple(data["shared_books"]),
        auto_books=tuple(data["auto_books"]),
        casework_books=tuple(data["casework_books"]),
        protective_orders_book=data["protective_orders_book"],
        common_documents_book=data["common_documents_book"],
        unsorted_attendance_book=data["unsorted_attendance_book"],
        library_root=data["library_root"],
        closed_library_root=data["closed_library_root"],
        onedrive_root_name=data["onedrive_root_name"],
        sharepoint_site_id=data["sharepoint_site_id"],
        key_vault_name=data["key_vault_name"],
        access_team_domain=data["access_team_domain"],
        hostnames=MappingProxyType(dict(data["hostnames"])),
        **{name: data[name] for name in COURT_FORM_FIELDS},
        pba_number=data["pba_number"],
        local_model_url=data["local_model_url"],
        backup_folder=data["backup_folder"],
        office_street=data["office_street"],
        office_town=data["office_town"],
        office_postcode=data["office_postcode"],
        email_heading=data["email_heading"],
        source=source,
    )


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(data: Any) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise ProfileError("jsonschema is needed to validate a profile file (pip install jsonschema)") from exc
    validator_cls = jsonschema.validators.validator_for(load_schema())
    errors = sorted(validator_cls(load_schema()).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.absolute_path) or "(top level)"
        more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
        raise ProfileError(f"invalid firm profile at {where}: {first.message}{more}")


def read_profile_file(path: Path) -> FirmProfile:
    try:
        import yaml
    except ImportError as exc:
        raise ProfileError("PyYAML is needed to read a profile file (pip install pyyaml)") from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"cannot read firm profile {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ProfileError(f"firm profile {path} is not valid YAML: {exc}") from exc
    validate(data)
    return _from_mapping(data, str(path))


@functools.lru_cache(maxsize=1)
def builtin_defaults() -> FirmProfile | None:
    if not DEFAULTS_MODULE_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_firm_profile_defaults", DEFAULTS_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return _from_mapping(module.DEFAULTS, "built-in defaults")


def firm_name_words() -> frozenset[str]:
    try:
        profile = load_profile()
    except Exception:
        return frozenset()
    return frozenset(w.lower() for w in re.findall(r"[A-Za-z]{4,}", f"{profile.firm_name} {profile.firm_short_name}"))


@functools.lru_cache(maxsize=1)
def misspelt_firm_domains() -> tuple[str, ...]:
    if not DEFAULTS_MODULE_PATH.is_file():
        return ()
    spec = importlib.util.spec_from_file_location("_firm_profile_defaults", DEFAULTS_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(str(d).strip().lower() for d in getattr(module, "MISSPELT_FIRM_DOMAINS", ()) if str(d).strip())


SETTING_FIELDS = {
    "firm_name": "firm_name",
    "firm_trading_name": "firm_short_name",
    "office_street": "office_street",
    "office_town": "office_town",
    "office_postcode": "office_postcode",
    "firm_phone": "legal_rep_phone",
    "email_heading": "email_heading",
    "solicitor_name": "statement_of_truth_signer",
    "solicitor_role_label": "statement_of_truth_position",
    "solicitor_email": "legal_rep_email",
}


def load_profile(path: str | os.PathLike[str] | None = None) -> FirmProfile:
    profile = load_base_profile(path)
    if path is not None:
        return profile
    try:
        import app_settings

        changes = {}
        for key, field in SETTING_FIELDS.items():
            resolved = app_settings.resolve(key)
            if resolved.source != "default" and str(resolved.value).strip():
                changes[field] = str(resolved.value).strip()
        return dataclasses.replace(profile, **changes) if changes else profile
    except Exception:
        return profile


VAULT_ENV = "CASEFORGE_KEY_VAULT"
MGMT_VAULT_ENV = "CASEFORGE_KEY_VAULT_MGMT"


def box_setting(name: str) -> str:
    try:
        from flags_env import flag_value
    except ImportError:
        from tools.flags_env import flag_value
    return flag_value(name)


def management_vault_name() -> str:
    return box_setting(MGMT_VAULT_ENV)


def load_base_profile(path: str | os.PathLike[str] | None = None) -> FirmProfile:
    if path is not None:
        return read_profile_file(Path(path))
    profile = _load_unpinned_profile()
    vault = box_setting(VAULT_ENV)
    if vault and vault != profile.key_vault_name:
        return dataclasses.replace(profile, key_vault_name=vault)
    return profile


def _load_unpinned_profile() -> FirmProfile:
    env_path = os.environ.get(ENV_VAR, "").strip()
    if env_path:
        candidate = Path(env_path).expanduser()
        if not candidate.is_file():
            raise ProfileError(f"{ENV_VAR} names {candidate}, which is not a file")
        return read_profile_file(candidate)
    if DEFAULT_PROFILE_PATH.is_file():
        return read_profile_file(DEFAULT_PROFILE_PATH)
    defaults = builtin_defaults()
    if defaults is None:
        raise ProfileError(
            f"no firm profile: set {ENV_VAR} or create {DEFAULT_PROFILE_PATH} "
            f"(see profile/firm.example.yaml)"
        )
    return defaults
