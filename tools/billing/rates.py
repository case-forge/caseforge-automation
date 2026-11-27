
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import firm_profile


ROUTINE_LETTER_OUT_RATE = Decimal("5.40")
ROUTINE_LETTER_IN_RATE = Decimal("2.70")
TELEPHONE_RATE = Decimal("5.40")
BUNDLE_PAGE_RATE = Decimal("1.98")
COURT_DOCUMENT_PAGE_RATE = BUNDLE_PAGE_RATE
BUNDLE_POSTAGE_RATE: Decimal | None = None
RECEIVED_DOCUMENT_CHAR_LIMIT: int | None = 2500
ATTENDANCE_PREP_RATE = Decimal("59.40")
ATTENDANCE_COUNSEL_COURT_RATE = Decimal("32.40")
ADVOCACY_COURT_RATE = Decimal("59.40")
TRAVELLING_WAITING_RATE = Decimal("28.80")
VAT_RATE = Decimal("0.20")

PERUSAL_FAMILY_RATE = Decimal("59.40")

PRIVATE_HOURLY_RATE = Decimal("250.00")

RATE_TIERS: dict[str, dict[str, Decimal | None]] = {
    "routine_letter_out": {"family": ROUTINE_LETTER_OUT_RATE, "children": None, "private": None},
    "routine_letter_in": {"family": ROUTINE_LETTER_IN_RATE, "children": None, "private": None},
    "telephone": {"family": TELEPHONE_RATE, "children": None, "private": None},
    "attendance_preparation": {"family": ATTENDANCE_PREP_RATE, "children": None, "private": PRIVATE_HOURLY_RATE},
    "attendance_counsel_court": {
        "family": ATTENDANCE_COUNSEL_COURT_RATE,
        "children": None,
        "private": PRIVATE_HOURLY_RATE,
    },
    "advocacy_court": {"family": ADVOCACY_COURT_RATE, "children": None, "private": PRIVATE_HOURLY_RATE},
    "travelling_waiting": {"family": TRAVELLING_WAITING_RATE, "children": None, "private": PRIVATE_HOURLY_RATE},
    "perusal": {"family": PERUSAL_FAMILY_RATE, "children": None, "private": PRIVATE_HOURLY_RATE},
}
CASEFORGE_DOMAIN = firm_profile.load_profile().mail_domains[0]
GROUP_LABELS = {
    "client": "Client",
    "other_side": "Other Side",
    "counsel": "Counsel",
    "court": "Court",
    "laa": "LAA",
    "other": "Others (Process Server, etc)",
}
