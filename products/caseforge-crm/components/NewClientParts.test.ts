
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BLANK_MANUAL_EXTRAS, ManualFields, NewClientChoice, PhoneField, PreviewCreateActions } from "./NewClientParts";

const noop = () => undefined;
const render = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node);

describe("the first choice", () => {
  const html = render(createElement(NewClientChoice, { onEmail: noop, onManual: noop, onCancel: noop }));
  it("offers adding by email and adding manually, and nothing else to fill in", () => {
    expect(html).toContain("Add client by email");
    expect(html).toContain("Add client manually");
    expect(html).not.toContain("<input");
  });
});

describe("the telephone field", () => {
  it("is always visible, with no reveal button", () => {
    const html = render(createElement(PhoneField, { value: "", onChange: noop }));
    expect(html).toContain('type="tel"');
    expect(html).toContain("Phone number (optional)");
    expect(html).not.toContain("Add phone number");
  });
  it("keeps its note for a good or blank number and shows the error for a bad one", () => {
    expect(render(createElement(PhoneField, { value: "07700 900123", onChange: noop }))).toContain("rung for an update");
    const bad = render(createElement(PhoneField, { value: "call me", onChange: noop }));
    expect(bad).toContain("does not look like a UK number");
    expect(bad).toContain('aria-invalid="true"');
  });
});

describe("preview, then create", () => {
  const base = { ready: true, busy: false, onCancel: noop, onPreview: noop, onCreate: noop };
  it("shows Preview only until a preview is showing", () => {
    const html = render(createElement(PreviewCreateActions, { ...base, hasPreview: false }));
    expect(html).toContain("Preview");
    expect(html).not.toContain("Create");
  });
  it("shows Create once the unchanged form has been previewed", () => {
    const html = render(createElement(PreviewCreateActions, { ...base, hasPreview: true }));
    expect(html).toContain("Preview");
    expect(html).toContain("Create");
  });
  it("disables both while the form is not ready", () => {
    const html = render(createElement(PreviewCreateActions, { ...base, ready: false, hasPreview: true }));
    expect(html.match(/disabled=""/g)?.length).toBe(2);
  });
});

describe("the manual form", () => {
  const values = { first: "", last: "", email: "", phone: "", category: "", ...BLANK_MANUAL_EXTRAS };
  const html = render(
    createElement(ManualFields, {
      values,
      categories: [{ key: "crime", label: "Crime" }],
      onChange: noop,
      addressCheck: false,
      addressChecked: false,
      onAddressChecked: noop,
    }),
  );
  it("asks for the names and matter, never a name to type, and marks email optional", () => {
    expect(html).toContain("First name");
    expect(html).toContain("Last name");
    expect(html).toContain("Matter");
    expect(html).not.toContain("Your name");
    expect(html).toContain("Email (optional)");
    expect(html.match(/required=""/g)?.length).toBe(3);
  });
  it("asks for the details the New Client Form collects, all optional", () => {
    for (const label of [
      "Middle name (optional)", "Date of birth (optional)", "NI number (optional)", "Address line 1",
      "Address line 2", "Address line 3", "Address line 4", "Postcode", "Brief details of the matter (optional)",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain("Title");
  });
  it("shows the telephone field with no reveal step and no test-client tick", () => {
    expect(html).toContain('type="tel"');
    expect(html).not.toContain("Add phone number");
    expect(html).not.toContain("test client");
    expect(html).not.toContain("checked");
  });
  it("shows the address-check box only when the hub asks for it", () => {
    expect(html).not.toContain("I have checked this email address");
    const asked = render(
      createElement(ManualFields, { values, categories: [], onChange: noop, addressCheck: true, addressChecked: false, onAddressChecked: noop }),
    );
    expect(asked).toContain("I have checked this email address");
  });
});
