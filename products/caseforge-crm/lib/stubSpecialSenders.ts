
import { parseMark } from "./specialSenderRules";
import type { SenderMark, SpecialSender } from "./specialSenderRules";

const START: SpecialSender[] = [
  { id: "ss_demo1", name: "Demo Chambers", domains: ["chambers.example.invalid"], new_clients: false, logo: "stub", mark: null },
  { id: "ss_demo2", name: "Demo Referrer", domains: [], new_clients: true, logo: "", mark: { text: "DR", colours: ["#1e7a34", "#111111"], background: "#d4d4d4" } },
];

let senders: SpecialSender[] = START.map((s) => ({ ...s }));

export function resetStubSpecialSenders(): void {
  senders = START.map((s) => ({ ...s }));
}

export function stubSpecialSenders(): { items: SpecialSender[] } {
  return { items: senders.map((s) => ({ ...s, domains: [...s.domains] })) };
}

export type StubEdit = { id?: string; name: string; domains: string[]; new_clients: boolean; mark?: SenderMark | null };

export function stubSaveSpecialSenders(edits: StubEdit[], isAdmin: boolean): { ok: true; view: { items: SpecialSender[] } } | { ok: false; status: number; message: string } {
  if (!isAdmin) return { ok: false, status: 403, message: "Only an administrator can change the special senders" };
  const next: SpecialSender[] = [];
  for (const edit of edits) {
    const name = edit.name.trim().replace(/\s+/g, " ");
    if (!name) return { ok: false, status: 422, message: "every special sender needs a name" };
    if (edit.domains.length === 0 && !edit.new_clients) return { ok: false, status: 422, message: `'${name}' needs a domain, or the new-clients switch, so there is something to recognise it by` };
    if (edit.mark && !parseMark(edit.mark)) return { ok: false, status: 422, message: "a made logo is one to 3 letters or digits, with a colour for each letter and the background" };
    const known = senders.find((s) => s.id === edit.id);
    if (edit.id && !known) return { ok: false, status: 422, message: "that special sender no longer exists; reload the page" };
    next.push({ id: known?.id ?? `ss_${Math.random().toString(16).slice(2, 12)}`, name, domains: edit.domains.map((d) => d.trim().toLowerCase()).filter(Boolean), new_clients: edit.new_clients, logo: edit.mark ? "" : known?.logo ?? "", mark: edit.mark ? { ...edit.mark, text: edit.mark.text.toUpperCase() } : null });
  }
  senders = next;
  return { ok: true, view: stubSpecialSenders() };
}

export function stubSetSenderLogo(id: string, has: boolean, isAdmin: boolean): { ok: boolean; status: number; message: string } {
  if (!isAdmin) return { ok: false, status: 403, message: "Only an administrator can change the special senders" };
  const target = senders.find((s) => s.id === id);
  if (!target) return { ok: false, status: 404, message: "no such special sender" };
  target.logo = has ? "stub" : "";
  if (has) target.mark = null;
  return { ok: true, status: 200, message: "" };
}

export function stubSenderHasLogo(id: string): boolean {
  return senders.some((s) => s.id === id && s.logo !== "");
}
