import { describe, expect, it } from "vitest";
import { PIPELINE_STEP_KEYS, PIPELINE_STEP_LABELS, PIPELINE_STEP_NUMBERS, stepRef, stepRefCap } from "./pipelineTypes";
import { stubPipeline } from "./stubPipeline";

describe("Case flow step numbers", () => {
  it("numbers each step by its place in the key list: from 0, no gap and no fraction, and stepRef reads the same lookup", () => {
    const numbers = PIPELINE_STEP_KEYS.map((key) => PIPELINE_STEP_NUMBERS[key]);
    expect(numbers).toEqual(Array.from({ length: PIPELINE_STEP_KEYS.length }, (_, i) => i));
    for (const key of PIPELINE_STEP_KEYS) expect(stepRef(key)).toBe(`step ${PIPELINE_STEP_KEYS.indexOf(key)}`);
    expect(stepRefCap("record")).toBe("Step 0");
    expect(stepRefCap("folder")).toBe("Step 1");
    expect(PIPELINE_STEP_KEYS.slice(2, 6)).toEqual(["statement", "email", "amend", "ws_sign"]);
  });

  it("shows the court steps, the hearing loop opening and the service steps in order", () => {
    expect(PIPELINE_STEP_KEYS.slice(6, 16)).toEqual(["court_pack", "court_email", "court_reply", "client_papers", "serve", "book_counsel", "bundle", "serve_other", "sos_received", "sos_to_court"]);
    for (const key of PIPELINE_STEP_KEYS) expect(PIPELINE_STEP_LABELS[key]).toBeTruthy();
  });

  it("starts with step 0, the client's sign-up, then the one folder step, and names step 0 as step 0", async () => {
    expect(PIPELINE_STEP_KEYS.slice(0, 2)).toEqual(["record", "folder"]);
    const { markDoneQuestion, resetStepQuestion } = await import("./pipelineDisplay");
    expect(resetStepQuestion({ number: 0, label: "Fetch" })).toContain("step 0, Fetch");
    expect(markDoneQuestion({ number: 0, label: "Fetch" }, "Sam")).toContain("step 0, Fetch");
  });

  it("puts the brief and the letters last", () => {
    expect(PIPELINE_STEP_KEYS.slice(17)).toEqual(["brief", "mid_letter", "closing_letter"]);
  });

  it("says who acts next on each step", () => {
    const steps = stubPipeline("stub-steps-test").steps;
    expect(steps.map((s) => s.key)).toEqual(PIPELINE_STEP_KEYS);
    for (const step of steps) expect(["you", "case flow", ""]).toContain(step.actor);
    expect(steps.find((s) => s.key === "record")?.actor).toBe("");
  });
});

describe("lastReadLabel", () => {
  it("names the oldest read among the steps still to do, in London time", async () => {
    const { lastReadLabel } = await import("./pipelineDisplay");
    const steps = [
      { status: "done", checked_utc: "2026-10-14T01:00:00Z" },
      { status: "todo", checked_utc: "2026-10-14T13:30:00Z" },
      { status: "attention", checked_utc: "2026-10-14T12:05:00Z" },
    ];
    expect(lastReadLabel(steps)).toBe("13:05");
    expect(lastReadLabel([{ status: "done", checked_utc: "2026-10-14T01:00:00Z" }, { status: "todo" }])).toBe("");
  });
});
