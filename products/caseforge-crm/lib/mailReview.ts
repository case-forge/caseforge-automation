
export type MailReviewAnswer = {
  job_id: string;
  n: number;
  route: string;
  also: string;
  no_clean_answer: boolean;
  matter: string;
  logic: string;
  saved_utc: string;
};

export type MailReviewOverview = {
  total: number;
  answered: number;
  routes: string[];
  counts: Record<string, number>;
  no_clean_answer: number;
  first_unanswered: number | null;
  items: { n: number; done: boolean; route: string; no_clean_answer: boolean }[];
  expires_utc: string;
  expired: boolean;
};

export type MailReviewItem = {
  n: number;
  total: number;
  from: string;
  to: string;
  cc: string;
  date: string;
  subject: string;
  attachments: string[];
  text: string;
  weblink: string;
  routes: string[];
  answer: MailReviewAnswer | null;
  expires_utc: string;
  expired: boolean;
};

export function startingItem(overview: MailReviewOverview): number {
  return overview.first_unanswered ?? Math.max(1, overview.total);
}

export function safeOutlookLink(link: string | null | undefined): string | null {
  return typeof link === "string" && /^https:\/\//i.test(link) ? link : null;
}

export function summaryLines(overview: MailReviewOverview): string[] {
  const routes = Object.entries(overview.counts)
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([route, count]) => `${route}: ${count}`);
  const noClean = overview.no_clean_answer > 0 ? [`No clean answer: ${overview.no_clean_answer}`] : [];
  return [`Answered ${overview.answered} of ${overview.total}`, ...routes, ...noClean];
}

export const BODY_HEAD_CHARS = 1800;

export function splitBody(text: string): { head: string; rest: string } {
  const body = text || "(no text body)";
  return { head: body.slice(0, BODY_HEAD_CHARS), rest: body.slice(BODY_HEAD_CHARS) };
}

export function answerReady(route: string, noCleanAnswer: boolean, logic: string): boolean {
  return Boolean(route) || noCleanAnswer || logic.trim().length > 0;
}

export function expiryLabel(expiresUtc: string, expired: boolean): string {
  const when = new Date(expiresUtc);
  const text = Number.isNaN(when.getTime())
    ? expiresUtc
    : when.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
  return expired ? `Expired ${text}: read only` : `Open until ${text}`;
}

export type ReviewTab = "review" | "control";

export function tabFromParam(value: string | null | undefined): ReviewTab {
  return value === "control" || value === "audit" ? "control" : "review";
}

export type QcItem = {
  n: number;
  job_id: string;
  from: string;
  to: string;
  cc: string;
  date: string;
  subject: string;
  attachments: string[];
  text: string;
  weblink: string;
  pool: string;
  applied_route: string;

  applied_destination?: string;

  applied_other_text?: string;
  route_source: string;
  stratum: string;
  model_route: string;
  model_conf: number | null;
  rules_route: string;
  reason: string;
  created_utc: string;
};

export type RecentDecision = {
  route: string;
  saved_utc: string;
  state: "waiting" | "applied" | "applied_blocked" | "not_applied" | "no_route";
  plain: string;
};

export const SAVED_NOTE =
  "Recorded. The route will be applied by the mail worker within about a minute. If the email is still held (for example no matter was found), the list below says why.";

export type DecideView = {
  total: number;
  oldest_days: number;
  routes: string[];
  item: (QcItem & { total: number }) | null;
  recent?: RecentDecision[];
};

export type ControlView = {
  date: string;
  total: number;
  answered: number;
  routes: string[];
  pool_sizes: Record<string, number>;
  items: { n: number; done: boolean; verdict: string }[];
  item: (QcItem & { answer: { route: string; verdict: string } | null }) | null;
};

export type ControlVerdict = "agree" | "disagree";

export function isUndecided(route: string): boolean {
  return !route || route === "Review";
}

export function shownDestination(item: Pick<QcItem, "applied_route" | "applied_destination" | "applied_other_text">): string {
  const word = item.applied_destination || item.applied_route;
  return (word === "Other" || word === "Other Side") && item.applied_other_text ? `${word} (${item.applied_other_text})` : word;
}

export function controlSentence(item: Pick<QcItem, "applied_route" | "applied_destination" | "applied_other_text">): string {
  return isUndecided(item.applied_route)
    ? "The classifier could not decide this one. Where does it go?"
    : `The classifier thinks this goes to ${shownDestination(item)}. Do you agree?`;
}

