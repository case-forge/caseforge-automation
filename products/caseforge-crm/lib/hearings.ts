
export type HearingStatus = "scheduled" | "vacated" | "cancelled";

export type VacateKind = "" | "moved" | "no_longer_acting" | "court_vacated" | "other" | "cancelled";

export type RequestState = "" | "vacation_requested" | "hybrid_requested";
export type ReviewState = "ok" | "needs_review" | "dismissed";
export type HearingMode = "" | "in person" | "video" | "telephone" | "hybrid";

export type HearingNotice = "" | "on notice" | "without notice";
export type HearingSourceKind = "email" | "ics" | "invite" | "manual" | "outlook_import";

export interface Hearing {
  hearing_id: number;
  matter_id: number | null;
  client_name: string | null;
  case_ref: string;
  hearing_date: string;
  hearing_time: string | null;
  duration_minutes: number;

  duration_stated?: boolean;
  hearing_type: string;
  order_types: string;
  is_final: boolean;
  court: string;
  mode: HearingMode;

  notice?: HearingNotice;

  not_before_date?: string;
  join_url: string;
  applicant: string;
  respondent: string;

  counsel?: string;

  chambers?: string;

  counsel_booked?: boolean;

  human_edited?: boolean;

  bundle_done?: boolean | null;
  bundle_why?: string;

  overridden?: Record<string, { reason?: string; by?: string }> | null;
  status: HearingStatus;

  vacate_kind?: VacateKind;
  request_state?: RequestState;

  request_reason?: string;

  replaced_by?: { hearing_id: number; hearing_date: string; hearing_time: string | null } | null;

  replaces_hearing_id?: number | null;
  review_state: ReviewState;
  review_reason: string;
  confidence: number | null;
  source_kind: HearingSourceKind;
  source_subject: string;
  source_received_utc: string;
  source_web_link: string;
  notes: string;
  created_utc: string;
  updated_utc: string;
  updated_by: string;

  confirmed_by?: string;
}

export interface HearingsResponse {
  hearings: Hearing[];
  needs_review_count: number;

  open_leads_count?: number;

  bank_holidays?: Record<string, string>;
}

export interface HearingLead {
  lead_id: number;
  source_subject: string;
  source_received_utc: string;
  source_web_link: string;
  reason: string;
  state: string;
  created_utc: string;
}

export interface HearingLeadsResponse {
  leads: HearingLead[];
}

export interface HearingLeadResponse {
  lead: HearingLead;
}

export function toCheckCount(needsReview: number, openLeads: number | undefined): number {
  return Math.max(0, needsReview || 0) + Math.max(0, openLeads || 0);
}

export function safeHttpsUrl(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  if (!text.startsWith("https://")) return "";
  try {
    const url = new URL(text);
    return url.protocol === "https:" ? url.toString() : "";
  } catch {
    return "";
  }
}

