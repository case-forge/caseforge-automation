
export interface EmailClassifierList {
  default: string[];
  added: string[];
  removed: string[];
  effective: string[];
}

export interface EmailClassifierView {
  lists: Record<string, EmailClassifierList>;
  audit: Array<Record<string, string>>;
}

export interface EmailClassifierBody {
  add: Record<string, string[]>;
  remove: Record<string, string[]>;
}

export const LIST_LABELS: Record<string, { label: string; feeds: string }> = {
  chambers_domains: { label: "Chambers (Counsel)", feeds: "Counsel" },
  court_domains: { label: "Courts", feeds: "Court" },
  referralpartner_addresses: { label: "referrer", feeds: "referrer" },
  process_server_domains: { label: "Process Servers", feeds: "Process Server" },
  process_server_keywords: { label: "Process Servers", feeds: "Process Server" },
  process_server_source_keywords: { label: "Process Servers", feeds: "Process Server" },
  newsletter_patterns: { label: "Newsletters", feeds: "Junk" },
  junk_subject_patterns: { label: "Junk subjects", feeds: "Junk" },
  bulk_sender_patterns: { label: "Bulk senders", feeds: "Junk" },
  work_experience_patterns: { label: "Work experience", feeds: "Junk" },
};

const PREFIX_LABELS: Array<[string, { label: string; feeds: string }]> = [
  ["drug_test_", { label: "Drug test labs", feeds: "Others (Drug Test Labs)" }],
  ["gp_", { label: "GPs", feeds: "Others (GP)" }],
  ["school_", { label: "Schools", feeds: "Others (School)" }],
  ["hospital_", { label: "Hospitals", feeds: "Others (Hospital)" }],
  ["contact_centre_", { label: "Contact centres", feeds: "Others (Contact Centre)" }],
  ["police_", { label: "Police", feeds: "Others (Police)" }],
];

export function labelFor(name: string): { label: string; feeds: string } {
  const exact = LIST_LABELS[name];
  if (exact) return exact;
  const hit = PREFIX_LABELS.find(([prefix]) => name.startsWith(prefix));
  return hit ? hit[1] : { label: name, feeds: "" };
}

export function kindOf(name: string): string {
  if (name.endsWith("_domains")) return "Sender domains";
  if (name.endsWith("_addresses")) return "Sender addresses";
  if (name.endsWith("_source_keywords")) return "Source keywords";
  if (name.endsWith("_keywords")) return "Keywords";
  if (name.endsWith("_patterns")) return "Patterns";
  return name.replace(/_/g, " ");
}

export function groupLists(view: EmailClassifierView): Array<{ label: string; feeds: string; names: string[] }> {
  const groups: Array<{ label: string; feeds: string; names: string[] }> = [];
  for (const name of Object.keys(view.lists)) {
    const { label, feeds } = labelFor(name);
    const group = groups.find((g) => g.label === label);
    if (group) group.names.push(name);
    else groups.push({ label, feeds, names: [name] });
  }
  return groups;
}

export function currentBody(view: EmailClassifierView): EmailClassifierBody {
  const body: EmailClassifierBody = { add: {}, remove: {} };
  for (const [name, list] of Object.entries(view.lists)) {
    if (list.added.length) body.add[name] = [...list.added];
    if (list.removed.length) body.remove[name] = [...list.removed];
  }
  return body;
}

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

export function addEntry(view: EmailClassifierView, name: string, entry: string): EmailClassifierBody {
  const body = currentBody(view);
  const text = entry.trim();
  const list = view.lists[name];
  if (!text || !list) return body;
  if (list.added.some((e) => same(e, text)) || list.default.some((e) => same(e, text))) return body;
  body.add[name] = [...(body.add[name] ?? []), text];
  return body;
}

export function removeAdded(view: EmailClassifierView, name: string, entry: string): EmailClassifierBody {
  const body = currentBody(view);
  const left = (body.add[name] ?? []).filter((e) => e !== entry);
  if (left.length) body.add[name] = left;
  else delete body.add[name];
  return body;
}

export function stopUsing(view: EmailClassifierView, name: string, entry: string): EmailClassifierBody {
  const body = currentBody(view);
  const list = view.lists[name];
  if (!list || !list.default.includes(entry) || (body.remove[name] ?? []).includes(entry)) return body;
  body.remove[name] = [...(body.remove[name] ?? []), entry];
  return body;
}

export function useAgain(view: EmailClassifierView, name: string, entry: string): EmailClassifierBody {
  const body = currentBody(view);
  const left = (body.remove[name] ?? []).filter((e) => e !== entry);
  if (left.length) body.remove[name] = left;
  else delete body.remove[name];
  return body;
}

export function auditLine(row: Record<string, string>): string {
  return [row.at, row.who, row.summary].filter((part) => typeof part === "string" && part !== "").join(" · ");
}

export type ClassifierLoad = { state: "ok"; view: EmailClassifierView } | { state: "error" };

export async function loadEmailClassifier(fetcher: typeof fetch = fetch): Promise<ClassifierLoad> {
  try {
    const res = await fetcher("/api/settings/email-classifier", { cache: "no-store" });
    if (!res.ok) return { state: "error" };
    const body = await res.json();
    return body && typeof body.lists === "object" && Array.isArray(body.audit) ? { state: "ok", view: body as EmailClassifierView } : { state: "error" };
  } catch {
    return { state: "error" };
  }
}

export type ClassifierSave = { ok: true; view: EmailClassifierView } | { ok: false; message: string };

export async function saveEmailClassifier(body: EmailClassifierBody, fetcher: typeof fetch = fetch): Promise<ClassifierSave> {
  const generic = "The change could not be saved.";
  try {
    const res = await fetcher("/api/settings/email-classifier", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const answer = await res.json().catch(() => null);
    if (res.ok && answer && typeof answer.lists === "object") return { ok: true, view: answer as EmailClassifierView };
    const message = typeof answer?.error === "string" ? answer.error : typeof answer?.detail === "string" ? answer.detail : generic;
    return { ok: false, message };
  } catch {
    return { ok: false, message: generic };
  }
}
