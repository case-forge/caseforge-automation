
import * as chrono from "chrono-node";
import { normaliseUkShorthand } from "./hearingDetection";

export interface ParsedTodo {

  title: string;

  due: string | null;
  hasTime: boolean;

  matchedText: string;
}

const WRITTEN =
  /\d|\b(?:today|tonight|tomorrow|tmr|tmrw|next|this|in)\b|\b(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b/i;
const DANGLING_END = /\s+(?:on|at|by|for|due|before|until|from)\s*$/i;
const DANGLING_START = /^(?:on|at|by|due)\s+/i;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function parseTodoText(raw: string, now: Date = new Date()): ParsedTodo {
  const original = raw.trim().replace(/\s+/g, " ");
  const none: ParsedTodo = { title: original, due: null, hasTime: false, matchedText: "" };
  if (!original) return none;

  const text = normaliseUkShorthand(original);
  const result = chrono.en.GB.parse(text, now, { forwardDate: true }).find((r) => WRITTEN.test(r.text));
  if (!result) return none;

  const hasTime = result.start.isCertain("hour");
  const date = result.start.date();
  const due = hasTime
    ? date.toISOString()
    : `${result.start.get("year") ?? date.getFullYear()}-${pad(result.start.get("month") ?? date.getMonth() + 1)}-${pad(result.start.get("day") ?? date.getDate())}`;

  let title = (text.slice(0, result.index) + " " + text.slice(result.index + result.text.length)).replace(/\s+/g, " ").trim();
  title = title.replace(DANGLING_END, "").replace(DANGLING_START, "").trim();
  return { title: title || original, due, hasTime, matchedText: result.text.trim() };
}

function londonDate(now: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function isPastDue(due: string, hasTime: boolean, now: Date = new Date()): boolean {
  if (!hasTime) return due < londonDate(now);
  const when = new Date(due).getTime();
  return Number.isFinite(when) && when < now.getTime();
}

export function offerableDue(parsed: ParsedTodo, now: Date = new Date()): ParsedTodo | null {
  if (!parsed.due) return null;
  return isPastDue(parsed.due, parsed.hasTime, now) ? null : parsed;
}
