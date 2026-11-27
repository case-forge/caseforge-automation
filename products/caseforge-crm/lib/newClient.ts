import type { ClientMatch } from "./types";
import { normaliseOrderText } from "./orderText";

export const NEW_CLIENT_DAYS = 3;

const DAY_MS = 24 * 60 * 60 * 1000;

export function createdAtOf(match: ClientMatch): Date | null {
  const raw = match.extra?.["created_utc"];
  if (typeof raw !== "string" || !raw.trim()) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function isNewClient(match: ClientMatch, now: Date = new Date()): boolean {
  const created = createdAtOf(match);
  if (!created) return false;
  const age = now.getTime() - created.getTime();
  return age >= -DAY_MS && age < NEW_CLIENT_DAYS * DAY_MS;
}

export type NewClientPreview = {
  preview: true;

  manual?: boolean;
  category: string;
  folder?: { path: string; book: string; subfolders?: string[] };
  record?: Record<string, Record<string, unknown>>;
  envelopes?: { documents: string; signer?: string }[];
  drafts?: { documents: string; to?: string; subject?: string }[];
  billing?: unknown[];
  pill?: string;
  pending?: { status: string; extra_forms?: string[] };
};

function manualDetailLines(person: Record<string, unknown>, matter: Record<string, unknown>): string[] {
  const text = (key: string) => String(person[key] ?? "").trim();
  const address = [1, 2, 3, 4].map((n) => text(`address_line${n}`)).filter(Boolean);
  const postcode = text("address_postcode");
  const notes = /matter details: ([\s\S]*)$/.exec(String(matter.tracker_notes ?? ""))?.[1]?.trim() ?? "";
  const shown: [string, string][] = [
    ["Middle name", text("name_middle")],
    ["Date of birth", text("dob_iso")],
    ["NI number", text("nino_canonical")],
    ["Address", [...address, postcode].filter(Boolean).join(", ")],
    ["Matter details", notes],
  ];
  const blank = [
    ...shown.filter(([, value]) => !value).map(([label]) => label),
    ...(person.email_primary ? [] : ["Email"]),
    ...(person.phone_primary ? [] : ["Telephone"]),
  ];
  return [
    ...shown.filter(([, value]) => value).map(([label, value]) => `${label}: ${value}`),
    ...(blank.length ? [`Left blank: ${blank.join(", ")}`] : []),
  ];
}

export function previewSections(p: NewClientPreview): { title: string; lines: string[] }[] {
  const sections: { title: string; lines: string[] }[] = [];
  if (p.folder) {
    const subs = p.folder.subfolders?.length ? [`${p.folder.subfolders.length} standard subfolders inside`] : [];
    sections.push({ title: `Folder, in ${p.folder.book}`, lines: [p.folder.path, ...subs] });
  }
  const matter = p.record?.matters ?? {};
  const person = p.record?.people ?? {};
  const manualLines = p.manual ? manualDetailLines(person, matter) : [];
  const recordLines = [
    person.canonical_name ? `Client: ${String(person.canonical_name)}` : "",
    person.email_primary ? `Email: ${String(person.email_primary)}` : "",
    person.phone_primary ? `Telephone: ${String(person.phone_primary)}` : "",
    matter.client_role ? `Role: ${String(matter.client_role)}` : "",
    matter.order_requested_text ? `Matter: ${normaliseOrderText(String(matter.order_requested_text))}` : "",
    ...manualLines,
    p.pill ? `Pill: ${p.pill}` : "",
  ].filter(Boolean);
  if (p.pending) sections.push({ title: "Waiting for the signed New Client Form", lines: ["Listed under the number on the new client button"] });
  if (recordLines.length) {
    sections.push({
      title: p.manual ? "Record, made when you press Create" : "Record, made when the signed New Client Form comes back",
      lines: recordLines,
    });
  }
  if (p.envelopes?.length) {
    sections.push({ title: "Documenso envelopes (not sent)", lines: p.envelopes.map((e) => e.documents) });
  }
  if (p.drafts?.length) {
    sections.push({
      title: "Outlook drafts (not sent)",
      lines: p.drafts.map((d) => [d.subject || d.documents, d.to ? `to ${d.to}` : ""].filter(Boolean).join(" ")),
    });
  }
  sections.push({ title: "Billing", lines: p.billing?.length ? p.billing.map(String) : ["No billing entry"] });
  return sections;
}

export const PHONE_ERROR = "That telephone number does not look like a UK number. Leave it blank or check it.";

export function cleanPhone(value: unknown): { ok: true; value: string } | { ok: false; error: string } {
  const text = String(value ?? "").split(/\s+/).filter(Boolean).join(" ");
  if (!text) return { ok: true, value: "" };
  if (!/^[+(]?[0-9][0-9 ()\-.]*$/.test(text)) return { ok: false, error: PHONE_ERROR };
  let digits = text.replace("(0)", "").replace(/\D/g, "");
  if (digits.startsWith("0044")) digits = `0${digits.slice(4)}`;
  else if (text.startsWith("+")) {
    if (!digits.startsWith("44")) return { ok: false, error: PHONE_ERROR };
    digits = `0${digits.slice(2)}`;
  }
  if (!/^0\d{9,10}$/.test(digits) || new Set(digits).size < 3 || digits[1] === "0") return { ok: false, error: PHONE_ERROR };
  return { ok: true, value: text };
}

export function currentPreview<T>(preview: { key: string; data: T } | null, formKey: string): T | null {
  return preview && preview.key === formKey ? preview.data : null;
}

export function manualReady(f: { first: string; last: string; category: string; phone: string }): boolean {

  return Boolean(f.first.trim() && f.last.trim() && f.category.trim() && cleanPhone(f.phone).ok);
}
