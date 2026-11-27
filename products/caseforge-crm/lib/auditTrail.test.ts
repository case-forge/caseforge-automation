import { describe, expect, it, vi } from "vitest";
import { changeParts, kindLabel, loadAuditTrail, queryString, sourceLabel, whenLabel, type AuditRow } from "./auditTrail";
import { stubAuditTrail } from "./stubAuditTrail";

const base: AuditRow = { id: "x", at: "2026-11-06T16:02:11Z", kind: "person", who: "p@example.test", area: "file", action: "Moved", what: "", from: "", to: "", where: "", ip: "", seen_by: ["microsoft"] };

describe("audit trail helpers", () => {
  it("builds the query the route forwards, leaving out a blank search", () => {
    expect(queryString({ kind: "person", days: 7, q: "  ", offset: 0, limit: 100 })).toBe("kind=person&days=7&limit=100&offset=0");
    expect(queryString({ kind: "all", days: 30, q: " intro ", offset: 100, limit: 100 })).toContain("q=intro");
  });

  it("reads a move as old place then new place, and anything else as the one thing acted on", () => {
    expect(changeParts({ ...base, from: "A/old.pdf", to: "B/old.pdf" })).toEqual({ from: "A/old.pdf", to: "B/old.pdf" });
    expect(changeParts({ ...base, what: "A/new.pdf" })).toEqual({ what: "A/new.pdf" });
    expect(changeParts({ ...base, from: "A/only-old", to: "" })).toEqual({ what: "" });
  });

  it("says which logs saw a change and which kind made it", () => {
    expect(sourceLabel(["ours", "microsoft"])).toBe("Both logs");
    expect(sourceLabel(["microsoft"])).toBe("Microsoft");
    expect(sourceLabel(["ours"])).toBe("Our log");
    expect(kindLabel("person")).toBe("Person");
    expect(kindLabel("agent")).toBe("Agent");
    expect(kindLabel("automation")).toBe("Automation");
    expect(kindLabel("")).toBe("");
  });

  it("shows London time, in summer and in winter", () => {
    expect(whenLabel("2026-11-06T16:02:11Z")).toBe("6 Nov, 16:02");
    expect(whenLabel("2026-07-06T16:02:11Z")).toBe("6 Jul, 17:02");
    expect(whenLabel("not a date")).toBe("not a date");
  });
});

describe("loadAuditTrail", () => {
  const query = { kind: "all" as const, days: 7, q: "", offset: 0, limit: 100 };
  it("returns the list, hides the page on a 403 and reports any other failure as an error", async () => {
    const ok = vi.fn().mockResolvedValue(Response.json(stubAuditTrail("all", "")));
    const loaded = await loadAuditTrail(query, ok as unknown as typeof fetch);
    expect(loaded.state).toBe("ok");
    expect(String(ok.mock.calls[0][0])).toBe("/api/audit-trail?kind=all&days=7&limit=100&offset=0");
    expect((await loadAuditTrail(query, (async () => new Response("{}", { status: 403 })) as typeof fetch)).state).toBe("hidden");
    expect((await loadAuditTrail(query, (async () => new Response("{}", { status: 502 })) as typeof fetch)).state).toBe("error");
    expect((await loadAuditTrail(query, (async () => { throw new Error("offline"); }) as typeof fetch)).state).toBe("error");
  });
});

describe("the stub", () => {
  it("filters by kind and search, and the counts keep all three kinds", () => {
    const people = stubAuditTrail("person", "");
    expect(people.rows.every((r) => r.kind === "person")).toBe(true);
    expect(people.counts.person).toBeGreaterThan(0);
    expect(people.counts.agent).toBeGreaterThan(0);
    expect(people.counts.automation).toBeGreaterThan(0);
    expect(stubAuditTrail("automation", "").rows.every((r) => r.kind === "automation")).toBe(true);
    expect(stubAuditTrail("agent", "").rows.every((r) => r.kind === "agent" && r.area === "case flow")).toBe(true);
    expect(stubAuditTrail("all", "casework-scans").rows).toHaveLength(1);
  });
  it("has moves that read from old to new", () => {
    expect(stubAuditTrail("all", "").rows.some((r) => r.from && r.to)).toBe(true);
  });
});
