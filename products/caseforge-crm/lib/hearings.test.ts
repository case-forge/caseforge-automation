import { describe, expect, it } from "vitest";
import {
  confirmedByWords,
  hearingMarkers,
  addYearsIso,
  matterHearingsWindow,
  onlyCourtReference,
  parseRange,
  splitMatterHearings,
  addDaysIso,
  compareHearings,
  countUnlinked,
  leadNotes,
  safeHttpsUrl,
  toCheckCount,
  truncateText,
  isUnlinked,
  linkableMatterId,
  linkOutcomeMessage,
  createPayloadFromForm,
  describeEdits,
  editsFromForm,
  emptyFormValues,
  endFloating,
  formFromHearing,
  formatDayHeading,
  formatTime12,
  formatTimeCompact,
  groupByDay,
  hearingLabel,
  hearingParties,
  hearingsQuery,
  inclusiveRange,
  isValidIsoDate,
  isWeekend,
  londonNowFloating,
  londonTodayIso,
  normaliseTime,
  safeHttpUrl,
  startFloating,
  toCalendarEvent,
  isCounselBooked,
  visibleConfidence,
  upcomingWindow,
  validateHearingForm,
  durationLabel,
} from "./hearings";
import type { Hearing } from "./hearings";

function hearing(over: Partial<Hearing> = {}): Hearing {
  return {
    hearing_id: 1,
    matter_id: 10,
    client_name: "Alice Medlartest",
    case_ref: "AB26F11111",
    hearing_date: "2026-09-25",
    hearing_time: "14:00",
    duration_minutes: 90,
    hearing_type: "Directions",
    order_types: "NMO/OO",
    is_final: false,
    court: "Central Family Court",
    mode: "in person",
    join_url: "",
    applicant: "Alice Medlartest",
    respondent: "Ben Medlartest",
    status: "scheduled",
    review_state: "ok",
    review_reason: "",
    confidence: 0.9,
    source_kind: "email",
    source_subject: "Notice of hearing",
    source_received_utc: "2026-09-20T09:00:00Z",
    source_web_link: "",
    notes: "",
    created_utc: "2026-09-20T09:00:00Z",
    updated_utc: "2026-09-20T09:00:00Z",
    updated_by: "system",
    ...over,
  };
}

describe("date helpers", () => {
  it("validates real calendar dates only", () => {
    expect(isValidIsoDate("2026-09-25")).toBe(true);
    expect(isValidIsoDate("2026-02-30")).toBe(false);
    expect(isValidIsoDate("25/09/2026")).toBe(false);
    expect(isValidIsoDate("")).toBe(false);
  });

  it("adds days across month and year boundaries", () => {
    expect(addDaysIso("2026-09-30", 1)).toBe("2026-10-01");
    expect(addDaysIso("2026-01-01", -1)).toBe("2025-12-31");
    expect(addDaysIso("2028-02-28", 1)).toBe("2028-02-29");
  });

  it("knows weekends", () => {
    expect(isWeekend("2026-09-19")).toBe(true);
    expect(isWeekend("2026-09-20")).toBe(true);
    expect(isWeekend("2026-09-21")).toBe(false);
  });

  it("reads London today from the London wall clock, not the UTC one", () => {

    const instant = new Date("2026-06-30T23:30:00Z");
    expect(londonTodayIso(instant)).toBe("2026-07-01");
    expect(londonNowFloating(instant)).toBe("2026-07-01T00:30:00");

    expect(londonNowFloating(new Date("2026-12-01T09:05:07Z"))).toBe("2026-12-01T09:05:07");
  });

  it("formats times the way the firm writes them", () => {
    expect(formatTime12("14:00")).toBe("2:00pm");
    expect(formatTime12("09:30")).toBe("9:30am");
    expect(formatTime12("00:15")).toBe("12:15am");
    expect(formatTime12("12:00")).toBe("12:00pm");
    expect(formatTime12(null)).toBe("Time TBC");
    expect(formatTime12("")).toBe("Time TBC");
  });

  it("has a compact form for month cells", () => {
    expect(formatTimeCompact("14:00")).toBe("2pm");
    expect(formatTimeCompact("10:00")).toBe("10am");
    expect(formatTimeCompact("09:30")).toBe("9:30am");
    expect(formatTimeCompact("12:00")).toBe("12pm");
    expect(formatTimeCompact("00:00")).toBe("12am");
    expect(formatTimeCompact(null)).toBe("TBC");
  });

  it("tolerates a seconds suffix on the time", () => {
    expect(normaliseTime("10:00:00")).toBe("10:00");
    expect(normaliseTime("9:05")).toBe("09:05");
    expect(normaliseTime("soon")).toBeNull();
  });

  it("labels rail headings relative to today", () => {
    expect(formatDayHeading("2026-09-23", "2026-09-23")).toBe("Today");
    expect(formatDayHeading("2026-09-24", "2026-09-23")).toBe("Tomorrow");
    expect(formatDayHeading("2026-09-25", "2026-09-23")).toBe("Friday 25 September");
  });
});