export function truncateText(value: string, max = 90): string {
  const text = value.trim();
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

export function leadNotes(lead: Pick<HearingLead, "source_subject">): string {
  const subject = lead.source_subject.trim();
  return subject ? `From email: ${truncateText(subject, 200)}` : "";
}

export interface HearingsReviewResponse {
  hearings: Hearing[];
  open_leads_count?: number;
}

export interface HearingResponse {
  hearing: Hearing;
}

export interface HearingHistoryEvent {
  event_id: number;
  hearing_id: number;
  at: string;
  actor: string;
  action: string;
  before: unknown;
  after: unknown;
  source_message_id: string;
}

export interface HearingHistoryResponse {
  events: HearingHistoryEvent[];
}

export type LinkReference = "recorded" | "exists" | "conflict" | "skipped" | "failed";

export interface HearingLinkResponse {
  hearing: Hearing;
  reference: LinkReference | string;
}

export interface MatterSuggestion {
  matter_id: number;
  client_name: string;
  matched_on: string;
  exact: boolean;
}

export interface MatterSuggestionsResponse {
  suggestions: MatterSuggestion[];
}

export const HEARING_MODES: { value: HearingMode; label: string }[] = [
  { value: "", label: "Not stated" },
  { value: "in person", label: "In person" },
  { value: "video", label: "Video" },
  { value: "telephone", label: "Telephone" },
  { value: "hybrid", label: "Hybrid" },
];

export const HEARING_NOTICES: { value: HearingNotice; label: string }[] = [
  { value: "", label: "Not stated" },
  { value: "on notice", label: "On notice" },
  { value: "without notice", label: "Without notice" },
];

const SOURCE_LABELS: Record<HearingSourceKind, string> = {
  email: "Email",
  ics: "Calendar file",
  invite: "Meeting invite",
  manual: "Entered by hand",
  outlook_import: "Imported from Outlook",
};

export function sourceKindLabel(kind: string): string {
  return SOURCE_LABELS[kind as HearingSourceKind] ?? kind;
}

export function statusLabel(status: HearingStatus): string {
  return status === "scheduled" ? "Scheduled" : "Vacated";
}

export function confirmedByWords(h: Pick<Hearing, "review_state" | "human_edited" | "confirmed_by">): string {
  if (h.review_state !== "ok" || !h.human_edited) return "";
  return `, confirmed by ${(h.confirmed_by || "").trim() || "a team member"}`;
}

export function isVacated(h: Pick<Hearing, "status">): boolean {
  return h.status === "vacated" || h.status === "cancelled";
}

export function requestLabel(h: Pick<Hearing, "request_state" | "status">): string {
  if (h.status !== "scheduled") return "";
  if (h.request_state === "vacation_requested") return "Vacation requested";
  if (h.request_state === "hybrid_requested") return "Hybrid requested";
  return "";
}

export function vacatedSummary(h: Pick<Hearing, "status" | "vacate_kind" | "replaced_by">): string {
  if (!isVacated(h)) return "";
  const moved = h.replaced_by ? `Moved to ${formatDateShort(h.replaced_by.hearing_date)}${h.replaced_by.hearing_time ? `, ${formatTime12(h.replaced_by.hearing_time)}` : ""}` : "";
  if (moved) return moved;
  switch (h.vacate_kind) {
    case "moved":
      return "Moved by the court";
    case "no_longer_acting":
      return "Vacated: no longer acting for the client";
    case "court_vacated":
      return "Vacated: the court agreed";
    default:
      return "Vacated";
  }
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

export function isValidIsoDate(value: string): boolean {
  if (!ISO_DATE_RE.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}

function isoFromUtc(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addDaysIso(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return isoFromUtc(new Date(Date.UTC(y, m - 1, d + days)));
}

export function weekdayOf(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}

export function isWeekend(iso: string): boolean {
  const day = weekdayOf(iso);
  return day === 0 || day === 6;
}

const LONDON_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function londonParts(now: Date): Record<string, string> {
  const parts: Record<string, string> = {};
  for (const part of LONDON_PARTS.formatToParts(now)) parts[part.type] = part.value;
  return parts;
}

export function londonTodayIso(now: Date = new Date()): string {
  const p = londonParts(now);
  return `${p.year}-${p.month}-${p.day}`;
}

export function londonNowFloating(now: Date = new Date()): string {
  const p = londonParts(now);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}

export function normaliseTime(value: string | null | undefined): string | null {
  const text = (value ?? "").trim();
  if (!text) return null;
  const match = text.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return null;
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

export function formatTime12(value: string | null | undefined): string {
  const time = normaliseTime(value);
  if (!time) return "Time TBC";
  const [h, m] = time.split(":").map(Number);
  const suffix = h >= 12 ? "pm" : "am";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return `${hour}:${String(m).padStart(2, "0")}${suffix}`;
}

export function formatTimeCompact(value: string | null | undefined): string {
  const time = normaliseTime(value);
  if (!time) return "TBC";
  const [h, m] = time.split(":").map(Number);
  const suffix = h >= 12 ? "pm" : "am";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return m === 0 ? `${hour}${suffix}` : `${hour}:${String(m).padStart(2, "0")}${suffix}`;
}

export function formatDateShort(iso: string): string {
  if (!isValidIsoDate(iso)) return iso;
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatDayHeading(iso: string, todayIso: string): string {
  if (iso === todayIso) return "Today";
  if (iso === addDaysIso(todayIso, 1)) return "Tomorrow";
  if (!isValidIsoDate(iso)) return iso;
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function startFloating(h: Pick<Hearing, "hearing_date" | "hearing_time">): string {
  const time = normaliseTime(h.hearing_time);
  return time ? `${h.hearing_date}T${time}:00` : h.hearing_date;
}

export function durationLabel(h: Pick<Hearing, "duration_minutes" | "duration_stated">): string {
  return h.duration_stated === false ? "Not stated" : `${h.duration_minutes} minutes`;
}

export function endFloating(h: Pick<Hearing, "hearing_date" | "hearing_time" | "duration_minutes">): string | null {
  const time = normaliseTime(h.hearing_time);
  if (!time) return null;
  const [y, mo, d] = h.hearing_date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const minutes = Number.isFinite(h.duration_minutes) && h.duration_minutes > 0 ? h.duration_minutes : 60;
  const end = new Date(Date.UTC(y, mo - 1, d, hh, mm + minutes));
  return `${isoFromUtc(end)}T${pad(end.getUTCHours())}:${pad(end.getUTCMinutes())}:00`;
}

export function hearingLabel(h: Pick<Hearing, "order_types" | "hearing_type">): string {
  return h.order_types.trim() || h.hearing_type.trim() || "Hearing";
}

export function hearingParties(h: Pick<Hearing, "client_name" | "applicant" | "respondent" | "case_ref">): string {
  const client = (h.client_name ?? "").trim();
  if (client) return client;
  const applicant = h.applicant.trim();
  const respondent = h.respondent.trim();
  if (applicant && respondent) return `${applicant} v ${respondent}`;
  return applicant || respondent || h.case_ref.trim() || "Unlinked hearing";
}

export function safeHttpUrl(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  if (!text) return "";
  try {
    const url = new URL(text);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : "";
  } catch {
    return "";
  }
}

export function isUnlinked(h: Pick<Hearing, "matter_id">): boolean {
  return h.matter_id === null || h.matter_id === undefined;
}

export function filterLeads<T extends Pick<HearingLead, "source_subject" | "reason">>(leads: T[], query: string): T[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return leads;
  return leads.filter((l) => {
    const text = `${l.source_subject ?? ""} ${l.reason ?? ""}`.toLowerCase();
    return words.every((w) => text.includes(w));
  });
}

export function isPastHearing(h: Pick<Hearing, "hearing_date">, todayIso: string): boolean {
  return h.hearing_date < todayIso;
}

export function filterHearings<T extends Pick<Hearing, "client_name" | "case_ref" | "court">>(hearings: T[], query: string): T[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return hearings;
  return hearings.filter((h) => {
    const text = `${h.client_name ?? ""} ${h.case_ref ?? ""} ${h.court ?? ""}`.toLowerCase();
    return words.every((w) => text.includes(w));
  });
}

export function calendarShown<T extends Pick<Hearing, "hearing_date" | "matter_id" | "review_state" | "client_name" | "case_ref" | "court">>(
  hearings: T[],
  opts: { todayIso: string; showPast: boolean; onlyUnlinked: boolean; filterText: string },
): T[] {
  const active = hearings.filter((h) => h.review_state !== "dismissed");
  const dated = opts.showPast ? active : active.filter((h) => !isPastHearing(h, opts.todayIso));
  return filterHearings(opts.onlyUnlinked ? dated.filter(isUnlinked) : dated, opts.filterText);
}

export function countUnlinked(hearings: Pick<Hearing, "matter_id" | "review_state">[]): number {
  return hearings.filter((h) => h.review_state !== "dismissed" && isUnlinked(h)).length;
}

export function linkableMatterId(value: unknown): number | null {
  if (typeof value === "number") return Number.isInteger(value) && value > 0 ? value : null;
  if (typeof value === "string" && /^\d+$/.test(value.trim())) {
    const n = Number(value.trim());
    return n > 0 ? n : null;
  }
  return null;
}

export function linkOutcomeMessage(reference: string, caseRef: string, clientName: string): string {
  const client = clientName.trim() || "the client";
  const number = caseRef.trim() || "this case number";
  const linked = `Linked to ${client}. Every unlinked hearing with the same case number is linked too.`;
  switch (reference) {
    case "recorded":
      return `${linked} ${number} is now recorded on ${client}, so future emails will link themselves.`;
    case "exists":
      return `${linked} ${number} was already recorded on ${client}.`;
    case "conflict":
      return `${linked} Note: ${number} already belongs to another client, so it was not recorded on ${client}. Check which client is right.`;
    case "failed":
      return `${linked} ${number} could not be recorded on ${client}, so future emails will not link themselves yet.`;
    default:
      return `${linked} ${number} was not recorded on ${client}, so future emails will not link themselves yet.`;
  }
}

export function isActive(h: Pick<Hearing, "review_state">): boolean {
  return h.review_state !== "dismissed";
}

export function isCounselBooked(h: Pick<Hearing, "counsel" | "counsel_booked" | "status">): boolean {
  return h.status === "scheduled" && (h.counsel_booked ?? Boolean(h.counsel && h.counsel.trim()));
}

export function hearingMarkers(h: Pick<Hearing, "counsel" | "counsel_booked" | "status" | "matter_id" | "bundle_done" | "bundle_why">): { key: string; label: string; short: string; why: string }[] {
  if (h.status !== "scheduled" || h.matter_id == null || typeof h.bundle_done !== "boolean") return [];
  const out: { key: string; label: string; short: string; why: string }[] = [];
  if (!isCounselBooked(h)) out.push({ key: "no-counsel", label: "Counsel not booked", short: "No counsel", why: "" });
  if (!h.bundle_done) out.push({ key: "no-bundle", label: "Bundle not done", short: "No bundle", why: h.bundle_why ?? "" });
  return out;
}

export function visibleConfidence(h: Pick<Hearing, "confidence" | "review_state" | "human_edited" | "counsel" | "counsel_booked" | "status">): number | null {
  if (h.confidence === null || h.confidence === undefined) return null;
  if (h.review_state !== "needs_review") return null;
  return h.confidence;
}

export function hearingClassNames(h: Hearing): string[] {
  const names = ["hearing-ev"];
  if (isVacated(h)) names.push("hearing-ev--vacated");
  if (requestLabel(h)) names.push("hearing-ev--request");
  if (h.review_state === "needs_review") names.push("hearing-ev--review");
  else if (isCounselBooked(h)) names.push("hearing-ev--counsel");
  if (h.is_final && h.status === "scheduled") names.push("hearing-ev--final");
  return names;
}

export interface CalendarEventInput {
  id: string;
  title: string;
  start: string;
  end?: string;
  allDay: boolean;
  classNames: string[];
  extendedProps: { hearing: Hearing };
}

export function toCalendarEvent(h: Hearing): CalendarEventInput {
  const end = endFloating(h);
  return {
    id: String(h.hearing_id),
    title: `${hearingLabel(h)} - ${hearingParties(h)}`,
    start: startFloating(h),
    ...(end ? { end } : {}),
    allDay: normaliseTime(h.hearing_time) === null,
    classNames: hearingClassNames(h),
    extendedProps: { hearing: h },
  };
}

export function compareHearings(a: Hearing, b: Hearing): number {
  if (a.hearing_date !== b.hearing_date) return a.hearing_date < b.hearing_date ? -1 : 1;
  const ta = normaliseTime(a.hearing_time);
  const tb = normaliseTime(b.hearing_time);
  if (ta !== tb) {
    if (ta === null) return 1;
    if (tb === null) return -1;
    return ta < tb ? -1 : 1;
  }
  return a.hearing_id - b.hearing_id;
}

export interface DayGroup {
  date: string;
  items: Hearing[];
}

export function groupByDay(hearings: Hearing[]): DayGroup[] {
  const sorted = [...hearings].filter(isActive).sort(compareHearings);
  const groups: DayGroup[] = [];
  for (const h of sorted) {
    const last = groups[groups.length - 1];
    if (last && last.date === h.hearing_date) last.items.push(h);
    else groups.push({ date: h.hearing_date, items: [h] });
  }
  return groups;
}

export function upcomingWindow(todayIso: string, days = 14): { from: string; to: string } {
  return { from: todayIso, to: addDaysIso(todayIso, Math.max(1, days) - 1) };
}

export function inclusiveRange(startStr: string, endExclusiveStr: string): { from: string; to: string } {
  const from = startStr.slice(0, 10);
  const endExclusive = endExclusiveStr.slice(0, 10);
  const to = addDaysIso(endExclusive, -1);
  return { from, to: to < from ? from : to };
}

export function hearingsQuery(from: string, to: string, matterId?: string | number): string {
  const params = new URLSearchParams({ from, to });
  if (matterId !== undefined && String(matterId).trim()) params.set("matter_id", String(matterId).trim());
  return params.toString();
}

const MAX_RANGE_DAYS = 800;
const MAX_MATTER_RANGE_DAYS = 2000;

export type RangeParse = { ok: true; from: string; to: string; matterId: string } | { ok: false; error: string };

export function parseRange(params: URLSearchParams): RangeParse {
  const from = (params.get("from") ?? "").trim();
  const to = (params.get("to") ?? "").trim();
  if (!isValidIsoDate(from) || !isValidIsoDate(to)) return { ok: false, error: "from and to must be dates (YYYY-MM-DD)" };
  if (to < from) return { ok: false, error: "to must not be before from" };
  const matterId = (params.get("matter_id") ?? "").trim();
  if (matterId && !/^\d+$/.test(matterId)) return { ok: false, error: "matter_id must be a number" };
  if (addDaysIso(from, matterId ? MAX_MATTER_RANGE_DAYS : MAX_RANGE_DAYS) < to) return { ok: false, error: "date range is too long" };
  return { ok: true, from, to, matterId };
}

export function addYearsIso(iso: string, years: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const target = y + years;
  const lastDay = new Date(Date.UTC(target, m, 0)).getUTCDate();
  return `${String(target).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(Math.min(d, lastDay)).padStart(2, "0")}`;
}

export function matterHearingsWindow(todayIso: string): { from: string; to: string } {
  return { from: addYearsIso(todayIso, -2), to: addYearsIso(todayIso, 3) };
}

export const PAST_VISIBLE = 5;

export interface MatterHearingGroups {

  upcoming: Hearing[];

  past: Hearing[];

  upcomingScheduled: number;
}

export function splitMatterHearings(hearings: Hearing[], todayIso: string): MatterHearingGroups {
  const live = hearings.filter(isActive);
  const upcoming = live.filter((h) => h.hearing_date >= todayIso).sort(compareHearings);
  const past = live.filter((h) => h.hearing_date < todayIso).sort((a, b) => compareHearings(b, a));
  return { upcoming, past, upcomingScheduled: upcoming.filter((h) => h.status === "scheduled").length };
}

export function onlyCourtReference(refs: string[]): string {
  const distinct = [...new Set(refs.map((r) => r.trim().toUpperCase()).filter(Boolean))];
  return distinct.length === 1 ? distinct[0] : "";
}

export function icsHref(from: string, to: string): string {
  return `/api/hearings/ics?${hearingsQuery(from, to)}`;
}

export interface HearingFormValues {
  case_ref: string;
  matter_id: string;
  applicant: string;
  respondent: string;
  counsel: string;
  chambers: string;
  hearing_date: string;
  hearing_time: string;
  duration_minutes: string;
  hearing_type: string;
  order_types: string;
  is_final: boolean;
  court: string;
  mode: HearingMode;
  notice: HearingNotice;
  join_url: string;
  notes: string;
}

export function emptyFormValues(defaults: Partial<HearingFormValues> = {}): HearingFormValues {
  return {
    case_ref: "",
    matter_id: "",
    applicant: "",
    respondent: "",
    counsel: "",
    chambers: "",
    hearing_date: "",
    hearing_time: "",
    duration_minutes: "",
    hearing_type: "",
    order_types: "",
    is_final: false,
    court: "",
    mode: "",
    notice: "",
    join_url: "",
    notes: "",
    ...defaults,
  };
}

export function formFromHearing(h: Hearing): HearingFormValues {
  return {
    case_ref: h.case_ref,
    matter_id: h.matter_id === null ? "" : String(h.matter_id),
    applicant: h.applicant,
    respondent: h.respondent,
    counsel: h.counsel ?? "",
    chambers: h.chambers ?? "",
    hearing_date: h.hearing_date,
    hearing_time: normaliseTime(h.hearing_time) ?? "",

    duration_minutes: h.duration_stated === false ? "" : String(h.duration_minutes || 60),
    hearing_type: h.hearing_type,
    order_types: h.order_types,
    is_final: h.is_final,
    court: h.court,
    mode: h.mode,
    notice: h.notice ?? "",
    join_url: h.join_url,
    notes: h.notes,
  };
}

export interface FormCheck {
  errors: Record<string, string>;

  warnings: string[];
}

export function validateHearingForm(values: HearingFormValues, opts: { requireCaseRef: boolean }): FormCheck {
  const errors: Record<string, string> = {};
  const warnings: string[] = [];

  if (opts.requireCaseRef && !values.case_ref.trim()) errors.case_ref = "Enter the court case number.";
  if (!isValidIsoDate(values.hearing_date.trim())) errors.hearing_date = "Enter a valid date.";
  const time = values.hearing_time.trim();
  if (time && !TIME_RE.test(time)) errors.hearing_time = "Use 24-hour time, for example 14:30.";
  const duration = values.duration_minutes.trim();
  if (duration) {
    const n = Number(duration);
    if (!Number.isInteger(n) || n < 5 || n > 600) errors.duration_minutes = "Enter whole minutes between 5 and 600.";
  }
  const matterId = values.matter_id.trim();
  if (matterId && !/^\d+$/.test(matterId)) errors.matter_id = "The matter ID is a number.";
  if (values.join_url.trim() && !safeHttpUrl(values.join_url)) errors.join_url = "Use a full https:// link.";

  if (!errors.hearing_date && isWeekend(values.hearing_date.trim())) {
    warnings.push("This date is a weekend. Courts do not normally sit then, so check the date.");
  }
  if (time && !errors.hearing_time && (time < "08:00" || time > "17:30")) {
    warnings.push("This time is outside normal court hours.");
  }
  return { errors, warnings };
}

export type HearingEdits = Partial<{
  case_ref: string;
  matter_id: number | null;
  applicant: string;
  respondent: string;
  counsel: string;
  chambers: string;
  hearing_date: string;
  hearing_time: string | null;

  duration_minutes: number | null;
  hearing_type: string;
  order_types: string;
  is_final: boolean;
  court: string;
  mode: HearingMode;
  notice: HearingNotice;
  join_url: string;
  notes: string;
}>;

function trimmedFields(values: HearingFormValues): Required<HearingEdits> {
  const time = values.hearing_time.trim();
  const matterId = values.matter_id.trim();
  return {
    case_ref: values.case_ref.trim().toUpperCase(),
    matter_id: matterId ? Number(matterId) : null,
    applicant: values.applicant.trim(),
    respondent: values.respondent.trim(),
    counsel: values.counsel.trim(),
    chambers: values.chambers.trim(),
    hearing_date: values.hearing_date.trim(),
    hearing_time: time || null,
    duration_minutes: values.duration_minutes.trim() ? Number(values.duration_minutes.trim()) : null,
    hearing_type: values.hearing_type.trim(),
    order_types: values.order_types.trim().toUpperCase(),
    is_final: values.is_final,
    court: values.court.trim(),
    mode: values.mode,
    notice: values.notice,
    join_url: values.join_url.trim(),
    notes: values.notes.trim(),
  };
}

export function editsFromForm(original: Hearing, values: HearingFormValues): HearingEdits {
  const next = trimmedFields(values);
  const before = trimmedFields(formFromHearing(original));
  const edits: Record<string, unknown> = {};
  for (const key of Object.keys(next) as (keyof HearingEdits)[]) {
    if (next[key] !== before[key]) edits[key] = next[key];
  }
  return edits as HearingEdits;
}

export const HEARING_FIELD_KEYS = [
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
  "notice",
  "join_url",
  "notes",
] as const;

export function pickHearingFields(input: unknown): { fields: Record<string, unknown>; unknown: string[] } {
  const fields: Record<string, unknown> = {};
  const unknown: string[] = [];
  if (input && typeof input === "object" && !Array.isArray(input)) {
    for (const [key, value] of Object.entries(input as Record<string, unknown>)) {
      if ((HEARING_FIELD_KEYS as readonly string[]).includes(key)) fields[key] = value;
      else unknown.push(key);
    }
  }
  return { fields, unknown };
}

export function createPayloadFromForm(values: HearingFormValues): HearingEdits {
  return trimmedFields(values);
}

export function describeEdits(edits: HearingEdits): string[] {
  const labels: Record<string, string> = {
    case_ref: "Case number",
    matter_id: "Matter ID",
    applicant: "Applicant",
    respondent: "Respondent",
    counsel: "Counsel",
    chambers: "Chambers",
    hearing_date: "Date",
    hearing_time: "Time",
    duration_minutes: "Duration (minutes)",
    hearing_type: "Hearing type",
    order_types: "Order types",
    is_final: "Final hearing",
    court: "Court",
    mode: "Mode",
    notice: "Notice",
    not_before_date: "Not before",
    join_url: "Join link",
    notes: "Notes",
  };
  return Object.entries(edits).map(([key, value]) => {
    const shown = value === null || value === "" ? "(blank)" : typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
    return `${labels[key] ?? key}: ${shown}`;
  });
}
