
import { STUB_BANK_HOLIDAYS } from "./stubBankHolidays";
import {
  addDaysIso,
  compareHearings,
  isValidIsoDate,
  isWeekend,
  londonTodayIso,
  normaliseTime,
  weekdayOf,
} from "./hearings";
import type {
  Hearing,
  HearingEdits,
  HearingHistoryEvent,
  HearingHistoryResponse,
  HearingLead,
  HearingLeadResponse,
  HearingLeadsResponse,
  HearingsResponse,
  HearingsReviewResponse,
  HearingStatus,
} from "./hearings";

const EDITABLE_KEYS = new Set([
  "case_ref",
  "matter_id",
  "applicant",
  "respondent",
  "counsel",
  "chambers",
  "hearing_date",
  "hearing_time",
  "duration_minutes",
  "hearing_type",
  "order_types",
  "is_final",
  "court",
  "mode",
  "join_url",
  "notes",
]);

let store: Hearing[] | null = null;

let withCalendarFixtures = false;
let history: HearingHistoryEvent[] = [];
let hearingSeq = 0;
let eventSeq = 0;

function nowUtc(): string {
  return new Date().toISOString();
}

function record(hearingId: number, actor: string, action: string, before: unknown, after: unknown): void {
  eventSeq += 1;
  history.push({
    event_id: eventSeq,
    hearing_id: hearingId,
    at: nowUtc(),
    actor,
    action,
    before,
    after,
    source_message_id: "",
  });
}

function base(over: Partial<Hearing> & Pick<Hearing, "hearing_date">): Hearing {
  hearingSeq += 1;
  const stamp = nowUtc();
  return {
    hearing_id: hearingSeq,
    matter_id: 100 + hearingSeq,
    client_name: null,
    case_ref: "",
    hearing_time: "10:00",
    duration_minutes: 60,
    duration_stated: true,
    hearing_type: "",
    order_types: "",
    is_final: false,
    court: "",
    mode: "",
    join_url: "",
    applicant: "",
    respondent: "",
    counsel: "",
    chambers: "",
    bundle_done: null,
    status: "scheduled",
    review_state: "ok",
    review_reason: "",
    confidence: 0.95,
    source_kind: "email",
    source_subject: "",
    source_received_utc: stamp,
    source_web_link: "",
    notes: "",
    created_utc: stamp,
    updated_utc: stamp,
    updated_by: "calendar-finder",
    ...over,
  };
}

