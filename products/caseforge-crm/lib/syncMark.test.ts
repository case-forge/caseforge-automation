import { describe, expect, it } from "vitest";
import { STALE_TEXT, syncMark } from "./syncMark";

describe("syncMark", () => {
  const sync = { level: 3, symbol: "🧬 ▰▰▰▱", meaning: "Position inferred from files", start_at: "email", start_number: 5, attention: false, scanned_utc: "2026-10-19T09:00:00Z" };
  it("says nothing when the hub sends no field", () => {
    expect(syncMark(undefined)).toBeNull();
  });
  it("marks an unscanned matter as muted not scanned", () => {
    expect(syncMark(null)).toMatchObject({ text: "not scanned", level: null, scanned: false, attention: false });
  });
  it("shows the symbol, the step to run from and the meaning as the tooltip", () => {
    expect(syncMark(sync)).toEqual({ text: "from step 5", level: 3, title: "Position inferred from files", attention: false, scanned: true, regressed: [], stale: false });
  });
  it("carries attention and leaves out the step when there is no number", () => {
    expect(syncMark({ ...sync, attention: true, start_number: null })).toMatchObject({ text: "", level: 3, attention: true });
  });
  it("keeps a step number of zero", () => {
    expect(syncMark({ ...sync, start_number: 0 })?.text).toContain("from step 0");
  });
  it("carries the reasons a case lost sync, in order", () => {
    const mark = syncMark({ ...sync, regressed: ["Sync level dropped from 4 to 3", "Moved book"] });
    expect(mark?.regressed).toEqual(["Sync level dropped from 4 to 3", "Moved book"]);
    expect(mark?.stale).toBe(false);
  });
  it("treats an empty or absent regressed list as not regressed", () => {
    expect(syncMark({ ...sync, regressed: [] })?.regressed).toEqual([]);
    expect(syncMark(sync)?.regressed).toEqual([]);
  });
  it("drops blank or non-string reasons so no empty bullet is drawn", () => {
    const mark = syncMark({ ...sync, regressed: ["", "  ", "Real reason", 7 as unknown as string] });
    expect(mark?.regressed).toEqual(["Real reason"]);
  });
  it("ignores a regressed value that is not a list (older or odd payloads)", () => {
    expect(syncMark({ ...sync, regressed: "oops" as unknown as string[] })?.regressed).toEqual([]);
  });
  it("flags a stale scan only when stale is exactly true", () => {
    expect(syncMark({ ...sync, stale: true })?.stale).toBe(true);
    expect(syncMark({ ...sync, stale: false })?.stale).toBe(false);
    expect(syncMark({ ...sync, stale: "yes" as unknown as boolean })?.stale).toBe(false);
    expect(STALE_TEXT).toBe("scan out of date");
  });
  it("keeps regressed and stale independent so both can show together", () => {
    const mark = syncMark({ ...sync, stale: true, regressed: ["A done step is no longer done"] });
    expect(mark).toMatchObject({ stale: true, regressed: ["A done step is no longer done"], scanned: true });
  });
  it("keeps every reason of a long list", () => {
    const many = Array.from({ length: 40 }, (_, i) => `Reason ${i + 1} ${"x".repeat(120)}`);
    expect(syncMark({ ...sync, regressed: many })?.regressed).toHaveLength(40);
  });
  it("gives an unscanned matter no regressed or stale state", () => {
    expect(syncMark(null)).toMatchObject({ regressed: [], stale: false });
  });
  it("is not changed by regressed or stale on the attention flag or the visible text", () => {
    expect(syncMark({ ...sync, stale: true, regressed: ["x"] })).toMatchObject({ text: "from step 5", level: 3, attention: false });
  });
});
