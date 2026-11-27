import { describe, expect, it } from "vitest";
import { attemptBadge, pipelineLoadingText, seenByLine } from "./pipelineDisplay";

describe("attemptBadge", () => {
  it("reads 'Attempt N out of M' for each failed attempt, filling one dot per attempt made", () => {
    expect(attemptBadge({ auto_tries: 1, auto_max: 3 })).toMatchObject({ total: 3, made: 1, text: "Attempt 1 out of 3", stopped: false });
    expect(attemptBadge({ auto_tries: 2, auto_max: 3 })?.text).toBe("Attempt 2 out of 3");
    expect(attemptBadge({ auto_tries: 1, auto_max: 3 })?.label).toBe("Attempt 1 out of 3 failed. Auto will try again.");
  });

  it("says Auto has stopped at the last attempt, and never counts past it", () => {
    expect(attemptBadge({ auto_tries: 3, auto_max: 3 })).toMatchObject({ made: 3, text: "Attempt 3 out of 3", stopped: true });
    expect(attemptBadge({ auto_tries: 3, auto_max: 3 })?.label).toBe("Attempt 3 out of 3 failed. Auto has stopped and needs a person.");
    expect(attemptBadge({ auto_tries: 9, auto_max: 3 })?.text).toBe("Attempt 3 out of 3");
  });

  it("shows nothing before the first failed attempt, or when an older hub sends no counts", () => {
    expect(attemptBadge({ auto_tries: 0, auto_max: 3 })).toBeNull();
    expect(attemptBadge({})).toBeNull();
    expect(attemptBadge({ auto_tries: 1, auto_max: 0 })).toBeNull();
    expect(attemptBadge({ auto_tries: 1, auto_max: 500 })).toBeNull();
  });
});

describe("pipelineLoadingText", () => {
  it("cycles its words every 3 seconds and adds the time from 20 seconds", () => {
    expect(pipelineLoadingText(0)).toBe("Reading the client's folders…");
    expect(pipelineLoadingText(3.2)).toBe("Checking the mailbox…");
    expect(pipelineLoadingText(17.9)).toBe("Lining up the steps…");
    expect(pipelineLoadingText(18)).toBe("Reading the client's folders…");
    expect(pipelineLoadingText(45.7)).toBe("Looking for the court's reply… still working (45s)");
  });
});

describe("seenByLine (the Activity log's Seen by)", () => {
  it("names each other person with when they last opened it, in London time", () => {
    const line = seenByLine([
      { who: "a@example.test", at: "2026-11-17T16:40:00Z" },
      { who: "b@example.test", at: "2026-07-01T09:12:00Z" },
    ]);
    expect(line).toBe("Seen by a@example.test, 17 Nov, 16:40; b@example.test, 1 Jul, 10:12");
  });

  it("is empty when nobody else has opened it, or the hub sent nothing", () => {
    expect(seenByLine([])).toBe("");
    expect(seenByLine(undefined)).toBe("");
    expect(seenByLine([{ who: " ", at: "2026-11-17T16:40:00Z" }])).toBe("");
  });

  it("keeps a viewer whose time cannot be read, without a stray comma", () => {
    expect(seenByLine([{ who: "a@example.test", at: "not a date" }])).toBe("Seen by a@example.test");
  });
});
