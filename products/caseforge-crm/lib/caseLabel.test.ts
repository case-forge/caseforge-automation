import { describe, expect, it } from "vitest";
import { caseDescriptor, caseLabelsFor, openedDateText, orderTypeText, personKeyOf } from "./caseLabel";
import { stubSearch } from "./stub";
import type { ClientMatch } from "./types";

function row(over: Partial<ClientMatch> & { matter_id: string }): ClientMatch {
  return { client_name: "Synthetic Person", extra: {}, ...over };
}

describe("caseLabelsFor", () => {
  it("labels nothing when every person has one matter in the list", () => {
    const labels = caseLabelsFor([
      row({ matter_id: "1", client_name: "Alpha Cedartest", extra: { primary_person_id: "10" } }),
      row({ matter_id: "2", client_name: "Beta Birchtest", extra: { primary_person_id: "11" } }),
    ]);
    expect(labels.size).toBe(0);
  });

  it("numbers one person's cases oldest first, with order type and opening date", () => {
    const labels = caseLabelsFor([
      row({
        matter_id: "20",
        order_requested_text: "CHILD ARRANGEMENTS ORDER",
        extra: { primary_person_id: "7", created_utc: "2026-07-21T09:00:00" },
      }),
      row({ matter_id: "30", client_name: "Someone Else", extra: { primary_person_id: "8" } }),
      row({
        matter_id: "12",
        order_requested_text: "NON-MOLESTATION ORDER",
        extra: { primary_person_id: "7", created_utc: "2025-03-04T10:15:00" },
      }),
    ]);
    expect(labels.get("12")).toBe("Case 1 of 2 · Non-molestation order · Opened 4 Mar 2025");
    expect(labels.get("20")).toBe("Case 2 of 2 · Child arrangements order · Opened 21 Jul 2026");
    expect(labels.has("30")).toBe(false);
  });

  it("never groups two different namesakes the hub numbered (i) and (ii)", () => {
    const labels = caseLabelsFor([
      row({ matter_id: "1", same_name_index: 1, same_name_count: 2, dob_iso: "1984-06-02" }),
      row({ matter_id: "2", same_name_index: 2, same_name_count: 2, dob_iso: "1991-11-30" }),
    ]);
    expect(labels.size).toBe(0);
  });

  it("groups by name and date of birth when the hub sent no person id", () => {
    const labels = caseLabelsFor([
      row({ matter_id: "5", dob_iso: "1990-01-01", extra: { order_type_tags: "NMO,OO" } }),
      row({ matter_id: "4", client_name: "synthetic  PERSON", dob_iso: "1990-01-01" }),
    ]);

    expect(labels.get("4")).toBe("Case 1 of 2 · Matter 4");
    expect(labels.get("5")).toBe("Case 2 of 2 · Non-Molestation Order and Occupation Order");
  });

  it("puts undated cases after dated ones and counts a repeated row once", () => {
    const dated = row({ matter_id: "9", extra: { primary_person_id: "1", created_utc: "2024-01-02" } });
    const labels = caseLabelsFor([
      row({ matter_id: "3", reference_summary: "court_family: ZZ00C00001", extra: { primary_person_id: "1" } }),
      dated,
      dated,
    ]);
    expect(labels.get("9")).toBe("Case 1 of 2 · Opened 2 Jan 2024");
    expect(labels.get("3")).toBe("Case 2 of 2 · Ref ZZ00C00001");
  });

  it("labels Stub Testperson's two stub cases and nobody else", () => {
    const labels = caseLabelsFor(stubSearch("stub").results);
    expect([...labels.keys()].sort()).toEqual(["9001", "9004"]);
    expect(labels.get("9001")).toMatch(/^Case 1 of 2 · Non-molestation order/);
    expect(labels.get("9004")).toMatch(/^Case 2 of 2 · Child arrangements order/);
  });
});

describe("helpers", () => {
  it("formats an opening date in British style and rejects nonsense", () => {
    expect(openedDateText("2025-03-04")).toBe("4 Mar 2025");
    expect(openedDateText("2025-02-30")).toBe("");
    expect(openedDateText("yesterday")).toBe("");
  });

  it("prefers the stored order text, shown in sentence case", () => {
    expect(orderTypeText(row({ matter_id: "1", order_requested_text: "C100 APPLICATION", extra: { order_type_tags: "CAO" } }))).toBe(
      "C100 application",
    );
    expect(orderTypeText(row({ matter_id: "1", extra: { order_type_tags: "PSO" } }))).toBe("Prohibited Steps Order");
  });

  it("falls back to the firm reference, then the matter number", () => {
    expect(caseDescriptor(row({ matter_id: "7", extra: { company_reference: "CaseForge-SYN-1" } }))).toBe("Ref CaseForge-SYN-1");
    expect(caseDescriptor(row({ matter_id: "7" }))).toBe("Matter 7");
  });

  it("has no key for a row with neither a person id nor a name", () => {
    expect(personKeyOf(row({ matter_id: "1", client_name: "" }))).toBe("");
  });
});