describe("event mapping", () => {
  it("keeps the wall clock: start and end are naive strings", () => {
    const h = hearing();
    expect(startFloating(h)).toBe("2026-09-25T14:00:00");
    expect(endFloating(h)).toBe("2026-09-25T15:30:00");
  });

  it("rolls the end over midnight without a zone shift", () => {
    expect(endFloating({ hearing_date: "2026-03-28", hearing_time: "23:30", duration_minutes: 60 })).toBe(
      "2026-03-29T00:30:00",
    );
  });

  it("treats a hearing with no time as an all-day, date-only event", () => {
    const event = toCalendarEvent(hearing({ hearing_time: null }));
    expect(event.allDay).toBe(true);
    expect(event.start).toBe("2026-09-25");
    expect(event.end).toBeUndefined();
  });

  it("falls back to 60 minutes for a nonsense duration", () => {
    expect(endFloating({ hearing_date: "2026-09-25", hearing_time: "10:00", duration_minutes: 0 })).toBe(
      "2026-09-25T11:00:00",
    );
  });

  it("marks final, vacated, cancelled and review-state hearings by class", () => {
    expect(toCalendarEvent(hearing({ is_final: true })).classNames).toContain("hearing-ev--final");
    expect(toCalendarEvent(hearing({ is_final: true, status: "vacated" })).classNames).not.toContain(
      "hearing-ev--final",
    );
    expect(toCalendarEvent(hearing({ status: "vacated" })).classNames).toContain("hearing-ev--vacated");

    expect(toCalendarEvent(hearing({ status: "cancelled" })).classNames).toContain("hearing-ev--vacated");
    expect(toCalendarEvent(hearing({ request_state: "vacation_requested" })).classNames).toContain("hearing-ev--request");
    expect(toCalendarEvent(hearing({ review_state: "needs_review" })).classNames).toContain("hearing-ev--review");
  });

  it("prefers order types over the free-text hearing type for the label", () => {
    expect(hearingLabel(hearing())).toBe("NMO/OO");
    expect(hearingLabel(hearing({ order_types: "" }))).toBe("Directions");
    expect(hearingLabel(hearing({ order_types: "", hearing_type: "" }))).toBe("Hearing");
  });

  it("names the client, else the parties, else the case number", () => {
    expect(hearingParties(hearing())).toBe("Alice Medlartest");
    expect(hearingParties(hearing({ client_name: null }))).toBe("Alice Medlartest v Ben Medlartest");
    expect(hearingParties(hearing({ client_name: null, applicant: "", respondent: "" }))).toBe("AB26F11111");
    expect(hearingParties(hearing({ client_name: null, applicant: "", respondent: "", case_ref: "" }))).toBe(
      "Unlinked hearing",
    );
  });
});

