
import { parseUtc } from "./matterTasks";

export interface LegalAidSection {
  matter_id: string;
  benefits: { text: string; decision: string; todos: string };
  application: { status: "found" | "missing" | string; date: string; name: string; url: string };
  signature: { status: "none" | "not_sent" | "drafted" | "signed" | string; date: string; by: string; url: string };
  can_send: boolean;
  problem: string;
}

export interface LegalAidSendResult {
  ok: boolean;
  code: string;
  message: string;
  section: LegalAidSection;
}

export interface LegalAidLine {
  key: "benefits" | "application" | "signature";
  label: string;
  ticked: boolean;
  text: string;

  url: string;

  note: string;
}

const LONDON_DATE = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "numeric", month: "short", year: "numeric" });

function day(iso: string): string {
  const ms = parseUtc(iso);
  return Number.isNaN(ms) ? "" : LONDON_DATE.format(new Date(ms));
}

function https(url: string): string {
  return typeof url === "string" && url.startsWith("https://") ? url : "";
}

function withDate(words: string, iso: string): string {
  const d = day(iso);
  return d ? `${words} on ${d}` : words;
}

function benefitsLine(b: LegalAidSection["benefits"]): LegalAidLine {
  const base = { key: "benefits" as const, label: "Benefits", url: "" };
  if (b.decision === "on_benefits") return { ...base, ticked: true, text: b.text || "On benefits", note: "" };
  if (b.decision === "not_on_benefits") {
    const note =
      b.todos === "made"
        ? "The Legal Aid Agency means-tests this client: the two legal aid to-dos are on the To do tab."
        : "The Legal Aid Agency means-tests this client.";
    return { ...base, ticked: false, text: b.text ? `Not on benefits (the intro says "${b.text}")` : "Not on benefits", note };
  }
  if (b.decision === "unrecognised") {
    return { ...base, ticked: false, text: b.text || "Not understood", note: "Check the intro: the benefits entry is not one the legal aid rule recognises." };
  }
  if (b.decision === "not_read") return { ...base, ticked: false, text: b.text || "Not read from the intro", note: "Check the intro for the benefits entry." };
  return { ...base, ticked: false, text: b.text || "Not on record", note: "" };
}

export function legalAidLines(section: LegalAidSection): LegalAidLine[] {
  const lines: LegalAidLine[] = [benefitsLine(section.benefits)];
  const app = section.application;
  if (app.status !== "found") {
    lines.push({ key: "application", label: "Completed application", ticked: false, text: "Not on record", url: "", note: "" });
    return lines;
  }
  lines.push({ key: "application", label: "Completed application", ticked: true, text: withDate("Found", app.date), url: https(app.url), note: "" });
  const sig = section.signature;
  const base = { key: "signature" as const, label: "Client declaration" };
  if (sig.status === "signed") {
    lines.push({ ...base, ticked: true, text: withDate("Received and signed", sig.date), url: https(sig.url), note: "" });
  } else if (sig.status === "drafted") {
    lines.push({
      ...base,
      ticked: false,
      text: withDate("Signing email drafted", sig.date),
      url: "",
      note: section.problem || "Send the AI DRAFTED email from Outlook Drafts: the client signs from the link in it.",
    });
  } else {
    lines.push({ ...base, ticked: false, text: "Not signed", url: "", note: section.problem });
  }
  return lines;
}

export function showSendButton(section: LegalAidSection): boolean {
  return section.application.status === "found" && section.signature.status === "not_sent";
}

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

export async function fetchLegalAid(matterId: string): Promise<LegalAidSection> {
  const res = await fetch(`/api/clients/legal-aid?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load legal aid.");
  return res.json();
}

export async function sendForSignature(matterId: string, addressChecked: boolean): Promise<LegalAidSendResult> {
  const res = await fetch("/api/clients/legal-aid/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, address_checked: addressChecked }),
  });
  if (!res.ok) return readError(res, "Nothing was made.");
  return res.json();
}
