
import { offerableDue, parseTodoText } from "./todoDates";

export interface AnTodoDraft {
  title: string;

  due: string;
  dueHasTime: boolean;
}

const FALLBACK_TITLE = "Follow up from attendance note";
const MAX_TITLE = 120;

function londonDate(instant: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit" }).format(instant);
}

export function sentenceAround(noteText: string, matchedText: string): string {
  const flat = noteText.replace(/\r/g, "");
  const at = matchedText ? flat.toLowerCase().indexOf(matchedText.toLowerCase()) : -1;
  if (at < 0) return "";
  let start = at;
  while (start > 0 && !/[\n.!?]/.test(flat[start - 1])) start -= 1;
  let end = at + matchedText.length;
  while (end < flat.length && !/[\n.!?]/.test(flat[end])) end += 1;
  return flat.slice(start, end).replace(/\s+/g, " ").trim();
}

export function buildAnTodo(
  noteText: string,
  detected: { date: string; matchedText: string },
  now: Date = new Date(),
): AnTodoDraft | null {
  const sentence = sentenceAround(noteText, detected.matchedText);
  const parsed = sentence ? parseTodoText(sentence, now) : null;
  let title = parsed && parsed.due ? parsed.title : sentence;
  title = title.replace(/\s+/g, " ").trim();
  if (title.length > MAX_TITLE) title = `${title.slice(0, MAX_TITLE - 1).trimEnd()}…`;
  if (!title) title = FALLBACK_TITLE;

  const timed = parsed && parsed.due && parsed.hasTime && londonDate(new Date(parsed.due)) === detected.date ? parsed : null;
  const draft: AnTodoDraft = timed
    ? { title, due: timed.due!, dueHasTime: true }
    : { title, due: detected.date, dueHasTime: false };
  return offerableDue({ title, due: draft.due, hasTime: draft.dueHasTime, matchedText: detected.matchedText }, now) ? draft : null;
}

export interface MarkedTodo {

  key: string;
  title: string;

  due: string | null;
  dueHasTime: boolean;
}

const TODO_MARKER = /(?:^|[\n.!?])[ \t]*(?:to[\s-]?do|todo)s?\b(?!\s+with\b)[ \t]*(?:list\b)?[ \t]*[:\-\u2013\u2014]?[ \t]*/gi;
const BULLET = /^\s*(?:[-•*\u2013\u2014]|\d{1,2}[.)])\s+/;
const MAX_MARKED = 10;

export function buildMarkedTodos(noteText: string, now: Date = new Date()): MarkedTodo[] {
  const text = noteText.replace(/\r/g, "");
  const out: MarkedTodo[] = [];
  const seen = new Set<string>();
  for (const match of text.matchAll(TODO_MARKER)) {
    const start = (match.index ?? 0) + match[0].length;
    const lines = text.slice(start).split("\n");
    const pieces: string[] = [];
    pieces.push(...lines[0].split(";"));
    for (const line of lines.slice(1)) {
      if (!BULLET.test(line)) break;
      pieces.push(...line.replace(BULLET, "").split(";"));
    }
    for (const piece of pieces) {
      const item = piece.replace(BULLET, "").replace(/\s+/g, " ").replace(/[\s.,]+$/, "").trim();
      if (item.length < 3) continue;
      const parsed = parseTodoText(item, now);
      const dated = offerableDue(parsed, now);
      let title = (dated ? dated.title : item).replace(/\s+/g, " ").trim();
      if (!title) title = item;
      if (title.length > MAX_TITLE) title = `${title.slice(0, MAX_TITLE - 1).trimEnd()}…`;
      const key = title.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ key, title, due: dated ? dated.due : null, dueHasTime: dated ? dated.hasTime : false });
      if (out.length >= MAX_MARKED) return out;
    }
  }
  return out;
}