describe("unlinked hearings", () => {
  it("counts hearings with no matter, ignoring dismissed ones", () => {
    const list = [
      hearing({ hearing_id: 1, matter_id: null }),
      hearing({ hearing_id: 2, matter_id: 7 }),
      hearing({ hearing_id: 3, matter_id: null, review_state: "dismissed" }),
      hearing({ hearing_id: 4, matter_id: null, review_state: "needs_review" }),
    ];
    expect(countUnlinked(list)).toBe(2);
    expect(isUnlinked(list[0])).toBe(true);
    expect(isUnlinked(list[1])).toBe(false);
  });

  it("is not a reason for review: an unlinked hearing maps to an ordinary event", () => {
    const event = toCalendarEvent(hearing({ matter_id: null }));
    expect(event.classNames).toEqual(["hearing-ev"]);
  });

  it("only lets a real numeric matter id through to a link request", () => {
    expect(linkableMatterId(42)).toBe(42);
    expect(linkableMatterId("42")).toBe(42);
    expect(linkableMatterId(" 42 ")).toBe(42);
    for (const bad of [null, undefined, "", "STUB-001", "42abc", "4.2", 0, "0", -3, 1.5, {}, NaN]) {
      expect(linkableMatterId(bad)).toBeNull();
    }
  });

  it("explains each outcome of the case-number memory, and always says the link was applied", () => {
    for (const ref of ["recorded", "exists", "conflict", "skipped", "failed", "something-new"]) {
      expect(linkOutcomeMessage(ref, "AB26F11111", "Alice Medlartest")).toContain("Linked to Alice Medlartest");
    }
    expect(linkOutcomeMessage("recorded", "AB26F11111", "Alice Medlartest")).toContain("future emails will link themselves");
    expect(linkOutcomeMessage("exists", "AB26F11111", "Alice Medlartest")).toContain("already recorded");
    const conflict = linkOutcomeMessage("conflict", "AB26F11111", "Alice Medlartest");
    expect(conflict).toContain("already belongs to another client");
    expect(conflict).toContain("Linked to Alice Medlartest");
    expect(linkOutcomeMessage("failed", "AB26F11111", "Alice Medlartest")).toContain("could not be recorded");
    expect(linkOutcomeMessage("recorded", "", "")).toContain("the client");
  });
});

describe("a client's hearings", () => {
  const today = "2026-09-24";

  it("moves whole years and clamps 29 February", () => {
    expect(addYearsIso("2026-09-24", -2)).toBe("2024-09-24");
    expect(addYearsIso("2026-09-24", 3)).toBe("2029-09-24");
    expect(addYearsIso("2028-02-29", 1)).toBe("2029-02-28");
    expect(addYearsIso("2028-02-29", 4)).toBe("2032-02-29");
  });

  it("loads two years back and three ahead", () => {
    expect(matterHearingsWindow(today)).toEqual({ from: "2024-09-24", to: "2029-09-24" });
  });

  it("splits upcoming (soonest first) from past (latest first) and treats today as upcoming", () => {
    const list = [
      hearing({ hearing_id: 1, hearing_date: "2026-09-10" }),
      hearing({ hearing_id: 2, hearing_date: "2026-10-01", hearing_time: "10:00" }),
      hearing({ hearing_id: 3, hearing_date: "2026-09-24", hearing_time: "09:00" }),
      hearing({ hearing_id: 4, hearing_date: "2025-01-05" }),
      hearing({ hearing_id: 5, hearing_date: "2026-09-30", review_state: "dismissed" }),
    ];
    const g = splitMatterHearings(list, today);
    expect(g.upcoming.map((h) => h.hearing_id)).toEqual([3, 2]);
    expect(g.past.map((h) => h.hearing_id)).toEqual([1, 4]);
  });

  it("counts only scheduled upcoming hearings for the tab badge", () => {
    const list = [
      hearing({ hearing_id: 1, hearing_date: "2026-10-01" }),
      hearing({ hearing_id: 2, hearing_date: "2026-10-02", status: "vacated" }),
      hearing({ hearing_id: 3, hearing_date: "2026-10-03", status: "cancelled" }),
      hearing({ hearing_id: 4, hearing_date: "2026-09-01" }),
    ];
    const g = splitMatterHearings(list, today);
    expect(g.upcoming).toHaveLength(3);
    expect(g.upcomingScheduled).toBe(1);
    expect(splitMatterHearings([], today).upcomingScheduled).toBe(0);
  });

  it("prefills a court number only when the record has exactly one", () => {
    expect(onlyCourtReference(["ab26f11111"])).toBe("AB26F11111");
    expect(onlyCourtReference(["AB26F11111", "ab26f11111"])).toBe("AB26F11111");
    expect(onlyCourtReference([])).toBe("");
    expect(onlyCourtReference(["AB26F11111", "CD26P22222"])).toBe("");
    expect(onlyCourtReference([" ", ""])).toBe("");
  });

  it("allows a long range for one matter, but not for the whole calendar", () => {
    const long = "from=2024-09-24&to=2029-09-24";
    expect(parseRange(new URLSearchParams(long)).ok).toBe(false);
    expect(parseRange(new URLSearchParams(`${long}&matter_id=42`)).ok).toBe(true);
    expect(parseRange(new URLSearchParams("from=2020-01-01&to=2030-01-01&matter_id=42")).ok).toBe(false);
    expect(parseRange(new URLSearchParams(`${long}&matter_id=abc`)).ok).toBe(false);
  });
});

