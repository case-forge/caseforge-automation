#!/usr/bin/env python3
"Order-type tag normalizer: free-text ``order_requested_text`` -> a fixed,"

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend
import matter_orders
import model_crosscheck as mc
import ops_db
import order_codes
import clientdb_sql
from order_codes import ORDER_LABELS
from vergil import client_edits

CANONICAL_ORDER_TYPES: tuple[str, ...] = matter_orders.CANONICAL_ORDER_TYPES

DEFAULT_PREFER: str | None = mc.PREFER_MODEL

BACKFILL_EDITOR = "system:order-type-normalizer"


class OrderTypeTagError(RuntimeError):
    "Raised when classification itself fails -- never for \"no tags found\","


_PROMPT_TEMPLATE = """You are classifying a family law order-type description into a fixed set \
of five canonical categories. This text was typed inconsistently by different people and systems \
(mixed case, "AND" vs "&", abbreviations, extra words) -- ignore the exact wording and decide which \
of the five categories the text is actually describing.

Categories (code: full name):
{labels}

Text to classify:
{text}

Reply with strict JSON only, no markdown fences, no other text:
{{"order_types": ["<code>", ...]}}

Use only codes from {codes}. Include a code only when the text genuinely supports it -- if the text \
does not clearly describe any of these five order types, reply {{"order_types": []}}. Never invent a \
code that isn't one of the five listed above."""


def _prompt_for(text: str) -> str:
    labels = "\n".join(f"{code}: {ORDER_LABELS[code]}" for code in CANONICAL_ORDER_TYPES)
    return _PROMPT_TEMPLATE.format(labels=labels, text=text[:2000], codes=", ".join(CANONICAL_ORDER_TYPES))


def classify_order_types(order_requested_text: str) -> list[str]:
    "Free text -> canonical tag codes, in ``CANONICAL_ORDER_TYPES`` order."
    text = re.sub(r"\s+", " ", str(order_requested_text or "")).strip()
    if not text:
        return []
    result = model_backend.run_model(model_backend.ROLE_ORDER_TYPE_TAGS, _prompt_for(text), backend="openrouter", timeout=60)
    if not result.ok:
        raise OrderTypeTagError(f"order-type classification call failed: {result.attempts[-1].error if result.attempts else 'unknown'}")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OrderTypeTagError(f"order-type classification did not return valid JSON: {exc}. Raw: {raw[:300]!r}") from exc
    found = {code for code in parsed.get("order_types", []) if code in CANONICAL_ORDER_TYPES}
    return [code for code in CANONICAL_ORDER_TYPES if code in found]


def tags_to_column_value(tags: list[str]) -> str:
    return ",".join(tags)


def tags_from_column_value(value: str | None) -> list[str]:
    if not value:
        return []
    found = {code.strip() for code in value.split(",") if code.strip() in CANONICAL_ORDER_TYPES}
    return [code for code in CANONICAL_ORDER_TYPES if code in found]



AGREE = "agree"
DISAGREE = "disagree"
UNRECOGNISED = "unrecognised"
EMPTY = "empty"
MODEL_FAILED = "model_failed"
OUTCOMES: tuple[str, ...] = (AGREE, DISAGREE, UNRECOGNISED, EMPTY, MODEL_FAILED)

_NCF = None


def _pill_for(code: str) -> str | None:
    global _NCF
    if _NCF is None:
        from onboarding import new_client_categories as cats

        _NCF = cats
    key = {
        "NMO": "non-molestation order", "OO": "occupation order", "CAO": "child arrangements order",
        "PSO": "prohibited steps / specific issue order", "SIO": "prohibited steps / specific issue order",
    }.get(code)
    pill = _NCF.NCF_MATTER_TYPE_FLAGS.get(key) if key else None
    return pill[0] if pill else None


def pills_for(codes: tuple[str, ...] | list[str]) -> list[str]:
    "The pill flags a set of codes earns: each code's matter-type pill and nothing else (a pill carries one matter"
    names: list[str] = []
    for code in codes:
        pill = _pill_for(code)
        if pill and pill not in names:
            names.append(pill)
    return names


