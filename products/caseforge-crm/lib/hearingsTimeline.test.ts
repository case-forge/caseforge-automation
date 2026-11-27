import { describe, expect, it } from "vitest";
import type { Hearing } from "./hearings";
import { hearingInstantMs, hearingsAndUpdates } from "./hearingsTimeline";
import type { MatterTaskItem } from "./types";

function hearing(over: Partial<Hearing> = {}): Hearing {
  return {
    hearing_id: 1,
    matter_id: 10,
    client_name: "Test Client",
    case_ref: "ZZ24F11111",
    hearing_date: "2026-09-25",
    hearing_time: "14:00",
    duration_minutes: 60,
    hearing_type: "Directions",
    order_types: "",
    is_final: false,
    court: "Example Family Court",
    mode: "in person",
    join_url: "",
    applicant: "",
    respondent: "",
    status: "scheduled",
    review_state: "ok",
    review_reason: "",
    confidence: 0.9,
    source_kind: "email",
    source_subject: "",
    source_received_utc: "",
    source_web_link: "",
    notes: "",
    created_utc: "",
    updated_utc: "",
    updated_by: "system",
    ...over,
  };
}

function update(task_id: string, created: string, over: Partial<MatterTaskItem> = {}): MatterTaskItem {
  return {
    task_id,
    kind: "update",
    complaint_domain: "",
    settlement_stage: "",
    subject: "",
    summary: `Summary ${task_id}`,
    deadline: "",
    importance: "normal",
    status: "notStarted",
    created,
    web_link: "",
    ...over,
  };
}

const keys = (hs: Hearing[], us: MatterTaskItem[]) => hearingsAndUpdates(hs, us).map((e) => e.key);

describe("when a hearing sits in the list", () => {
  it("is its date and time in London, British Summer Time included", () => {

    expect(hearingInstantMs(hearing({ hearing_date: "2026-09-25", hearing_time: "14:00" }))).toBe(Date.UTC(2026, 8, 25, 13, 0));
    expect(hearingInstantMs(hearing({ hearing_date: "2026-11-25", hearing_time: "14:00" }))).toBe(Date.UTC(2026, 10, 25, 14, 0));
  });

  it("puts a hearing with no time yet at the end of its day, and an unreadable date last", () => {
    expect(hearingInstantMs(hearing({ hearing_date: "2026-11-25", hearing_time: null }))).toBe(Date.UTC(2026, 10, 25, 23, 59, 59, 999));
    expect(hearingInstantMs(hearing({ hearing_date: "not a date" }))).toBe(Number.NEGATIVE_INFINITY);
  });
});

describe("the Hearings & updates list", () => {
  it("lists hearings only, newest first", () => {
    const hs = [
      hearing({ hearing_id: 1, hearing_date: "2026-09-01" }),
      hearing({ hearing_id: 2, hearing_date: "2026-12-01" }),
      hearing({ hearing_id: 3, hearing_date: "2026-10-01" }),
    ];
    expect(keys(hs, [])).toEqual(["hearing-2", "hearing-3", "hearing-1"]);
  });

  it("lists updates only, in the newest-first order they always had, unreadable times last", () => {
    const us = [update("a", "2026-10-01T09:00:00Z"), update("b", ""), update("c", "2026-10-08T09:00:00Z")];
    expect(keys([], us)).toEqual(["update-c", "update-a", "update-b"]);
  });

  it("slots each hearing in by its date among the updates", () => {
    const hs = [
      hearing({ hearing_id: 7, hearing_date: "2026-10-05", hearing_time: "10:00" }),
      hearing({ hearing_id: 8, hearing_date: "2026-11-20", hearing_time: "09:30" }),
    ];
    const us = [
      update("old", "2026-09-30T12:00:00Z"),
      update("mid", "2026-10-07T12:00:00Z"),

      update("same-day", "2026-10-05T08:30:00Z"),
      update("new", "2026-10-15T12:00:00Z"),
    ];
    expect(keys(hs, us)).toEqual(["hearing-8", "update-new", "update-mid", "hearing-7", "update-same-day", "update-old"]);
  });

  it("keeps a vacated hearing at its date, and leaves a dismissed one out", () => {
    const hs = [
      hearing({ hearing_id: 1, hearing_date: "2026-10-05", status: "vacated" }),
      hearing({ hearing_id: 2, hearing_date: "2026-10-06", review_state: "dismissed" }),
    ];
    const entries = hearingsAndUpdates(hs, [update("u", "2026-10-07T12:00:00Z"), update("v", "2026-10-01T12:00:00Z")]);
    expect(entries.map((e) => e.key)).toEqual(["update-u", "hearing-1", "update-v"]);
    const vacated = entries[1];
    expect(vacated.kind === "hearing" && vacated.hearing.status).toBe("vacated");
  });

  it("gives rows at the same moment a fixed order: hearings first, then updates as they came", () => {

    const hs = [
      hearing({ hearing_id: 4, hearing_date: "2026-10-05", hearing_time: "10:00" }),
      hearing({ hearing_id: 9, hearing_date: "2026-10-05", hearing_time: "10:00" }),
    ];
    const us = [update("x", "2026-10-05T09:00:00Z"), update("y", "2026-10-05T09:00:00Z")];
    const first = keys(hs, us);
    expect(first).toEqual(["hearing-9", "hearing-4", "update-x", "update-y"]);

    expect(keys([...hs].reverse(), us)).toEqual(first);
  });

  it("is empty when there is nothing", () => {
    expect(hearingsAndUpdates([], [])).toEqual([]);
  });
});