describe("leads (emails to check)", () => {
  it("adds doubtful hearings and open leads for the badge, tolerating a hub that omits the leads count", () => {
    expect(toCheckCount(3, 2)).toBe(5);
    expect(toCheckCount(0, 0)).toBe(0);
    expect(toCheckCount(3, undefined)).toBe(3);
    expect(toCheckCount(-1, -4)).toBe(0);
  });

  it("only ever lets an https link become an href", () => {
    expect(safeHttpsUrl("https://outlook.office365.com/owa/?ItemID=abc")).toBe("https://outlook.office365.com/owa/?ItemID=abc");
    for (const bad of ["http://outlook.office365.com/x", "javascript:alert(1)", "data:text/html,x", "//evil.example", "HTTPS://x.example", "  ", "", null, undefined, "https://"]) {
      expect(safeHttpsUrl(bad)).toBe("");
    }
    expect(safeHttpsUrl("  https://ok.example/a  ")).toBe("https://ok.example/a");
  });

  it("truncates long subjects with an ellipsis and leaves short ones alone", () => {
    expect(truncateText("Short")).toBe("Short");
    const long = "x".repeat(200);
    const cut = truncateText(long, 50);
    expect(cut.length).toBe(50);
    expect(cut.endsWith("…")).toBe(true);
    expect(truncateText("  padded  ")).toBe("padded");
  });

  it("prefills the notes of a hearing added from an email, and nothing for a blank subject", () => {
    expect(leadNotes({ source_subject: "RE: Notice of hearing" })).toBe("From email: RE: Notice of hearing");
    expect(leadNotes({ source_subject: "   " })).toBe("");
    expect(leadNotes({ source_subject: "y".repeat(400) }).length).toBeLessThanOrEqual("From email: ".length + 200);
  });
});

describe("grouping and ordering", () => {
  it("sorts by date then time, untimed last, and drops dismissed rows", () => {
    const list = [
      hearing({ hearing_id: 3, hearing_date: "2026-09-26", hearing_time: "10:00" }),
      hearing({ hearing_id: 2, hearing_time: null }),
      hearing({ hearing_id: 1, hearing_time: "09:30" }),
      hearing({ hearing_id: 4, review_state: "dismissed" }),
    ];
    const groups = groupByDay(list);
    expect(groups.map((g) => g.date)).toEqual(["2026-09-25", "2026-09-26"]);
    expect(groups[0].items.map((h) => h.hearing_id)).toEqual([1, 2]);
    expect(list.sort(compareHearings)[0].hearing_id).toBe(1);
  });
});