@dataclass(frozen=True)
class CrossCheck:
    outcome: str
    tags: tuple[str, ...] = ()
    model_codes: tuple[str, ...] = ()
    reader_codes: tuple[str, ...] = ()
    phrases: tuple[str, ...] = ()
    reader_unrecognised: bool = False
    children_form: bool = False
    error: str = ""
    use: tuple[str, ...] = ()
    use_from: str = ""
    flag: bool = False
    reason: str = ""


def _phrase(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:80]


_canonical = matter_orders.canonical


CONCEPT = matter_orders.CONCEPT


def _model_reading(text: str, classifier: Callable[[str], list[str]] | None) -> mc.Reading:
    try:
        codes = _canonical((classifier or classify_order_types)(text))
    except Exception as exc:
        return mc.failed(f"{type(exc).__name__}: {str(exc)[:160]}")
    return mc.given(codes) if codes else mc.empty()


def _rule_reading(reader: "order_codes.OrderResult") -> mc.Reading:
    codes = _canonical(reader.codes)
    return mc.unrecognised() if (reader.unrecognised or not codes) else mc.given(codes)


def cross_check(
    text: object, *, classifier: Callable[[str], list[str]] | None = None, prefer: str | None = "default"
) -> CrossCheck:
    "Read the order wording twice (model, then ``order_codes``) through ``model_crosscheck`` and say what to"
    prefer = DEFAULT_PREFER if prefer == "default" else prefer
    reader = order_codes.resolve_order_text(text)
    wording = _phrase(text)
    if reader.empty:
        return CrossCheck(EMPTY, flag=True, reason=matter_orders.plain_reason("missing"))
    reader_codes = _canonical(reader.codes)
    base = {"reader_codes": reader_codes, "reader_unrecognised": bool(reader.unrecognised), "children_form": reader.children_form}
    model = _model_reading(str(text), classifier)
    result = mc.crosscheck(CONCEPT, model, _rule_reading(reader), normalise=_canonical, prefer=prefer)
    model_codes = _canonical(model.value or ())
    use = tuple(result.use or ())
    held = "" if use else "nothing recorded"
    reason = ""
    if result.status == mc.AGREE:
        outcome = AGREE
    elif result.status == mc.DISAGREE:
        outcome = DISAGREE
        reason = matter_orders.plain_reason("differ", model=model_codes, rules=reader_codes, wording=wording, note=held)
    elif model.why == mc.FAILED:
        outcome = MODEL_FAILED
        reason = matter_orders.plain_reason("model_down", rules=reader_codes, wording=wording, note=held)
    else:
        outcome = UNRECOGNISED
        if model_codes:
            reason = matter_orders.plain_reason("rules_blind", model=model_codes, wording=wording, note=held)
        elif use:
            reason = matter_orders.plain_reason("model_down", rules=reader_codes, wording=wording)
        elif reader.children_form and not reader_codes and not reader.unrecognised:
            reason = matter_orders.plain_reason("only_form", wording=wording)
        else:
            reason = matter_orders.plain_reason("not_understood", wording=wording)
    phrases = () if outcome == AGREE else (wording,) if outcome in (DISAGREE, MODEL_FAILED) else tuple(reader.unrecognised) or (wording,)
    return CrossCheck(
        outcome, tags=result.value if outcome == AGREE else (), model_codes=model_codes, phrases=phrases,
        error=model.detail if outcome == MODEL_FAILED else "", use=use, use_from=result.use_from, flag=result.needs_flag,
        reason=reason, **base,
    )


def review_reason(check: CrossCheck) -> str:
    "The plain-words review reason a result raises (``matter_orders.plain_reason``): what is wrong, which side"
    return check.reason


REVIEW_PREFIX = matter_orders.REASON_MARKER


