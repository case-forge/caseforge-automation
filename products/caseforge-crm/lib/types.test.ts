import { describe, expect, it } from "vitest";
import type { ClientMatch } from "./types";
import {
  addressBlocks,
  applyFieldUpdate,
  ageOn,
  childrenOf,
  concludedStatus,
  dateJoinedOf,
  formatDateForDisplay,
  hasC8,
  isConcludedFolder,
  isDeleteLaterFolder,
  matchedViaOf,
  nextHearingOf,
  notesOf,
  orderTypeTagsOf,
  partyDobBlocks,
  referenceGroupsOf,
  courtDetailsOf,
  withLiveAges,
} from "./types";

function match(overrides: Partial<ClientMatch> = {}): ClientMatch {
  return { extra: {}, ...overrides };
}

describe("hasC8", () => {
  it("reads the untyped extra.has_c8 flag", () => {
    expect(hasC8(match({ extra: { has_c8: true } }))).toBe(true);
    expect(hasC8(match({ extra: { has_c8: 1 } }))).toBe(true);
  });

  it("is false when absent, false, or falsy-but-present", () => {
    expect(hasC8(match())).toBe(false);
    expect(hasC8(match({ extra: { has_c8: false } }))).toBe(false);
    expect(hasC8(match({ extra: { has_c8: 0 } }))).toBe(false);
  });
});

describe("isDeleteLaterFolder", () => {
  it("is true for a folder inside a Delete Later holding folder", () => {
    expect(
      isDeleteLaterFolder(match({ live_matter_folder: "Company_Data/.../1 Concluded Matters/001-Delete Later/Example Client" })),
    ).toBe(true);
  });

  it("is false for a plain concluded folder or when absent", () => {
    expect(isDeleteLaterFolder(match({ live_matter_folder: "Company_Data/.../1 Concluded Matters/2024-Concluded/Example Client" }))).toBe(false);
    expect(isDeleteLaterFolder(match())).toBe(false);
  });
});

describe("isConcludedFolder", () => {
  it("matches a live_matter_folder under either year's Concluded subfolder, case-insensitively", () => {
    expect(
      isConcludedFolder(match({ live_matter_folder: "Company_Data/.../Clients - Protective Orders/2026-Concluded/Lucia Hornbeamtest" })),
    ).toBe(true);
    expect(
      isConcludedFolder(match({ live_matter_folder: "Company_Data/.../Clients - Protective Orders/2025-concluded/Someone" })),
    ).toBe(true);
  });

  it("is false for an active folder or when absent", () => {
    expect(isConcludedFolder(match({ live_matter_folder: "Company_Data/.../Clients - Protective Orders/Jane Hickorytest" }))).toBe(false);
    expect(isConcludedFolder(match())).toBe(false);
  });
});

describe("concludedStatus", () => {
  it("prefers a real closed_at date over the folder inference, formatted without the time", () => {
    expect(
      concludedStatus(
        match({ closed_at: "2026-05-01T00:00:00Z", live_matter_folder: ".../2026-Concluded/X" }),
      ),
    ).toEqual({ label: "1 May 2026", source: "closed_at" });
  });

  it("falls back to a dateless folder inference when closed_at is unset", () => {
    expect(concludedStatus(match({ live_matter_folder: ".../2026-Concluded/X" }))).toEqual({
      label: "Concluded",
      source: "folder",
    });
  });

  it("is null for a matter unticked (reopened) while its folder still sits under Concluded", () => {
    expect(
      concludedStatus(match({ live_matter_folder: ".../2026-Concluded/X", extra: { closed_notes: "Reopened by Sam" } })),
    ).toBeNull();
  });

  it("still shows the closed date when closed_at is set, whatever an old note says", () => {
    expect(
      concludedStatus(match({ closed_at: "2026-05-01T00:00:00Z", extra: { closed_notes: "Reopened by Sam" } })),
    ).toEqual({ label: "1 May 2026", source: "closed_at" });
  });

  it("ticked then unticked leaves no badge, and ticked again brings it back", () => {
    const folder = ".../2026-Concluded/X";
    const ticked = applyFieldUpdate(match({ live_matter_folder: folder }), "concluded", "1");
    expect(concludedStatus(ticked)?.source).toBe("closed_at");
    const unticked = applyFieldUpdate(ticked, "concluded", "0");
    expect(concludedStatus(unticked)).toBeNull();
    expect(concludedStatus(applyFieldUpdate(unticked, "concluded", "1"))?.source).toBe("closed_at");
  });

  it("is null for an active matter with no closed_at and no Concluded folder", () => {
    expect(concludedStatus(match({ live_matter_folder: ".../Jane Hickorytest" }))).toBeNull();
    expect(concludedStatus(match())).toBeNull();
  });
});

