
import type { AttentionItem, AttentionObligation, AttentionResponse } from "./types";
import { DEMO_FIRM, DEMO_PRINCIPAL, DEMO_SECOND } from "./stubFirm";

const completed = new Set<string>();

function row(over: Partial<AttentionItem>): AttentionItem {
  return {
    task_id: "demo",
    matter_id: "9001",
    who: "Stub Testperson",
    kind: "update",
    label: "UPDATE",
    complaint_domain: "",
    settlement_stage: "",
    subject: "Sample",
    summary: "Sample summary text.",
    deadline: "",
    importance: "normal",
    created: "",
    web_link: "",
    sender_domain: "",
    can_complete: false,
    ...over,
  };
}

function open(rows: AttentionItem[]): AttentionItem[] {
  return rows.filter((r) => !completed.has(r.task_id));
}

export function stubCompleteAttention(taskId: string): { ok: true } {
  completed.add(taskId);
  return { ok: true };
}

export function stubAttention(): AttentionResponse {
  if (process.env.CASEFORGE_STUB_ATTENTION_DEMO !== "1") {
    return { configured: true, red_count: 0, yellow_count: 0, green_count: 0, red: [], yellow: [], green: [] };
  }

  const ago = (minutes: number): string => new Date(Date.now() - minutes * 60_000).toISOString();
  const complaint = row({ task_id: "c1", kind: "complaint", label: "COMPLAINT", complaint_domain: "other", summary: "Says the link would not open.", created: ago(25) });
  const task = row({ task_id: "t1", who: "Third Stubperson", matter_id: "9003", summary: "Court asked for a bundle." });

  const toned = [
    row({ task_id: "t2", importance: "high", deadline: "Friday 4pm", summary: "Court wants the position statement by Friday.", created: ago(130) }),
    row({ task_id: "t3", who: "Second Stubperson", matter_id: "9002", summary: "Asks for a call back about contact arrangements.", created: ago(60 * 26) }),
    row({ task_id: "t4", label: "FYI", importance: "low", summary: "referrer has already acknowledged the email.", created: ago(60 * 24 * 3) }),
    row({ task_id: "t5", label: "NEW REFERRAL", who: "Second Stubperson", matter_id: "9002", summary: "New referral from referrer.", created: ago(7) }),
    row({ task_id: "sw1", kind: "switchboard", label: "SWITCHBOARD", severity: "soft", who: "Second Stubperson", matter_id: "9002", summary: "Asks when the next hearing is.", created: ago(45) }),
  ];
  const settlement = row({ task_id: "s1", kind: "settlement", label: "SETTLEMENT" });
  const scope = open([
    row({
      task_id: "a:21",
      kind: "scope_creep",
      label: "SCOPE CREEP",
      who: "Second Stubperson",
      matter_id: "9002",
      subject: "Divorce",
      summary: "Asks the firm to start divorce proceedings, which is outside the instruction.",
      created: "2026-09-25T10:12:00Z",
      can_complete: true,
    }),
  ]);
  const accepted = open([
    row({
      task_id: "a:22",
      kind: "counsel_accepted",
      label: "COUNSEL ACCEPTED",
      summary: "Counsel accepts the brief for the hearing on 14 October and asks for the bundle by Friday.",
      created: "2026-09-26T08:30:00Z",
      sender_domain: "3boltcourt.com",
      can_complete: true,
    }),
    row({
      task_id: "a:23",
      kind: "counsel_accepted",
      label: "COUNSEL ACCEPTED",
      who: "Third Stubperson",
      matter_id: "9003",
      summary: "Counsel confirms availability for the return date.",
      created: "2026-09-24T15:02:00Z",
      sender_domain: "chambers.example.invalid",
      can_complete: false,
    }),
  ]);
  const rejected = open([
    row({
      task_id: "a:24",
      kind: "counsel_rejected",
      label: "COUNSEL DECLINED",
      who: "Second Stubperson",
      matter_id: "9002",
      summary: "Counsel is unavailable on the listed date and cannot take the brief.",
      created: "2026-09-26T09:05:00Z",
      sender_domain: "3boltcourt.com",
      can_complete: true,
    }),
  ]);
  const courtOrder = open([
    row({
      task_id: "a:25",
      kind: "court_order",
      label: "COURT ORDER",
      who: "Stub Testperson",
      matter_id: "9001",
      summary: "The court has sent the sealed non-molestation order.",
      created: "2026-10-10T09:15:00Z",
      sender_domain: "justice.gov.uk",
      can_complete: true,
    }),
  ]);
  const courtRejected = open([
    row({
      task_id: "a:26",
      kind: "court_rejected",
      label: "COURT REJECTED",
      who: "Second Stubperson",
      matter_id: "9002",
      summary: "The court will not take the application by email: it must go through the online portal.",
      created: "2026-10-10T11:40:00Z",
      sender_domain: "justice.gov.uk",
      can_complete: true,
    }),
  ]);
  const obligations: AttentionObligation[] = [
    {
      matter_id: "9001",
      client: "Stub Testperson",
      label: "Serve the order",
      urgency: "red",
      reason: "Order made 6 working days ago and no statement of service on file.",
      hearing_date: "2026-10-02",
      age_working_days: 6,
    },
    {
      matter_id: "9003",
      client: "Third Stubperson",
      label: "Send the bundle to counsel",
      urgency: "amber",
      reason: "Hearing in 3 weeks and the bundle has not gone.",
      hearing_date: "2026-10-16",
      age_working_days: 3,
    },
  ];
  const red = [complaint];
  const yellow = [task, ...toned];
  const scopeShown = scope;
  const obligationsShown = obligations;
  return {
    configured: true,
    red_count: red.length,
    yellow_count: yellow.length,
    green_count: 1,
    red,
    yellow,
    green: [settlement],
    scope_creep_count: scopeShown.length,
    scope_creep: scopeShown,
    counsel_accepted_count: accepted.length,
    counsel_accepted: accepted,
    counsel_rejected_count: rejected.length,
    counsel_rejected: rejected,
    court_order_count: courtOrder.length,
    court_order: courtOrder,
    court_rejected_count: courtRejected.length,
    court_rejected: courtRejected,
    obligations_count: obligationsShown.length,
    obligations: obligationsShown,
  };
}