export function promptQuestion(item: Pick<QcItem, "applied_route" | "applied_destination" | "applied_other_text">): { lead: string; ask: string } {
  return isUndecided(item.applied_route)
    ? { lead: "Our email sorter could not decide where this email goes.", ask: "Where does it belong?" }
    : { lead: `Our email sorter put this under \u201c${shownDestination(item)}\u201d.`, ask: "Is that right?" };
}

export function decideContext(item: Pick<QcItem, "reason" | "model_route" | "model_conf" | "rules_route" | "applied_route"> & Partial<Pick<QcItem, "applied_destination" | "applied_other_text">>): string[] {
  const lines: string[] = [];
  if (item.reason) lines.push(item.reason);
  if (item.applied_other_text) lines.push(`Noted: ${item.applied_other_text}.`);
  if (item.model_route) {
    const conf = typeof item.model_conf === "number" ? ` (${Math.round(item.model_conf * 100)}% sure)` : "";
    lines.push(`The model said ${item.model_route}${conf}.`);
  }
  if (item.rules_route) lines.push(`The rules said ${item.rules_route}.`);
  if (item.applied_route && !isUndecided(item.applied_route)) lines.push(`Best guess so far: ${shownDestination(item as Pick<QcItem, "applied_route" | "applied_destination" | "applied_other_text">)}.`);
  return lines;
}

export function backlogLine(total: number, oldestDays: number): string {
  if (total === 0) return "Nothing is waiting for a decision.";
  const age = oldestDays < 1 ? "under a day" : `${Math.floor(oldestDays)} day${Math.floor(oldestDays) === 1 ? "" : "s"}`;
  return `${total} email${total === 1 ? "" : "s"} waiting; the oldest has waited ${age}.`;
}

export const PROMPT_STORAGE_KEY = "caseforge-client-viewer:classifier-prompt";
export const PROMPT_MIN_GAP_MS = 60 * 60 * 1000;

export function poolBadge(pool: string): { letter: "C" | "R"; tip: string } | null {
  if (pool === "control") {
    return { letter: "C", tip: "C is a control email: the sorter was confident about it. We ask about a few of these to check it is not quietly getting things wrong." };
  }
  if (pool === "review") {
    return { letter: "R", tip: "R is a review email: the sorter was unsure, or its two checks disagreed. Your answer matters most here." };
  }
  return null;
}

export function safeEmailLink(weblink: string | undefined): string {
  return typeof weblink === "string" && /^https:\/\//i.test(weblink) ? weblink : "";
}

export type PromptMemory = { lastShownAt: number; snoozeUntil: number };

export function nextLocalMidnight(now: number): number {
  const day = new Date(now);
  return new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1).getTime();
}

export function holdAfterClose(now: number): PromptMemory {
  return { lastShownAt: now, snoozeUntil: 0 };
}

export function holdAfterNotToday(now: number): PromptMemory {
  return { lastShownAt: now, snoozeUntil: nextLocalMidnight(now) };
}

export function promptAllowed(memory: PromptMemory, now: number, typing: boolean): boolean {
  if (typing) return false;
  if (now < memory.snoozeUntil) return false;
  return now - memory.lastShownAt >= PROMPT_MIN_GAP_MS;
}

export function loadPromptMemory(): PromptMemory {
  const blank = { lastShownAt: 0, snoozeUntil: 0 };
  try {
    const raw = window.localStorage.getItem(PROMPT_STORAGE_KEY);
    if (!raw) return blank;
    const parsed = JSON.parse(raw) as Partial<PromptMemory>;
    return {
      lastShownAt: Number.isFinite(parsed.lastShownAt) ? Number(parsed.lastShownAt) : 0,
      snoozeUntil: Number.isFinite(parsed.snoozeUntil) ? Number(parsed.snoozeUntil) : 0,
    };
  } catch {
    return blank;
  }
}

export function savePromptMemory(memory: PromptMemory): void {
  try {
    window.localStorage.setItem(PROMPT_STORAGE_KEY, JSON.stringify(memory));
  } catch {

  }
}

export function isTypingTarget(element: Element | null | undefined): boolean {
  if (!element) return false;
  const tag = element.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") {
    const type = (element as HTMLInputElement).type;
    return !["button", "checkbox", "radio", "submit", "reset", "range", "color", "file", "image"].includes(type);
  }
  return (element as HTMLElement).isContentEditable === true;
}
