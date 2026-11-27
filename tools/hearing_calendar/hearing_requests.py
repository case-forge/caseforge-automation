#!/usr/bin/env python3

from __future__ import annotations

import html
from typing import Any, Sequence

from firm_profile import load_profile
from hearing_calendar import hearing_store

FORMS = ("FP2", "C2")
KINDS = ("vacation", "hybrid")
CHILDREN_CODES = ("PSO", "CAO", "SIO")
FAMILY_CODES = ("NMO", "OO")

VACATION_REASONS: tuple[tuple[str, str, str], ...] = (
    (
        "no_counsel",
        "No counsel available",
        "The Applicant has been unable to secure counsel to represent the Applicant at the hearing listed for {date}. Counsel was instructed to attend but is not available on that date.",
    ),
    (
        "counsel_unavailable_clash",
        "Counsel is in another court",
        "Counsel instructed to represent the Applicant at the hearing listed for {date} is already committed to another hearing on that date and cannot attend.",
    ),
    (
        "counsel_withdrawn",
        "Counsel has returned the brief",
        "Counsel previously instructed has returned the brief and, despite enquiries of other chambers, no replacement counsel has yet been secured for the hearing listed for {date}.",
    ),
    (
        "legal_aid_pending",
        "Legal aid / funding not yet in place",
        "Funding for counsel's attendance at the hearing listed for {date} is not yet in place, so counsel cannot be formally instructed in time.",
    ),
    (
        "unrepresented_prejudice",
        "Unfair for the Applicant to proceed unrepresented",
        "It would be unfair for the Applicant to proceed without representation at the hearing listed for {date}, given the nature of the issues before the Court.",
    ),
    (
        "relist_request",
        "Relist at the earliest date counsel is available",
        "The Applicant respectfully asks that the hearing be vacated and relisted at the earliest date convenient to the Court on which counsel is available to attend.",
    ),
)

HYBRID_REASONS: tuple[tuple[str, str, str], ...] = (
    (
        "remote_applicant_and_representative",
        "Remote attendance for the Applicant and their representative",
        "The Applicant respectfully applies for the hearing listed for {date} to be conducted remotely, with both the Applicant and the Applicant's legal representative attending remotely.",
    ),
    (
        "health_wellbeing",
        "Health and wellbeing (add this client's own facts)",
        "Attending in person would present a risk to the Applicant's health and wellbeing, and remote attendance would enable the Applicant to participate in the proceedings safely. [Add this matter's own grounds here.]",
    ),
    (
        "safety_separate_attendance",
        "Safety: avoid being in the same place as the Respondent",
        "The Applicant's safety would be put at risk by attending the same building as the Respondent. A remote or hybrid hearing would avoid that risk.",
    ),
    (
        "distance_travel",
        "Distance and travel",
        "The Applicant lives a considerable distance from the Court, and attending in person would be disproportionately difficult.",
    ),
    (
        "childcare",
        "Childcare",
        "The Applicant has no childcare available for the hearing listed for {date}, and remote attendance would allow the Applicant to take part without leaving the children without proper care.",
    ),
    (
        "counsel_remote",
        "Counsel to attend remotely",
        "Counsel instructed for the Applicant is based a long way from the Court, and the Applicant asks for permission for counsel to attend remotely.",
    ),
)


def _reasons(kind: str) -> tuple[tuple[str, str, str], ...]:
    if kind not in KINDS:
        raise hearing_store.HearingError(f"kind must be one of {list(KINDS)}")
    return VACATION_REASONS if kind == "vacation" else HYBRID_REASONS


def long_date(value: str) -> str:
    import datetime as dt

    day = dt.date.fromisoformat(str(value)[:10])
    return f"{day:%A} {day.day} {day:%B %Y}"


def stock_reasons(kind: str, hearing_date: str = "") -> list[dict[str, str]]:
    date = long_date(hearing_date) if hearing_date else "the hearing date"
    return [{"id": rid, "label": label, "text": text.replace("{date}", date)} for rid, label, text in _reasons(kind)]


def form_for(order_types: str = "", matter_order_text: str = "", matter_order_codes: Sequence[str] = ()) -> str:
    import order_codes

    def codes(text: str) -> list[str]:
        return list(order_codes.codes_in_text(text))

    for text in (order_types, matter_order_text):
        found = list(matter_order_codes) if (text is matter_order_text and matter_order_codes) else codes(text or "")
        if not found:
            continue
        children = any(c in CHILDREN_CODES for c in found)
        family = any(c in FAMILY_CODES for c in found)
        if children and family:
            return ""
        return "C2" if children else "FP2"
    return ""


def options(hearing_id: int) -> dict[str, Any]:
    hearing = hearing_store.get_hearing(int(hearing_id))
    if hearing is None:
        raise hearing_store.HearingError(f"hearing {hearing_id} not found")
    order_text, order_codes_found = "", ()
    if hearing.get("matter_id") is not None:
        try:
            from onboarding.pipeline import load_context

            ctx = load_context(str(hearing["matter_id"]))
            order_text, order_codes_found = ctx.order_text, tuple(ctx.order_info.codes)
        except Exception:
            order_text, order_codes_found = "", ()
    form = form_for(hearing.get("order_types", ""), order_text, order_codes_found)
    return {
        "hearing_id": int(hearing_id),
        "form": form,
        "form_known": bool(form),
        "forms": list(FORMS),
        "vacation_reasons": stock_reasons("vacation", hearing["hearing_date"]),
        "hybrid_reasons": stock_reasons("hybrid", hearing["hearing_date"]),
    }


