from __future__ import annotations

ACTIONS: list[tuple[str, str, str, bool]] = [
    ("Run Startup",          ":material/rocket_launch:", "Use tasks/startup-monitor/AGENT.md. Run the startup monitor and tell me what needs doing today.", True),
    ("Email Triage",         ":material/mail:", "Use context/emails.md and context/email-routing.md. Run a focused Graph mailbox triage for today's emails, sort by urgency (same-day hearings first, then high/normal/low within 3/7/14 working days), and give me a short action list. Do not run the full startup briefing.", True),
    ("Hearing Check",        ":material/event:", "Use the deterministic hearing telemetry route if available. What hearings are coming up in the next 14 days?", True),
    ("Client Search",        ":material/search:", "Client search: [NAME / PHONE / EMAIL / CASE NUMBER]", False),
    ("Status",               ":material/monitoring:", "Show today's status.", False),
    ("Legal Aid",            ":material/currency_pound:", "Open the Legal Aid signing queue.", False),
    ("Missing Order",        ":material/download:", "Open the Missing Order queue.", False),
    ("Missing Emails",       ":material/mark_email_read:", "Open the Missing Emails queue.", False),
    ("Invoices / Fee Notes", ":material/receipt_long:", "Open the Invoices / Fee Notes queue.", False),
    ("Sort Folder",          ":material/rule_folder:", "Open the Folder Sort queue.", False),
    ("Billing CSV",          ":material/calculate:", "Open the Billing CSV queue.", False),
    ("Attendance Note",      ":material/assignment:", "Use tasks/attendance-note/AGENT.md and make an attendance note for CLIENTNAME — ", False),
    ("Attendance Note Fast", ":material/edit_note:", "Use tasks/attendance-note-fast/AGENT.md. Make an attendance note from the facts I give you next. If the client/matter is already clear, do not re-ask for discovery. Backdate the note if I specify a date.", False),
    ("Case Snapshot",        ":material/summarize:", "Use skills/case-summary/SKILL.md. Give a short on-the-fly operational snapshot for CLIENTNAME: current position, next hearing/court/time/counsel, what is outstanding, and source map. Do not create or save a summary file.", False),
    ("Client Care Letter",   ":material/draft:",  "Use tasks/opening-letter/AGENT.md and make a client care letter for CLIENTNAME through Caseflow's client care letter step (tools/onboarding/pipeline/make_ccl.py). Do not draft one any other way.", False),
    ("Letterhead",           ":material/article:", "Open the client letterhead panel.", False),
    ("Notice of Acting",     ":material/contract:", "Create a Notice of Acting for CLIENTNAME", False),
    ("Brief to Counsel",     ":material/gavel:",  "Use templates/Brief to Counsel Instructions.md and live precedents. Prepare a brief to counsel for CLIENTNAME for the [DATE] hearing.", False),
    ("Bundle",               ":material/folder:", "Use tasks/bundle-preparation/AGENT.md and build the hearing bundle for CLIENTNAME for the [DATE] hearing", False),
    ("Closing Letter",       ":material/outbox:", "Use tasks/closing-letter/AGENT.md and draft a closing letter for CLIENTNAME. Use the client database/live matter data where available, then run tools/documents/lint_closing_letter.py and fix every flagged issue before any PDF export or mailbox draft.", False),
    ("Statement of Service", ":material/description:", "Use context/documents.md Statement of Service Standard and tools/documents/create-statement-of-service.py. Prepare a statement of service for CLIENTNAME.", False),
    ("File Scanned Docs",    ":material/drive_file_move:", "Use tasks/file-scanned-docs/AGENT.md. List unfiled scanned documents in the Scanned Docs inbox, match each to the correct client matter folder using the client database, and ask for confirmation before moving anything.", False),
]

CLIENT_ACTION_LABELS = {
    "Legal Aid",
    "Client Care Letter",
    "Letterhead",
    "Closing Letter",
    "Notice of Acting",
    "Case Snapshot",
}
START_TASK_ACTION_LABELS = {
    "Status",
    "Missing Emails",
    "Invoices / Fee Notes",
    "Sort Folder",
    "Billing CSV",
}
COUNSEL_ACTION_LABELS = {
    "Brief to Counsel",
}
COURT_ACTION_LABELS = {
    "Missing Order",
    "Bundle",
    "Statement of Service",
    "File Scanned Docs",
}


def client_action_rows() -> list[tuple[str, str, str]]:
    return [
        (label, icon, prompt)
        for label, icon, prompt, auto_send in ACTIONS
        if not auto_send and label in CLIENT_ACTION_LABELS
    ]


def action_rows_for(labels: set[str]) -> list[tuple[str, str, str]]:
    return [
        (label, icon, prompt)
        for label, icon, prompt, auto_send in ACTIONS
        if not auto_send and label in labels
    ]
