#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from billing import billing_items
from onboarding.pipeline import load_context

FILENAME_PREFIX = "Bill-of-Costs"


def bill_csv(matter_id: str) -> tuple[str, str]:
    ctx = load_context(matter_id)
    surname = re.sub(r"[^A-Za-z0-9-]+", "-", (ctx.surname or "").strip()).strip("-") or "client"
    return f"{FILENAME_PREFIX}-{surname}.csv", billing_items.generate_itemized_bill_csv(ctx.matter_id, ctx.client_name)
