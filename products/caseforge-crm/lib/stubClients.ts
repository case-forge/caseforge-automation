
import type { ClientMatch, MatterChild, MatterParty } from "./types";

export const STUB_FIXED_IDS = ["9001", "9002", "9003"] as const;
export const STUB_MADE_FIRST_ID = 9100;

const MATTER_NAMES: Record<string, string> = {
  nmo_cao: "NMO-CAO",
  care_proceedings: "Care Proceedings",
  immigration: "Immigration",
};

export interface StubAddress {
  line1?: string;
  line2?: string;
  postcode?: string;
}

export interface StubPerson {
  name?: string;
  first?: string;
  last?: string;
  dob?: string;
  phone?: string;
  address?: StubAddress;
}

export interface StubDetails extends StubPerson {
  nino?: string;
  respondent?: StubPerson;
  children?: { name?: string; dob?: string; pr?: string; sex?: string }[];
  order?: string;
  court?: string;
  caseReference?: string;
  c8?: boolean;
}

interface Store {
  next: number;
  clients: Map<string, ClientMatch>;
  created: Map<string, number>;
  details: Map<string, StubDetails>;
}

const g = globalThis as unknown as { __stubMadeClients?: Store };

function store(): Store {
  if (!g.__stubMadeClients) g.__stubMadeClients = { next: STUB_MADE_FIRST_ID, clients: new Map(), created: new Map(), details: new Map() };
  return g.__stubMadeClients;
}

export function isStubFixedId(matterId: string): boolean {
  return (STUB_FIXED_IDS as readonly string[]).includes(matterId);
}

export function isStubMadeId(matterId: string): boolean {
  return store().clients.has(matterId);
}

export function isoFromUk(value: string | undefined): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value ?? "");
  return m ? `${m[3]}-${m[2]}-${m[1]}` : null;
}

export function stubMakeClient(input: {
  first: string;
  last: string;
  email: string;
  category: string;
  details?: StubDetails;
}): { matter_id: string; client: ClientMatch } {
  const s = store();
  const matter_id = String(s.next++);
  const name = `${input.first} ${input.last}`;
  const d = input.details ?? {};
  const home = d.address ?? {};
  const respondent = d.respondent;
  const client: ClientMatch = {
    matter_id,
    client_name: name,
    matter_name: d.order || MATTER_NAMES[input.category] || input.category,
    client_role: "Applicant",
    case_reference: d.caseReference ?? null,
    reference_summary: d.caseReference ? `court_family: ${d.caseReference}` : null,
    email_primary: input.email,
    phone_primary: d.phone ?? null,
    dob_iso: isoFromUk(d.dob),
    address_summary: home.line1 ? `Applicant: ${[home.line1, home.line2, home.postcode].filter(Boolean).join(", ")}` : null,
    party_summary: respondent?.name ? `Applicant: ${name} | Respondent: ${respondent.name}` : `Applicant: ${name}`,
    matched_party_summary: `Applicant: ${name}`,
    order_requested_text: d.order ?? null,
    legal_aid_tracker_status: null,
    closed_at: null,
    extra: {
      ...(d.nino ? { nino_canonical: d.nino } : {}),
      ...(d.c8 !== undefined ? { has_c8: d.c8 } : {}),
      ...(d.children?.length ? { children_summary: d.children.map((c) => `${c.name} (${c.dob})`).join("; ") } : {}),
      ...(d.court ? { court: d.court } : {}),
      ...(home.line1 ? { client_address_line1: home.line1 } : {}),
      ...(home.line2 ? { client_address_line2: home.line2 } : {}),
      ...(home.postcode ? { client_address_postcode: home.postcode } : {}),
    },
  };
  s.details.set(matter_id, d);
  s.clients.set(matter_id, client);
  s.created.set(matter_id, Date.now());
  return { matter_id, client };
}

export function stubMadeClients(query: string): ClientMatch[] {
  const q = query.trim().toLowerCase();
  return [...store().clients.values()].filter((c) => {
    if (!q || q === "*") return true;
    return [c.client_name, c.email_primary, String(c.matter_id)].some((v) => (v ?? "").toLowerCase().includes(q));
  });
}

export function stubMadeCreated(matterId: string): number {
  return store().created.get(matterId) ?? Date.now();
}

export function stubMadeClient(matterId: string): ClientMatch | undefined {
  return store().clients.get(matterId);
}

export function stubDeleteMadeClient(matterId: string): { deleted: true } | { error: string } {
  if (isStubFixedId(matterId)) return { error: "The three fixed stub clients cannot be deleted." };
  if (!store().clients.delete(matterId)) return { error: "No such stub client." };
  store().created.delete(matterId);
  store().details.delete(matterId);
  return { deleted: true };
}

export function resetStubMadeClients(): void {
  g.__stubMadeClients = { next: STUB_MADE_FIRST_ID, clients: new Map(), created: new Map(), details: new Map() };
}

function party(role: string, matterId: string, id: string, p: StubPerson, email: string): MatterParty {
  const a = p.address ?? {};
  return {
    party_id: id,
    matter_id: matterId,
    role,
    display_name: p.name ?? "",
    name_first: p.first ?? "",
    name_middle: "",
    name_last: p.last ?? "",
    aka_name: "",
    dob_iso: isoFromUk(p.dob) ?? "",
    address_text: [a.line1, a.line2, a.postcode].filter(Boolean).join(", "),
    address_line1: a.line1 ?? "",
    address_line2: a.line2 ?? "",
    address_line3: "",
    address_line4: "",
    address_postcode: a.postcode ?? "",
    work_address_line1: "",
    work_address_line2: "",
    work_address_line3: "",
    work_address_line4: "",
    work_address_postcode: "",
    phone_primary: p.phone ?? "",
    email_primary: email,
  };
}

export function stubMadeParties(matterId: string): MatterParty[] | undefined {
  const d = store().details.get(matterId);
  if (!d) return undefined;
  return d.respondent?.name ? [party("Respondent", matterId, `${matterId}-respondent`, d.respondent, "")] : [];
}

export function stubMadeChildren(matterId: string): MatterChild[] | undefined {
  const d = store().details.get(matterId);
  if (!d) return undefined;
  return (d.children ?? []).map((c, index) => {
    const name = c.name ?? "";
    const at = name.lastIndexOf(" ");
    return {
      child_id: `${matterId}-child-${index + 1}`,
      matter_id: matterId,
      child_name: name,
      name_first: at < 0 ? name : name.slice(0, at),
      name_middle: "",
      name_last: at < 0 ? "" : name.slice(at + 1),
      dob_iso: isoFromUk(c.dob) ?? "",
      gender: c.sex ?? "",
      parental_responsibility: c.pr ?? "",
      lives_with: "",
      notes: "",
    };
  });
}
