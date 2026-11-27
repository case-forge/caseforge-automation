import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { legalAidLines, showSendButton } from "./legalAid";
import type { LegalAidSection } from "./legalAid";
import { resetStubLegalAid, STUB_UNPLACED, stubLegalAid, stubSendLegalAid } from "./stubLegalAid";

function section(over: Partial<LegalAidSection> = {}): LegalAidSection {
  return {
    matter_id: "9001",
    benefits: { text: "", decision: "not_on_benefits", todos: "made" },
    application: { status: "missing", date: "", name: "", url: "" },
    signature: { status: "none", date: "", by: "", url: "" },
    can_send: false,
    problem: "",
    ...over,
  };
}

const FOUND = { status: "found", date: "2026-10-10T23:30:00Z", name: "Completed application for civil legal aid - STUBPERSON.pdf", url: "https://short.example.invalid/app" };

describe("legalAidLines", () => {
  it("shows an empty box and Not on record until the application is found, and no signature line", () => {
    const lines = legalAidLines(section());
    expect(lines.map((l) => l.key)).toEqual(["benefits", "application"]);
    expect(lines[1]).toMatchObject({ label: "Completed application", ticked: false, text: "Not on record", url: "" });
    expect(showSendButton(section())).toBe(false);
  });

  it("ticks a found application with its London date and link, then offers Not signed", () => {
    const s = section({ application: FOUND, signature: { status: "not_sent", date: "", by: "", url: "" }, can_send: true });
    const [, app, sig] = legalAidLines(s);
    expect(app).toMatchObject({ ticked: true, text: "Found on 11 Oct 2026", url: "https://short.example.invalid/app" });
    expect(sig).toMatchObject({ label: "Client declaration", ticked: false, text: "Not signed", note: "" });
    expect(showSendButton(s)).toBe(true);
  });

  it("says the signing email is drafted, not sent, and takes the button away", () => {
    const s = section({ application: FOUND, signature: { status: "drafted", date: "2026-10-12T09:00:00Z", by: "Sam", url: "" } });
    const sig = legalAidLines(s)[2];
    expect(sig.ticked).toBe(false);
    expect(sig.text).toBe("Signing email drafted on 12 Oct 2026");
    expect(sig.note).toContain("Send the AI DRAFTED email");
    expect(showSendButton(s)).toBe(false);
  });

  it("ticks the signed declaration with its date and link", () => {
    const s = section({ application: FOUND, signature: { status: "signed", date: "2026-10-14T10:00:00Z", by: "", url: "https://short.example.invalid/signed" } });
    expect(legalAidLines(s)[2]).toMatchObject({ ticked: true, text: "Received and signed on 14 Oct 2026", url: "https://short.example.invalid/signed" });
    expect(showSendButton(s)).toBe(false);
  });

  it("shows why the fields could not be placed under Not signed, and keeps the button", () => {
    const s = section({ application: FOUND, signature: { status: "not_sent", date: "", by: "", url: "" }, problem: STUB_UNPLACED, can_send: true });
    expect(legalAidLines(s)[2]).toMatchObject({ text: "Not signed", note: STUB_UNPLACED });
    expect(showSendButton(s)).toBe(true);
  });

  it("only links to an https address", () => {
    const s = section({ application: { ...FOUND, url: "javascript:alert(1)" }, signature: { status: "signed", date: "", by: "", url: "http://plain.example.invalid" } });
    const [, app, sig] = legalAidLines(s);
    expect(app.url).toBe("");
    expect(sig).toMatchObject({ url: "", text: "Received and signed" });
  });

  it("says what the intro meant for benefits", () => {
    const line = (benefits: LegalAidSection["benefits"]) => legalAidLines(section({ benefits }))[0];
    expect(line({ text: "Universal Credit", decision: "on_benefits", todos: "none" })).toMatchObject({ ticked: true, text: "Universal Credit", note: "" });
    expect(line({ text: "", decision: "not_on_benefits", todos: "made" })).toMatchObject({ ticked: false, text: "Not on benefits" });
    expect(line({ text: "NO", decision: "not_on_benefits", todos: "made" }).note).toContain("two legal aid to-dos are on the To do tab");
    expect(line({ text: "Unknown", decision: "unrecognised", todos: "none" }).note).toContain("Check the intro");
    expect(line({ text: "", decision: "", todos: "none" })).toMatchObject({ ticked: false, text: "Not on record", note: "" });
  });
});

describe("the stub", () => {
  beforeEach(() => resetStubLegalAid());

  it("offers every state the section has", () => {
    expect(stubLegalAid("9002").application.status).toBe("missing");
    expect(stubLegalAid("9001").signature.status).toBe("not_sent");
    expect(stubLegalAid("9003").signature.status).toBe("signed");
    expect(stubLegalAid("9099")).toMatchObject({ can_send: false });
  });

  it("drafts on the first press and refuses the second", () => {
    const first = stubSendLegalAid("9001", "Sam");
    expect(first).toMatchObject({ ok: true, code: "drafted" });
    expect(first.section.signature).toMatchObject({ status: "drafted", by: "Sam" });
    expect(stubLegalAid("9001").signature.status).toBe("drafted");
    expect(stubSendLegalAid("9001", "Sam")).toMatchObject({ ok: false, code: "sent" });
  });

  it("refuses an application whose signing boxes cannot be found, and makes nothing", () => {
    const result = stubSendLegalAid("9004", "Sam");
    expect(result).toMatchObject({ ok: false, code: "unplaced", message: `${STUB_UNPLACED}.` });
    expect(result.section.signature.status).toBe("not_sent");
    expect(result.section.problem).toBe(STUB_UNPLACED);
  });

  it("refuses a signed and a missing matter", () => {
    expect(stubSendLegalAid("9003", "Sam").code).toBe("signed");
    expect(stubSendLegalAid("9002", "Sam").code).toBe("no_application");
  });
});

describe("the Details tab", () => {
  const panel = readFileSync(join(__dirname, "..", "components", "DetailPanel.tsx"), "utf8");

  it("renders the Legal aid section and none of the fields it replaced", () => {
    expect(panel).toContain("<LegalAidSection");
    for (const gone of ["Gateway evidence", "Legal aid certificate", "Legal aid reference", "gateway-evidence-status", "legal-aid-certificate-status"]) {
      expect(panel).not.toContain(gone);
    }
  });
});
