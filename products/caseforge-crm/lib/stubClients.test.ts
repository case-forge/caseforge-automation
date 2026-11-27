import { beforeEach, describe, expect, it } from "vitest";
import { stubSearch } from "./stub";
import {
  STUB_FIXED_IDS,
  STUB_MADE_FIRST_ID,
  isStubMadeId,
  resetStubMadeClients,
  stubDeleteMadeClient,
  stubMadeChildren,
  stubMadeParties,
  stubMakeClient,
} from "./stubClients";

const input = { first: "Demo", last: "Person", email: "demo@example.invalid", category: "nmo_cao" };

describe("clients made in stub mode", () => {
  beforeEach(() => resetStubMadeClients());

  it("numbers made clients from the first made id, clear of the fixed and fixture ids", () => {
    expect(stubMakeClient(input).matter_id).toBe(String(STUB_MADE_FIRST_ID));
    expect(stubMakeClient(input).matter_id).toBe(String(STUB_MADE_FIRST_ID + 1));
  });

  it("finds a made client in search beside the three fixed ones", () => {
    const made = stubMakeClient(input);
    const all = stubSearch("*").results.map((r) => String(r.matter_id));
    expect(all).toEqual(expect.arrayContaining([...STUB_FIXED_IDS, made.matter_id]));
    expect(stubSearch("demo person").results.map((r) => String(r.matter_id))).toContain(made.matter_id);
    expect(stubSearch("nobody matches this").results.map((r) => String(r.matter_id))).not.toContain(made.matter_id);
  });

  it("deletes a made client for good", () => {
    const made = stubMakeClient(input);
    expect(stubDeleteMadeClient(made.matter_id)).toEqual({ deleted: true });
    expect(isStubMadeId(made.matter_id)).toBe(false);
    expect(stubSearch("demo person").results.map((r) => String(r.matter_id))).not.toContain(made.matter_id);
  });

  it("never deletes the three fixed stub clients", () => {
    for (const id of STUB_FIXED_IDS) {
      expect(stubDeleteMadeClient(id)).toEqual({ error: "The three fixed stub clients cannot be deleted." });
    }
    expect(stubSearch("stub").results.map((r) => String(r.matter_id))).toEqual(expect.arrayContaining([...STUB_FIXED_IDS]));
  });
});

import { stubFlagCounts, stubFlaggedMatters, stubSetFlag } from "./stub";
import { stubRecentIntakes } from "./stubIntakeTray";

describe("clients made in stub mode, in the rest of the app", () => {
  beforeEach(() => resetStubMadeClients());

  it("carries the game's referral details onto the client, its parties and its children", () => {
    const made = stubMakeClient({
      ...input,
      details: {
        dob: "07/03/1990",
        phone: "07700 900123",
        address: { line1: "4 Mill Lane", line2: "Testford", postcode: "ZZ1 1AA" },
        respondent: { name: "Sam Other", first: "Sam", last: "Other", dob: "01/01/1985", phone: "07700 900999", address: { line1: "9 High Street", line2: "Otherton", postcode: "ZZ2 2BB" } },
        nino: "AB123456C",
        c8: true,
        children: [{ name: "Ivy Person", dob: "01/02/2015", pr: "Yes", sex: "Female" }],
        caseReference: "ZZ25F11111",
        order: "Occupation Order",
      },
    });
    expect(made.client).toMatchObject({
      dob_iso: "1990-03-07",
      phone_primary: "07700 900123",
      case_reference: "ZZ25F11111",
      matter_name: "Occupation Order",
      address_summary: "Applicant: 4 Mill Lane, Testford, ZZ1 1AA",
      party_summary: "Applicant: Demo Person | Respondent: Sam Other",
    });
    expect(made.client.extra).toMatchObject({ nino_canonical: "AB123456C", has_c8: true, client_address_line1: "4 Mill Lane", client_address_postcode: "ZZ1 1AA" });
    expect(stubMadeParties(made.matter_id)).toMatchObject([{ role: "Respondent", display_name: "Sam Other", name_last: "Other", dob_iso: "1985-01-01", address_postcode: "ZZ2 2BB" }]);
    expect(stubMadeChildren(made.matter_id)).toMatchObject([{ child_name: "Ivy Person", name_first: "Ivy", name_last: "Person", dob_iso: "2015-02-01", parental_responsibility: "Yes" }]);
    expect(stubMadeParties("9001")).toBeUndefined();
  });

  it("lists a made client among the recent intakes until it is deleted", () => {
    const made = stubMakeClient(input);
    expect(stubRecentIntakes().find((i) => i.matter_id === made.matter_id)).toBeDefined();
    stubDeleteMadeClient(made.matter_id);
    expect(stubRecentIntakes().find((i) => i.matter_id === made.matter_id)).toBeUndefined();
  });

  it("counts and lists flagged and starred clients, made ones included", () => {
    const made = stubMakeClient(input);
    stubSetFlag({ matterId: made.matter_id, flagName: "flagged", isSet: true, setBy: "demo" });
    stubSetFlag({ matterId: "9001", flagName: "starred", isSet: true, setBy: "demo" });
    expect(stubFlagCounts(["flagged", "starred"])).toMatchObject({ flagged: 1, starred: 1 });
    expect(stubFlaggedMatters(["flagged"]).results.map((r) => String(r.matter_id))).toEqual([made.matter_id]);
    stubSetFlag({ matterId: made.matter_id, flagName: "flagged", isSet: false, setBy: "demo" });
    stubSetFlag({ matterId: "9001", flagName: "starred", isSet: false, setBy: "demo" });
    expect(stubFlagCounts(["flagged", "starred"])).toMatchObject({ flagged: 0, starred: 0 });
  });
});
