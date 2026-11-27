import { describe, expect, it } from "vitest";
import { NEW_CLIENT_DAYS, cleanPhone, createdAtOf, currentPreview, isNewClient, manualReady, previewSections } from "./newClient";
import type { ClientMatch } from "./types";

const NOW = new Date("2026-09-24T12:00:00Z");

function match(created: unknown): ClientMatch {
  return { matter_id: "1", extra: created === undefined ? {} : { created_utc: created } } as unknown as ClientMatch;
}

describe("isNewClient", () => {
  it("is new the day the record is created", () => {
    expect(isNewClient(match("2026-09-24T09:00:00Z"), NOW)).toBe(true);
  });

  it("is still new just inside the window", () => {
    expect(isNewClient(match("2026-09-21T13:00:00Z"), NOW)).toBe(true);
  });

  it("expires once the window has passed", () => {
    expect(isNewClient(match("2026-09-21T11:00:00Z"), NOW)).toBe(false);
    expect(isNewClient(match("2026-03-27T00:00:00Z"), NOW)).toBe(false);
  });

  it("uses a three day window", () => {
    expect(NEW_CLIENT_DAYS).toBe(3);
  });

  it("never reads an unknown or unparseable date as new", () => {
    expect(isNewClient(match(undefined), NOW)).toBe(false);
    expect(isNewClient(match(""), NOW)).toBe(false);
    expect(isNewClient(match("not a date"), NOW)).toBe(false);
    expect(isNewClient(match(12345), NOW)).toBe(false);
  });

  it("treats a timestamp well in the future as bad data, not new", () => {
    expect(isNewClient(match("2026-10-30T00:00:00Z"), NOW)).toBe(false);
  });

  it("tolerates a few hours of clock skew", () => {
    expect(isNewClient(match("2026-09-24T18:00:00Z"), NOW)).toBe(true);
  });

  it("reads a record with no extra at all as not new", () => {
    expect(isNewClient({ matter_id: "1" } as unknown as ClientMatch, NOW)).toBe(false);
    expect(createdAtOf({ matter_id: "1" } as unknown as ClientMatch)).toBeNull();
  });
});

describe("previewSections", () => {
  it("says where the folder goes, what the record holds, and that nothing is sent", () => {
    const sections = previewSections({
      preview: true,
      category: "Crime",
      folder: { path: "Live/2A-Z - Crime/Testa Fakename", book: "2A-Z - Crime", subfolders: ["a", "b"] },
      record: {
        people: { canonical_name: "Testa Fakename", email_primary: "t@example.com" },
        matters: { client_role: "Applicant", order_requested_text: "Crime" },
      },
      envelopes: [{ documents: "New Client Form + Letter of Authority" }],
      drafts: [{ documents: "New Client Form + Letter of Authority", to: "t@example.com", subject: "Forms" }],
      billing: [],
      pill: "Crime",
    });
    expect(sections.map((s) => s.title)).toEqual([
      "Folder, in 2A-Z - Crime",
      "Record, made when the signed New Client Form comes back",
      "Documenso envelopes (not sent)",
      "Outlook drafts (not sent)",
      "Billing",
    ]);
    expect(sections[3].lines).toEqual(["Forms to t@example.com"]);
    expect(sections[4].lines).toEqual(["No billing entry"]);
  });
});

describe("cleanPhone (the optional number on the new client form)", () => {
  it("treats blank as no number", () => {
    expect(cleanPhone("")).toEqual({ ok: true, value: "" });
    expect(cleanPhone("   ")).toEqual({ ok: true, value: "" });
    expect(cleanPhone(undefined)).toEqual({ ok: true, value: "" });
  });

  it.each(["07700 900123", "07700900123", "020 7946 0958", "+44 7700 900123", "+44 (0)7700 900123", "0044 7700 900123", "(020) 7946-0958"])(
    "accepts %s",
    (value) => {
      expect(cleanPhone(value)).toEqual({ ok: true, value });
    },
  );

  it("tidies stray spaces", () => {
    expect(cleanPhone("  07700   900123 ")).toEqual({ ok: true, value: "07700 900123" });
  });

  it.each(["abc", "12345", "077009001", "00000000000", "07777777777", "+1 202 555 0100", "+44 7700", "07700 900123 ext 5", "44 7700 900123"])(
    "rejects %s",
    (value) => {
      expect(cleanPhone(value).ok).toBe(false);
    },
  );
});

