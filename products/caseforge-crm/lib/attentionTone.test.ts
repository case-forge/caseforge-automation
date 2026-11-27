import { describe, expect, it } from "vitest";
import { bellItemTone, bellItemWhen, obligationTone, orderBellItems } from "./attention";
import type { AttentionItem } from "./types";

function item(overrides: Partial<AttentionItem>): AttentionItem {
  return {
    task_id: "t1",
    matter_id: "9001",
    who: "Stub Testperson",
    kind: "update",
    label: "",
    complaint_domain: "",
    settlement_stage: "",
    subject: "Sample",
    summary: "Sample summary text.",
    deadline: "",
    importance: "normal",
    created: "",
    web_link: "",
    ...overrides,
  };
}

describe("bellItemTone", () => {
  it("keeps a complaint red, whatever else it carries", () => {
    expect(bellItemTone(item({ kind: "complaint", importance: "high", deadline: "Friday" }))).toBe("red");
    expect(bellItemTone(item({ kind: "court_rejected" }))).toBe("red");
    expect(bellItemTone(item({ kind: "counsel_rejected" }))).toBe("red");
  });

  it("makes work the firm wants green", () => {
    expect(bellItemTone(item({ kind: "settlement", label: "SETTLEMENT" }))).toBe("green");
    expect(bellItemTone(item({ kind: "settlement", label: "CARE PROCEEDINGS" }))).toBe("green");
    expect(bellItemTone(item({ kind: "court_order" }))).toBe("green");
    expect(bellItemTone(item({ kind: "counsel_accepted" }))).toBe("green");
    expect(bellItemTone(item({ label: "NEW REFERRAL" }))).toBe("green");
  });

  it("makes a deadline or an urgent task amber", () => {
    expect(bellItemTone(item({ importance: "high" }))).toBe("amber");
    expect(bellItemTone(item({ deadline: "by 4pm Friday" }))).toBe("amber");
    expect(bellItemTone(item({ label: "NEW REFERRAL", deadline: "tomorrow" }))).toBe("amber");
  });

  it("greys out what needs no action", () => {
    expect(bellItemTone(item({ kind: "scope_creep", label: "SCOPE CREEP" }))).toBe("grey");
    expect(bellItemTone(item({ label: "FYI" }))).toBe("grey");
    expect(bellItemTone(item({ label: "PROSPECT" }))).toBe("grey");
    expect(bellItemTone(item({ importance: "low" }))).toBe("grey");
  });

  it("leaves an ordinary task blue, with no label or an unknown one", () => {
    expect(bellItemTone(item({}))).toBe("blue");
    expect(bellItemTone(item({ label: "UPDATE" }))).toBe("blue");
    expect(bellItemTone(item({ kind: "something_new" }))).toBe("blue");
  });

  it("copes with a hub that leaves label or deadline out", () => {
    const bare = item({}) as unknown as Record<string, unknown>;
    delete bare.label;
    delete bare.deadline;
    expect(bellItemTone(bare as unknown as AttentionItem)).toBe("blue");
  });
});

describe("obligationTone", () => {
  it("follows the aging board's urgency", () => {
    expect(obligationTone("red")).toBe("red");
    expect(obligationTone("amber")).toBe("amber");
    expect(obligationTone("")).toBe("blue");
    expect(obligationTone("green")).toBe("blue");
  });
});

describe("bellItemWhen", () => {
  const now = new Date("2026-10-18T12:00:00Z");

  it("shows how long ago, with the exact date and time for the hover", () => {
    const when = bellItemWhen("2026-10-18T10:00:00Z", now);
    expect(when?.label).toBe("2 h ago");
    expect(when?.exact).toMatch(/^18 Oct 2026, \d\d:\d\d$/);
  });

  it("uses the shared age wording at each step", () => {
    expect(bellItemWhen("2026-10-18T11:59:50Z", now)?.label).toBe("just now");
    expect(bellItemWhen("2026-10-18T11:35:00Z", now)?.label).toBe("25 min ago");
    expect(bellItemWhen("2026-10-15T12:00:00Z", now)?.label).toBe("3 d ago");
  });

  it("never says a future time is ago", () => {
    expect(bellItemWhen("2026-10-18T13:00:00Z", now)?.label).toBe("just now");
  });

  it("shows nothing for no time at all", () => {
    expect(bellItemWhen("", now)).toBeNull();
    expect(bellItemWhen("   ", now)).toBeNull();
  });

  it("shows an unparseable value as it stands rather than hiding it", () => {
    expect(bellItemWhen("sometime last week", now)).toEqual({ label: "sometime last week", exact: "sometime last week" });
  });
});

describe("soft complaints (status chases)", () => {
  it("are amber, not red, and a hard or unmarked complaint stays red", () => {
    expect(bellItemTone(item({ kind: "complaint", severity: "soft" }))).toBe("amber");
    expect(bellItemTone(item({ kind: "complaint", severity: "hard" }))).toBe("red");
    expect(bellItemTone(item({ kind: "complaint", severity: "" }))).toBe("red");
    expect(bellItemTone(item({ kind: "complaint" }))).toBe("red");
  });

  it("sink below every other row, keeping the order of the rest", () => {
    const rows = [
      item({ task_id: "a", kind: "complaint", severity: "soft" }),
      item({ task_id: "b", kind: "complaint", severity: "hard" }),
      item({ task_id: "c", kind: "update" }),
      item({ task_id: "d", kind: "complaint", severity: "soft" }),
      item({ task_id: "e", label: "NEW REFERRAL" }),
    ];
    expect(orderBellItems(rows).map((r) => r.task_id)).toEqual(["b", "c", "e", "a", "d"]);
  });
});