describe("formatDateForDisplay", () => {
  it("drops the time component and uses a British day-month-year format", () => {
    expect(formatDateForDisplay("2025-11-18T16:59:00Z")).toBe("18 Nov 2025");
  });

  it("falls back to the raw string when it can't be parsed as a date", () => {
    expect(formatDateForDisplay("not-a-date")).toBe("not-a-date");
  });
});

describe("orderTypeTagsOf", () => {
  it("reads the comma-separated extra.order_type_tags field", () => {
    expect(orderTypeTagsOf(match({ extra: { order_type_tags: "NMO,OO" } }))).toEqual(["NMO", "OO"]);
  });

  it("always returns tags in fixed ORDER_TYPE_LABELS order regardless of storage order", () => {
    expect(orderTypeTagsOf(match({ extra: { order_type_tags: "PSO,NMO,CAO" } }))).toEqual(["NMO", "CAO", "PSO"]);

    expect(orderTypeTagsOf(match({ extra: { order_type_tags: "SIO,PSO,CAO" } }))).toEqual(["CAO", "PSO", "SIO"]);
  });

  it("drops any code outside the five-value vocabulary", () => {
    expect(orderTypeTagsOf(match({ extra: { order_type_tags: "NMO,BOGUS" } }))).toEqual(["NMO"]);
  });

  it("is empty when absent or blank -- 'not yet classified', not an error", () => {
    expect(orderTypeTagsOf(match())).toEqual([]);
    expect(orderTypeTagsOf(match({ extra: { order_type_tags: "" } }))).toEqual([]);
  });
});

describe("notesOf", () => {
  it("reads extra.tracker_notes when populated", () => {
    expect(notesOf(match({ extra: { tracker_notes: "Client transferred to another firm" } }))).toBe(
      "Client transferred to another firm",
    );
  });

  it("is null when absent or blank", () => {
    expect(notesOf(match())).toBeNull();
    expect(notesOf(match({ extra: { tracker_notes: "   " } }))).toBeNull();
  });
});

describe("nextHearingOf", () => {
  it("reads extra.next_hearing_text when populated", () => {
    expect(
      nextHearingOf(match({ extra: { next_hearing_text: "2026-10-05 | Harrogate Family Court" } })),
    ).toBe("2026-10-05 | Harrogate Family Court");
  });

  it("is null when absent or blank -- never fabricated", () => {
    expect(nextHearingOf(match())).toBeNull();
    expect(nextHearingOf(match({ extra: { next_hearing_text: "   " } }))).toBeNull();
  });
});