describe("previewSections with a phone number", () => {
  it("lists the telephone on the record only when one was given", () => {
    const base = { preview: true as const, category: "NMO-CAO" };
    const withPhone = previewSections({ ...base, record: { people: { canonical_name: "A B", phone_primary: "07700 900123" } } });
    expect(withPhone.flatMap((s) => s.lines)).toContain("Telephone: 07700 900123");
    const without = previewSections({ ...base, record: { people: { canonical_name: "A B" } } });
    expect(without.flatMap((s) => s.lines).join("|")).not.toContain("Telephone");
  });
});

describe("currentPreview: a preview counts only for the unchanged form", () => {
  const shown = { key: "form-1", data: { preview: true as const } };
  it("is shown for the same form key", () => {
    expect(currentPreview(shown, "form-1")).toEqual({ preview: true });
  });
  it("is stale, so Create is hidden, once the form changes", () => {
    expect(currentPreview(shown, "form-2")).toBeNull();
  });
  it("is absent before any preview", () => {
    expect(currentPreview(null, "form-1")).toBeNull();
  });
});

describe("manualReady", () => {
  const ok = { first: "A", last: "B", category: "crime", phone: "" };
  it("needs names, a matter and who is adding them; email and phone may be blank", () => {
    expect(manualReady(ok)).toBe(true);
  });
  it.each(["first", "last", "category"] as const)("is not ready without %s", (field) => {
    expect(manualReady({ ...ok, [field]: "  " })).toBe(false);
  });
  it("is not ready with a telephone number that is not a UK number", () => {
    expect(manualReady({ ...ok, phone: "call me" })).toBe(false);
    expect(manualReady({ ...ok, phone: "07700 900123" })).toBe(true);
  });
});

describe("previewSections for a client added by hand", () => {
  it("says the record is made when Create is pressed, not when a form comes back", () => {
    const sections = previewSections({ preview: true, manual: true, category: "Crime", record: { people: { canonical_name: "A B" } } });
    expect(sections.map((s) => s.title)).toContain("Record, made when you press Create");
    expect(sections.map((s) => s.title).join("|")).not.toContain("signed New Client Form");
  });
});

describe("previewSections lists every detail a client added by hand would carry", () => {
  const base = { preview: true as const, manual: true, category: "Crime" };
  it("lists each given detail and names what is left blank", () => {
    const sections = previewSections({
      ...base,
      record: {
        people: {
          canonical_name: "A B", name_middle: "Q", dob_iso: "1959-09-20", nino_canonical: "AB123456C",
          address_line1: "1 Example Road", address_line2: "Testville", address_postcode: "SW1A 1AA", phone_primary: "07700 900123",
        },
        matters: { tracker_notes: "Added manually in the CRM (Crime)\nAdded manually, matter details: Synthetic details." },
      },
    });
    const lines = sections.flatMap((s) => s.lines);
    expect(lines).toContain("Middle name: Q");
    expect(lines).toContain("Date of birth: 1959-09-20");
    expect(lines).toContain("NI number: AB123456C");
    expect(lines).toContain("Address: 1 Example Road, Testville, SW1A 1AA");
    expect(lines).toContain("Matter details: Synthetic details.");
    expect(lines).toContain("Left blank: Email");
  });
  it("says everything is blank when only the basics were given", () => {
    const lines = previewSections({ ...base, record: { people: { canonical_name: "A B" } } }).flatMap((s) => s.lines);
    expect(lines).toContain("Left blank: Middle name, Date of birth, NI number, Address, Matter details, Email, Telephone");
  });
  it("adds none of this to a by-email preview", () => {
    const lines = previewSections({ preview: true, category: "Crime", record: { people: { canonical_name: "A B" } } }).flatMap((s) => s.lines);
    expect(lines.join("|")).not.toContain("Left blank");
  });
});
