from __future__ import annotations

import datetime as dt
import html
import json
import logging
import re
from typing import Mapping

import monitoring.ops_supervisor as ops_supervisor_lib

from vergil.signature_alerts import startup_signature_alerts
from documents.order_text_case import normalise_order_text
from vergil.formatting import LONDON_TZ, markdown_table
from vergil.hearings import active_case_status, calendar_hearing_state, hearing_detail
from vergil.intake_log import load_referralpartner_intake_log_today, merge_new_client_rows
from vergil.primitives import (
    REPO_ROOT,
    int_env,
    latest_json,
    normalise_client_key,
    normalise_space,
    ttl_cache,
)
from vergil.security import security_alert_display_rows
from vergil.security_store import load_security_alert_rows
from vergil.prompt_routing import (
    briefing_row_client,
    looks_like_incoming_order_row,
    looks_like_missing_email_archive_row,
)
from vergil.user_state import is_guest

OPS_SUPERVISOR_ALERT_LIMIT = int_env("CASEFORGE_CHAT_OPS_SUPERVISOR_ALERT_LIMIT", 4, 1)
OPS_SUPERVISOR_LOOKBACK_HOURS = int_env("CASEFORGE_CHAT_OPS_SUPERVISOR_HOURS", 72, 1)
OPS_SUPERVISOR_STARTUP_DAYS = int_env("CASEFORGE_CHAT_OPS_SUPERVISOR_STARTUP_DAYS", 7, 1)
BRIEFING_WORK_CARD_LIMIT = 3

log = logging.getLogger(__name__)


def load_posture_review() -> dict:
    path = REPO_ROOT / "telemetry" / "posture-review" / "latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        log.warning("posture review unreadable: %s", exc)
        return {"error": "The posture memo could not be read."}
    return payload if isinstance(payload, dict) else {}


def posture_review_section_html(review: Mapping) -> str:
    if not review:
        return ""
    if review.get("error"):
        return (
            '<div class="briefing-section" style="border-left:3px solid var(--amber);padding-left:10px;margin-bottom:8px;">'
            '<strong style="color:var(--amber)">AI posture memo unavailable</strong>'
            f'<br><span class="briefing-status">{html.escape(str(review.get("error"))[:220])}</span>'
            '</div>'
        )
    findings = [item for item in list(review.get("findings") or []) if isinstance(item, Mapping)]
    if not findings:
        return ""
    priority = str(findings[0].get("priority") or "monitor").lower()
    if priority == "do_now":
        colour = "var(--red)"
    elif priority == "monitor":
        colour = "var(--amber)"
    else:
        colour = "var(--lbl-green)"
    rows = ""
    for item in findings[:4]:
        label = html.escape(str(item.get("priority") or "").replace("_", " ").upper())
        title = html.escape(str(item.get("title") or "Posture review").strip()[:120])
        reward = html.escape(str(item.get("expected_reward") or "").strip()[:180])
        rows += (
            f'<div class="briefing-client">'
            f'<strong>{label}</strong> · {title}'
            f'{"<br>" if reward else ""}<span class="briefing-status">{reward}</span>'
            f'</div>'
        )
    generated = html.escape(str(review.get("generated_at") or "").strip()[:16].replace("T", " "))
    generated_html = f'<br><span class="briefing-status">{generated} UTC</span>' if generated else ""
    return (
        f'<div class="briefing-section" style="border-left:3px solid {colour};padding-left:10px;margin-bottom:8px;">'
        f'<strong style="color:{colour}">AI posture memo</strong>'
        f'{generated_html}'
        f'{rows}'
        '</div>'
    )


def ops_supervisor_alert_icon(severity: str) -> str:
    if severity == "red":
        return ":material/error:"
    if severity == "amber":
        return ":material/warning:"
    return ":material/info:"


