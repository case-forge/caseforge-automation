
import type { EmailClassifierView } from "./emailClassifier";

const DEFAULTS: Record<string, string[]> = {
  court_domains: ["court.example", "tribunal.example"],
  gp_keywords: ["repeat prescription", "surgery appointment"],
  newsletter_patterns: ["unsubscribe", "view in browser"],
};

let added: Record<string, string[]> = {};
let removed: Record<string, string[]> = {};
let audit: Array<Record<string, string>> = [];

export function resetStubEmailClassifier(): void {
  added = {};
  removed = {};
  audit = [];
}

export function stubEmailClassifier(): EmailClassifierView {
  const lists: EmailClassifierView["lists"] = {};
  for (const [name, base] of Object.entries(DEFAULTS)) {
    const add = added[name] ?? [];
    const off = removed[name] ?? [];
    lists[name] = { default: base, added: add, removed: off, effective: [...base.filter((e) => !off.includes(e)), ...add] };
  }
  return { lists, audit };
}

export function stubSaveEmailClassifier(
  add: Record<string, string[]>,
  remove: Record<string, string[]>,
  isAdmin: boolean,
): { ok: true; view: EmailClassifierView } | { ok: false; status: number; message: string } {
  if (!isAdmin) return { ok: false, status: 403, message: "Only an administrator can change the classifier lists" };
  for (const [name, entries] of Object.entries(add)) {
    if (!(name in DEFAULTS)) return { ok: false, status: 422, message: `${name} is not a list that can be edited` };
    if (entries.some((e) => e.trim() === "")) return { ok: false, status: 422, message: "An entry cannot be empty" };
  }
  added = Object.fromEntries(Object.entries(add).filter(([, v]) => v.length));
  removed = Object.fromEntries(Object.entries(remove).filter(([, v]) => v.length));
  audit = [...audit, { who: "stub", at: "now", summary: "Changed the classifier lists" }].slice(-10);
  return { ok: true, view: stubEmailClassifier() };
}
