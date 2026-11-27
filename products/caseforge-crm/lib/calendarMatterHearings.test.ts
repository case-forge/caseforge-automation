
import { beforeEach, describe, expect, it } from "vitest";
import { addDaysIso, calendarShown, londonTodayIso } from "./hearings";
import { stubCreateHearing, stubListHearings, stubResetHearings } from "./stubHearings";

const MATTER = 9616;

function add(days: number, extra: Record<string, unknown> = {}) {
  return stubCreateHearing({ case_ref: `ZZ26F0${days + 50}`, hearing_date: addDaysIso(londonTodayIso(), days), matter_id: MATTER, ...extra }, "Sam");
}

describe("a matter's hearings on the calendar", () => {
  beforeEach(() => stubResetHearings());

  it("shows a linked upcoming hearing, in the range listing and the matter's own listing", () => {
    const today = londonTodayIso();
    const next = add(2);
    const range = stubListHearings(addDaysIso(today, -7), addDaysIso(today, 35));
    const shown = calendarShown(range.hearings, { todayIso: today, showPast: false, onlyUnlinked: false, filterText: "" });
    expect(shown.map((h) => h.hearing_id)).toContain(next.hearing_id);
    expect(stubListHearings(addDaysIso(today, -7), addDaysIso(today, 35), String(MATTER)).hearings.map((h) => h.hearing_id)).toEqual([next.hearing_id]);
  });

  it("hides a past hearing until 'show past' is on, and never shows a dismissed one", () => {
    const today = londonTodayIso();
    const past = add(-3);
    const range = stubListHearings(addDaysIso(today, -7), addDaysIso(today, 35)).hearings;
    expect(calendarShown(range, { todayIso: today, showPast: false, onlyUnlinked: false, filterText: "" }).map((h) => h.hearing_id)).not.toContain(past.hearing_id);
    expect(calendarShown(range, { todayIso: today, showPast: true, onlyUnlinked: false, filterText: "" }).map((h) => h.hearing_id)).toContain(past.hearing_id);
    const dismissed = { ...range.find((h) => h.hearing_id === past.hearing_id)!, review_state: "dismissed" as const };
    expect(calendarShown([dismissed], { todayIso: today, showPast: true, onlyUnlinked: false, filterText: "" })).toEqual([]);
  });

  it("keeps a linked hearing out of the Unlinked toggle and a today hearing on the calendar", () => {
    const today = londonTodayIso();
    const now = add(0);
    const range = stubListHearings(today, addDaysIso(today, 7)).hearings;
    expect(calendarShown(range, { todayIso: today, showPast: false, onlyUnlinked: false, filterText: "" }).map((h) => h.hearing_id)).toContain(now.hearing_id);
    expect(calendarShown(range, { todayIso: today, showPast: false, onlyUnlinked: true, filterText: "" }).map((h) => h.hearing_id)).not.toContain(now.hearing_id);
  });
});
