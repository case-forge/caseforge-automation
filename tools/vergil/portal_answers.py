from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FORMAT = "caseforge-portal-answers/2"
DEFAULT_TTL_MINUTES = 15
MAX_TTL_MINUTES = 60
KEY_ENV = "PORTAL_EXPORT_SIGNING_KEY"
KEY_ID_ENV = "PORTAL_EXPORT_KEY_ID"
DEFAULT_KEY_ID = "portal-export-1"
KV_SECRET_NAME = "portal-export-signing-key"
MAP_PATH = Path(__file__).resolve().parents[2] / "runtime-data" / "portal-answers-map.json"
AUDIT_FILE = "portal-answers-audit.jsonl"

RECORD_FIELDS = (
    "name_last", "dob_iso", "sex", "phone_primary", "email_primary",
    "address_line1", "address_line2", "address_line3", "address_line4", "address_postcode",
    "has_c8", "c8_phone", "c8_email", "c8_address",
)
_C8_CATEGORY = (("c8_address", "address"), ("c8_email", "email"), ("c8_phone", "phone_number"))
_GENDER = {"male": "male", "female": "female", "other": "unspecified"}


class ExportError(Exception):
    pass



def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    text = text.strip()
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text.replace("+", "-").replace("/", "_") + pad)


def canonical(value: Any) -> bytes:
    _reject_floats(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise ExportError("An export carries no fractional numbers.")
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)


