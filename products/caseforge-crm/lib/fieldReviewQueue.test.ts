import { describe, expect, it } from "vitest";
import { missingReferralFormOf, reviewReasonOf } from "./fieldReviewQueue";
import type { FieldReviewFlag } from "./types";

function flag(overrides: Partial<FieldReviewFlag>): FieldReviewFlag {
  return {
    review_id: "r1",
    matter_id: "1",
    client_name: "Someone",
    field_name: "address_line1",
    field_label: "Address line 1",
    value_snapshot: "",
    note: "",
    flagged_by: "Someone Else",
    flagged_at: "2026-09-20T09:00:00Z",
    resolved_by: null,
    resolved_at: null,
    ...overrides,
  };
}

describe("reviewReasonOf", () => {
  it("is null for no flags or undefined", () => {
    expect(reviewReasonOf(undefined)).toBeNull();
    expect(reviewReasonOf([])).toBeNull();
  });

  it("lists the flagged fields' labels", () => {
    expect(reviewReasonOf([flag({ field_label: "Address line 1" }), flag({ field_label: "Date of birth" })])).toBe(
      "Marked: Address line 1, Date of birth",
    );
  });

  it("de-duplicates repeated labels", () => {
    expect(reviewReasonOf([flag({ field_label: "Telephone" }), flag({ field_label: "Telephone" })])).toBe(
      "Marked: Telephone",
    );
  });

  it("falls back to the field name when no label is given", () => {
    expect(reviewReasonOf([flag({ field_label: "", field_name: "custom_field" })])).toBe("Marked: custom_field");
  });

  it("shows an automatic entry's own note, not the generic label", () => {
    const auto = flag({ review_id: "auto:1", field_name: "missing_information", field_label: "Missing information", note: "Missing: address, date of birth", flagged_by: "Automatic" });
    expect(reviewReasonOf([auto])).toBe("Missing: address, date of birth");
  });

  it("joins a manual mark and an automatic gap", () => {
    const auto = flag({ review_id: "auto:1", field_name: "missing_information", field_label: "Missing information", note: "Missing: address", flagged_by: "Automatic" });
    expect(reviewReasonOf([flag({ field_label: "Date of birth" }), auto])).toBe("Marked: Date of birth. Missing: address");
  });
});

describe("the missing referral form entry", () => {
  const referral = flag({ field_name: "missing_referral_form", field_label: "Missing referral form", flagged_by: "Automatic", note: "Missing referral form" });

  it("is its own flag, not part of the yellow reason line", () => {
    expect(missingReferralFormOf([referral])).toBe(true);
    expect(missingReferralFormOf([flag({ field_label: "Telephone" })])).toBe(false);
    expect(reviewReasonOf([referral])).toBeNull();
    expect(reviewReasonOf([flag({ field_label: "Date of birth" }), referral])).toBe("Marked: Date of birth");
  });
});
