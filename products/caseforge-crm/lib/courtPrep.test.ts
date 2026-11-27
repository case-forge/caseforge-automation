import { describe, expect, it } from "vitest";
import { COURT_PREP_COLUMNS, COURT_PREP_KEYS, courtPrepCell, courtPrepRows, hearingLine } from "./courtPrep";
import { stubCourtPrep } from "./stubCourtPrep";

describe("Court Prep", () => {
  it("has the seven columns in the agreed order, Court Informed first", () => {
    expect(COURT_PREP_COLUMNS.map((c) => c.label)).toEqual(["Court Informed", "Client Informed", "Process Server Informed", "Papers Served", "Counsel Booked", "Bundle Sent", "Brief Sent"]);
    expect(COURT_PREP_COLUMNS.map((c) => c.key)).toEqual([...COURT_PREP_KEYS]);
  });
  it("writes a cell as the day, Yes for counsel with no known day, and nothing for nothing", () => {
    expect(courtPrepCell("2026-11-06T10:15:00Z")).toBe("06 Nov (Fri)");
    expect(courtPrepCell("yes")).toBe("Yes");
    expect(courtPrepCell("")).toBe("");
  });
  it("writes the hearing as a day, a time and a type", () => {
    expect(hearingLine({ hearing_date: "2026-11-15", hearing_time: "10:00:00", hearing_type: "FHDRA" })).toBe("15 Nov (Sun) 10:00 · FHDRA");
    expect(hearingLine({ hearing_date: "2026-11-15", hearing_time: "", hearing_type: "" })).toBe("15 Nov (Sun)");
  });
  it("keeps one row per hearing, soonest first, and a client with two hearings has two rows", () => {
    const rows = courtPrepRows(stubCourtPrep().items);
    expect(rows.map((r) => r.hearing_id)).toEqual([...rows.map((r) => r.hearing_id)].sort((a, b) => rows.find((r) => r.hearing_id === a)!.hearing_date.localeCompare(rows.find((r) => r.hearing_id === b)!.hearing_date)));
    expect(rows.filter((r) => r.matter_id === "9001")).toHaveLength(2);
    expect(new Set(rows.map((r) => r.hearing_id)).size).toBe(rows.length);
  });
});
