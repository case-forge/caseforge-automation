
import { isValidIsoDate, isVacated, normaliseTime } from "./hearings";
import type { Hearing, HearingFormValues } from "./hearings";

export type VacateChoice = "moved" | "no_longer_acting";
export type RequestKind = "vacation" | "hybrid";

export const VACATE_CHOICES: { kind: VacateChoice; label: string }[] = [
  { kind: "moved", label: "Moved to a new date/time" },
  { kind: "no_longer_acting", label: "No longer acting for the client" },
];

export const REQUEST_CHOICES: { kind: RequestKind; label: string; short: string }[] = [
  { kind: "vacation", label: "Request vacation (e.g. lack of counsel)", short: "Request vacation" },
  { kind: "hybrid", label: "Request remote/hybrid hearing", short: "Request remote/hybrid" },
];

export interface StockReason {
  id: string;
  label: string;
  text: string;
}

export interface RequestOptions {
  hearing_id: number;

  form: string;
  form_known: boolean;
  forms: string[];
  vacation_reasons: StockReason[];
  hybrid_reasons: StockReason[];
}

export interface VacateResponse {
  hearing: Hearing;
  replacement: Hearing | null;
}

export interface CourtRequestResponse {
  hearing: Hearing;
  form: string;
  draft: { web_link?: string } | null;
  summary: string;
}

export function reasonsFor(options: RequestOptions, kind: RequestKind): StockReason[] {
  return kind === "vacation" ? options.vacation_reasons : options.hybrid_reasons;
}

export type HearingState = "scheduled" | "vacation_requested" | "hybrid_requested" | "vacated";

export function hearingState(h: Pick<Hearing, "status" | "request_state">): HearingState {
  if (isVacated(h)) return "vacated";
  if (h.request_state === "vacation_requested" || h.request_state === "hybrid_requested") return h.request_state;
  return "scheduled";
}

export interface MoveInput {
  hearing_date: string;

  hearing_time: string;
}

export function validateMove(original: Pick<Hearing, "hearing_date" | "hearing_time">, input: MoveInput): string | null {
  if (!input.hearing_date) return "Enter the new date.";
  if (!isValidIsoDate(input.hearing_date)) return "The new date is not a real date.";
  const typed = input.hearing_time.trim();
  if (typed && !/^([01]\d|2[0-3]):[0-5]\d$/.test(typed)) return "Enter the new time as HH:MM (24-hour).";
  const time = typed ? typed : null;
  if (input.hearing_date === original.hearing_date && time === normaliseTime(original.hearing_time)) {
    return "That is the same date and time: nothing has moved.";
  }
  return null;
}

export function vacateBody(hearingId: number, kind: VacateChoice, reason: string, move?: MoveInput) {
  const replacement =
    kind === "moved" && move
      ? { hearing_date: move.hearing_date, ...(move.hearing_time.trim() ? { hearing_time: move.hearing_time.trim() } : {}) }
      : undefined;
  return { hearing_id: hearingId, kind, ...(reason.trim() ? { reason: reason.trim() } : {}), ...(replacement ? { replacement } : {}) };
}

export const NEARBY_MINUTES = 180;

export interface DuplicateMatches {

  exact: Hearing | null;

  nearby: Hearing[];
}

function minutes(time: string | null | undefined): number | null {
  const t = normaliseTime(time);
  if (!t) return null;
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

function normCase(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, "").toUpperCase();
}

export function findDuplicateHearings(existing: Hearing[], form: Pick<HearingFormValues, "case_ref" | "matter_id" | "hearing_date" | "hearing_time">): DuplicateMatches {
  const none: DuplicateMatches = { exact: null, nearby: [] };
  if (!isValidIsoDate(form.hearing_date)) return none;
  const caseRef = normCase(form.case_ref);
  const matterId = form.matter_id.trim();
  if (!caseRef && !matterId) return none;
  const sameCase = existing.filter(
    (h) =>
      h.hearing_date === form.hearing_date &&
      !isVacated(h) &&
      h.review_state !== "dismissed" &&
      (caseRef ? normCase(h.case_ref) === caseRef : h.matter_id !== null && String(h.matter_id) === matterId),
  );
  const wanted = form.hearing_time.trim() ? minutes(form.hearing_time) : null;
  const exact = sameCase.find((h) => (wanted === null ? false : minutes(h.hearing_time) === wanted)) ?? null;
  const nearby = sameCase.filter((h) => {
    if (h === exact) return false;
    const at = minutes(h.hearing_time);
    return wanted === null || at === null || Math.abs(at - wanted) <= NEARBY_MINUTES;
  });
  return { exact, nearby };
}

export function duplicateMessage(matches: DuplicateMatches): string {
  if (matches.exact) return "This case already has a hearing at that date and time.";
  if (matches.nearby.length) return "This case already has a hearing that day. If the court moved it, vacate it as moved instead of adding a second one.";
  return "";
}

export function duplicateTarget(matches: DuplicateMatches): Hearing | null {
  return matches.exact ?? matches.nearby[0] ?? null;
}

export function moveStart(h: Pick<Hearing, "hearing_date" | "hearing_time">): MoveInput {
  return { hearing_date: h.hearing_date, hearing_time: normaliseTime(h.hearing_time) ?? "" };
}