describe("childrenOf", () => {
  it("reads extra.children_summary when populated", () => {
    expect(childrenOf(match({ extra: { children_summary: "1 child (age 6)" } }))).toBe(
      "1 child (age 6)",
    );
  });

  it("returns null when absent or blank", () => {
    expect(childrenOf(match())).toBeNull();
    expect(childrenOf(match({ extra: { children_summary: "   " } }))).toBeNull();
  });

  it("shows the current age from the date of birth, replacing a stored one", () => {
    const today = new Date(2026, 8, 27);
    expect(childrenOf(match({ extra: { children_summary: "Milo Willowtest (2016-11-19, age 7)" } }), today)).toBe(
      "Milo Willowtest (2016-11-19, age 9)",
    );
    expect(childrenOf(match({ extra: { children_summary: "Ivy Charlietest (2020-03-04); Sam Charlietest (2018-12-25)" } }), today)).toBe(
      "Ivy Charlietest (2020-03-04, age 6); Sam Charlietest (2018-12-25, age 7)",
    );
  });
});

describe("ageOn", () => {
  const today = new Date(2026, 8, 27);

  it("turns over on the birthday, not before", () => {
    expect(ageOn("2016-09-27", today)).toBe(10);
    expect(ageOn("2016-09-28", today)).toBe(9);
  });

  it("is null for an unparseable, impossible or future date", () => {
    expect(ageOn("", today)).toBeNull();
    expect(ageOn("19.12.1994", today)).toBeNull();
    expect(ageOn("2026-02-30", today)).toBeNull();
    expect(ageOn("2030-01-01", today)).toBeNull();
  });
});

describe("withLiveAges", () => {
  it("drops a stale age on a future date of birth and leaves other text alone", () => {
    const today = new Date(2026, 8, 27);
    expect(withLiveAges("Baby (2030-01-01, age 4)", today)).toBe("Baby (2030-01-01)");
    expect(withLiveAges("Two children, names to follow", today)).toBe("Two children, names to follow");
  });
});

describe("addressBlocks", () => {
  it("splits a single party address into heading + comma-separated lines", () => {
    expect(
      addressBlocks(match({ address_summary: "Applicant: 1 Example Street, Testville, TE1 1ST" })),
    ).toEqual([{ heading: "Applicant", lines: ["1 Example Street", "Testville", "TE1 1ST"] }]);
  });

  it("splits multiple parties (' | '-joined) into separate blocks", () => {
    const blocks = addressBlocks(
      match({
        address_summary: "Applicant: 1 A Street, AA1 1AA | Respondent: 2 B Street, ZZ2 2BB",
      }),
    );
    expect(blocks).toEqual([
      { heading: "Applicant", lines: ["1 A Street", "AA1 1AA"] },
      { heading: "Respondent", lines: ["2 B Street", "ZZ2 2BB"] },
    ]);
  });

  it("returns an empty array when there is nothing to show, never a placeholder block", () => {
    expect(addressBlocks(match())).toEqual([]);
    expect(addressBlocks(match({ address_summary: null }))).toEqual([]);
  });

  it("title-cases the role heading -- mp.role is stored inconsistently, and a bare lowercase 'respondent' reads as an unexplained internal value", () => {
    expect(
      addressBlocks(match({ address_summary: "respondent: 1 Example Street, Testville, TE1 1ST" })),
    ).toEqual([{ heading: "Respondent", lines: ["1 Example Street", "Testville", "TE1 1ST"] }]);
  });

  it("keeps an address_owner annotation in the heading (clientdb_sql.search_clients appends '(owner)' before the colon)", () => {
    expect(
      addressBlocks(match({ address_summary: "Respondent (Mother): 9 Third Road, Testville, TE1 1AC" })),
    ).toEqual([{ heading: "Respondent (Mother)", lines: ["9 Third Road", "Testville", "TE1 1AC"] }]);
  });

  it("drops a trailing standalone 'UK' line -- every address here is genuinely in the UK", () => {
    expect(
      addressBlocks(match({ address_summary: "Respondent: 10 Example Square, Sampleton, UK" })),
    ).toEqual([{ heading: "Respondent", lines: ["10 Example Square", "Sampleton"] }]);
  });

  it("never strips 'UK' as a mere substring of a real address component", () => {
    expect(
      addressBlocks(match({ address_summary: "Applicant: 1 Cuke Avenue, Testville, UK1 1AA" })),
    ).toEqual([{ heading: "Applicant", lines: ["1 Cuke Avenue", "Testville", "UK1 1AA"] }]);
  });
});

