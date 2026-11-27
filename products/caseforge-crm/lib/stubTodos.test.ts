import { describe, expect, it } from "vitest";
import { stubListTodos, stubSetAutomatic, stubSummary } from "./stubTodos";

const q = (view: string, extra: Partial<{ matterId: number | null; includeDone: boolean }> = {}) => stubListTodos({ view, matterId: null, includeDone: false, ...extra });

describe("the offline task list follows the real list's rules for automatic rows", () => {
  it("shows automatic rows only in their category and under All, never in the personal lists", () => {
    for (const view of ["my_day", "important", "planned", "tasks", "completed"]) {
      expect(q(view).filter((t) => t.source !== "manual"), view).toEqual([]);
    }
    expect(q("all").some((t) => t.source !== "manual")).toBe(true);
    expect(q("all", { includeDone: true }).some((t) => t.source !== "manual")).toBe(true);
    expect(q("all", { matterId: 9001 }).filter((t) => t.source !== "manual")).toEqual([]);
    const court = q("auto_court");
    expect(court.length).toBeGreaterThan(0);
    expect(court.every((t) => t.source !== "manual")).toBe(true);
    expect(q("auto_caseflow").every((t) => t.source !== "manual")).toBe(true);
  });

  it("hides them everywhere when the firm switch is off, and the counts match the lists", () => {
    stubSetAutomatic(false, []);
    expect(q("all").some((t) => t.source !== "manual")).toBe(false);
    expect(q("auto_court")).toEqual([]);
    expect(stubSummary().auto_on).toBe(0);
    stubSetAutomatic(true, ["court"]);
    expect(q("auto_court")).toEqual([]);
    expect(q("auto_bundle").length).toBeGreaterThan(0);
    stubSetAutomatic(true, []);
    const counts = stubSummary();
    expect(counts.tasks).toBe(q("tasks").length);
    expect(counts.planned).toBe(q("planned").length);
  });
});
