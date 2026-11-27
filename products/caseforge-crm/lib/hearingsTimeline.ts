
import { compareHearings, isActive, isValidIsoDate, normaliseTime } from "./hearings";
import type { Hearing } from "./hearings";
import { newestFirst, parseUtc } from "./matterTasks";
import type { MatterTaskItem } from "./types";

export type TimelineEntry =
  | { kind: "hearing"; key: string; at: number; hearing: Hearing }
  | { kind: "update"; key: string; at: number; item: MatterTaskItem };

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

function londonWallClockMs(y: number, mo: number, d: number, h: number, mi: number, s: number, ms: number): number {
  const guess = Date.UTC(y, mo - 1, d, h, mi, s, ms);
  const p = Object.fromEntries(LONDON_PARTS.formatToParts(new Date(guess)).map((part) => [part.type, Number(part.value)]));
  const shownAsUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second, ms);
  return guess - (shownAsUtc - guess);
}

export function hearingInstantMs(hearing: Pick<Hearing, "hearing_date" | "hearing_time">): number {
  if (!isValidIsoDate(hearing.hearing_date)) return Number.NEGATIVE_INFINITY;
  const [y, mo, d] = hearing.hearing_date.split("-").map(Number);
  const time = normaliseTime(hearing.hearing_time);
  if (!time) return londonWallClockMs(y, mo, d, 23, 59, 59, 999);
  const [h, mi] = time.split(":").map(Number);
  return londonWallClockMs(y, mo, d, h, mi, 0, 0);
}

export function hearingsAndUpdates(hearings: Hearing[], items: MatterTaskItem[]): TimelineEntry[] {
  const entries: TimelineEntry[] = [
    ...hearings
      .filter(isActive)
      .sort((a, b) => compareHearings(b, a))
      .map((hearing): TimelineEntry => ({ kind: "hearing", key: `hearing-${hearing.hearing_id}`, at: hearingInstantMs(hearing), hearing })),
    ...newestFirst(items).map((item): TimelineEntry => {
      const ms = parseUtc(item.created);
      return { kind: "update", key: `update-${item.task_id}`, at: Number.isNaN(ms) ? Number.NEGATIVE_INFINITY : ms, item };
    }),
  ];
  return entries
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => (a.entry.at === b.entry.at ? a.index - b.index : b.entry.at > a.entry.at ? 1 : -1))
    .map(({ entry }) => entry);
}
