import { describe, expect, it } from "vitest";
import { DEFAULT_LOCK_REASON, eventTime, lockedReason, newestFirst, runBlockedReason, statusMark } from "./pipelineDisplay";
import { stubPipeline, stubRun, stubSetMode } from "./stubPipeline";
import { EMAIL_VARIANTS, MODE_WARNING, PIPELINE_STEP_KEYS } from "./pipelineTypes";

describe("statusMark", () => {
  it("gives every state a word and a shape", () => {
    for (const s of ["done", "todo", "attention", "blocked", "unknown"]) {
      const m = statusMark(s);
      expect(m.word.length).toBeGreaterThan(2);
      expect(m.shape.length).toBeGreaterThan(0);
    }
    expect(statusMark("mystery").word).toBe("Not known");
  });
});

describe("runBlockedReason", () => {
  it("says why, in the order that matters", () => {
    expect(runBlockedReason({ canRun: true, running: false })).toBe("");
    expect(runBlockedReason({ canRun: false, running: false })).toMatch(/cannot run/);
    expect(runBlockedReason({ canRun: true, running: true })).toMatch(/running/);
  });
});

describe("events", () => {
  it("sorts newest first and formats London time", () => {
    const rows = newestFirst([{ created_utc: "2026-09-25T10:00:00Z" }, { created_utc: "2026-09-25T12:00:00Z" }]);
    expect(rows[0].created_utc).toBe("2026-09-25T12:00:00Z");
    expect(eventTime("2026-09-25T14:30:00Z")).toMatch(/15:30/);
    expect(eventTime("nonsense")).toBe("");
  });
});

describe("stub pipeline", () => {
  it("has every step, the first done, and runs one at a time", () => {
    const p = stubPipeline("t-1");
    expect(p.steps.map((s) => s.key)).toEqual(PIPELINE_STEP_KEYS);
    expect(p.steps[0].key).toBe("record");
    expect(p.steps[0].status).toBe("done");
    expect(p.steps[1].key).toBe("folder");
    expect(p.steps[1].status).toBe("todo");
    expect(p.steps[3].can_run).toBe(false);
    const out = stubRun("t-1", "folder", "Sam", "");
    expect("error" in out).toBe(false);
    if (!("error" in out)) {
      expect(out.pipeline.steps[1].status).toBe("done");
      expect(out.pipeline.events.at(-1)?.by).toBe("Sam");
    }
  });
  it("needs a variant for the email step and knows both", () => {
    stubRun("t-2", "folder", "C", ""); stubRun("t-2", "statement", "C", "");
    expect(stubRun("t-2", "email", "C", "")).toHaveProperty("error");
    expect(EMAIL_VARIANTS.map((v) => v.key)).toEqual(["loa_signing"]);
    expect(stubRun("t-2", "email", "C", "loa_signing")).toHaveProperty("ok", true);
  });
  it("switches mode and refuses anything else", () => {
    expect(stubSetMode("auto")).toEqual({ mode: "auto" });
    expect(stubPipeline("t-3").mode).toBe("auto");
    expect(stubSetMode("wild")).toHaveProperty("error");
    stubSetMode("manual");
  });
  it("states the mode warning in plain words", () => {
    expect(MODE_WARNING).toMatch(/^Auto:.*Manual:/);
  });
});

describe("lockedReason", () => {
  it("treats a missing locked flag as unlocked (an older hub)", () => {
    expect(lockedReason(undefined)).toBe("");
    expect(lockedReason({})).toBe("");
    expect(lockedReason({ locked: false, lock_reason: "x" })).toBe("");
  });
  it("gives the hub's reason, or a default when it sends none", () => {
    expect(lockedReason({ locked: true, lock_reason: "Locked for a test" })).toBe("Locked for a test");
    expect(lockedReason({ locked: true, lock_reason: "  " })).toBe(DEFAULT_LOCK_REASON);
  });
  it("blocks every run with the lock reason first", () => {
    expect(runBlockedReason({ canRun: true, running: false, locked: "Locked" })).toBe("Locked");
  });
});
