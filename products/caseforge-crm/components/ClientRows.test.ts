import { describe, expect, it } from "vitest";
import { isClientParty } from "./ClientRows";

describe("isClientParty", () => {
  it("hides the party whose role is the client's own role", () => {
    expect(isClientParty("Applicant", "Applicant")).toBe(true);
    expect(isClientParty("Respondent", "Applicant")).toBe(false);
    expect(isClientParty("Respondent", "Respondent")).toBe(true);
    expect(isClientParty("Applicant", "Respondent")).toBe(false);
  });
  it("always hides a party called Client", () => {
    expect(isClientParty("Client", "Applicant")).toBe(true);
    expect(isClientParty("client", "")).toBe(true);
  });
  it("with no client role on record hides only Client and Applicant", () => {
    expect(isClientParty("Applicant", null)).toBe(true);
    expect(isClientParty("Respondent", undefined)).toBe(false);
    expect(isClientParty("Local authority", "")).toBe(false);
    expect(isClientParty("", "Applicant")).toBe(false);
  });
});