def ops_supervisor_alert_rows(alerts: list[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for alert in alerts[:OPS_SUPERVISOR_ALERT_LIMIT]:
        rows.append(
            {
                "Severity": str(alert.get("severity") or ""),
                "Issue": str(alert.get("title") or ""),
            }
        )
    return rows


def health_colour(status: str, available: bool) -> str:
    if available and status == "available":
        return "#166534"
    if status in {"rate_limited", "timeout"}:
        return "var(--amber)"
    return "var(--red)"


def briefing_source_hint(row: Mapping, fallback: str = "") -> str:
    subject = normalise_space(str(row.get("subject") or "")).strip()
    folder = normalise_space(str(row.get("source_folder") or "")).strip()
    received = normalise_space(str(row.get("received_utc") or "")).strip()
    bits = [bit for bit in (folder, received[:16], subject[:120]) if bit]
    return " | ".join(bits) or fallback


def format_health_command_response(username: str | None = None) -> str:
    if is_guest(username):
        return "That command is only available to signed-in CaseForge users."
    try:
        payload = ops_supervisor_lib.evaluate_supervisor(
            hours=OPS_SUPERVISOR_LOOKBACK_HOURS,
            startup_days=OPS_SUPERVISOR_STARTUP_DAYS,
        )
    except Exception as exc:
        log.warning("health supervisor failed: %s", exc)
        return "Health supervisor failed."

    generated = str(payload.get("generated_at") or "")[:19].replace("T", " ")
    view = ops_supervisor_lib.plain_health_view(payload)
    severity = view["overall_severity"].upper()
    count = view["count"]
    lines = [
        f"**Health Supervisor - {generated} UTC**",
        "",
        f"Severity: **{severity}**",
    ]
    if count:
        lines.extend(["", f"{count} current alert{'s' if count != 1 else ''}."])
        rows = [
            [row["Severity"].upper(), row["Issue"]]
            for row in ops_supervisor_alert_rows(list(payload.get("alerts") or []))
        ]
        lines.extend(["", markdown_table(["Severity", "Issue"], rows)])
    else:
        lines.extend(["", "No current supervisor alerts."])

    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else {}
    calendar = metrics.get("hearing_calendar") if isinstance(metrics.get("hearing_calendar"), Mapping) else {}
    scanned = metrics.get("scanned_docs") if isinstance(metrics.get("scanned_docs"), Mapping) else {}
    tunnel = metrics.get("tunnel_health") if isinstance(metrics.get("tunnel_health"), Mapping) else {}
    if calendar or scanned or tunnel:
        quick_rows = [
            [
                "Calendar",
                f"upcoming 14d={calendar.get('upcoming_14d', 0)}, needs review={calendar.get('needs_review', 0)}, review soon={calendar.get('review_soon', 0)}",
            ],
            [
                "Scanned Docs",
                f"items={scanned.get('item_count', 0)}, changes={scanned.get('change_count', 0)}, calendar candidates={scanned.get('calendar_candidate_count', 0)}",
            ],
            [
                "Runtime",
                f"tunnel={tunnel.get('overall', 'unknown')}, red={tunnel.get('red', 0)}, amber={tunnel.get('amber', 0)}",
            ],
        ]
        lines.extend(["", markdown_table(["Area", "Snapshot"], quick_rows)])
    return "\n".join(line for line in lines if line is not None).strip()


def briefing_startup_work_items(data: Mapping) -> list[dict]:
    graph = data.get("graph") if isinstance(data.get("graph"), Mapping) else {}
    rows = [row for row in list((graph or {}).get("rows") or []) if isinstance(row, Mapping)]
    legal_aid_alerts = [alert for alert in list(data.get("legal_aid_signature_alerts") or []) if isinstance(alert, Mapping)]
    items: list[dict] = []
    order_clients: set[str] = set()
    seen: set[tuple[str, str]] = set()

    for row in rows:
        if not looks_like_incoming_order_row(row):
            continue
        client = briefing_row_client(row)
        key = ("missing_order", client.lower())
        if key in seen:
            continue
        seen.add(key)
        order_clients.add(client.lower())
        items.append(
            {
                "kind": "missing_order",
                "client": client,
                "task_type": "Incoming order",
                "source_hint": briefing_source_hint(row, "Startup detected an order-ready message."),
            }
        )
        if len([item for item in items if item.get("kind") == "missing_order"]) >= BRIEFING_WORK_CARD_LIMIT:
            break

    for alert in legal_aid_alerts[:BRIEFING_WORK_CARD_LIMIT]:
        client = normalise_space(str(alert.get("client") or "")).strip(" .,:;")
        if not client:
            continue
        key = ("legal_aid", client.lower())
        if key in seen:
            continue
        seen.add(key)
        subject = normalise_space(str(alert.get("subject") or "Legal Aid confirmation")).strip()
        received = normalise_space(str(alert.get("received_utc") or "")).strip()
        items.append(
            {
                "kind": "legal_aid",
                "client": client,
                "task_type": "Legal Aid signing pending",
                "source_hint": " | ".join(bit for bit in (received[:16], subject[:120]) if bit),
            }
        )

    archive_count = 0
    for row in rows:
        if not looks_like_missing_email_archive_row(row):
            continue
        client = briefing_row_client(row)
        if client.lower() in order_clients:
            continue
        key = ("email_archive", client.lower())
        if key in seen:
            continue
        seen.add(key)
        archive_count += 1
        items.append(
            {
                "kind": "email_archive",
                "client": client,
                "task_type": "Missing emails/archive work",
                "source_hint": briefing_source_hint(row, "Startup detected email archive work."),
            }
        )
        if archive_count >= BRIEFING_WORK_CARD_LIMIT:
            break

    return items


@ttl_cache(300)
def load_new_clients_today() -> tuple[list[dict], str]:
    results: list[dict] = []
    sql_error = ""
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    intake_results = load_referralpartner_intake_log_today(today)
    if intake_results:
        results = merge_new_client_rows(results, intake_results)

    try:
        _, graph = latest_json("graph-startup/*-readonly.json")
        if graph:
            for row in (graph.get("rows") or []):
                if (
                    str(row.get("category", "")).lower() == "referralpartner"
                    and row.get("has_attachments")
                    and not str(row.get("subject", "")).upper().startswith("RE:")
                ):
                    name = str(row.get("client_match") or "").strip()
                    if not name:
                        subject = str(row.get("subject") or "").strip()
                        match = re.search(r"\bDV\s*ASSIST\s*-\s*(.+)$", subject, flags=re.I)
                        name = normalise_space(match.group(1)) if match else ""
                    if name:
                        results = merge_new_client_rows(results, [{"name": name, "orders": "", "referral_source": "ReferralPartner"}])
    except Exception:
        pass

    try:
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT / "tools"))
        from clientdb_sql import get_connection
        sql = """
            SELECT p.canonical_name, m.order_requested_text, m.referral_source
            FROM   matters m
            JOIN   people  p ON m.primary_person_id = p.person_id
            WHERE  LEFT(m.created_utc, 10) = ?
            ORDER  BY m.created_utc
        """
        with get_connection() as conn:
            conn.timeout = 5
            cur = conn.cursor()
            cur.execute(sql, (today,))
            rows = cur.fetchall()
        if rows:
            sql_results = [
                {"name": r[0], "orders": normalise_order_text((r[1] or "").strip()), "referral_source": (r[2] or "").strip()}
                for r in rows
            ]
            results = merge_new_client_rows(results, sql_results)
    except Exception:
        sql_error = ""

    return results, sql_error

