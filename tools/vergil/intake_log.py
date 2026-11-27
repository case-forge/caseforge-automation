from __future__ import annotations

import json

from vergil.primitives import REPO_ROOT


def load_referralpartner_intake_log_today(today: str) -> list[dict]:
    path = REPO_ROOT / "telemetry" / "referralpartner-intake" / "intake.jsonl"
    if not path.exists():
        return []
    rows_by_name: dict[str, dict] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if str(row.get("referral_date") or "") != today:
                continue
            if str(row.get("status") or "") not in {"inserted", "already-in-sql"}:
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
            order_type = str(fields.get("order_type") or "").strip()
            respondent = str(fields.get("respondent_name") or "").strip()
            meta_bits = [bit for bit in [order_type, f"R: {respondent}" if respondent else ""] if bit]
            if row.get("has_c8"):
                meta_bits.append("C8")
            item = {
                "name": name,
                "orders": order_type,
                "referral_source": "ReferralPartner",
                "summary": " · ".join(meta_bits),
            }
            rows_by_name[name.lower()] = item
    except Exception:
        return []
    return list(rows_by_name.values())


def merge_new_client_rows(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in primary + secondary:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        existing = merged.get(key, {})
        combined = {**existing, **{k: v for k, v in row.items() if v}}
        merged[key] = combined
    return list(merged.values())
