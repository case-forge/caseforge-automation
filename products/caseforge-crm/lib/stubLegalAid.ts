
import type { LegalAidSection, LegalAidSendResult } from "./legalAid";

export const STUB_UNPLACED = "This application's signing boxes could not be found: place the fields by hand in Documenso";

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
const NOT_ON = { text: "", decision: "not_on_benefits", todos: "made" };
const LINK = "https://example.invalid/stub-document";

function seed(matterId: string): LegalAidSection {
  const none = { status: "none", date: "", by: "", url: "" };
  const found = (n: number) => ({ status: "found", date: daysAgo(n), name: "Completed application for civil legal aid - STUBPERSON.pdf", url: LINK });
  const base = { matter_id: matterId, benefits: NOT_ON, can_send: false, problem: "" };
  if (matterId === "9001" || matterId === "9004") {
    return { ...base, application: found(1), signature: { ...none, status: "not_sent" }, can_send: true };
  }
  if (matterId === "9003") {
    return { ...base, application: found(6), signature: { status: "signed", date: daysAgo(2), by: "", url: LINK } };
  }
  if (matterId === "9002") {
    return { ...base, benefits: { text: "Universal Credit", decision: "on_benefits", todos: "none" }, application: { status: "missing", date: "", name: "", url: "" }, signature: none };
  }
  return {
    ...base,
    application: { status: "missing", date: "", name: "", url: "" },
    signature: none,
  };
}

const states = new Map<string, LegalAidSection>();

export function stubLegalAid(matterId: string): LegalAidSection {
  let s = states.get(matterId);
  if (!s) {
    s = seed(matterId);
    states.set(matterId, s);
  }
  return s;
}

export function stubSendLegalAid(matterId: string, by: string): LegalAidSendResult {
  const s = stubLegalAid(matterId);
  const refuse = (code: string, message: string): LegalAidSendResult => ({ ok: false, code, message, section: s });
  if (s.signature.status === "signed") return refuse("signed", "The signed declaration is already on file.");
  if (s.signature.status === "drafted") return refuse("sent", "The application has already been sent for signing.");
  if (s.application.status !== "found") return refuse("no_application", "No completed application is on record for this client.");
  if (matterId === "9004") {
    s.problem = STUB_UNPLACED;
    return refuse("unplaced", `${STUB_UNPLACED}.`);
  }
  s.signature = { status: "drafted", date: new Date().toISOString(), by, url: "" };
  s.can_send = false;
  s.problem = "";
  return { ok: true, code: "drafted", message: "Stub: the envelope and the AI DRAFTED email would be made here. Nothing was sent.", section: s };
}

export function resetStubLegalAid(): void {
  states.clear();
}