describe("matchedViaOf", () => {
  it("surfaces a party match distinct from the client's own name", () => {
    expect(
      matchedViaOf(
        match({ client_name: "Craig Figtest", matched_party_summary: "Respondent: Natalie Dappletest" }),
      ),
    ).toBe("Respondent: Natalie Dappletest");
  });

  it("is null when the match is the client themselves, or there is none", () => {
    expect(
      matchedViaOf(match({ client_name: "Craig Figtest", matched_party_summary: "Craig Figtest" })),
    ).toBeNull();
    expect(matchedViaOf(match())).toBeNull();
  });
});

describe("referenceGroupsOf", () => {
  it("splits court and company references into separate buckets rather than one run-on string", () => {
    expect(
      referenceGroupsOf(match({ reference_summary: "court_family:CW26F44444 | company_ref:260223/01FL" })),
    ).toEqual({ court: ["CW26F44444"], company: ["260223/01FL"], legalAid: [], other: [] });
  });

  it("groups every known court ref_type together", () => {
    expect(
      referenceGroupsOf(
        match({ reference_summary: "court_family:AA1 | court_children:BB2 | court_ref:CC3" }),
      ),
    ).toEqual({ court: ["AA1", "BB2", "CC3"], company: [], legalAid: [], other: [] });
  });

  it("routes legal aid ref_types (ccms_ref, laa_case_ref) to their own bucket", () => {
    expect(
      referenceGroupsOf(match({ reference_summary: "ccms_ref:X1 | laa_case_ref:Y2" })),
    ).toEqual({ court: [], company: [], legalAid: ["X1", "Y2"], other: [] });
  });

  it("puts an unrecognised ref_type in 'other' rather than dropping it", () => {
    expect(referenceGroupsOf(match({ reference_summary: "some_new_type:Z9" }))).toEqual({
      court: [],
      company: [],
      legalAid: [],
      other: ["Z9"],
    });
  });

  it("falls back to case_reference when reference_summary is absent", () => {
    expect(referenceGroupsOf(match({ case_reference: "260223/01FL" }))).toEqual({
      court: [],
      company: [],
      legalAid: [],
      other: ["260223/01FL"],
    });
  });

  it("is all-empty when neither field is present", () => {
    expect(referenceGroupsOf(match())).toEqual({ court: [], company: [], legalAid: [], other: [] });
  });

  it("falls back to extra.company_reference when matter_references has no mirrored row at all", () => {

    expect(
      referenceGroupsOf(match({ extra: { company_reference: "260814/01FL" } })),
    ).toEqual({ court: [], company: ["260814/01FL"], legalAid: [], other: [] });
  });

  it("shows the matters.company_reference column over a matter_references row, which can lag an edit", () => {
    expect(
      referenceGroupsOf(
        match({
          reference_summary: "company_ref:260223/01FL",
          extra: { company_reference: "should-not-appear" },
        }),
      ),
    ).toEqual({ court: [], company: ["should-not-appear"], legalAid: [], other: [] });
  });

  it("uses the matter_references row when the column is empty", () => {
    expect(referenceGroupsOf(match({ reference_summary: "company_ref:260223/01FL" })).company).toEqual(["260223/01FL"]);
  });
});