def private_key_from_seed(seed_text: str) -> Ed25519PrivateKey:
    try:
        seed = _unb64(seed_text)
    except Exception as exc:
        raise ExportError("The signing key is not valid base64.") from exc
    if len(seed) != 32:
        raise ExportError("The signing key must be a 32-byte Ed25519 seed.")
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_b64u(key: Ed25519PrivateKey) -> str:
    return _b64u(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def signing_key_from_env(env: Mapping[str, str] | None = None) -> tuple[Ed25519PrivateKey, str]:
    env = os.environ if env is None else env
    seed = (env.get(KEY_ENV) or "").strip()
    if not seed:
        raise ExportError("No signing key is configured (Key Vault secret portal-export-signing-key).")
    return private_key_from_seed(seed), (env.get(KEY_ID_ENV) or DEFAULT_KEY_ID).strip()


def sign_body(body: dict, key: Ed25519PrivateKey, key_id: str) -> dict:
    return {"format": FORMAT, "key_id": key_id, "signature": _b64u(key.sign(canonical(body))), "body": body}



def load_map(path: Path | None = None) -> dict:
    return json.loads((path or MAP_PATH).read_text(encoding="utf-8"))


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _resolve(source: str, record: Mapping[str, Any], extra: Mapping[str, Any]) -> Any:
    scope, _, name = source.partition(".")
    if scope == "extra":
        return extra.get(name)
    if scope != "applicant":
        return None
    if name == "c8_flags":
        return {flag: _truthy(record.get(flag)) for flag, _ in _C8_CATEGORY}
    return record.get(name)


def _transform(kind: str, value: Any, record: Mapping[str, Any]) -> Any:
    if kind == "yes_if_true":
        held = _text(value).lower()
        return "yes" if held and held not in {"0", "false", "no", "n", "none"} else None
    if kind == "gender":
        return _GENDER.get(_text(value).lower())
    if kind == "c8_categories":
        if not _truthy(record.get("has_c8")):
            return None
        picked = [name for flag, name in _C8_CATEGORY if value.get(flag)]
        return picked or None
    return _text(value) or None


def build_pages(record: Mapping[str, Any], extra: Mapping[str, Any] | None = None, table: dict | None = None) -> tuple[dict, dict, bool]:
    table = table or load_map()
    extra = extra or {}
    pages: dict[str, list[dict]] = {}
    report: dict[str, dict] = {}
    contains_c8 = False
    for page in table["pages"]:
        emitted: dict[str, dict] = {}
        missing: list[str] = []
        for spec in page["fields"]:
            when = spec.get("when")
            if when and (emitted.get(when["key"]) or {}).get("value") != when["equals"]:
                continue
            answer = _transform(spec.get("transform", "as_is"), _resolve(spec["source"], record, extra), record)
            if answer is None:
                if spec.get("required"):
                    missing.append(spec["key"])
                continue
            field = {"name": spec["name"], "type": spec["type"], "value": answer}
            if spec.get("conditional"):
                field["conditional"] = True
            emitted[spec["key"]] = field
            c8 = spec.get("c8")
            if c8 == "always" or (c8 and _truthy(record.get(c8))):
                contains_c8 = True
        if emitted:
            pages[page["path"]] = list(emitted.values())
        status = "empty" if not emitted else ("complete" if not missing else "incomplete")
        report[page["path"]] = {"status": status, "filled": len(emitted), "missing": missing}
    return pages, report, contains_c8



def read_record(matter_id: str) -> dict:
    import clientdb_sql

    if not clientdb_sql.get_primary_person_id(matter_id):
        raise ExportError("No such matter.")
    return {name: clientdb_sql.get_editable_field(matter_id, name) for name in RECORD_FIELDS}


def audit_path() -> Path:
    import telemetry_sqlite

    return telemetry_sqlite.resolve_telemetry_root() / AUDIT_FILE


def write_audit(row: dict) -> None:
    from graph_mail_safe_ops import _append_jsonl_locked

    _append_jsonl_locked(audit_path(), row)
    try:
        import telemetry_sqlite

        telemetry_sqlite.record_runtime_event({
            "event_name": "portal_answers_export", "runtime_label": "hub-api", "model_label": "",
            "command": "portal_answers.generate", "files_read": [], "files_written": [],
            "metrics": {key: row[key] for key in ("matter_id", "pages", "contains_c8", "key_id", "ttl_minutes", "requested_by")},
        })
    except Exception:
        pass


def generate(matter_id: str, *, requested_by: str, ttl_minutes: int = DEFAULT_TTL_MINUTES, now: dt.datetime | None = None,
             record: Mapping[str, Any] | None = None, extra: Mapping[str, Any] | None = None,
             env: Mapping[str, str] | None = None, table: dict | None = None) -> dict:
    matter_id = str(matter_id or "").strip()
    if not (matter_id.isdigit() and len(matter_id) <= 20):
        raise ExportError("A matter number is needed.")
    if not isinstance(ttl_minutes, int) or isinstance(ttl_minutes, bool) or not 1 <= ttl_minutes <= MAX_TTL_MINUTES:
        raise ExportError(f"The lifetime must be 1 to {MAX_TTL_MINUTES} minutes.")
    key, key_id = signing_key_from_env(env)
    record = dict(record) if record is not None else read_record(matter_id)
    surname = _text(record.get("name_last"))
    if not surname:
        raise ExportError("The client's record has no surname.")
    pages, report, contains_c8 = build_pages(record, extra, table)
    if not pages:
        raise ExportError("The record holds no answers for any page.")
    issued = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0)
    expires = issued + dt.timedelta(minutes=ttl_minutes)
    z = lambda moment: moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "client": {"reference": matter_id, "surname": surname},
        "contains_c8": contains_c8,
        "expires": z(expires),
        "format": FORMAT,
        "issued": z(issued),
        "matter_id": matter_id,
        "nonce": secrets.token_hex(8),
        "page_must_show": "",
        "pages": pages,
    }
    write_audit({
        "timestamp": z(issued), "matter_id": matter_id, "requested_by": requested_by, "key_id": key_id,
        "ttl_minutes": ttl_minutes, "contains_c8": contains_c8, "pages": sorted(pages), "complete_pages": sorted(p for p, r in report.items() if r["status"] == "complete"),
    })
    return {"export": sign_body(body, key, key_id), "report": report, "contains_c8": contains_c8, "expires": body["expires"]}



def keygen(vault: str, key_id: str, *, runner=subprocess.run) -> dict:
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "seed"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(base64.b64encode(seed).decode("ascii"))
        done = runner(["az", "keyvault", "secret", "set", "--vault-name", vault, "--name", KV_SECRET_NAME, "--file", str(path), "--encoding", "utf-8", "--output", "none"],
                      capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise ExportError("Key Vault refused the secret; nothing was stored.")
    return {"key_id": key_id, "public_key": public_key_b64u(key), "secret_name": KV_SECRET_NAME}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signed answers export: key management (generation is the hub endpoint).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    make = sub.add_parser("keygen", help="make the signing key and store it in Key Vault; prints the public key only")
    make.add_argument("--vault", required=True, help="the production vault's name: the hub API reads the key there")
    make.add_argument("--key-id", default=DEFAULT_KEY_ID)
    sub.add_parser("pubkey", help="print the public key of the configured signing key (run under load_kv_secrets.py exec --)")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "keygen":
            print(json.dumps(keygen(args.vault, args.key_id), indent=2))
        else:
            key, key_id = signing_key_from_env()
            print(json.dumps({"key_id": key_id, "public_key": public_key_b64u(key)}, indent=2))
    except ExportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