function seed(): Hearing[] {
  const today = londonTodayIso();
  const d = (n: number) => addDaysIso(today, n);

  let saturday = addDaysIso(today, 1);
  while (weekdayOf(saturday) !== 6) saturday = addDaysIso(saturday, 1);

  return [
    base({
      hearing_date: d(0), hearing_time: "10:00", client_name: "Alice Rivertest", case_ref: "ZZ26F11111",
      applicant: "Alice Rivertest", respondent: "Ben Rivertest", order_types: "NMO", hearing_type: "Return hearing",
      court: "Central Family Court", mode: "in person", source_subject: "Notice of hearing ZZ26F11111",
      counsel: "A. Barristertest", bundle_done: true,
    }),
    base({
      hearing_date: d(1), hearing_time: "14:00", duration_minutes: 90, client_name: "Priya Meadowtest", case_ref: "ZZ26P22222",
      applicant: "Priya Meadowtest", respondent: "Rohan Meadowtest", order_types: "CAO", hearing_type: "FHDRA",
      court: "Leeds Combined Court Centre", mode: "in person", source_subject: "FHDRA listing - ZZ26P22222",
      bundle_done: false, bundle_why: "no bundle step logged and no bundle plus sent email found in the folders",
    }),
    base({
      hearing_date: d(2), hearing_time: "10:30", client_name: "Chloe Fieldtest", case_ref: "ZZ26F33333",
      applicant: "Chloe Fieldtest", respondent: "Dan Brooktest", order_types: "PSO", hearing_type: "Directions",
      court: "Remote hearing", mode: "video", join_url: "https://example.invalid/join/stub-303",
      source_subject: "Remote hearing details ZZ26F33333",
      counsel: "B. Counseltest", bundle_done: false,
    }),
    base({
      hearing_date: d(3), hearing_time: "10:00", duration_minutes: 240, client_name: "Grace Willowtest", case_ref: "ZZ26F44444",
      applicant: "Grace Willowtest", respondent: "Sam Elmtest", order_types: "NMO/OO", hearing_type: "Final hearing",
      is_final: true, court: "Wolverhampton Family Court", mode: "in person", source_subject: "Final hearing listed - ZZ26F44444",
    }),
    base({
      hearing_date: d(4), hearing_time: "10:13", client_name: "Helen Oaktest", case_ref: "ZZ26F55555",
      applicant: "Helen Oaktest", respondent: "Tom Oaktest", hearing_type: "Hearing", court: "Chambers",
      review_state: "needs_review", confidence: 0.55,
      review_reason: "10:13 is not a normal listing time; it may be the email's own timestamp. Check the notice.",
      source_subject: "RE: Oaktest - hearing",
    }),
    base({
      hearing_date: saturday, hearing_time: "09:00", client_name: "Imogen Ferntest", case_ref: "ZZ26F66666",
      applicant: "Imogen Ferntest", respondent: "Luke Ferntest", order_types: "NMO", hearing_type: "Hearing",
      court: "Worcester Family Court", review_state: "needs_review", confidence: 0.6,
      review_reason: "This date is a Saturday. Courts do not sit at weekends, so the date is probably wrong.",
      source_subject: "Listing - ZZ26F66666",
    }),
    base({
      hearing_date: d(6), hearing_time: "11:00", client_name: "Jasmine Mosstest", case_ref: "ZZ26F77777",
      applicant: "Jasmine Mosstest", respondent: "Kai Mosstest", order_types: "OO", hearing_type: "Directions",
      court: "Nottingham County Court", mode: "in person", status: "vacated", source_subject: "Hearing vacated - ZZ26F77777",
    }),
    base({
      hearing_date: d(7), hearing_time: "15:00", client_name: "Kavita Laketest", case_ref: "ZZ26P88888",
      applicant: "Kavita Laketest", respondent: "Anil Laketest", hearing_type: "Directions hearing",
      court: "Coventry Combined Court Centre", mode: "hybrid", source_subject: "Hearing notice ZZ26P88888",
    }),
    base({
      hearing_date: d(8), hearing_time: "12:00", client_name: "Laura Pinetest", case_ref: "ZZ26F99999",
      applicant: "Laura Pinetest", respondent: "Mark Pinetest", order_types: "CAO", hearing_type: "Mention",
      court: "Milton Keynes Family Court", status: "cancelled", source_subject: "Cancelled - ZZ26F99999",
    }),
    base({
      hearing_date: d(9), hearing_time: null, client_name: "Megan Stonetest", case_ref: "ZZ26F00000",
      applicant: "Megan Stonetest", respondent: "Ned Stonetest", order_types: "NMO", hearing_type: "Hearing",
      court: "Croydon Family Court", review_state: "needs_review", confidence: 0.5,
      duration_stated: false,
      review_reason: "The notice gives a date but no time.", source_subject: "Listing Croydon ZZ26F00000",
    }),
    base({
      hearing_date: d(10), hearing_time: "10:00", duration_minutes: 180, client_name: "Nadia Heathtest", case_ref: "ZZ26P11111",
      applicant: "Nadia Heathtest", respondent: "Omar Heathtest", order_types: "CAO", hearing_type: "Final hearing",
      is_final: true, court: "East London Family Court", mode: "in person", source_subject: "Final hearing ZZ26P11111",
    }),

    base({
      hearing_date: d(12), hearing_time: "11:00", matter_id: null, client_name: null, case_ref: "ZZ25F22222",
      applicant: "Rosa Cedartest", respondent: "Marco Cedartest", hearing_type: "Directions", court: "Slough Family Court",
      source_subject: "Listing - Cedartest v Cedartest - ZZ25F22222",
    }),
    base({
      hearing_date: d(15), hearing_time: "14:00", matter_id: null, client_name: null, case_ref: "ZZ25F22222",
      applicant: "Rosa Cedartest", respondent: "Marco Cedartest", hearing_type: "Return hearing", court: "Slough Family Court",
      source_subject: "Relisting - ZZ25F22222",
    }),
    base({
      hearing_date: d(5), hearing_time: "10:30", matter_id: null, client_name: null, case_ref: "ZZ26P33333",
      hearing_type: "FHDRA", court: "Reading County Court", source_subject: "Notice of hearing ZZ26P33333",
    }),
    base({
      hearing_date: d(13), hearing_time: "10:00", client_name: "Olivia Valetest", case_ref: "ZZ25F33333",
      applicant: "Olivia Valetest", respondent: "Paul Valetest", order_types: "NMO", hearing_type: "Return hearing",
      court: "Barnet Family Court", source_subject: "Return date ZZ25F33333",
    }),
    base({
      hearing_date: d(13), hearing_time: "14:30", client_name: "Quinn Marshtest", case_ref: "ZZ25F44444",
      applicant: "Quinn Marshtest", respondent: "Rita Marshtest", order_types: "PSO", hearing_type: "Directions",
      court: "Barnet Family Court", source_subject: "Directions ZZ25F44444",
    }),
    base({
      hearing_date: d(20), hearing_time: "10:30", client_name: "Sana Glentest", case_ref: "ZZ26P55555",
      applicant: "Sana Glentest", respondent: "Umar Glentest", order_types: "CAO", hearing_type: "FHDRA",
      court: "Manchester Civil Justice Centre", mode: "in person", source_subject: "FHDRA ZZ26P55555",
    }),
    base({
      hearing_date: d(-3), hearing_time: "11:00", client_name: "Vera Birchtest", case_ref: "ZZ25F66666",
      applicant: "Vera Birchtest", respondent: "Will Birchtest", order_types: "NMO", hearing_type: "Return hearing",
      court: "Central Family Court", source_subject: "Return date ZZ25F66666",
    }),
    base({
      hearing_date: d(-10), hearing_time: "10:00", source_kind: "outlook_import", client_name: "Xenia Reedtest", case_ref: "ZZ25F77777",
      applicant: "Xenia Reedtest", respondent: "Yusuf Reedtest", order_types: "OO", hearing_type: "Directions",
      court: "Leeds Combined Court Centre", source_subject: "Imported from the old calendar",
    }),
  ];
}

