import { describe, expect, it } from "vitest";
import { PARTY_FIELDS, EDITABLE_FIELDS } from "./types";
import { ROLE_CHOICES, roleChoiceOf, roleOtherTextOf, roleToStore } from "./partyFields";

describe("role box", () => {
  it("offers Applicant, Respondent and Other", () => {
    expect([...ROLE_CHOICES]).toEqual(["Applicant", "Respondent", "Other"]);
  });
  it("shows a stored odd role as Other with its text", () => {
    expect(roleChoiceOf("Local authority")).toBe("Other");
    expect(roleOtherTextOf("Local authority")).toBe("Local authority");
  });
  it("shows the named roles as themselves, with no Other text", () => {
    expect(roleChoiceOf("respondent")).toBe("Respondent");
    expect(roleChoiceOf("Applicant")).toBe("Applicant");
    expect(roleOtherTextOf("Respondent")).toBe("");
  });
  it("shows no choice for no role, and stores a blank Other as Other party", () => {
    expect(roleChoiceOf("")).toBe("");
    expect(roleToStore("  ")).toBe("Other party");
    expect(roleToStore(" Grandmother ")).toBe("Grandmother");
  });
});

describe("party fields", () => {
  it("has no sex field on parties or on the client", () => {
    expect(PARTY_FIELDS.map((f) => f.name)).not.toContain("sex");
    expect(PARTY_FIELDS.map((f) => f.name)).not.toContain("sex_other");
    expect(EDITABLE_FIELDS.map((f) => f.name)).not.toContain("sex");
    expect(EDITABLE_FIELDS.map((f) => f.name)).not.toContain("sex_other");
  });
  it("labels the alias Alias", () => {
    expect(PARTY_FIELDS.find((f) => f.name === "aka_name")?.label).toBe("Alias");
  });
});