describe("ranges", () => {
  it("converts FullCalendar's exclusive end into the API's inclusive to", () => {
    expect(inclusiveRange("2026-09-01T00:00:00", "2026-10-06T00:00:00")).toEqual({
      from: "2026-09-01",
      to: "2026-10-05",
    });
  });

  it("never returns to before from", () => {
    expect(inclusiveRange("2026-09-01", "2026-09-01")).toEqual({ from: "2026-09-01", to: "2026-09-01" });
  });

  it("builds the rail window inclusively", () => {
    expect(upcomingWindow("2026-09-23", 14)).toEqual({ from: "2026-09-23", to: "2026-10-06" });
  });

  it("encodes the query and only adds a matter when given one", () => {
    expect(hearingsQuery("2026-09-01", "2026-09-30")).toBe("from=2026-09-01&to=2026-09-30");
    expect(hearingsQuery("2026-09-01", "2026-09-30", 42)).toBe("from=2026-09-01&to=2026-09-30&matter_id=42");
    expect(hearingsQuery("2026-09-01", "2026-09-30", " ")).toBe("from=2026-09-01&to=2026-09-30");
  });
});

describe("safeHttpUrl", () => {
  it("accepts http(s) and rejects script and data URLs", () => {
    expect(safeHttpUrl("https://example.org/join")).toBe("https://example.org/join");
    expect(safeHttpUrl("javascript:alert(1)")).toBe("");
    expect(safeHttpUrl("data:text/html,x")).toBe("");
    expect(safeHttpUrl("not a url")).toBe("");
    expect(safeHttpUrl(null)).toBe("");
  });
});

describe("form validation", () => {
  const good = emptyFormValues({ case_ref: "AB26F11111", hearing_date: "2026-09-25", hearing_time: "10:00" });

  it("accepts a complete entry", () => {
    expect(validateHearingForm(good, { requireCaseRef: true })).toEqual({ errors: {}, warnings: [] });
  });

  it("requires a case number only when asked", () => {
    const blank = { ...good, case_ref: "" };
    expect(validateHearingForm(blank, { requireCaseRef: true }).errors.case_ref).toBeTruthy();
    expect(validateHearingForm(blank, { requireCaseRef: false }).errors.case_ref).toBeUndefined();
  });

  it("rejects bad dates, times, durations, matter ids and links", () => {
    const bad = { ...good, hearing_date: "2026-13-01", hearing_time: "25:00", duration_minutes: "2", matter_id: "x1", join_url: "ftp://x" };
    const { errors } = validateHearingForm(bad, { requireCaseRef: true });
    expect(Object.keys(errors).sort()).toEqual(["duration_minutes", "hearing_date", "hearing_time", "join_url", "matter_id"]);
  });

  it("warns, without blocking, on weekend dates and out-of-hours times", () => {
    const check = validateHearingForm({ ...good, hearing_date: "2026-09-19", hearing_time: "07:00" }, { requireCaseRef: true });
    expect(check.errors).toEqual({});
    expect(check.warnings).toHaveLength(2);
  });

  it("allows an empty time (time to be confirmed)", () => {
    expect(validateHearingForm({ ...good, hearing_time: "" }, { requireCaseRef: true }).errors).toEqual({});
  });
});

