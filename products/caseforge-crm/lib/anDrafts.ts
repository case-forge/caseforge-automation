
import type { AttendanceCaller, AttendanceNoteKind } from "./types";
import { currentKind, isAttendanceKind } from "./types";

export interface AnFormState {
  caller: AttendanceCaller | "";
  callerOther: string;
  noteText: string;

  kind?: AttendanceNoteKind;
}

export interface AnDraft extends AnFormState {
  id: string;
  savedAt: string;
}

const WORK_PREFIX = "caseforge-client-viewer:an-work:";
const DRAFTS_PREFIX = "caseforge-client-viewer:an-drafts:";
const MAX_DRAFTS_PER_MATTER = 30;

export const EMPTY_AN_FORM: AnFormState = { caller: "", callerOther: "", noteText: "", kind: "call" };

export function kindOf(form: { kind?: unknown }): AttendanceNoteKind {
  return isAttendanceKind(form.kind) ? currentKind(form.kind) : "call";
}

export function isBlankAnForm(form: AnFormState): boolean {
  return form.caller === "" && form.callerOther.trim() === "" && form.noteText.trim() === "";
}

function read<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {

  }
}

function clear(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {

  }
}

export function loadWorkingCopy(matterId: string): AnFormState {
  if (!matterId) return EMPTY_AN_FORM;
  const saved = read<Partial<AnFormState>>(WORK_PREFIX + matterId, {});
  return {
    caller: saved.caller ?? "",
    callerOther: saved.callerOther ?? "",
    noteText: saved.noteText ?? "",
    kind: kindOf(saved),
  };
}

export function saveWorkingCopy(matterId: string, form: AnFormState): void {
  if (!matterId) return;

  if (isBlankAnForm(form) && kindOf(form) === "call") clear(WORK_PREFIX + matterId);
  else write(WORK_PREFIX + matterId, form);
}

export function clearWorkingCopy(matterId: string): void {
  if (matterId) clear(WORK_PREFIX + matterId);
}

export function loadDrafts(matterId: string): AnDraft[] {
  if (!matterId) return [];
  const drafts = read<AnDraft[]>(DRAFTS_PREFIX + matterId, []);
  return Array.isArray(drafts) ? drafts : [];
}

export function saveDraft(matterId: string, form: AnFormState, now: Date = new Date()): AnDraft {
  const draft: AnDraft = {
    ...form,
    id: `${now.getTime()}-${Math.random().toString(36).slice(2, 8)}`,
    savedAt: now.toISOString(),
  };
  const next = [draft, ...loadDrafts(matterId)].slice(0, MAX_DRAFTS_PER_MATTER);
  write(DRAFTS_PREFIX + matterId, next);
  return draft;
}

export function saveDrafts(matterId: string, drafts: AnDraft[]): void {
  if (!matterId) return;
  if (drafts.length === 0) clear(DRAFTS_PREFIX + matterId);
  else write(DRAFTS_PREFIX + matterId, drafts.slice(0, MAX_DRAFTS_PER_MATTER));
}

export function deleteDraft(matterId: string, id: string): AnDraft[] {
  const next = loadDrafts(matterId).filter((d) => d.id !== id);
  write(DRAFTS_PREFIX + matterId, next);
  return next;
}

const SENT_PREFIX = "caseforge-client-viewer:an-sent:";
const FROM_DRAFT_PREFIX = "caseforge-client-viewer:an-from-draft:";
const MAX_SENT_PER_MATTER = 20;

export interface SentNote extends AnFormState {
  draftId: string;
  sentAt: string;
}

export function rememberSent(matterId: string, draftId: string, form: AnFormState, now: Date = new Date()): void {
  if (!matterId || !draftId) return;
  const next: SentNote[] = [
    { ...form, draftId, sentAt: now.toISOString() },
    ...loadSent(matterId).filter((n) => n.draftId !== draftId),
  ].slice(0, MAX_SENT_PER_MATTER);
  write(SENT_PREFIX + matterId, next);
}

export function loadSent(matterId: string): SentNote[] {
  if (!matterId) return [];
  const sent = read<SentNote[]>(SENT_PREFIX + matterId, []);
  return Array.isArray(sent) ? sent : [];
}

export function forgetSent(matterId: string, draftId: string): void {
  if (!matterId) return;
  const next = loadSent(matterId).filter((n) => n.draftId !== draftId);
  if (next.length === 0) clear(SENT_PREFIX + matterId);
  else write(SENT_PREFIX + matterId, next);
}

export function markWorkingFromDraft(matterId: string, on: boolean): void {
  if (!matterId) return;
  if (on) write(FROM_DRAFT_PREFIX + matterId, true);
  else clear(FROM_DRAFT_PREFIX + matterId);
}

export function isWorkingFromDraft(matterId: string): boolean {
  return !!matterId && read<boolean>(FROM_DRAFT_PREFIX + matterId, false) === true;
}

export function hasUnfinishedDraft(matterId: string): boolean {
  return loadDrafts(matterId).length > 0 || isWorkingFromDraft(matterId);
}

export function formatDraftTime(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const date = when.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const time = when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time}`;
}
