
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const src = readFileSync(new URL("./NewClientButton.tsx", import.meta.url), "utf8");

describe("NewClientButton", () => {
  it("opens on the choice, and each choice opens its own form", () => {
    expect(src).toContain('setMode("choose")');
    expect(src).toContain('onEmail={() => choose("email")}');
    expect(src).toContain('onManual={() => choose("manual")}');
  });
  it("posts the manual form to its own route and the email form to the existing one", () => {
    expect(src).toContain('"/api/new-client/manual"');
    expect(src).toContain('"/api/new-client"');
  });
  it("has no phone reveal step or phoneOpen state", () => {
    expect(src).not.toContain("phoneOpen");
    expect(src).not.toContain("Add phone number");
  });
  it("never creates from a form submit: Enter previews, and Create is a separate button shown after a preview", () => {
    expect(src).not.toContain('type="submit"');
    expect(src).toMatch(/function submit[\s\S]*?send\(true\)/);
    expect(src).toContain("hasPreview={Boolean(shownPreview)}");
  });
  it("makes any change of the form stale, the mode and the address tick included", () => {
    expect(src).toMatch(/const formKey = JSON\.stringify\(\[mode, first, last, email, phone, category, sendRif, sendLaif, addressChecked, extras\]\)/);
    expect(src).toContain("currentPreview(preview, formKey)");
  });
  it("keeps the press id for the email form and sends none for the manual one", () => {
    expect(src).toContain("request_id: pressRef.current.id");
    expect(src).toMatch(/manual \? \{ \.\.\.common, \.\.\.manualFields \} : \{ \.\.\.common, send_rif/);
  });
  it("sends the manual details only on the manual route", () => {
    expect(src).toContain("manual ? { ...common, ...manualFields }");
    for (const field of ["middle_name", "dob", "nino", "address_line1", "address_line4", "postcode", "matter_details"]) {
      expect(src).toContain(`${field}:`);
    }
  });
});
