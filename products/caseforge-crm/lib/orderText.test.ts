import { describe, expect, it } from "vitest";
import { isAllCaps, normaliseOrderText } from "./orderText";
import { clientContextSummary } from "./vergilContext";

describe("normaliseOrderText", () => {
  it("sentence-cases ALL CAPS order text", () => {
    expect(normaliseOrderText("NON-MOLESTATION ORDER")).toBe("Non-molestation order");
    expect(normaliseOrderText("PROHIBITED STEPS ORDER & CHILD ARRANGEMENTS ORDER")).toBe(
      "Prohibited steps order & child arrangements order",
    );
  });

  it("keeps known acronyms in capitals", () => {
    expect(normaliseOrderText("NMO-CAO-PSO")).toBe("NMO-CAO-PSO");
    expect(normaliseOrderText("CHILD ARRANGEMENTS ORDER (C100) AND FL401 VIA LAA, DV, UK")).toBe(
      "Child arrangements order (C100) and FL401 via LAA, DV, UK",
    );
  });

  it("uses the court list's casing for court names", () => {
    expect(normaliseOrderText("NMO AT CENTRAL FAMILY COURT")).toBe("NMO at Central Family Court");
    expect(normaliseOrderText("NON-MOLESTATION ORDER. THE FAMILY COURT AT LEEDS")).toBe(
      "Non-molestation order. The Family Court at Leeds",
    );
    expect(normaliseOrderText("ORDER FOR READING")).toBe("Order for reading");
  });

  it("leaves mixed-case text untouched", () => {
    expect(normaliseOrderText("Non-Molestation Order")).toBe("Non-Molestation Order");
    expect(normaliseOrderText("nmo and cao")).toBe("nmo and cao");
    expect(isAllCaps("Non-molestation ORDER")).toBe(false);
  });

  it("handles an empty value", () => {
    expect(normaliseOrderText("")).toBe("");
    expect(normaliseOrderText("   ")).toBe("");
    expect(normaliseOrderText(null)).toBe("");
    expect(normaliseOrderText(undefined)).toBe("");
  });

  it("is applied where the CRM puts order text in Vergil's context", () => {
    const summary = clientContextSummary({ extra: {}, client_name: "Iris Indiatest", order_requested_text: "NON-MOLESTATION ORDER" });
    expect(summary).toContain("Order sought: Non-molestation order");
  });
});
