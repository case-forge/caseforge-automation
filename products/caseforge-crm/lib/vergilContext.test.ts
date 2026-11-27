import { describe, expect, it } from "vitest";
import type { ClientMatch } from "./types";
import { clientContextSummary } from "./vergilContext";

function match(overrides: Partial<ClientMatch> = {}): ClientMatch {
  return { extra: {}, ...overrides };
}

describe("clientContextSummary", () => {
  it("includes the client name and matter basics", () => {
    const summary = clientContextSummary(
      match({
        client_name: "Iris Indiatest",
        matter_name: "Iris Indiatest",
        client_role: "Applicant",
        order_requested_text: "Non-Molestation Order",
        live_matter_folder: "Company_Data/.../Iris Indiatest",
      }),
    );
    expect(summary).toContain("Client: Iris Indiatest");
    expect(summary).toContain("Matter: Iris Indiatest - Applicant");
    expect(summary).toContain("Order sought: Non-Molestation Order");
    expect(summary).toContain("Live folder: Company_Data/.../Iris Indiatest");
  });

  it("flags C8 explicitly when set", () => {
    const summary = clientContextSummary(match({ extra: { has_c8: true } }));
    expect(summary).toContain("C8 confidentiality flag is set");
  });

  it("omits C8 warning when not set", () => {
    const summary = clientContextSummary(match({ extra: { has_c8: false } }));
    expect(summary).not.toContain("C8 confidentiality flag");
  });

  it("surfaces hearing/order/email status from extra when present", () => {
    const summary = clientContextSummary(
      match({
        extra: {
          next_hearing_text: "2026-09-15 10:00, Central Family Court",
          order_status: "sealed",
          last_material_email_subject: "RE: hearing bundle",
          last_material_email_received: "2026-09-06",
        },
      }),
    );
    expect(summary).toContain("Next hearing: 2026-09-15 10:00, Central Family Court");
    expect(summary).toContain("Order status: sealed");
    expect(summary).toContain("Last material email: RE: hearing bundle - 2026-09-06");
  });

  it("omits a line entirely when the field is absent rather than printing an empty one", () => {
    const summary = clientContextSummary(match({ client_name: "Jane Doe" }));
    expect(summary).not.toContain("Next hearing:");
    expect(summary).not.toContain("Order status:");
    expect(summary.split("\n").every((line) => line.trim().length > 0)).toBe(true);
  });

  it("falls back to the placeholder name when nothing is on record", () => {
    const summary = clientContextSummary(match());
    expect(summary).toContain("Client: (no name on record)");
  });
});
