import { describe, expect, it } from "vitest";
import { cleanExtract, hearingDefaults } from "./hearingExtract";

const found = { date: "2026-09-25", time: "13:30", matchedText: "on Friday", court: "Medway County Court" };
const client = { matterId: "596", caseRef: "ZZ21D00000", name: "Stub Testperson", role: "Applicant" };

describe("cleanExtract", () => {
  it("turns anything unexpected into empty rather than throwing", () => {
    for (const junk of [null, undefined, "text", 5, [], { court: 5, time: "25:99", mode: "spaceship", without_notice: "yes" }]) {
      expect(cleanExtract(junk)).toEqual({
        court: "", hearing_type: "", counsel: "", chambers: "", mode: "", time: null, without_notice: false, notes: "",
      });
    }
  });

  it("keeps good values and trims them", () => {
    expect(cleanExtract({ court: " Medway County Court ", counsel: "Sarah Kingfishertest", chambers: "1 Sample Court", mode: "telephone", time: "09:30", without_notice: true })).toMatchObject({
      court: "Medway County Court", counsel: "Sarah Kingfishertest", chambers: "1 Sample Court", mode: "telephone", time: "09:30", without_notice: true,
    });
  });
});

describe("hearingDefaults", () => {
  it("uses the date and time read from the text, the client in the right role, and the extracted extras", () => {
    const d = hearingDefaults(found, cleanExtract({ counsel: "Sarah Kingfishertest", chambers: "1 Sample Court", without_notice: true }), client);
    expect(d).toMatchObject({
      hearing_date: "2026-09-25", hearing_time: "13:30", court: "Medway County Court",
      counsel: "Sarah Kingfishertest", chambers: "1 Sample Court", hearing_type: "", notice: "without notice",
      applicant: "Stub Testperson", respondent: "", matter_id: "596", case_ref: "ZZ21D00000",
    });
  });

  it("keeps the named hearing type as it is, puts without notice in its own setting, and prefers the extracted court over the pattern", () => {
    const d = hearingDefaults(found, cleanExtract({ court: "Chatham Family Court", hearing_type: "Return date", without_notice: true }), client);
    expect(d.hearing_type).toBe("Return date");
    expect(d.notice).toBe("without notice");
    expect(d.court).toBe("Chatham Family Court");
  });

  it("works with no extraction at all", () => {
    expect(hearingDefaults(found, null, { ...client, role: "Respondent" })).toMatchObject({
      court: "Medway County Court", counsel: "", respondent: "Stub Testperson", applicant: "",
    });
  });

  it("takes the extracted time only when the text gave none", () => {
    expect(hearingDefaults({ ...found, time: null }, cleanExtract({ time: "10:15" }), client).hearing_time).toBe("10:15");
    expect(hearingDefaults(found, cleanExtract({ time: "10:15" }), client).hearing_time).toBe("13:30");
  });
});
