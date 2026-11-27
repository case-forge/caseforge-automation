
import * as chrono from "chrono-node";

export interface DetectedHearing {

  date: string;

  time: string | null;

  matchedText: string;

  court: string;
}

const VAGUE_SPAN = /\b(week|month|year|fortnight)s?\b/i;

const WRITTEN_DATE_WORDS =
  /\d|\b(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b/i;

function isWrittenDate(result: chrono.ParsedResult): boolean {
  return WRITTEN_DATE_WORDS.test(result.text);
}
const LEADING_NOISE = new Set(["called", "spoke", "rang", "phoned", "emailed", "contacted", "attended", "at", "to", "with", "advised", "the", "of"]);
const COURT_RE = /((?:[A-Z][A-Za-z']+\s+){0,2}[A-Z][A-Za-z']+\s+(?:County|Magistrates'?|Family|Crown|High)\s+Court)/g;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function detectCourt(text: string): string {
  const match = COURT_RE.exec(text);
  COURT_RE.lastIndex = 0;
  if (!match) return "";
  const words = match[1].split(/\s+/);
  while (words.length > 3 && LEADING_NOISE.has(words[0].toLowerCase())) words.shift();
  while (words.length > 0 && LEADING_NOISE.has(words[0].toLowerCase())) words.shift();
  return words.join(" ");
}

function timeFrom(results: chrono.ParsedResult[]): string | null {
  for (const result of results) {
    if (!isWrittenDate(result)) continue;
    if (result.start.isCertain("hour")) {
      const minute = result.start.isCertain("minute") ? result.start.get("minute") ?? 0 : 0;
      return `${pad(result.start.get("hour") ?? 0)}:${pad(minute)}`;
    }
  }
  return null;
}

function isoOf(result: chrono.ParsedResult): string | null {
  const year = result.start.get("year");
  const month = result.start.get("month");
  const day = result.start.get("day");
  if (year == null || month == null || day == null) return null;
  return `${year}-${pad(month)}-${pad(day)}`;
}

export function normaliseUkShorthand(text: string): string {
  return text
    .replace(/\b(\d{1,2})\.(\d{1,2})\.(\d{2})\b(?!\d)/g, "$1/$2/20$3")
    .replace(/\b(\d{1,2})\.(\d{2})\s*([ap]m)\b/gi, "$1:$2$3");
}

export function detectHearing(rawText: string, todayIso: string, now: Date = new Date()): DetectedHearing | null {
  const text = normaliseUkShorthand(rawText);
  if (!text.trim()) return null;

  const plain = chrono.en.GB.parse(text, now);
  const forward = chrono.en.GB.parse(text, now, { forwardDate: true });
  const time = timeFrom(forward);

  const candidates: { index: number; date: string; matchedText: string }[] = [];
  for (const result of plain) {
    if (!(result.start.isCertain("day") && result.start.isCertain("month"))) continue;
    if (VAGUE_SPAN.test(result.text) || !isWrittenDate(result)) continue;
    const date = isoOf(result);
    if (date) candidates.push({ index: result.index, date, matchedText: result.text.trim() });
  }
  for (const result of forward) {
    const explicit = result.start.isCertain("day") && result.start.isCertain("month");
    if (explicit || !result.start.isCertain("weekday")) continue;
    if (VAGUE_SPAN.test(result.text) || !isWrittenDate(result)) continue;
    const date = isoOf(result);
    if (date) candidates.push({ index: result.index, date, matchedText: result.text.trim() });
  }

  candidates.sort((a, b) => a.index - b.index);
  const upcoming = candidates.find((c) => c.date >= todayIso);
  if (!upcoming) return null;
  return { date: upcoming.date, time, matchedText: upcoming.matchedText, court: detectCourt(rawText) };
}

export interface ListedHearing {
  hearing_id: number;
  hearing_date: string;
  hearing_time: string | null;
  status: string;
}

function hhmm(time: string | null | undefined): string | null {
  const m = /^(\d{1,2}):(\d{2})/.exec(time ?? "");
  return m ? `${m[1].padStart(2, "0")}:${m[2]}` : null;
}

export function listedHearingsFor<T extends ListedHearing>(hearings: readonly T[], detected: Pick<DetectedHearing, "date" | "time">): T[] {
  const wanted = hhmm(detected.time);
  return hearings.filter(
    (h) =>
      h.status === "scheduled" &&
      h.hearing_date === detected.date &&
      (wanted === null || hhmm(h.hearing_time) === wanted),
  );
}