def raise_review(
    matter_id: str, check: CrossCheck, *, client_name: str = "", reason: str | None = None, written: bool = False
) -> str:
    "Put the matter's order on the To check list and its review reasons. Idempotent: an open flag and an"
    reason = reason or review_reason(check)
    if not reason:
        return ""
    clear_order_flag(matter_id)
    client_edits.flag_field_for_review(
        matter_id=str(matter_id), client_name=client_name, field_name="order_requested_text", field_label="Order to check",
        value_snapshot=reason[:300], flagged_by=BACKFILL_EDITOR,
        note=(
            "The order was recorded from the model's reading (or the rules' where the model was unavailable); the two readings "
            "did not agree or one could not read it. Work is not held: check which orders are wanted."
            if written
            else "The order wording was blank, unreadable or could not be read by either reader; no order has been recorded."
        ),
    )
    with clientdb_sql.acting_as(f"{BACKFILL_EDITOR} via order cross-check"), clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT review_reasons FROM matters WHERE matter_id = ?", (int(matter_id),))
        row = cur.fetchone()
        current = str((row[0] if row else "") or "")
        if row is not None and not matter_orders.has_order_reason(current):
            joined = f"{current} | {reason}" if current else reason
            cur.execute("UPDATE matters SET review_required = 1, review_reasons = ? WHERE matter_id = ?", (joined, int(matter_id)))
    return reason


def _strip_order_reasons(current: str) -> str:
    kept = [seg for seg in str(current or "").split(" | ") if seg.strip() and not matter_orders.has_order_reason(seg)]
    return " | ".join(kept)


def clear_order_flag(matter_id: str) -> dict[str, Any]:
    "Clear what this tool itself raised about a matter's order: its open To check item (flagged by"
    matter = str(matter_id)
    cleared: dict[str, Any] = {"matter_id": matter, "flags": 0, "reason": False}
    for flag in client_edits.list_open_review_flags_for_matters([matter]).get(matter, []):
        if flag["field_name"] == "order_requested_text" and flag["flagged_by"] == BACKFILL_EDITOR:
            client_edits.resolve_field_review(review_id=flag["review_id"], resolved_by=BACKFILL_EDITOR)
            cleared["flags"] += 1
    with clientdb_sql.acting_as(f"{BACKFILL_EDITOR} via order cross-check"), clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT review_reasons FROM matters WHERE matter_id = ?", (int(matter),))
        row = cur.fetchone()
        current = str((row[0] if row else "") or "")
        if row is not None and matter_orders.has_order_reason(current):
            left = _strip_order_reasons(current)
            if left:
                cur.execute("UPDATE matters SET review_reasons = ? WHERE matter_id = ?", (left, int(matter)))
            else:
                cur.execute("UPDATE matters SET review_required = 0, review_reasons = NULL WHERE matter_id = ?", (int(matter),))
            cleared["reason"] = True
    return cleared


def _human_edited_matters() -> set[str]:
    "Matters whose tags or order-type rows a person has edited (any editor not ``system:``); never touched."
    with ops_db.connect() as conn:
        conn.row_factory = None
        rows = conn.execute(
            "SELECT DISTINCT matter_id FROM client_edit_history WHERE field_name IN ('order_type_tags', 'order_types') "
            "AND edited_by NOT LIKE 'system:%'"
        ).fetchall()
    return {str(r[0]) for r in rows}


def _row_codes() -> dict[str, tuple[str, ...]]:
    out: dict[str, set[str]] = {}
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT matter_id, order_type_code FROM matter_order_types")
        for matter_id, code in cur.fetchall():
            out.setdefault(str(matter_id), set()).add(str(code or "").strip().upper())
    return {m: _canonical(codes) for m, codes in out.items()}