describe("applyFieldUpdate", () => {
  it("patches a direct ClientMatch field", () => {
    const updated = applyFieldUpdate(match({ phone_primary: "old" }), "phone_primary", "new");
    expect(updated.phone_primary).toBe("new");
  });

  it("patches an extraKey field without disturbing other extra values", () => {
    const updated = applyFieldUpdate(
      match({ extra: { nino_canonical: "old", has_c8: false } }),
      "nino_canonical",
      "QQ123456C",
    );
    expect(updated.extra?.nino_canonical).toBe("QQ123456C");
    expect(updated.extra?.has_c8).toBe(false);
  });

  it("never mutates the original match", () => {
    const original = match({ phone_primary: "old" });
    applyFieldUpdate(original, "phone_primary", "new");
    expect(original.phone_primary).toBe("old");
  });

  it("sets has_c8 as a real boolean in extra, not the string wire value", () => {
    const updated = applyFieldUpdate(match(), "has_c8", "1");
    expect(updated.extra?.has_c8).toBe(true);
  });

  it("approximates concluded with a real timestamp on '1' and clears it on '0'", () => {
    const closed = applyFieldUpdate(match(), "concluded", "1");
    expect(typeof closed.closed_at).toBe("string");
    const reopened = applyFieldUpdate(match({ closed_at: "2026-01-01T00:00:00Z" }), "concluded", "0");
    expect(reopened.closed_at).toBeNull();
  });

  it("is a no-op for an unrecognised field name", () => {
    const original = match({ phone_primary: "old" });
    expect(applyFieldUpdate(original, "not_a_real_field", "x")).toEqual(original);
  });
});

describe("dateJoinedOf", () => {
  it("prefers extra.referral_sent_at, formatted", () => {
    expect(dateJoinedOf(match({ extra: { referral_sent_at: "2026-08-14" } }))).toBe("14 Aug 2026");
  });

  it("falls back to extra.source_email_sent_at when referral_sent_at is absent", () => {
    expect(dateJoinedOf(match({ extra: { source_email_sent_at: "2026-07-01" } }))).toBe("1 Jul 2026");
  });

  it("prefers referral_sent_at over source_email_sent_at when both are present", () => {
    expect(
      dateJoinedOf(
        match({ extra: { referral_sent_at: "2026-08-14", source_email_sent_at: "2026-07-01" } }),
      ),
    ).toBe("14 Aug 2026");
  });

  it("is null when neither is present", () => {
    expect(dateJoinedOf(match())).toBeNull();
  });
});

describe("partyDobBlocks", () => {
  it("parses extra.party_dob_summary the same way partyBlocks parses party_summary", () => {
    expect(
      partyDobBlocks(match({ extra: { party_dob_summary: "Respondent: 1990-04-15" } })),
    ).toEqual([{ role: "Respondent", name: "1990-04-15" }]);
  });

  it("is an empty array when the field is absent, same as no address on record", () => {
    expect(partyDobBlocks(match())).toEqual([]);
    expect(partyDobBlocks(match({ extra: {} }))).toEqual([]);
  });
});

import { c8Of as _c8Of, reconcileParty as _reconcileParty, splitAddress as _splitAddress, splitName as _splitName, applyFieldUpdate as _applyFieldUpdate } from "./types";
import type { ClientMatch as _ClientMatch } from "./types";

describe("row editor helpers", () => {
  it("splits a flat name into first / middle / last", () => {
    expect(_splitName("Stella May Godwittest")).toEqual({ name_first: "Stella", name_middle: "May", name_last: "Godwittest" });
    expect(_splitName("Stella Godwittest")).toEqual({ name_first: "Stella", name_middle: "", name_last: "Godwittest" });
    expect(_splitName("Cher")).toEqual({ name_first: "Cher", name_middle: "", name_last: "" });
  });

  it("splits a flat address into four lines and a postcode", () => {
    expect(_splitAddress("2 Example Close, Sampleford, Testtown, ZZ3 7AA")).toEqual({
      address_line1: "2 Example Close", address_line2: "Sampleford", address_line3: "Testtown", address_line4: "", address_postcode: "ZZ3 7AA",
    });
    expect(_splitAddress("1 Rd, A, B, C, D, E").address_line4).toBe("C, D, E");
    expect(_splitAddress("1 Rd, Town, UK").address_postcode).toBe("");
  });

  it("re-derives parts from a flat value that disagrees with them (a newer edit)", () => {
    const row = {
      display_name: "Stella Godwittest", name_first: "Stella", name_middle: "", name_last: "Godwittest",
      address_text: "2 Example Close, Sampleford, Testtown",
      address_line1: "2 Example Close", address_line2: "Sampleford", address_line3: "Testtown", address_line4: "Testtown", address_postcode: "UK",
    };
    const out = _reconcileParty(row);
    expect(out.address_line4).toBe("");
    expect(out.address_postcode).toBe("");
    expect(out.name_last).toBe("Godwittest");
  });

  it("leaves a row alone when the flat text matches its parts, and an AKA name's parts", () => {
    const row = { display_name: "DAVID JOHN TALENT AKA DAVID JOHN BURN", name_first: "DAVID", name_middle: "JOHN", name_last: "TALENT", address_text: "" };
    expect(_reconcileParty(row)).toEqual(row);
  });
});

