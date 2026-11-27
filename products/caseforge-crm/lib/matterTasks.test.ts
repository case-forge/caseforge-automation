import { describe, expect, it } from "vitest";
import {
  complaintDomainLabel,
  formatArrived,
  isCompleted,
  newestFirst,
  openItemCount,
  parseUtc,
  settlementStageLabel,
  subjectLine,
  taskPillLabel,
} from "./matterTasks";
import type { MatterTaskItem } from "./types";

function item(overrides: Partial<MatterTaskItem>): MatterTaskItem {
  return {
    task_id: "t1",
    kind: "update",
    complaint_domain: "",
    settlement_stage: "",
    subject: "",
    summary: "",
    deadline: "",
    importance: "normal",
    status: "notStarted",
    created: "",
    web_link: "",
    ...overrides,
  };
}

describe("complaintDomainLabel", () => {
  it("labels the known domains", () => {
    expect(complaintDomainLabel("ccl_terms")).toBe("CCL terms");
    expect(complaintDomainLabel("documenso_process")).toBe("Documenso");
    expect(complaintDomainLabel("other")).toBe("Other");
  });

  it("falls back to Other for an unknown domain rather than hiding it or showing the raw key", () => {
    expect(complaintDomainLabel("something_new")).toBe("Other");
    expect(complaintDomainLabel("")).toBe("Other");
  });
});

describe("taskPillLabel", () => {
  it("names a complaint with its domain", () => {
    expect(taskPillLabel(item({ kind: "complaint", complaint_domain: "documenso_process" }))).toBe(
      "Complaint · Documenso",
    );
  });

  it("names scope creep", () => {
    expect(taskPillLabel(item({ kind: "scope_creep" }))).toBe("Scope creep");
  });

  it("names an employment settlement with its stage, or plainly when the stage is unknown", () => {
    expect(taskPillLabel(item({ kind: "settlement", settlement_stage: "signed" }))).toBe(
      "Settlement · Signed and returned",
    );
    expect(taskPillLabel(item({ kind: "settlement", settlement_stage: "" }))).toBe("Settlement");
  });

  it("gives an ordinary update no pill", () => {
    expect(taskPillLabel(item({ kind: "update" }))).toBeNull();
  });
});

describe("isCompleted", () => {
  it("is true only for a completed task", () => {
    expect(isCompleted(item({ status: "completed" }))).toBe(true);
    expect(isCompleted(item({ status: "notStarted" }))).toBe(false);
  });
});

describe("subjectLine", () => {
  it("adds the prefix to a plain subject", () => {
    expect(subjectLine("Signing problem")).toBe("Re: Signing problem");
  });

  it("does not double a prefix the subject already has", () => {
    expect(subjectLine("Re: Signing problem")).toBe("Re: Signing problem");
    expect(subjectLine("RE: Signing problem")).toBe("RE: Signing problem");
  });

  it("is empty for an empty subject", () => {
    expect(subjectLine("  ")).toBe("");
  });
});

describe("settlementStageLabel", () => {
  it("labels the three stages and nothing else", () => {
    expect(settlementStageLabel("requested")).toBe("Requested");
    expect(settlementStageLabel("sent")).toBe("Sent out");
    expect(settlementStageLabel("signed")).toBe("Signed and returned");
    expect(settlementStageLabel("negotiating")).toBe("");
  });
});

describe("formatArrived", () => {
  const now = new Date("2026-10-08T15:00:00Z");

  it("shows the London date and time, in summer time an hour after UTC", () => {
    expect(formatArrived("2026-10-08T12:00:00Z", now)).toBe("8 Oct 13:00");
  });

  it("shows GMT in winter and adds the year only when it is not this year", () => {
    expect(formatArrived("2025-12-24T09:05:00Z", now)).toBe("24 Dec 2025 09:05");
  });

  it("reads Graph's seven fractional digits and a time with no zone as UTC", () => {
    expect(formatArrived("2026-10-08T12:00:00.1234567Z", now)).toBe("8 Oct 13:00");
    expect(formatArrived("2026-10-08T12:00:00", now)).toBe("8 Oct 13:00");
  });

  it("is empty for a missing or unreadable time", () => {
    expect(formatArrived("", now)).toBe("");
    expect(formatArrived("not a date", now)).toBe("");
    expect(Number.isNaN(parseUtc("nonsense"))).toBe(true);
  });
});

describe("newestFirst and openItemCount", () => {
  it("orders by arrival, newest first, with an unreadable time last, whatever the kind or status", () => {
    const rows = [
      item({ task_id: "old-complaint", kind: "complaint", created: "2026-10-01T09:00:00Z" }),
      item({ task_id: "none", created: "" }),
      item({ task_id: "new-done", status: "completed", created: "2026-10-08T09:00:00Z" }),
      item({ task_id: "mid", created: "2026-10-05T09:00:00.0000000Z" }),
    ];
    expect(newestFirst(rows).map((r) => r.task_id)).toEqual(["new-done", "mid", "old-complaint", "none"]);
    expect(rows[0].task_id).toBe("old-complaint");
  });

  it("counts every open item and nothing for an unconfigured or missing answer", () => {
    const items = [item({ task_id: "a" }), item({ task_id: "b", kind: "complaint" }), item({ task_id: "c", status: "completed" })];
    const base = { matter_id: "9001", open_complaints: 1, open_updates: 1, open_settlements: 0, items };
    expect(openItemCount({ ...base, configured: true })).toBe(2);
    expect(openItemCount({ ...base, configured: false })).toBe(0);
    expect(openItemCount(null)).toBe(0);
  });
});


describe("care proceedings pill", () => {
  it("reads 'Care proceedings', not a settlement stage", async () => {
    const { taskPillLabel } = await import("./matterTasks");
    const item = { kind: "settlement", settlement_stage: "care" } as unknown as import("./types").MatterTaskItem;
    expect(taskPillLabel(item)).toBe("Care proceedings");
  });
});
