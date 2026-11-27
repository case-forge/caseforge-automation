import { describe, expect, it } from "vitest";
import {
  attentionItemTitle,
  bellButtonLabel,
  bellContents,
  canComplete,
  canOpenClient,
  canOpenObligation,
  complaintPill,
  counselItems,
  faceButtonLabel,
  obligationDetail,
  obligationUrgencyLabel,
  withoutItem,
} from "./attention";
import type { AttentionItem, AttentionObligation, AttentionResponse } from "./types";

function item(overrides: Partial<AttentionItem>): AttentionItem {
  return {
    task_id: "t1",
    matter_id: "544",
    who: "Amelia Client",
    kind: "complaint",
    label: "COMPLAINT",
    complaint_domain: "documenso_process",
    settlement_stage: "",
    subject: "Signing problem",
    summary: "cannot open the link",
    deadline: "",
    importance: "normal",
    created: "",
    web_link: "",
    ...overrides,
  };
}

describe("bellButtonLabel", () => {
  it("puts the counts in the words", () => {
    expect(bellButtonLabel(0, 1)).toBe("Notifications, 1 open");
    expect(bellButtonLabel(1, 2)).toBe("Notifications, 3 open, 1 complaint");
    expect(bellButtonLabel(2, 0)).toBe("Notifications, 2 open, 2 complaints");
  });

  it("reads zero as calm, not blank", () => {
    expect(bellButtonLabel(0, 0)).toBe("Notifications, none open");
  });
});

describe("bellContents", () => {
  const response = (over: Partial<AttentionResponse>): AttentionResponse => ({
    configured: true,
    red_count: 0,
    yellow_count: 0,
    green_count: 0,
    red: [],
    yellow: [],
    green: [],
    ...over,
  });

  it("lists complaints before tasks and totals both", () => {
    const c = item({ task_id: "c1" });
    const t = item({ task_id: "t1", kind: "update", label: "UPDATE", complaint_domain: "" });
    const out = bellContents(response({ red: [c], yellow: [t], red_count: 4, yellow_count: 2 }));
    expect(out.items.map((i) => i.task_id)).toEqual(["c1", "t1"]);
    expect(out.total).toBe(6);
    expect(out.complaints).toBe(4);
  });

  it("leaves employment settlements out of the bell", () => {
    const s = item({ task_id: "s1", kind: "settlement" });
    const out = bellContents(response({ green: [s], green_count: 3 }));
    expect(out.items).toEqual([]);
    expect(out.total).toBe(0);
  });

  it("puts a new referrer client in the bell, counted, after the tasks", () => {
    const t = item({ task_id: "t1", kind: "update", label: "UPDATE", complaint_domain: "" });
    const n = item({ task_id: "n1", kind: "new_client", label: "NEW REFERRAL", complaint_domain: "" });
    const s = item({ task_id: "s1", kind: "settlement" });
    const out = bellContents(response({ yellow: [t], yellow_count: 1, green: [s, n], green_count: 2 }));
    expect(out.items.map((i) => i.task_id)).toEqual(["t1", "n1"]);
    expect(out.total).toBe(2);
  });
});

describe("complaintPill", () => {
  it("says complaint, never other", () => {
    expect(complaintPill("other")).toBe("Complaint");
    expect(complaintPill("something new")).toBe("Complaint");
    expect(complaintPill("")).toBe("Complaint");
  });

  it("keeps a known domain as the detail", () => {
    expect(complaintPill("ccl_terms")).toBe("Complaint · CCL terms");
    expect(complaintPill("documenso_process")).toBe("Complaint · Documenso");
  });
});

describe("attentionItemTitle", () => {
  it("prefers who, then the subject, then a fixed fallback", () => {
    expect(attentionItemTitle(item({}))).toBe("Amelia Client");
    expect(attentionItemTitle(item({ who: "  ", subject: "Signing problem" }))).toBe("Signing problem");
    expect(attentionItemTitle(item({ who: "", subject: "" }))).toBe("Unknown sender");
  });
});

describe("canOpenClient", () => {
  it("needs both a matter and a name to search on", () => {
    expect(canOpenClient(item({}))).toBe(true);
    expect(canOpenClient(item({ matter_id: "" }))).toBe(false);
    expect(canOpenClient(item({ who: "" }))).toBe(false);
  });
});

const response = (over: Partial<AttentionResponse>): AttentionResponse => ({
  configured: true,
  red_count: 0,
  yellow_count: 0,
  green_count: 0,
  red: [],
  yellow: [],
  green: [],
  ...over,
});

const obligation = (over: Partial<AttentionObligation>): AttentionObligation => ({
  matter_id: "544",
  client: "Amelia Client",
  label: "Serve the order",
  urgency: "red",
  reason: "No statement of service on file.",
  hearing_date: "2026-10-02",
  age_working_days: 6,
  ...over,
});

describe("bellContents with scope creep and obligations", () => {
  it("counts scope creep and obligations in the total but never as complaints", () => {
    const sc = item({ task_id: "a:1", kind: "scope_creep" });
    const out = bellContents(
      response({
        yellow_count: 2,
        scope_creep: [sc],
        scope_creep_count: 3,
        obligations: [obligation({})],
        obligations_count: 4,
      }),
    );
    expect(out.total).toBe(2 + 3 + 4);
    expect(out.complaints).toBe(0);
    expect(out.scopeCreep.map((i) => i.task_id)).toEqual(["a:1"]);
    expect(out.obligations).toHaveLength(1);
  });

  it("falls back to the list lengths when a count is missing, and to zero for an older hub", () => {
    const out = bellContents(response({ scope_creep: [item({ task_id: "a:1" })], obligations: [obligation({}), obligation({ urgency: "amber" })] }));
    expect(out.scopeCreepCount).toBe(1);
    expect(out.obligationsCount).toBe(2);
    expect(bellContents(response({})).total).toBe(0);
  });

  it("keeps complaints first among the bell's own items", () => {
    const c = item({ task_id: "c1" });
    const t = item({ task_id: "t1", kind: "update", complaint_domain: "" });
    const out = bellContents(response({ red: [c], yellow: [t], red_count: 1, yellow_count: 1 }));
    expect(out.items.map((i) => i.task_id)).toEqual(["c1", "t1"]);
    expect(out.complaints).toBe(1);
  });
});