describe("edits", () => {
  it("sends only the fields that changed", () => {
    const h = hearing();
    const values = { ...formFromHearing(h), hearing_time: "15:30", notes: "  Counsel to attend " };
    expect(editsFromForm(h, values)).toEqual({ hearing_time: "15:30", notes: "Counsel to attend" });
  });

  it("sends nothing when nothing changed", () => {
    const h = hearing();
    expect(editsFromForm(h, formFromHearing(h))).toEqual({});
  });

  it("clears a time by sending null", () => {
    const h = hearing();
    expect(editsFromForm(h, { ...formFromHearing(h), hearing_time: "" })).toEqual({ hearing_time: null });
  });

  it("normalises the case number and order types to upper case", () => {
    const h = hearing({ case_ref: "", order_types: "" });
    const edits = editsFromForm(h, { ...formFromHearing(h), case_ref: "ab26f99999", order_types: "nmo/oo" });
    expect(edits).toEqual({ case_ref: "AB26F99999", order_types: "NMO/OO" });

    expect(editsFromForm(hearing(), { ...formFromHearing(hearing()), order_types: "nmo/oo" })).toEqual({});
  });

  it("builds a full create payload with a numeric matter id or null", () => {
    const payload = createPayloadFromForm(emptyFormValues({ case_ref: "ab26f11111", hearing_date: "2026-09-25", matter_id: "12" }));
    expect(payload.case_ref).toBe("AB26F11111");
    expect(payload.matter_id).toBe(12);
    expect(payload.hearing_time).toBeNull();

    expect(payload.duration_minutes).toBeNull();
    expect(createPayloadFromForm(emptyFormValues({ duration_minutes: "90" })).duration_minutes).toBe(90);
    expect(createPayloadFromForm(emptyFormValues()).matter_id).toBeNull();
  });

  describe("a duration nobody stated", () => {
    it("reads Not stated, and a stated one reads in minutes", () => {
      expect(durationLabel(hearing({ duration_minutes: 60, duration_stated: false }))).toBe("Not stated");
      expect(durationLabel(hearing({ duration_minutes: 90, duration_stated: true }))).toBe("90 minutes");

      expect(durationLabel(hearing({ duration_minutes: 60 }))).toBe("60 minutes");
    });

    it("opens the edit form with the box blank, so the 60 is not mistaken for a choice", () => {
      expect(formFromHearing(hearing({ duration_minutes: 60, duration_stated: false })).duration_minutes).toBe("");
      expect(formFromHearing(hearing({ duration_minutes: 90 })).duration_minutes).toBe("90");
    });

    it("sends no edit when it is left blank, and a number when one is typed", () => {
      const h = hearing({ duration_minutes: 60, duration_stated: false });
      expect(editsFromForm(h, formFromHearing(h))).toEqual({});
      expect(editsFromForm(h, { ...formFromHearing(h), duration_minutes: "45" })).toEqual({ duration_minutes: 45 });
    });

    it("clearing a stated length sends null, which puts it back to not stated", () => {
      const h = hearing({ duration_minutes: 90 });
      expect(editsFromForm(h, { ...formFromHearing(h), duration_minutes: "" })).toEqual({ duration_minutes: null });
    });

    it("does not change how long the calendar block is", () => {
      const unstated = hearing({ hearing_date: "2026-09-25", hearing_time: "10:00", duration_minutes: 60, duration_stated: false });
      const stated = hearing({ hearing_date: "2026-09-25", hearing_time: "10:00", duration_minutes: 60 });
      expect(endFloating(unstated)).toBe(endFloating(stated));
    });
  });

  it("describes edits for a confirm dialog", () => {
    expect(describeEdits({ hearing_time: null, is_final: true, court: "Leeds" })).toEqual([
      "Time: (blank)",
      "Final hearing: Yes",
      "Court: Leeds",
    ]);
  });
});

describe("filterHearings", () => {
  const rows = [
    { client_name: "Amina Kingfishertest", case_ref: "ZC25P44444", court: "Central Family Court" },
    { client_name: null, case_ref: "BV26C77777", court: "Barnet County Court" },
  ];
  it("keeps everything when the box is empty", async () => {
    const { filterHearings } = await import("./hearings");
    expect(filterHearings(rows, "  ")).toHaveLength(2);
  });
  it("matches client, case number and court, any case, every word", async () => {
    const { filterHearings } = await import("./hearings");
    expect(filterHearings(rows, "kingfishertest")).toEqual([rows[0]]);
    expect(filterHearings(rows, "bv26")).toEqual([rows[1]]);
    expect(filterHearings(rows, "county barnet")).toEqual([rows[1]]);
    expect(filterHearings(rows, "kingfishertest barnet")).toEqual([]);
  });
});

describe("isPastHearing", () => {
  it("is past only when the date is before today", async () => {
    const { isPastHearing } = await import("./hearings");
    expect(isPastHearing({ hearing_date: "2026-10-08" }, "2026-10-09")).toBe(true);
    expect(isPastHearing({ hearing_date: "2026-10-09" }, "2026-10-09")).toBe(false);
    expect(isPastHearing({ hearing_date: "2026-10-10" }, "2026-10-09")).toBe(false);
  });
});

