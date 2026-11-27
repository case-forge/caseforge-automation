import { parseUtc } from "./matterTasks";
import type { StatusBoardItem } from "./matterMilestones";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

export const COMPACT_ROWS = 7;

export const NEW_DAYS = 3;

const LONDON_YMD = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit" });

export function londonYmd(iso: string): [number, number, number] | null {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) {
    const [y, m, d] = iso.split("-").map(Number);
    return [y, m, d];
  }
  const ms = parseUtc(iso);
  if (Number.isNaN(ms)) return null;
  const [y, m, d] = LONDON_YMD.format(new Date(ms)).split("-").map(Number);
  return [y, m, d];
}

export function formatBoardDay(iso: string): string {
  const ymd = londonYmd(iso);
  if (!ymd) return "";
  const [y, m, d] = ymd;
  const weekday = new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay();
  return `${String(d).padStart(2, "0")} ${MONTHS[m - 1]} (${DAYS[weekday]})`;
}

export const COMPACT_COLUMNS: readonly { key: string; label: string; value: (i: StatusBoardItem) => string }[] = [
  { key: "referred", label: "Referred", value: (i) => i.date_joined },
  { key: "contacted", label: "Contacted", value: (i) => i.milestones.contacted ?? "" },
  { key: "ws", label: "WS Signed", value: (i) => i.initial_ws },
  { key: "filed", label: "Filed to Court", value: (i) => i.milestones.filed ?? "" },
  { key: "service_requested", label: "Service Requested", value: (i) => i.milestones.service_requested ?? "" },
  { key: "served", label: "Served", value: (i) => i.milestones.served ?? "" },
  { key: "laa_final", label: "LAA Final Cert", value: (i) => i.milestones.laa_final_cert ?? "" },
];

export function recentItems(items: readonly StatusBoardItem[], limit: number = COMPACT_ROWS): StatusBoardItem[] {

  const key = (i: StatusBoardItem) => {
    const ymd = londonYmd(i.date_joined);
    return ymd ? `${ymd[0]}-${String(ymd[1]).padStart(2, "0")}-${String(ymd[2]).padStart(2, "0")}` : "";
  };
  return [...items]
    .sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : a.client_name.localeCompare(b.client_name, "en-GB", { numeric: true })))
    .slice(0, limit);
}

export function isNewReferral(item: StatusBoardItem, now: Date = new Date()): boolean {
  const ymd = londonYmd(item.date_joined);
  const today = londonYmd(now.toISOString());
  if (!ymd || !today) return false;
  const age = (Date.UTC(today[0], today[1] - 1, today[2]) - Date.UTC(ymd[0], ymd[1] - 1, ymd[2])) / 86_400_000;
  return age >= 0 && age <= NEW_DAYS;
}

export const LEAVING_DAYS = 5;

const dayNumber = (ymd: [number, number, number]): number => Date.UTC(ymd[0], ymd[1] - 1, ymd[2]) / 86_400_000;

export function finishDay(item: StatusBoardItem): number | null {
  let latest: number | null = null;
  for (const c of COMPACT_COLUMNS) {
    if (c.key === "service_requested" || c.key === "served") continue;
    const ymd = londonYmd(c.value(item));
    if (!ymd) return null;
    const n = dayNumber(ymd);
    if (latest === null || n > latest) latest = n;
  }
  return latest;
}

export function finishState(item: StatusBoardItem, now: Date = new Date()): "" | "leaving" | "gone" {
  const done = finishDay(item);
  const today = londonYmd(now.toISOString());
  if (done === null || !today) return "";
  return dayNumber(today) - done > LEAVING_DAYS ? "gone" : "leaving";
}

export function awaitingSignature(item: { initial_ws?: string; milestones?: { contacted?: string } }): boolean {
  return Boolean(item.milestones?.contacted) && !item.initial_ws;
}

export function daysWaiting(item: Pick<StatusBoardItem, "initial_ws" | "milestones">, now: Date = new Date()): number | null {
  if (!awaitingSignature(item)) return null;
  const since = londonYmd(item.milestones.contacted ?? "");
  const today = londonYmd(now.toISOString());
  if (!since || !today) return null;
  return Math.max(0, dayNumber(today) - dayNumber(since));
}

export function waitingLabel(days: number): string {
  if (days <= 0) return "Waiting since today";
  return `Waiting ${days} day${days === 1 ? "" : "s"}`;
}

export const BOARD_DAYS = 30;

export function boardAge(item: Pick<StatusBoardItem, "date_joined" | "milestones">, now: Date = new Date()): number | null {
  const since = londonYmd(item.milestones?.contacted || item.date_joined || "");
  const today = londonYmd(now.toISOString());
  if (!since || !today) return null;
  return dayNumber(today) - dayNumber(since);
}

export function boardRows(items: readonly StatusBoardItem[], now: Date = new Date(), limit: number = COMPACT_ROWS): StatusBoardItem[] {
  const kept = items.filter((i) => {
    const age = boardAge(i, now);
    return age !== null && age <= BOARD_DAYS && finishState(i, now) !== "gone";
  });
  const newest = recentItems(kept, limit);
  const carried = kept.filter((i) => awaitingSignature(i) && !newest.includes(i));
  return recentItems([...newest, ...carried], Number.POSITIVE_INFINITY);
}