describe("obligation rows", () => {
  it("says the state in words", () => {
    expect(obligationUrgencyLabel("red")).toBe("Red · overdue");
    expect(obligationUrgencyLabel("amber")).toBe("Amber · ageing");
    expect(obligationUrgencyLabel("")).toBe("Open");
  });

  it("joins the reason and the age, with the right singular", () => {
    expect(obligationDetail(obligation({}))).toBe("No statement of service on file. · 6 working days old");
    expect(obligationDetail(obligation({ age_working_days: 1, reason: "" }))).toBe("1 working day old");
    expect(obligationDetail(obligation({ age_working_days: null, reason: "  " }))).toBe("");
  });

  it("opens only with a client and a matter", () => {
    expect(canOpenObligation(obligation({}))).toBe(true);
    expect(canOpenObligation(obligation({ matter_id: 544 }))).toBe(true);
    expect(canOpenObligation(obligation({ matter_id: null }))).toBe(false);
    expect(canOpenObligation(obligation({ client: " " }))).toBe(false);
  });
});

describe("counselItems", () => {
  const data = response({
    counsel_accepted: [item({ task_id: "a:1" }), item({ task_id: "a:2" })],
    counsel_accepted_count: 5,
    counsel_rejected: [item({ task_id: "a:3" })],
  });

  it("returns the hub's count when it has one, else the list length", () => {
    expect(counselItems(data, "accepted").count).toBe(5);
    expect(counselItems(data, "rejected").count).toBe(1);
  });

  it("is empty before the first answer and for an older hub", () => {
    expect(counselItems(null, "accepted")).toEqual({ items: [], count: 0 });
    expect(counselItems(response({}), "rejected")).toEqual({ items: [], count: 0 });
  });
});

describe("faceButtonLabel", () => {
  it("names both counts in words", () => {
    expect(faceButtonLabel("smile", 2, 1)).toBe("Approved and accepted, 2 statements approved, 1 counsel accepted");
    expect(faceButtonLabel("frown", 1, 0)).toBe("Wants changes or declined, 1 statement needing changes");
    expect(faceButtonLabel("frown", 0, 3)).toBe("Wants changes or declined, 3 counsel declined");
  });

  it("reads zero as calm", () => {
    expect(faceButtonLabel("smile", 0, 0)).toBe("Approved and accepted, none");
  });
});

describe("Done: canComplete and withoutItem", () => {
  it("only hub-held rows can be completed", () => {
    expect(canComplete(item({ task_id: "a:9", can_complete: true }))).toBe(true);
    expect(canComplete(item({ task_id: "a:9", can_complete: false }))).toBe(false);
    expect(canComplete(item({ task_id: "a:9" }))).toBe(false);
    expect(canComplete(item({ task_id: " ", can_complete: true }))).toBe(false);
  });

  it("drops the item from its list and lowers only that list's count", () => {
    const start = response({
      yellow: [item({ task_id: "t1" })],
      yellow_count: 4,
      scope_creep: [item({ task_id: "a:1" }), item({ task_id: "a:2" })],
      scope_creep_count: 2,
      counsel_rejected: [item({ task_id: "a:3" })],
      counsel_rejected_count: 1,
    });
    const out = withoutItem(start, "a:2");
    expect(out.scope_creep?.map((i) => i.task_id)).toEqual(["a:1"]);
    expect(out.scope_creep_count).toBe(1);
    expect(out.yellow_count).toBe(4);
    expect(out.counsel_rejected_count).toBe(1);
    expect(bellContents(out).total).toBe(4 + 1);
  });

  it("leaves everything alone for an id it does not hold, and never goes below zero", () => {
    const start = response({ scope_creep: [item({ task_id: "a:1" })], scope_creep_count: 0 });
    expect(withoutItem(start, "a:404")).toEqual(start);
    expect(withoutItem(start, "a:1").scope_creep_count).toBe(0);
  });

  it("does not add keys an older hub never sent", () => {
    const out = withoutItem(response({}), "a:1");
    expect(out.scope_creep).toBeUndefined();
    expect(out.counsel_accepted_count).toBeUndefined();
  });
});

import { isCourtItem } from "./attention";

describe("isCourtItem", () => {
  it("goes by the classifier's court route (the stored label) or the court's own kinds, never the sender name", () => {
    expect(isCourtItem({ label: "Court", kind: "update" })).toBe(true);
    expect(isCourtItem({ label: " court ", kind: "update" })).toBe(true);
    expect(isCourtItem({ label: "", kind: "court_order" })).toBe(true);
    expect(isCourtItem({ label: "", kind: "court_rejected" })).toBe(true);
    expect(isCourtItem({ label: "Counsel", kind: "update" })).toBe(false);
    expect(isCourtItem({ label: "courtyard services", kind: "update" })).toBe(false);
    expect(isCourtItem({})).toBe(false);
  });
});