describe("filterLeads", () => {
  const leads = [
    { source_subject: "Notice of hearing SK26F33333", reason: "no date" },
    { source_subject: "Re: directions", reason: "ambiguous time" },
  ];
  it("keeps all for an empty box and matches every word in subject or reason", async () => {
    const { filterLeads } = await import("./hearings");
    expect(filterLeads(leads, " ")).toHaveLength(2);
    expect(filterLeads(leads, "sk26f33333")).toEqual([leads[0]]);
    expect(filterLeads(leads, "directions ambiguous")).toEqual([leads[1]]);
    expect(filterLeads(leads, "directions notice")).toEqual([]);
  });
});

describe("counsel booked and confidence display", () => {
  it("turns a scheduled hearing with counsel purple and calls it counsel booked", () => {
    const h = hearing({ counsel: "A. Barrister", counsel_booked: true, review_state: "ok" });
    expect(isCounselBooked(h)).toBe(true);
    expect(toCalendarEvent(h).classNames).toContain("hearing-ev--counsel");
  });

  it("falls back to the counsel text when the server does not send counsel_booked", () => {
    expect(isCounselBooked(hearing({ counsel: "A. Barrister" }))).toBe(true);
    expect(isCounselBooked(hearing({ counsel: "  " }))).toBe(false);
  });

  it("keeps review amber over purple and never purples a vacated hearing", () => {
    expect(toCalendarEvent(hearing({ counsel: "X", review_state: "needs_review" })).classNames).not.toContain("hearing-ev--counsel");
    expect(toCalendarEvent(hearing({ counsel: "X", status: "vacated" })).classNames).not.toContain("hearing-ev--counsel");
  });

  it("shows confidence only on a read nobody has confirmed", () => {
    expect(visibleConfidence(hearing({ confidence: 0.5, review_state: "ok", human_edited: true }))).toBeNull();
    expect(visibleConfidence(hearing({ confidence: 0.95, review_state: "needs_review" }))).toBe(0.95);
    expect(visibleConfidence(hearing({ confidence: null, review_state: "needs_review" }))).toBeNull();
  });
});

describe("hearing markers for the hearings panel", () => {
  const h = { counsel: "", counsel_booked: false, status: "scheduled" as const, matter_id: 1, bundle_done: false, bundle_why: "no bundle step logged" };
  it("says counsel not booked and bundle not done, with the evidence", () => {
    expect(hearingMarkers(h).map((m) => m.label)).toEqual(["Counsel not booked", "Bundle not done"]);
    expect(hearingMarkers(h)[1].why).toBe("no bundle step logged");
  });
  it("says nothing once both are done, or when the hub did not work it out, or for a vacated or unlinked hearing", () => {
    expect(hearingMarkers({ ...h, counsel_booked: true, bundle_done: true })).toEqual([]);
    expect(hearingMarkers({ ...h, bundle_done: null })).toEqual([]);
    expect(hearingMarkers({ ...h, status: "vacated" })).toEqual([]);
    expect(hearingMarkers({ ...h, matter_id: null })).toEqual([]);
    expect(hearingMarkers({ ...h, counsel_booked: true }).map((m) => m.key)).toEqual(["no-bundle"]);
  });
});

describe("confirmedByWords (gh#1638)", () => {
  const base = { review_state: "ok", human_edited: true } as const;

  it("names the person who confirmed it", () => {
    expect(confirmedByWords({ ...base, confirmed_by: "Sam" })).toBe(", confirmed by Sam");
  });

  it("never names a system actor: only confirmed_by is read, not who wrote last", () => {
    const row = { ...base, updated_by: "system:calendar-finder" } as Parameters<typeof confirmedByWords>[0];
    expect(confirmedByWords(row)).toBe(", confirmed by a team member");
    expect(confirmedByWords({ ...base, confirmed_by: "   " })).toBe(", confirmed by a team member");
    expect(confirmedByWords(row)).not.toContain("system");
  });

  it("says nothing when no person has confirmed it", () => {
    expect(confirmedByWords({ review_state: "ok", human_edited: false, confirmed_by: "Sam" })).toBe("");
    expect(confirmedByWords({ review_state: "needs_review", human_edited: true, confirmed_by: "Sam" })).toBe("");
  });
});