describe("per-field C8", () => {
  const base = (extra: Record<string, unknown>) => ({ matter_id: 1, client_name: "A", extra }) as unknown as _ClientMatch;

  it("reads each flag, falling back to the whole-matter flag only where the column is absent", () => {
    expect(_c8Of(base({ has_c8: 1, c8_phone: 1, c8_email: 0, c8_address: 0 }), "c8_email")).toBe(false);
    expect(_c8Of(base({ has_c8: 1, c8_phone: 1, c8_email: 0, c8_address: 0 }), "c8_phone")).toBe(true);
    expect(_c8Of(base({ has_c8: 1 }), "c8_address")).toBe(true);
    expect(_c8Of(base({ has_c8: 0 }), "c8_address")).toBe(false);
  });

  it("keeps has_c8 equal to any of the three after a toggle", () => {
    const m = base({ has_c8: 1, c8_phone: 1, c8_email: 0, c8_address: 0 });
    const off = _applyFieldUpdate(m, "c8_phone", "0");
    expect(off.extra?.has_c8).toBe(false);
    const on = _applyFieldUpdate(off, "c8_email", "1");
    expect(on.extra?.has_c8).toBe(true);
    expect(on.extra?.c8_phone).toBe(false);
  });
});

describe("court and court_email references", () => {
  const summary = "court_family:CW26F44444 | court:Example Family Court | court_email:court@example.test | other_thing:X1";

  it("keeps court and court_email out of the other references", () => {
    const groups = referenceGroupsOf(match({ reference_summary: summary }));
    expect(groups.other).toEqual(["X1"]);
    expect(groups.court).toEqual(["CW26F44444"]);
  });

  it("leaves other ref_types unchanged", () => {
    expect(referenceGroupsOf(match({ reference_summary: "foo:A | bar:B" })).other).toEqual(["A", "B"]);
  });

  it("returns the court name and email", () => {
    expect(courtDetailsOf(match({ reference_summary: summary }))).toEqual({
      name: "Example Family Court",
      email: "court@example.test",
    });
  });

  it("returns nulls when empty or absent", () => {
    expect(courtDetailsOf(match({ reference_summary: null }))).toEqual({ name: null, email: null });
    expect(courtDetailsOf(match({ reference_summary: "court:  | court_email:" }))).toEqual({ name: null, email: null });
    expect(courtDetailsOf(match({ reference_summary: "court_family:AA1" }))).toEqual({ name: null, email: null });
  });
});

import { addressLinesOfText } from "./types";
describe("addressLinesOfText", () => {
  it("shows a flat address one part per line, from commas or line breaks, and nothing for blank", () => {
    expect(addressLinesOfText("1 High Street, Leeds,  TE1 1ST")).toEqual(["1 High Street", "Leeds", "TE1 1ST"]);
    expect(addressLinesOfText("Flat 2\n3 Mill Road\nHull")).toEqual(["Flat 2", "3 Mill Road", "Hull"]);
    expect(addressLinesOfText("")).toEqual([]);
    expect(addressLinesOfText(null)).toEqual([]);
  });
});