def load_briefing() -> dict:
    scorecard_dir = REPO_ROOT / "telemetry" / "startup-scorecards"
    graph_dir     = REPO_ROOT / "telemetry" / "graph-startup"
    todo_file     = REPO_ROOT / "telemetry" / "todo" / "latest-lint-report.json"
    result: dict = {}
    try:
        files = sorted(scorecard_dir.glob("scorecard-*.json")) if scorecard_dir.exists() else []
        if files:
            result["scorecard"] = json.loads(files[-1].read_text())
    except Exception:
        pass
    try:
        files = sorted(f for f in graph_dir.glob("*-readonly.json")) if graph_dir.exists() else []
        if files:
            result["graph"] = json.loads(files[-1].read_text())
            result["legal_aid_signature_alerts"] = startup_signature_alerts(result["graph"])
    except Exception:
        pass
    try:
        if todo_file.exists():
            result["todo"] = json.loads(todo_file.read_text())
    except Exception:
        pass
    try:
        new_clients, sql_error = load_new_clients_today()
        result["new_clients"] = new_clients
        result["sql_health_error"] = sql_error
    except Exception:
        pass
    try:
        todo_lint = ((result.get("scorecard") or {}).get("sub_results") or {}).get("todo_lint") or {}
        if todo_lint and not todo_lint.get("success", True):
            result["todo_lint_error"] = str(todo_lint.get("error") or "To Do lint failed")
    except Exception:
        pass
    try:
        result["posture_review"] = load_posture_review()
    except Exception:
        pass
    return result