function seedStubClientHearings(): Hearing[] {
  const today = londonTodayIso();
  const d = (n: number) => addDaysIso(today, n);
  const mine = (over: Partial<Hearing> & Pick<Hearing, "hearing_date">) =>
    base({
      matter_id: 9001, client_name: "Stub Testperson", case_ref: "ZZ21D00000", applicant: "Stub Testperson", respondent: "Stub Otherperson",
      court: "Central Family Court", mode: "in person", ...over,
    });
  const past = (days: number, type: string, time: string) =>
    mine({ hearing_date: d(-days), hearing_time: time, order_types: "NMO", hearing_type: type, source_subject: `${type} - ZZ21D00000` });
  return [
    mine({ hearing_date: d(4), hearing_time: "10:00", order_types: "NMO", hearing_type: "Return hearing", source_subject: "Return date ZZ21D00000", bundle_done: false, bundle_why: "no bundle step logged and no bundle plus sent email found in the folders" }),
    mine({ hearing_date: d(40), hearing_time: "10:30", duration_minutes: 180, order_types: "NMO/OO", hearing_type: "Final hearing", is_final: true, source_subject: "Final hearing ZZ21D00000" }),
    mine({ hearing_date: d(18), hearing_time: "14:00", order_types: "OO", hearing_type: "Directions", status: "vacated", source_subject: "Vacated - ZZ21D00000" }),
    mine({
      hearing_date: d(7), hearing_time: "10:13", hearing_type: "Hearing", review_state: "needs_review", confidence: 0.55,
      review_reason: "10:13 is not a normal listing time. This is a stub entry.", source_subject: "Stub hearing to check",
    }),
    past(12, "Directions", "11:00"),
    past(35, "Mention", "09:30"),
    past(60, "Directions", "10:00"),
    past(95, "Return hearing", "14:30"),
    past(130, "FHDRA", "10:00"),
    past(210, "Directions", "12:00"),
    past(320, "First hearing", "10:00"),
  ];
}