def _time12(value: str | None) -> str:
    if not value:
        return ""
    h, m = int(value[:2]), value[3:5]
    return f"{(h % 12) or 12}:{m} {'AM' if h < 12 else 'PM'}"


def build_draft(hearing: dict[str, Any], *, kind: str, form: str, reasons: list[str], case_name: str = "") -> tuple[str, str]:
    form = form.upper()
    if form not in FORMS:
        raise hearing_store.HearingError(f"form must be one of {list(FORMS)}")
    reasons = [r.strip() for r in reasons if r and r.strip()]
    if not reasons:
        raise hearing_store.HearingError("choose or write at least one reason")
    ask = "Request for Vacation of Hearing" if kind == "vacation" else "Request for Remote Hearing"
    date, when = hearing["hearing_date"], _time12(hearing.get("hearing_time"))
    subject_bits = [hearing.get("case_ref", ""), f"{form} Application", ask, f"Hearing on {date[8:10]}.{date[5:7]}.{date[:4]}" + (f" at {when}" if when else ""), case_name]
    subject = " || ".join(bit for bit in subject_bits if bit)
    esc = html.escape
    lines = ["Dear Sirs,", ""]
    if hearing.get("case_ref"):
        lines.append(esc(hearing["case_ref"]))
    if case_name:
        lines.append(esc(case_name))
    lines.append(f"Hearing On: {esc(long_date(date))}")
    if when:
        lines.append(f"At: {when}")
    firm = load_profile()
    lines += ["", f"{form} Application", ""]
    if firm.pba_number:
        lines += [
            "PBA DETAILS", esc(firm.pba_number), esc(firm.firm_name), "",
            "We confirm our consent for payment to be deducted from our PBA account.", "",
        ]
    lines += [
        f"Please find attached a {form} Application and Draft Order for the above hearing.", "",
    ]
    lines += [esc(r) + "<br>" for r in reasons]
    lines += [
        "",
        "We would be grateful if the Court could consider this application urgently and confirm the arrangements in advance of the hearing.", "",
        "Should the Court require any further information regarding this application, please do not hesitate to contact us.", "",
        "Yours faithfully,",
    ]
    body = "<html><body>" + "".join(f"<div>{line or '<br>'}</div>" for line in lines) + "</body></html>"
    return subject, body


def request_court(
    hearing_id: int, kind: str, *, actor: str, reasons: list[str], form: str = "", draft: bool = True,
) -> dict[str, Any]:
    _reasons(kind)
    hearing = hearing_store.get_hearing(int(hearing_id))
    if hearing is None:
        raise hearing_store.HearingError(f"hearing {hearing_id} not found")
    if hearing["status"] != "scheduled":
        raise hearing_store.HearingError("only a live hearing can have a request made about it")
    clean = [r.strip() for r in reasons if r and r.strip()]
    if not clean:
        raise hearing_store.HearingError("choose or write at least one reason")
    chosen = (form or options(int(hearing_id))["form"]).upper()
    if chosen not in FORMS:
        raise hearing_store.HearingError("choose FP2 (family) or C2 (children): the matter's orders do not say which")
    made: dict[str, Any] | None = None
    if draft:
        try:
            made = _make_draft(hearing, kind=kind, form=chosen, reasons=clean)
        except hearing_store.HearingError:
            raise
        except Exception as exc:
            raise hearing_store.HearingError(f"The application draft could not be made just now ({type(exc).__name__}). The hearing has not been changed.") from exc
    asked = "vacation_requested" if kind == "vacation" else "hybrid_requested"
    row = hearing_store.request_from_court(int(hearing_id), asked, actor=actor, reason="\n".join(clean))
    what = "vacation of the hearing" if kind == "vacation" else "a remote or hybrid hearing"
    summary = f"{chosen} application asking for {what} is in Outlook Drafts, marked AI DRAFTED. Nothing was sent." if made else f"Recorded as requested ({chosen}). No draft was made."
    return {"hearing": row, "draft": made, "form": chosen, "summary": summary}


def _make_draft(hearing: dict[str, Any], *, kind: str, form: str, reasons: list[str]) -> dict[str, Any]:
    from onboarding.pipeline import court_common as cc
    from onboarding.pipeline import load_context, step_court_email

    if hearing.get("matter_id") is None:
        raise hearing_store.HearingError("link this hearing to a client first: the draft needs the client's court on record")
    ctx = load_context(str(hearing["matter_id"]))
    to, why = step_court_email.court_email(ctx)
    if not to:
        raise hearing_store.HearingError(f"no court email is on record for this client: {why or 'confirm the court on the Case flow court step'}")
    subject, body = build_draft(hearing, kind=kind, form=form, reasons=reasons, case_name=cc.case_name(ctx))
    created = cc.make_draft(ctx, subject=subject, html_body=body, to=[to], files=[], source="hearing-request")
    return {"web_link": str((created or {}).get("webLink") or "")}
