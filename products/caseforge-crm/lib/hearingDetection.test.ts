import { describe, expect, it } from "vitest";
import { detectCourt, detectHearing, listedHearingsFor } from "./hearingDetection";

const NOW = new Date("2026-09-24T14:00:00+01:00");
const TODAY = "2026-09-24";

describe("detectHearing", () => {
  it("reads the owner's real sentence: a weekday and a separate time, plus the court", () => {
    const found = detectHearing(
      "Called Medway County Court to list hearing for 1:30pm without notice on Friday. Court number 01632 960726.",
      TODAY,
      NOW,
    );
    expect(found).toMatchObject({ date: "2026-09-25", time: "13:30", court: "Medway County Court" });
  });

  it("reads a dotted date and a written-out date", () => {
    expect(detectHearing("FHDRA 30.09.2026 Reading Magistrates' Court", TODAY, NOW)?.date).toBe("2026-09-30");
    expect(detectHearing("hearing listed 3 November at 10:30", TODAY, NOW)).toMatchObject({ date: "2026-11-03", time: "10:30" });
  });

  it("does not offer for a bare time, a vague span, a phone number or a case number", () => {
    expect(detectHearing("spoke to client at 2pm about the order", TODAY, NOW)).toBeNull();
    expect(detectHearing("she will ring back next week", TODAY, NOW)).toBeNull();
    expect(detectHearing("Court number 01632 960726", TODAY, NOW)).toBeNull();
    expect(detectHearing("case RG26P77777", TODAY, NOW)).toBeNull();
    expect(detectHearing("", TODAY, NOW)).toBeNull();
  });

  it("does not offer a date that has already passed", () => {
    expect(detectHearing("the last hearing was on 3 September", TODAY, NOW)).toBeNull();
  });

  it("reads UK shorthand: a dotted two-digit-year date and a dotted time", () => {
    expect(detectHearing("adjourned to 4.11.26 at 11.30am", TODAY, NOW)).toMatchObject({ date: "2026-11-04", time: "11:30" });
  });

  it("does not mistake a version-like or money figure for a date", () => {
    expect(detectHearing("costs came to 12.50 plus 3.75 for copies", TODAY, NOW)).toBeNull();
  });

  it("gives a date with no time a null time rather than a guess", () => {
    expect(detectHearing("hearing on 1st Oct", TODAY, NOW)).toMatchObject({ date: "2026-10-01", time: null });
  });
});

describe("detectCourt", () => {
  it("drops a leading verb from the sentence", () => {
    expect(detectCourt("Called Medway County Court to list")).toBe("Medway County Court");
    expect(detectCourt("Spoke to Reading Magistrates' Court")).toBe("Reading Magistrates' Court");
  });

  it("finds nothing when no court is named", () => {
    expect(detectCourt("rang the client about the hearing")).toBe("");
  });
});

describe("the word now is not a hearing", () => {
  it("does not offer a hearing for the owner's real note, which gave no date", () => {
    const note = "counsel called again. couldnt get through to her and now in court. calling her,";
    expect(detectHearing(note, TODAY, NOW)).toBeNull();
    expect(detectHearing("now in court", TODAY, NOW)).toBeNull();
    expect(detectHearing("right now she is at the county court", TODAY, NOW)).toBeNull();
  });

  it("does not let now lend its clock time to a real date written later", () => {
    const found = detectHearing("counsel is in court now, hearing listed 3 November", TODAY, NOW);
    expect(found).toMatchObject({ date: "2026-11-03", time: null });
  });

  it("still reads a real date and time in the same note", () => {
    expect(detectHearing("out of court now. hearing 25 September at 2pm", TODAY, NOW)).toMatchObject({ date: "2026-09-25", time: "14:00" });
  });
});

describe("listedHearingsFor", () => {
  const h = (id: number, date: string, time: string | null, status = "scheduled") => ({ hearing_id: id, hearing_date: date, hearing_time: time, status });
  const list = [h(1, "2026-09-25", "14:00:00"), h(2, "2026-09-25", "10:30"), h(3, "2026-09-26", "14:00"), h(4, "2026-09-25", "16:00", "vacated")];

  it("matches on date and time when the note gives a time, whatever the stored seconds", () => {
    expect(listedHearingsFor(list, { date: "2026-09-25", time: "14:00" }).map((x) => x.hearing_id)).toEqual([1]);
    expect(listedHearingsFor(list, { date: "2026-09-25", time: "10:30" }).map((x) => x.hearing_id)).toEqual([2]);
  });

  it("does not match a different time on the same date, or the same time on another date", () => {
    expect(listedHearingsFor(list, { date: "2026-09-25", time: "15:00" })).toEqual([]);
    expect(listedHearingsFor(list, { date: "2026-09-27", time: "14:00" })).toEqual([]);
  });

  it("matches every scheduled hearing on the date when the note gives only a date", () => {
    expect(listedHearingsFor(list, { date: "2026-09-25", time: null }).map((x) => x.hearing_id)).toEqual([1, 2]);
  });

  it("ignores a vacated or cancelled hearing, so a fresh one can be added over it", () => {
    expect(listedHearingsFor(list, { date: "2026-09-25", time: "16:00" })).toEqual([]);
  });

  it("matches nothing against an empty list", () => {
    expect(listedHearingsFor([], { date: "2026-09-25", time: "14:00" })).toEqual([]);
  });
});