function ensure(): Hearing[] {
  if (!store) {
    store = [...(withCalendarFixtures ? seed() : []), ...seedStubClientHearings()];
    for (const h of store) record(h.hearing_id, "calendar-finder", "created", null, { hearing_date: h.hearing_date, hearing_time: h.hearing_time });
  }
  return store;
}

export function stubUseCalendarFixtures(): void {
  withCalendarFixtures = true;
  stubResetHearings();
}

export function stubResetHearings(): void {
  store = null;
  history = [];
  leads = null;
  hearingSeq = 0;
  eventSeq = 0;
}

function needsReviewCount(list: Hearing[]): number {
  return list.filter((h) => h.review_state === "needs_review").length;
}

let leads: HearingLead[] | null = null;

function ensureLeads(): HearingLead[] {
  if (!leads) {
    const today = londonTodayIso();
    const at = (daysAgo: number, time: string) => `${addDaysIso(today, -daysAgo)}T${time}Z`;
    const lead = (id: number, subject: string, daysAgo: number, reason: string, link: string): HearingLead => ({
      lead_id: id,
      source_subject: subject,
      source_received_utc: at(daysAgo, "09:12:00"),
      source_web_link: link,
      reason,
      state: "open",
      created_utc: at(daysAgo, "09:14:00"),
    });
    leads = [
      lead(1, "STUB: ZZ21D00000 - Notice of hearing - Stub Testperson v Stub Otherperson", 2,
        "The email mentions a hearing but gives no date I could read.", "https://outlook.example.invalid/owa/?ItemID=stub-lead-1"),
      lead(2, "STUB: listing notification, stub court (attachment: stub_scan.pdf)", 1,
        "The notice is a scanned attachment that could not be read.", "https://outlook.example.invalid/owa/?ItemID=stub-lead-2"),
      lead(3, "STUB: Directions hearing moved?", 0,
        "The email talks about moving a hearing but does not say to when.", ""),
    ];
  }
  return leads;
}

function openLeadsCount(): number {
  return ensureLeads().filter((l) => l.state === "open").length;
}

export function stubListLeads(): HearingLeadsResponse {
  return { leads: ensureLeads().filter((l) => l.state === "open").map((l) => ({ ...l })) };
}

export function stubResolveLead(id: number, action: string, editedBy: string): HearingLeadResponse {
  if (action !== "done" && action !== "dismissed") throw new Error("action must be 'done' or 'dismissed'");
  if (!editedBy.trim()) throw new Error("actor (your name) is required");
  const found = ensureLeads().find((l) => l.lead_id === id);
  if (!found) throw new Error(`lead ${id} not found`);
  found.state = action;
  return { lead: { ...found } };
}

export function stubListHearings(from: string, to: string, matterId?: string): HearingsResponse {
  const list = ensure();
  const rows = list
    .filter((h) => h.review_state !== "dismissed")
    .filter((h) => h.hearing_date >= from && h.hearing_date <= to)
    .filter((h) => (matterId ? String(h.matter_id ?? "") === matterId : true))
    .sort(compareHearings);
  const bankHolidays = Object.fromEntries(Object.entries(STUB_BANK_HOLIDAYS).filter(([d]) => d >= from && d <= to));
  return { hearings: rows, needs_review_count: needsReviewCount(list), open_leads_count: openLeadsCount(), bank_holidays: bankHolidays };
}

export function stubReviewHearings(): HearingsReviewResponse {
  return {
    hearings: ensure().filter((h) => h.review_state === "needs_review").sort(compareHearings),
    open_leads_count: openLeadsCount(),
  };
}

function checkEdits(edits: HearingEdits): void {
  for (const key of Object.keys(edits)) {
    if (!EDITABLE_KEYS.has(key)) throw new Error(`unknown field ${key}`);
  }
  if (edits.hearing_date !== undefined && !isValidIsoDate(edits.hearing_date)) throw new Error("invalid hearing_date");
  if (edits.hearing_time !== undefined && edits.hearing_time !== null && normaliseTime(edits.hearing_time) === null) {
    throw new Error("invalid hearing_time");
  }
}

function findOrThrow(id: number): Hearing {
  const found = ensure().find((h) => h.hearing_id === id);
  if (!found) throw new Error("hearing not found");
  return found;
}