def format_pii_command_response(username: str | None = None) -> str:
    if is_guest(username):
        return "That command is only available to signed-in CaseForge users."

    data = load_briefing()
    graph = data.get("graph") if isinstance(data.get("graph"), Mapping) else {}
    graph_rows = [row for row in list((graph or {}).get("rows") or []) if isinstance(row, dict)]
    client_statuses = [row for row in list((graph or {}).get("client_statuses") or []) if isinstance(row, dict)]
    scorecard = data.get("scorecard") if isinstance(data.get("scorecard"), Mapping) else {}
    run_utc = str(scorecard.get("run_utc") or "")

    exposed_clients: set[str] = set()
    hidden_clients = 0

    def allow_client(client: str) -> bool:
        nonlocal hidden_clients
        key = normalise_client_key(client)
        if not key:
            return True
        if key in exposed_clients:
            return True
        if len(exposed_clients) >= 9:
            hidden_clients += 1
            return False
        exposed_clients.add(key)
        return True

    work_rows: list[list[object]] = []
    for item in briefing_startup_work_items(data):
        client = str(item.get("client") or "").strip()
        if not client or not allow_client(client):
            continue
        work_rows.append([client, str(item.get("task_type") or ""), str(item.get("source_hint") or "")])

    for nc in list(data.get("new_clients") or []):
        if not isinstance(nc, Mapping):
            continue
        client = str(nc.get("name") or "").strip()
        if not client or not allow_client(client):
            continue
        detail = str(nc.get("summary") or "").strip() or " / ".join(
            bit for bit in [str(nc.get("orders") or "").strip(), str(nc.get("referral_source") or "").strip()] if bit
        )
        work_rows.append([client, "New client", detail])

    todo = data.get("todo") if isinstance(data.get("todo"), Mapping) else {}
    for task in list((todo or {}).get("new_client_tasks") or []):
        if not isinstance(task, Mapping):
            continue
        client = str(task.get("title") or "").strip()
        if not client or not allow_client(client):
            continue
        detail = " / ".join(
            bit
            for bit in [str(task.get("list") or "").strip(), f"due {task.get('due_date')}" if task.get("due_date") else ""]
            if bit
        )
        work_rows.append([client, "New-client task", detail])

    active_rows: list[list[object]] = []
    for row in client_statuses:
        client = str(row.get("client") or "").strip()
        flags = [str(item).strip() for item in list(row.get("attention_flags") or []) if str(item).strip()]
        status = active_case_status(row)
        if not client or not (flags or status) or not allow_client(client):
            continue
        active_rows.append([client, ", ".join(flags[:3]) or "Status", status])
        if len(active_rows) >= 8:
            break

    today = dt.datetime.now(LONDON_TZ).date()
    calendar_state = calendar_hearing_state()
    hearing_details: list[dict] = []
    for row in client_statuses:
        detail = hearing_detail(row, graph_rows, calendar_state)
        if detail and isinstance(detail.get("date"), dt.date) and detail["date"] >= today:
            hearing_details.append(detail)
    hearing_details.sort(key=lambda item: item["date"])
    hearing_rows: list[list[object]] = []
    for detail in hearing_details:
        client = str(detail.get("client") or "").strip()
        if not client or not allow_client(client):
            continue
        bits = [str(detail.get("time") or ""), str(detail.get("court") or ""), str(detail.get("counsel") or ""), str(detail.get("awaiting") or "")]
        hearing_rows.append([client, detail["date"].strftime("%d %B %Y"), " / ".join(bit for bit in bits if bit)])
        if len(hearing_rows) >= 8:
            break

    security_rows, security_error = load_security_alert_rows()
    safe_security_rows = security_alert_display_rows(security_rows)

    lines = ["**CaseForge Chat Briefing Snapshot**"]
    if run_utc:
        lines.extend(["", f"Latest startup: {run_utc[:19].replace('T', ' ')} UTC"])
    if work_rows:
        lines.extend(["", "**Work Ready**", markdown_table(["Client", "Task", "Detail"], work_rows[:10])])
    else:
        lines.extend(["", "**Work Ready**", "No front-page work-ready rows in the latest briefing."])
    if hearing_rows:
        lines.extend(["", "**Hearings**", markdown_table(["Client", "Date", "Detail"], hearing_rows)])
    if active_rows:
        lines.extend(["", "**Active Case Flags**", markdown_table(["Client", "Flag", "Status"], active_rows)])
    if hidden_clients:
        lines.extend(["", f"{hidden_clients} additional client-linked row(s) hidden by the single-response exposure cap."])

    if security_error:
        lines.extend(["", "**High-Risk Audit Warnings**", security_error])
    elif safe_security_rows:
        rows = [
            [
                row.get("Time", ""),
                row.get("Risk", ""),
                row.get("Operation", ""),
                row.get("Workload", ""),
                row.get("Result", ""),
                row.get("Source", ""),
            ]
            for row in safe_security_rows[:8]
        ]
        lines.extend(["", "**High-Risk Audit Warnings**", markdown_table(["Time", "Risk", "Operation", "Workload", "Result", "Source"], rows)])
    else:
        lines.extend(["", "**High-Risk Audit Warnings**", "No current high-risk local audit warnings in the alert window."])
    return "\n".join(line for line in lines if line).strip()
