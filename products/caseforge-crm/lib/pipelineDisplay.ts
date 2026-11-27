
import { SERVICE_RECIPIENT_KINDS, stepRef } from "./pipelineTypes";
import type { ActivityViewer, PipelineStepStatus } from "./pipelineTypes";

export interface StatusMark {
  shape: string;
  word: string;
}

const MARKS: Record<PipelineStepStatus, StatusMark> = {
  done: { shape: "●", word: "Done" },
  todo: { shape: "○", word: "To do" },
  attention: { shape: "▲", word: "Needs attention" },
  blocked: { shape: "■", word: "Blocked" },
  unknown: { shape: "◇", word: "Not known" },
  not_needed: { shape: "◌", word: "Not needed" },
};

export function statusMark(status: string): StatusMark {
  return MARKS[status as PipelineStepStatus] ?? MARKS.unknown;
}

export const DEFAULT_LOCK_REASON = "Locked: Case flow is not available for this client.";

export function lockedReason(pipeline: { locked?: boolean; lock_reason?: string } | null | undefined): string {
  if (!pipeline || pipeline.locked !== true) return "";
  return (pipeline.lock_reason ?? "").trim() || DEFAULT_LOCK_REASON;
}

export function runBlockedReason(opts: { canRun: boolean; running: boolean; locked?: string }): string {
  if (opts.locked) return opts.locked;
  if (opts.running) return "A step is running.";
  if (!opts.canRun) return "This step cannot run yet.";
  return "";
}

export function eventTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
}

export function seenByLine(viewers: ActivityViewer[] | undefined): string {
  const named = (viewers ?? []).filter((v) => v.who.trim());
  if (named.length === 0) return "";
  return `Seen by ${named.map((v) => [v.who, eventTime(v.at)].filter(Boolean).join(", ")).join("; ")}`;
}

export function newestFirst<T extends { created_utc: string }>(events: T[]): T[] {
  return [...events].sort((a, b) => b.created_utc.localeCompare(a.created_utc));
}

export function oldestFirst<T extends { created_utc: string }>(events: T[]): T[] {
  return [...events].sort((a, b) => a.created_utc.localeCompare(b.created_utc));
}

export function canMarkDone(step: { status: string; key?: string }): boolean {
  return step.status !== "done" && step.status !== "not_needed";
}

export function isOutstanding(step: { status: string }): boolean {
  return step.status !== "done" && step.status !== "not_needed";
}

export function canResetStep(step: { status: string; resettable?: boolean; key?: string }): boolean {
  if (step.key === "amend") return step.resettable === true;
  return step.resettable === true || (step.resettable === undefined && step.status === "done");
}

export function resetStepQuestion(step: { number?: number; label: string }): string {
  const which = typeof step.number === "number" ? `step ${step.number}, ${step.label}` : step.label;
  return `Forget the mark on ${which}? Only this step is forgotten; it is then checked again. Files, folders, drafts and envelopes are NOT deleted.`;
}

export function safeLinks(links: { label: string; url: string }[] | undefined): { label: string; url: string }[] {
  return (links ?? []).filter((l) => typeof l?.url === "string" && l.url.startsWith("https://"));
}

export function markDoneQuestion(step: { number?: number; label: string }, by: string): string {
  const which = typeof step.number === "number" ? `step ${step.number}, ${step.label}` : step.label;
  return `Mark ${which}, as done outside Case flow by ${by}? Nothing is run, sent or changed in the client's folder; the step's reset undoes it. Add a note if you like.`;
}

export function canConfirmCourt(step: { key: string; status: string; summary?: string; court_suggestions?: unknown[] }): boolean {
  return step.key === "court_email" && step.status !== "done" && (Boolean(step.court_suggestions?.length) || /^Confirm the court/.test(step.summary ?? ""));
}

export function courtSuggestionLabel(suggestion: { name: string; email: string }): string {
  return `${suggestion.name}${suggestion.email ? ` (${suggestion.email})` : " (no family email given)"}`;
}

export function confirmCourtCheck(court: string, email: string): string {
  return `Record ${court || "the recorded court"}${email ? ` with the email ${email}` : ""} as this matter's court? Nothing is drafted or sent; ${stepRef("court_email")} can then draft the court email.`;
}

export function recipientKind(typed: string): string {
  const clean = typed.trim().toLowerCase().replace(/\s+/g, " ");
  return (SERVICE_RECIPIENT_KINDS as readonly string[]).includes(clean) ? clean : "";
}

export function serviceRecipientCheck(kind: string, name: string, email: string, by: string): string {
  return `Add ${name} (${kind}, ${email}) to serve, as ${by}? Case flow then drafts their service email; nothing is sent.`;
}

export function eventStatusWord(status: string): string {
  const words: Record<string, string> = { ok: "Worked", failed: "Failed", waiting: "Waiting", held: "Held", outside: "Outside", reset: "Reset" };
  return words[status] ?? "Note";
}

export function lastReadLabel(steps: { status: string; checked_utc?: string }[]): string {
  const times = steps
    .filter((s) => s.status !== "done" && s.checked_utc)
    .map((s) => Date.parse(s.checked_utc as string))
    .filter((t) => Number.isFinite(t));
  if (times.length === 0) return "";
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Europe/London" }).format(
    new Date(Math.min(...times)),
  );
}

export function attemptBadge(step: { auto_tries?: number; auto_max?: number }): { total: number; made: number; text: string; label: string; stopped: boolean } | null {
  const total = Math.floor(step.auto_max ?? 0);
  if (total < 1 || total > 10) return null;
  const made = Math.min(total, Math.max(0, Math.floor(step.auto_tries ?? 0)));
  if (made < 1) return null;
  const stopped = made === total;
  const text = `Attempt ${made} out of ${total}`;
  const label = stopped ? `${text} failed. Auto has stopped and needs a person.` : `${text} failed. Auto will try again.`;
  return { total, made, text, label, stopped };
}

export const PIPELINE_LOADING_WORDS = [
  "Reading the client's folders",
  "Checking the mailbox",
  "Finding the signed statement",
  "Looking for the court's reply",
  "Counting the forms",
  "Lining up the steps",
] as const;

export function pipelineLoadingText(seconds: number): string {
  const word = PIPELINE_LOADING_WORDS[Math.floor(Math.max(0, seconds) / 3) % PIPELINE_LOADING_WORDS.length];
  return seconds < 20 ? `${word}…` : `${word}… still working (${Math.floor(seconds)}s)`;
}