function applyEdits(h: Hearing, edits: HearingEdits, actor: string): { before: Record<string, unknown>; after: Record<string, unknown> } {
  const before: Record<string, unknown> = {};
  const after: Record<string, unknown> = {};

  if (edits.duration_minutes !== undefined) {
    const stated = edits.duration_minutes !== null;
    const minutes = stated ? (edits.duration_minutes as number) : 60;
    if (h.duration_minutes !== minutes || h.duration_stated !== stated) {
      before.duration_minutes = h.duration_stated === false ? null : h.duration_minutes;
      after.duration_minutes = edits.duration_minutes;
      h.duration_minutes = minutes;
      h.duration_stated = stated;
    }
  }
  for (const [key, value] of Object.entries(edits)) {
    if (key === "duration_minutes") continue;
    const current = (h as unknown as Record<string, unknown>)[key];
    if (current === value) continue;
    before[key] = current;
    after[key] = value;
    (h as unknown as Record<string, unknown>)[key] = value;
  }
  if (Object.keys(after).length) {
    h.updated_utc = nowUtc();
    h.updated_by = actor;
  }
  return { before, after };
}

export function stubCreateHearing(payload: HearingEdits, editedBy: string): Hearing {
  checkEdits(payload);
  if (!payload.case_ref || !payload.case_ref.trim()) throw new Error("case_ref is required");
  if (!payload.hearing_date) throw new Error("hearing_date is required");
  const list = ensure();
  const h = base({ hearing_date: payload.hearing_date, source_kind: "manual", source_subject: "", confidence: null });
  Object.assign(h, { hearing_time: null, updated_by: editedBy });
  applyEdits(h, payload, editedBy);
  h.updated_by = editedBy;
  h.matter_id = payload.matter_id ?? null;
  list.push(h);
  record(h.hearing_id, editedBy, "created", null, { hearing_date: h.hearing_date, hearing_time: h.hearing_time });
  return h;
}

export function stubUpdateHearing(id: number, edits: HearingEdits, editedBy: string): Hearing {
  checkEdits(edits);
  const h = findOrThrow(id);
  const { before, after } = applyEdits(h, edits, editedBy);
  if (Object.keys(after).length) record(id, editedBy, "updated", before, after);
  return h;
}

export function stubSetHearingStatus(id: number, status: HearingStatus, editedBy: string): Hearing {
  if (!["scheduled", "vacated", "cancelled"].includes(status)) throw new Error("invalid status");
  const h = findOrThrow(id);
  const before = h.status;
  if (before !== status) {
    h.status = status;
    h.updated_utc = nowUtc();
    h.updated_by = editedBy;
    record(id, editedBy, "status", { status: before }, { status });
  }
  return h;
}

export function stubResolveHearingReview(id: number, action: "confirm" | "dismiss", edits: HearingEdits | undefined, editedBy: string): Hearing {
  if (action !== "confirm" && action !== "dismiss") throw new Error("invalid action");
  const h = findOrThrow(id);
  if (edits && Object.keys(edits).length) {
    checkEdits(edits);
    const { before, after } = applyEdits(h, edits, editedBy);
    if (Object.keys(after).length) record(id, editedBy, "updated", before, after);
  }
  const before = h.review_state;
  h.review_state = action === "confirm" ? "ok" : "dismissed";
  h.updated_utc = nowUtc();
  h.updated_by = editedBy;
  record(id, editedBy, action === "confirm" ? "review_confirmed" : "review_dismissed", { review_state: before }, { review_state: h.review_state });
  return h;
}

export function stubHearingHistory(id: number): HearingHistoryResponse {
  ensure();
  return { events: history.filter((e) => e.hearing_id === id).sort((a, b) => b.event_id - a.event_id) };
}

const STUB_CONFLICT_MATTER = 999;

const STUB_SEARCH_CLIENTS: Record<number, string> = { 9001: "Stub Testperson", 9002: "Second Stubperson", 9003: "Third Stubperson" };

function stubClientName(matterId: number): string {
  if (STUB_SEARCH_CLIENTS[matterId]) return STUB_SEARCH_CLIENTS[matterId];
  return ensure().find((h) => h.matter_id === matterId && h.client_name)?.client_name ?? `Client ${matterId}`;
}