def process_matter(
    matter_id: str,
    text: str,
    *,
    existing_tags: list[str] | None = None,
    existing_rows: list[str] | None = None,
    human_edited: bool | None = None,
    flag_rows: dict[tuple[str, str], dict[str, Any]] | None = None,
    client_name: str = "",
    dry_run: bool = False,
    classifier: Callable[[str], list[str]] | None = None,
    prefer: str | None = "default",
) -> dict[str, Any]:
    "Cross-check one matter and write what the policy says (``cross_check``): tags (mirror), order-type rows"
    matter = str(matter_id)
    check = cross_check(text, classifier=classifier, prefer=prefer)
    result: dict[str, Any] = {
        "matter_id": matter, "outcome": check.outcome, "tags": list(check.tags), "use": list(check.use), "use_from": check.use_from,
        "phrases": list(check.phrases), "actions": [], "skipped": "", "review": "", "applied": False,
    }
    if human_edited is None:
        human_edited = matter in _human_edited_matters()
    if check.outcome != AGREE:
        print(f"[order-cross-check] matter {matter}: {check.outcome} {check.error}".rstrip(), file=sys.stderr)
    if human_edited:
        result["skipped"] = "human_edited"
        return result
    flag_reason = check.reason if check.flag else ""
    if not check.use:
        result["review"] = flag_reason
        if flag_reason and not dry_run:
            raise_review(matter, check, client_name=client_name)
        return result

    if existing_tags is None:
        existing_tags = tags_from_column_value(clientdb_sql.get_editable_field(matter, "order_type_tags"))
    if existing_rows is None:
        existing_rows = list(_row_codes().get(matter, ()))
    wanted = set(check.use)
    if (existing_tags and set(existing_tags) != wanted) or (existing_rows and set(existing_rows) != wanted):
        result["skipped"] = "existing_differs"
        result["review"] = matter_orders.plain_reason(
            "existing_differs", model=check.use, wording=_phrase(text),
            note=f"recorded tags: {', '.join(existing_tags) or 'none'}; rows: {', '.join(existing_rows) or 'none'}",
        )
        if not dry_run:
            raise_review(matter, check, client_name=client_name, reason=result["review"])
        return result

    write_tags = not existing_tags
    write_rows = not existing_rows
    pill_names = pills_for(check.use)
    if flag_rows is None:
        flag_rows = client_edits.list_flag_rows(pill_names)
    new_pills = [name for name in pill_names if (matter, name) not in flag_rows]
    if write_tags:
        result["actions"].append("tags")
    if write_rows:
        result["actions"].append("rows")
    result["actions"].extend(f"pill:{name}" for name in new_pills)
    result["review"] = flag_reason
    if not result["actions"]:
        result["skipped"] = "nothing_to_do"
    if dry_run:
        return result
    note = {mc.BOTH: "Model and rule reader agree", mc.MODEL: "Model reading used; the rule reader differed or could not read it"}.get(
        check.use_from, "Rule reading used; the model was unavailable"
    )
    if write_tags:
        client_edits.record_edit(
            matter_id=matter, field_name="order_type_tags", new_value=tags_to_column_value(list(check.use)),
            note=note, edited_by=BACKFILL_EDITOR,
        )
    if write_rows:
        client_edits.add_order_types(
            matter_id=matter, codes=list(check.use), source_text=text, note=note, edited_by=BACKFILL_EDITOR,
        )
    for name in new_pills:
        client_edits.set_flag(matter_id=matter, flag_name=name, is_set=True, set_by=BACKFILL_EDITOR, reason="Order wording read at intake")
    result["applied"] = bool(result["actions"])
    if flag_reason and result["actions"]:
        raise_review(matter, check, client_name=client_name, written=True)
    elif not flag_reason:
        try:
            clear_order_flag(matter)
        except Exception as exc:
            print(f"[order-cross-check] matter {matter}: could not clear the old order flag ({type(exc).__name__})", file=sys.stderr)
    return result


resolve_matter_orders = matter_orders.resolve_matter_orders



CATEGORY_PILL = "cat_nmo_cao"
INTAKE_PILL_REASON = "Order wording read at intake"


