from __future__ import annotations

from pathlib import Path

try:
    import firm_profile
except ImportError:
    from tools import firm_profile

PRODUCT_NAME = "Vergil"
FIRM_NAME = firm_profile.load_profile().firm_name
FIRM_SHORT_NAME = firm_profile.load_profile().firm_short_name


def strip_em_dashes(text: str) -> str:
    return text.replace("—", ", ")


def model_text(result, fallback: str) -> str:
    if not result.ok:
        return fallback
    text = strip_em_dashes((result.text or "").strip())
    return text if text else fallback


_MODULE_DIR = Path(__file__).resolve().parent


def goose_policy_path() -> Path:
    return _MODULE_DIR / "goose-policy.md"