export function stubLinkHearing(id: number, matterId: number, editedBy: string): { hearing: Hearing; reference: string } {
  const h = findOrThrow(id);
  if (!Number.isInteger(matterId) || matterId <= 0) throw new Error("invalid matter_id");
  const name = stubClientName(matterId);
  const same = ensure().filter((x) => x.matter_id === null && x.case_ref === h.case_ref);
  for (const row of same.length ? same : [h]) {
    const before = { matter_id: row.matter_id };
    row.matter_id = matterId;
    row.client_name = name;
    row.updated_utc = nowUtc();
    row.updated_by = editedBy;
    record(row.hearing_id, editedBy, "linked", before, { matter_id: matterId });
  }
  const reference = matterId === STUB_CONFLICT_MATTER ? "conflict" : h.case_ref ? "recorded" : "skipped";
  return { hearing: h, reference };
}

export function stubUnlinkHearing(id: number, editedBy: string): Hearing {
  const h = findOrThrow(id);
  const before = { matter_id: h.matter_id };
  h.matter_id = null;
  h.client_name = null;
  h.updated_utc = nowUtc();
  h.updated_by = editedBy;
  record(id, editedBy, "unlinked", before, { matter_id: null });
  return h;
}

export function stubSuggestMatters(id: number): { suggestions: { matter_id: number; client_name: string; matched_on: string; exact: boolean }[] } {
  const h = findOrThrow(id);
  if (h.matter_id !== null) return { suggestions: [] };
  const surname = (h.applicant || h.respondent).split(/\s+/).pop()?.toLowerCase() ?? "";
  if (!surname) return { suggestions: [] };
  const seen = new Map<number, { matter_id: number; client_name: string; matched_on: string; exact: boolean }>();
  for (const other of ensure()) {
    if (other.matter_id === null || !other.client_name) continue;
    const otherSurname = other.client_name.split(/\s+/).pop()?.toLowerCase() ?? "";
    if (otherSurname === surname) {
      seen.set(other.matter_id, { matter_id: other.matter_id, client_name: other.client_name, matched_on: `surname ${surname} in the email`, exact: false });
    }
  }
  if (surname === "cedartest") {
    seen.set(9001, { matter_id: 9001, client_name: "Stub Testperson", matched_on: "name similar to Rosa Cedartest", exact: false });
  }
  return { suggestions: [...seen.values()].slice(0, 5) };
}