def remove_category_pills(*, apply: bool = False) -> dict[str, Any]:
    "Remove the ``cat_nmo_cao`` pill the first backfill added, and only that: set by this tool"
    rows = client_edits.list_flag_rows([CATEGORY_PILL])
    todo, skipped = [], []
    for (matter, _flag), row in sorted(rows.items()):
        if not row["is_set"]:
            continue
        if row["set_by"] != BACKFILL_EDITOR or row["reason"] != INTAKE_PILL_REASON:
            skipped.append(matter)
            continue
        others = [
            e for e in client_edits.list_edits(matter, limit=200) if e.get("field_name") == f"flag:{CATEGORY_PILL}" and e.get("edited_by") != BACKFILL_EDITOR
        ]
        (skipped if others else todo).append(matter)
    if apply:
        for matter in todo:
            client_edits.set_flag(matter_id=matter, flag_name=CATEGORY_PILL, is_set=False, set_by=BACKFILL_EDITOR, only_if_reason=INTAKE_PILL_REASON)
    return {"mode": "apply" if apply else "dry-run", "removed" if apply else "would_remove": len(todo), "matter_ids": sorted(todo, key=int), "left_alone": sorted(skipped, key=int)}


def repair_mirror(*, apply: bool = False, classifier: Callable[[str], list[str]] | None = None) -> dict[str, Any]:
    "Make tags and rows read from the same sheet for every matter where they differ: re-read the wording with the"
    matters = {str(m["matter_id"]): m for m in _all_matters()}
    rows = _row_codes()
    human = _human_edited_matters()
    out: dict[str, Any] = {"mode": "apply" if apply else "dry-run", "repaired": [], "hand_edited": [], "nothing_to_use": [], "errored": []}
    flag_rows = client_edits.list_flag_rows(pills_for(list(CANONICAL_ORDER_TYPES)))
    for mid, m in sorted(matters.items(), key=lambda kv: int(kv[0])):
        tags = tags_from_column_value(m.get("order_type_tags"))
        have = rows.get(mid)
        if not (tags and have and set(tags) != set(have)):
            continue
        if mid in human:
            out["hand_edited"].append(int(mid))
            continue
        text = str(m.get("order_requested_text") or "")
        try:
            check = cross_check(text, classifier=classifier)
            if not check.use:
                out["nothing_to_use"].append(int(mid))
                if apply:
                    raise_review(mid, check, client_name=str(m.get("canonical_name") or ""),
                                 reason=matter_orders.plain_reason("mirror", wording=_phrase(text), note=f"tags: {', '.join(tags)}; rows: {', '.join(have)}; nothing readable to settle it"))
                continue
            entry = {"matter_id": int(mid), "was_tags": tags, "was_rows": list(have), "now": list(check.use), "from": check.use_from}
            if apply:
                note = "Tags and rows differed; both now follow the model-preferred reading"
                client_edits.record_edit(matter_id=mid, field_name="order_type_tags", new_value=tags_to_column_value(list(check.use)), note=note, edited_by=BACKFILL_EDITOR)
                client_edits.replace_order_types(matter_id=mid, codes=list(check.use), source_text=text, note=note, edited_by=BACKFILL_EDITOR)
                for name in pills_for(check.use):
                    if (mid, name) not in flag_rows:
                        client_edits.set_flag(matter_id=mid, flag_name=name, is_set=True, set_by=BACKFILL_EDITOR, reason=INTAKE_PILL_REASON)
                raise_review(
                    mid, check, client_name=str(m.get("canonical_name") or ""), written=True,
                    reason=matter_orders.plain_reason(
                        "mirror_repaired", model=check.use, rules=check.reader_codes, wording=_phrase(text),
                        note=f"was tags: {', '.join(tags)}; rows: {', '.join(have)}",
                    ),
                )
            out["repaired"].append(entry)
        except Exception as exc:
            out["errored"].append({"matter_id": int(mid), "reason": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return out


INTAKE_LOG = REPO_ROOT / "telemetry" / "referralpartner-intake" / "intake.jsonl"


def _logged_order_fields(log_path: Path) -> dict[str, list[str]]:
    "matter id -> the ``order_type`` value the intake read for each logged run of it (blank string when it read none)."
    seen: dict[str, list[str]] = {}
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                mid = str(row.get("matter_id") or "").strip()
                fields = row.get("fields")
                if mid and isinstance(fields, dict):
                    seen.setdefault(mid, []).append(str(fields.get("order_type") or "").strip())
    except OSError:
        return {}
    return seen


def flag_defaulted_nmo(*, apply: bool = False, log_path: Path | None = None) -> dict[str, Any]:
    "referrer matters whose order wording is exactly ``NMO`` may have been defaulted by the older intake"
    logged = _logged_order_fields(log_path or INTAKE_LOG)
    human = _human_edited_matters()
    open_flags = set(client_edits.list_matters_with_open_review())
    out: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run", "candidates": 0, "blank_at_intake": [], "source_not_found": [],
        "referral_stated_nmo": [], "closed": [], "hand_edited": [], "already_flagged": [], "flagged": 0,
    }
    for m in _all_matters():
        if not _is_referral_partner(m) or str(m.get("order_requested_text") or "").strip().upper() != "NMO":
            continue
        out["candidates"] += 1
        mid = str(m["matter_id"])
        runs = logged.get(mid, [])
        if any(r and "NMO" in order_codes.resolve_order_text(r).codes for r in runs):
            out["referral_stated_nmo"].append(int(mid))
            continue
        if mid in human:
            out["hand_edited"].append(int(mid))
            continue
        if mid in open_flags or matter_orders.has_order_reason(m.get("review_reasons")):
            out["already_flagged"].append(int(mid))
            continue
        if _is_closed(m):
            out["closed"].append(int(mid))
            continue
        kind = "blank_at_intake" if runs and not any(runs) else "source_not_found"
        out[kind].append(int(mid))
        if apply:
            reason = matter_orders.plain_reason(
                "defaulted_nmo_blank" if kind == "blank_at_intake" else "defaulted_nmo_unconfirmed", wording="NMO"
            )
            raise_review(mid, CrossCheck(EMPTY, flag=True, reason=reason), client_name=str(m.get("canonical_name") or ""), reason=reason)
            out["flagged"] += 1
    for key in ("blank_at_intake", "source_not_found"):
        out[key] = sorted(out[key])
    return out


def _is_closed(row: dict[str, Any]) -> bool:
    return bool(str(row.get("closed_at") or "").strip())



def _all_matters() -> list[dict[str, Any]]:
    sql = (
        "SELECT matter_id, order_requested_text, order_type_tags, intake_source, review_required, review_reasons, "
        "created_utc, canonical_name, closed_at FROM matters"
    )
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _is_referral_partner(row: dict[str, Any]) -> bool:
    return str(row.get("intake_source") or "").strip().lower().startswith("referrer")


def _has_own_order_flag(matter_id: str, matters: list[dict[str, Any]]) -> bool:
    "Whether this tool has an open order flag or order reason on the matter (for a dry run's count)."
    open_flags = client_edits.list_open_review_flags_for_matters([matter_id]).get(matter_id, [])
    if any(f["field_name"] == "order_requested_text" and f["flagged_by"] == BACKFILL_EDITOR for f in open_flags):
        return True
    row = next((m for m in matters if str(m["matter_id"]) == matter_id), {})
    return matter_orders.has_order_reason(row.get("review_reasons"))


def backfill_all_matters(*, apply: bool = False, limit: int | None = None, classifier: Callable[[str], list[str]] | None = None) -> dict[str, Any]:
    "Cross-check every matter with order text but missing tags or order-type rows. Dry run unless ``apply``."
    matters = _all_matters()
    rows = _row_codes()
    human = _human_edited_matters()
    selected = []
    missing_wording: list[str] = []
    for m in matters:
        text = str(m.get("order_requested_text") or "").strip()
        if not text:
            continue
        if order_codes.resolve_order_text(text).empty:
            missing_wording.append(str(m["matter_id"]))
            continue
        tags = tags_from_column_value(m.get("order_type_tags"))
        if not tags or not rows.get(str(m["matter_id"])):
            selected.append((m, text, tags))
    if limit:
        selected = selected[:limit]
    flag_rows = client_edits.list_flag_rows(pills_for(list(CANONICAL_ORDER_TYPES)))
    summary: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run", "selected": len(selected),
        "outcomes": {name: 0 for name in OUTCOMES},
        "agree": {"with_writes": 0, "nothing_to_do": 0, "existing_differs": 0, "human_edited": 0},
        "policy": "model-preferred" if DEFAULT_PREFER == mc.PREFER_MODEL else "strict",
        "written_by_reading": {mc.BOTH: 0, mc.MODEL: 0, mc.DETERMINISTIC: 0}, "nothing_written": 0, "matters": [],
        "would_write" if not apply else "written": {"tags": 0, "rows": 0, "pills": 0},
        "flagged_for_review": 0, "errored": [], "unrecognised_phrases": {}, "disagreements": [],
        "missing_wording_matters": len(missing_wording), "cleared_missing_wording_flags": 0,
    }
    for mid in missing_wording:
        if mid in human:
            continue
        try:
            if apply:
                cleared = clear_order_flag(mid)
                summary["cleared_missing_wording_flags"] += bool(cleared["flags"] or cleared["reason"])
            else:
                summary["cleared_missing_wording_flags"] += _has_own_order_flag(mid, matters)
        except Exception as exc:
            summary["errored"].append({"matter_id": mid, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"})
    write_key = "written" if apply else "would_write"
    for m, text, tags in selected:
        mid = str(m["matter_id"])
        try:
            res = process_matter(
                mid, text, existing_tags=tags, existing_rows=list(rows.get(mid, ())), human_edited=mid in human,
                flag_rows=flag_rows, client_name=str(m.get("canonical_name") or ""), dry_run=not apply, classifier=classifier,
            )
        except Exception as exc:
            summary["errored"].append({"matter_id": mid, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        summary["outcomes"][res["outcome"]] += 1
        summary["matters"].append({
            "matter_id": mid, "outcome": res["outcome"], "use": res["use"], "use_from": res["use_from"],
            "actions": [a.split(":")[0] for a in res["actions"]], "skipped": res["skipped"], "flagged": bool(res["review"]),
        })
        if res["actions"]:
            summary["agree"]["with_writes"] += res["outcome"] == AGREE
            summary["written_by_reading"][res["use_from"]] += 1
            summary[write_key]["tags"] += "tags" in res["actions"]
            summary[write_key]["rows"] += "rows" in res["actions"]
            summary[write_key]["pills"] += sum(a.startswith("pill:") for a in res["actions"])
        else:
            if res["outcome"] == AGREE:
                summary["agree"][res["skipped"]] += 1
            if not res["use"] or res["skipped"] in ("existing_differs", "human_edited"):
                summary["nothing_written"] += 1
        if res["review"]:
            summary["flagged_for_review"] += 1
        if res["outcome"] in (UNRECOGNISED, MODEL_FAILED):
            for phrase in res["phrases"]:
                summary["unrecognised_phrases"][phrase] = summary["unrecognised_phrases"].get(phrase, 0) + 1
        if res["outcome"] == DISAGREE:
            summary["disagreements"].append({"matter_id": mid, "phrase": res["phrases"][0] if res["phrases"] else "", **({"model": res["use"]} if res["use"] else {})})
    summary["tags_rows_mismatch"] = [
        {"matter_id": str(m["matter_id"]), "tags": ",".join(tags_from_column_value(m.get("order_type_tags"))), "rows": ",".join(rows[str(m["matter_id"])])}
        for m in matters
        if tags_from_column_value(m.get("order_type_tags")) and rows.get(str(m["matter_id"]))
        and set(tags_from_column_value(m.get("order_type_tags"))) != set(rows[str(m["matter_id"])])
    ]
    dv = [m for m in matters if _is_referral_partner(m)]
    summary["referral_partner_matters"] = len(dv)
    summary["blank_order_text"] = sum(1 for m in dv if not str(m.get("order_requested_text") or "").strip())
    summary["bare_nmo_text_possibly_defaulted"] = sum(1 for m in dv if str(m.get("order_requested_text") or "").strip().upper() == "NMO")
    return summary


def find_gaps(*, older_than_days: int = 1, now: Any = None) -> dict[str, Any]:
    "The standing check: referrer matters older than ``older_than_days`` with order text but missing tags or"
    import datetime as dt

    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(days=older_than_days)).isoformat().replace("+00:00", "Z")
    matters = [m for m in _all_matters() if _is_referral_partner(m) and str(m.get("order_requested_text") or "").strip()
               and not order_codes.resolve_order_text(m.get("order_requested_text")).empty
               and str(m.get("created_utc") or "") < cutoff]
    rows = _row_codes()
    human = _human_edited_matters()
    open_flags = set(client_edits.list_matters_with_open_review())
    gaps = []
    for m in matters:
        mid = str(m["matter_id"])
        if tags_from_column_value(m.get("order_type_tags")) and rows.get(mid):
            continue
        if mid in human or mid in open_flags or matter_orders.has_order_reason(m.get("review_reasons")):
            continue
        gaps.append(int(mid))
    mismatch = sorted(
        int(m["matter_id"]) for m in _all_matters()
        if tags_from_column_value(m.get("order_type_tags")) and rows.get(str(m["matter_id"]))
        and set(tags_from_column_value(m.get("order_type_tags"))) != set(rows[str(m["matter_id"])])
    )
    return {"checked": len(matters), "gaps": len(gaps), "matter_ids": sorted(gaps), "mirror_mismatch": mismatch}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matter-id", help="Cross-check one matter (writes only with --apply)")
    parser.add_argument("--backfill", action="store_true", help="Cross-check every matter with order text but missing tags or rows; dry run unless --apply")
    parser.add_argument("--apply", action="store_true", help="Write the AGREE cases and flag the rest for review (default is a dry run)")
    parser.add_argument("--dry-run", action="store_true", help="Accepted for compatibility; dry run is the default")
    parser.add_argument("--check-gaps", action="store_true", help="Standing check: list referrer matters older than a day with order text and no tags/rows; exit 1 on any")
    parser.add_argument("--limit", type=int, default=None, help="With --backfill, cap how many matters are processed")
    parser.add_argument("--flag-defaulted-nmo", action="store_true", help="Flag referrer matters whose order is exactly NMO for a person to confirm against the referral; changes nothing else; dry run unless --apply")
    parser.add_argument("--remove-category-pills", action="store_true", help="Remove the cat_nmo_cao pill this tool once added (its own only); dry run unless --apply")
    parser.add_argument("--repair-mirror", action="store_true", help="Make tags and rows agree where they differ (model-preferred reading); dry run unless --apply")
    args = parser.parse_args(argv)

    if args.flag_defaulted_nmo:
        print(json.dumps(flag_defaulted_nmo(apply=args.apply), indent=2))
        return 0

    if args.remove_category_pills:
        print(json.dumps(remove_category_pills(apply=args.apply), indent=2))
        return 0

    if args.repair_mirror:
        report = repair_mirror(apply=args.apply)
        print(json.dumps(report, indent=2))
        return 1 if report["errored"] else 0

    if args.check_gaps:
        gaps = find_gaps()
        print(json.dumps(gaps, indent=2))
        return 1 if gaps["gaps"] else 0

    if args.backfill:
        summary = backfill_all_matters(apply=args.apply and not args.dry_run, limit=args.limit)
        print(json.dumps(summary, indent=2, default=str))
        return 1 if summary["errored"] else 0

    if not args.matter_id:
        parser.error("--matter-id, --backfill or --check-gaps is required")

    text = (clientdb_sql.get_editable_field(args.matter_id, "order_requested_text") or "").strip()
    if not text:
        print(json.dumps({"matter_id": args.matter_id, "error": "matter has no order_requested_text on record"}, indent=2))
        return 1
    result = process_matter(args.matter_id, text, dry_run=not args.apply)
    stored = resolve_matter_orders(args.matter_id)
    result["stored"] = {"codes": list(stored.codes), "source": stored.source, "needs_review": stored.needs_review, "reason": stored.review_reason}
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
