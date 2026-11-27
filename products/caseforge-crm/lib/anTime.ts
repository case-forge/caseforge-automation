
export interface AnTime {
  hours: string;
  minutes: string;
}

const KEY = "caseforge-client-viewer:an-time-default";
export const SERVER_DEFAULT_MINUTES = 24;

export function totalMinutes(time: AnTime): number | null {
  const h = time.hours.trim() === "" ? 0 : Number(time.hours);
  const m = time.minutes.trim() === "" ? 0 : Number(time.minutes);
  if (!Number.isInteger(h) || !Number.isInteger(m)) return null;
  if (h < 0 || h > 99 || m < 0 || m > 59) return null;
  const total = h * 60 + m;
  return total >= 1 ? total : null;
}

export function timeFromMinutes(total: number | null | undefined): AnTime {
  if (typeof total !== "number" || !Number.isInteger(total) || total < 1 || total > 99 * 60 + 59) return { hours: "", minutes: "" };
  return { hours: String(Math.floor(total / 60)), minutes: String(total % 60) };
}

export function formatTimeSpent(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  const mins = `${String(m).padStart(2, "0")} mins`;
  return h >= 1 ? `${h} ${h === 1 ? "hour" : "hours"} ${mins}` : mins;
}

export const MIN_NOTE_MINUTES = 6;

export function minutesForPages(pages: number, perPage: number): number | null {
  if (!Number.isInteger(pages) || pages < 1 || !Number.isInteger(perPage) || perPage < 1) return null;
  const total = Math.max(pages * perPage, MIN_NOTE_MINUTES);
  return total <= 99 * 60 + 59 ? total : null;
}

export function loadDefaultTime(): AnTime | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AnTime>;
    const time = { hours: String(parsed.hours ?? ""), minutes: String(parsed.minutes ?? "") };
    return totalMinutes(time) === null ? null : time;
  } catch {
    return null;
  }
}

export function saveDefaultTime(time: AnTime): void {
  if (typeof window === "undefined") return;
  try {
    if (totalMinutes(time) === null) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, JSON.stringify(time));
  } catch {

  }
}