function icsEscape(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

function icsLocal(date: string, time: string | null): string {
  const t = normaliseTime(time);
  return t ? `${date.replace(/-/g, "")}T${t.replace(":", "")}00` : date.replace(/-/g, "");
}

export function stubHearingsIcs(from: string, to: string): string {
  const rows = stubListHearings(from, to).hearings.filter((h) => h.status === "scheduled");
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CaseForge//CRM stub//EN", "CALSCALE:GREGORIAN"];
  for (const h of rows) {
    const timed = normaliseTime(h.hearing_time) !== null;
    lines.push("BEGIN:VEVENT", `UID:stub-hearing-${h.hearing_id}@client-viewer.invalid`, `DTSTAMP:${nowUtc().replace(/[-:]/g, "").slice(0, 15)}Z`);
    lines.push(timed ? `DTSTART;TZID=Europe/London:${icsLocal(h.hearing_date, h.hearing_time)}` : `DTSTART;VALUE=DATE:${icsLocal(h.hearing_date, null)}`);
    lines.push(`SUMMARY:${icsEscape(`${h.order_types || h.hearing_type || "Hearing"} ${h.case_ref}`.trim())}`, `LOCATION:${icsEscape(h.court)}`, "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return `${lines.join("\r\n")}\r\n`;
}

export function stubSeedHasWeekendRow(): boolean {
  return ensure().some((h) => isWeekend(h.hearing_date));
}

const STUB_VACATE_KINDS = ["moved", "no_longer_acting", "court_vacated", "other"];

export function stubVacateHearing(
  id: number,
  kind: string,
  reason: string,
  replacement: { hearing_date?: string; hearing_time?: string } | undefined,
  editedBy: string,
): { hearing: Hearing; replacement: Hearing | null } {
  if (!STUB_VACATE_KINDS.includes(kind)) throw new Error("invalid kind");
  const old = findOrThrow(id);
  if (old.status !== "scheduled") throw new Error("this hearing is already vacated");
  let created: Hearing | null = null;
  if (kind === "moved") {
    if (!replacement?.hearing_date) throw new Error("a moved hearing needs its new date");
    if (replacement.hearing_date === old.hearing_date && (replacement.hearing_time ?? null) === old.hearing_time) {
      throw new Error("the new date and time are the same as this hearing's; nothing has moved");
    }
    created = base({
      hearing_date: replacement.hearing_date,
      hearing_time: replacement.hearing_time ?? null,
      matter_id: old.matter_id,
      client_name: old.client_name,
      case_ref: old.case_ref,
      court: old.court,
      hearing_type: old.hearing_type,
      order_types: old.order_types,
      counsel: old.counsel,
      chambers: old.chambers,
      applicant: old.applicant,
      respondent: old.respondent,
      source_kind: "manual",
      notes: reason ? `Moved from ${old.hearing_date}. Reason: ${reason}` : `Moved from ${old.hearing_date}.`,
    });
    created.updated_by = editedBy;
    created.replaces_hearing_id = old.hearing_id;
    ensure().push(created);
    record(created.hearing_id, editedBy, "created", null, { moved_from: old.hearing_id });
  }
  old.status = "vacated";
  old.vacate_kind = kind as Hearing["vacate_kind"];
  old.request_state = "";
  old.updated_by = editedBy;
  old.updated_utc = nowUtc();
  if (created) old.replaced_by = { hearing_id: created.hearing_id, hearing_date: created.hearing_date, hearing_time: created.hearing_time };
  record(id, editedBy, "status", { status: "scheduled" }, { status: "vacated", vacate_kind: kind });
  return { hearing: old, replacement: created };
}

export function stubRequestOptions(id: number) {
  const h = findOrThrow(id);
  const date = h.hearing_date;
  const form = /CAO|PSO|SIO/.test(h.order_types) ? "C2" : /NMO|OO/.test(h.order_types) ? "FP2" : "";
  return {
    hearing_id: id,
    form,
    form_known: form !== "",
    forms: ["FP2", "C2"],
    vacation_reasons: [
      { id: "no_counsel", label: "No counsel available", text: `Counsel is not available for the hearing listed for ${date}.` },
      { id: "relist_request", label: "Relist at the earliest date counsel is available", text: "Please relist at the earliest date counsel is available." },
    ],
    hybrid_reasons: [
      { id: "remote_applicant_and_representative", label: "Remote attendance for the Applicant and their representative", text: `The Applicant applies for the hearing listed for ${date} to be conducted remotely.` },
      { id: "distance_travel", label: "Distance and travel", text: "Attending in person would be disproportionately difficult." },
    ],
  };
}

export function stubRequestFromCourt(id: number, kind: string, reasons: string[], form: string, editedBy: string) {
  const h = findOrThrow(id);
  if (h.status !== "scheduled") throw new Error("only a live hearing can have a request made about it");
  if (kind !== "vacation" && kind !== "hybrid") throw new Error("invalid kind");
  if (reasons.filter((r) => r.trim()).length === 0) throw new Error("choose or write at least one reason");
  h.request_state = kind === "vacation" ? "vacation_requested" : "hybrid_requested";
  h.request_reason = reasons.join("\n");
  h.updated_by = editedBy;
  h.updated_utc = nowUtc();
  record(id, editedBy, "request", { request_state: "" }, { request_state: h.request_state });
  const chosen = form || stubRequestOptions(id).form;
  return { hearing: h, form: chosen, draft: { web_link: "" }, summary: `${chosen} application is in Outlook Drafts, marked AI DRAFTED. Nothing was sent.` };
}

export function stubCourtDecision(id: number, agreed: boolean, editedBy: string): Hearing {
  const h = findOrThrow(id);
  const state = h.request_state ?? "";
  if (!state) throw new Error("no request is waiting for the court's answer on this hearing");
  if (agreed && state === "vacation_requested") {
    h.status = "vacated";
    h.vacate_kind = "court_vacated";
  } else if (agreed) {
    h.mode = "hybrid";
  }
  h.request_state = "";
  h.request_reason = "";
  h.updated_by = editedBy;
  h.updated_utc = nowUtc();
  record(id, editedBy, "request", { request_state: state }, { agreed });
  return h;
}
