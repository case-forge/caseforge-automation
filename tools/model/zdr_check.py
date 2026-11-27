#!/usr/bin/env python3
"Probe every OpenRouter model this repo is actually configured to use for"
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend as mb

PROBE_PROMPT = "Reply with the single word OK."


def models_to_check() -> dict[str, str]:
    "Every OpenRouter model id this repo currently points at, labelled by role/use."
    return {f"role:{role}": mb.model_for_role(role, backend="openrouter") for role in mb.ROLES}


def check_one(model_id: str, *, timeout: float = 20.0) -> tuple[bool, str]:
    "Return (zdr_ok, detail). Reuses the exact runner model_backend.py itself"
    try:
        text = mb._run_openrouter(model_id, PROBE_PROMPT, timeout=timeout)
        return True, text.strip()[:40]
    except mb.ModelBackendError as exc:
        return False, str(exc)[:200]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    args = ap.parse_args(argv)

    results = []
    any_failed = False
    for label, model_id in models_to_check().items():
        ok, detail = check_one(model_id)
        any_failed = any_failed or not ok
        results.append({"label": label, "model": model_id, "zdr_ok": ok, "detail": detail})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            status = "OK  " if r["zdr_ok"] else "FAIL"
            print(f"[{status}] {r['label']:24} {r['model']:38} {r['detail']}")

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
