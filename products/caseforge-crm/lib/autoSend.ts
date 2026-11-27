import { parseUtc } from "./matterTasks";

export type AutoSendState = "leaving_soon" | "left" | "cancelled" | "blocked";

export interface AutoSendItem {
  id: string;
  matter_id: string;
  client_name: string;
  subject: string;
  recipients: string[];

  class: string;
  state: AutoSendState;
  armed_utc: string;
  leaves_utc: string;
  sent_utc: string;
  stopped_utc: string;
  stopped_reason: string;
  body_text: string;

  outlook_link: string;

  sharepoint_link: string;

  dismissed?: boolean;
}

export interface AutoSendResponse {
  items: AutoSendItem[];
}

export const TABS: readonly { state: AutoSendState; label: string }[] = [
  { state: "leaving_soon", label: "Leaving soon" },
  { state: "left", label: "Left" },
  { state: "cancelled", label: "Cancelled" },
  { state: "blocked", label: "Blocked" },
];

export const EMPTY_LINE = "Nothing here.";
export const UNAVAILABLE_LINE = "Auto Send is not available yet.";

export function rowTime(item: AutoSendItem): string {
  return item.state === "leaving_soon" ? item.leaves_utc : item.state === "left" ? item.sent_utc : item.stopped_utc;
}

export function groupItems(items: readonly AutoSendItem[]): Record<AutoSendState, AutoSendItem[]> {
  const groups: Record<AutoSendState, AutoSendItem[]> = { leaving_soon: [], left: [], cancelled: [], blocked: [] };
  for (const item of items.filter((i) => !i.dismissed)) groups[item.state]?.push(item);
  const ms = (i: AutoSendItem) => {
    const t = parseUtc(rowTime(i));
    return Number.isNaN(t) ? 0 : t;
  };
  groups.leaving_soon.sort((a, b) => ms(a) - ms(b));
  groups.left.sort((a, b) => ms(b) - ms(a));
  groups.cancelled.sort((a, b) => ms(b) - ms(a));
  groups.blocked.sort((a, b) => ms(b) - ms(a));
  return groups;
}

export function minutesLeft(leavesUtc: string, now: Date = new Date()): number | null {
  const t = parseUtc(leavesUtc);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.ceil((t - now.getTime()) / 60_000));
}

export function leavesLabel(leavesUtc: string, now: Date = new Date()): string {
  const m = minutesLeft(leavesUtc, now);
  if (m === null) return "";
  return m === 0 ? "Leaving now" : `Leaves in ${m} min`;
}

const LONDON = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });

export function clockLabel(iso: string): string {
  const t = parseUtc(iso);
  if (Number.isNaN(t)) return "";
  return LONDON.format(new Date(t)).replace(/^(\d{2} \w{3}),? /, "$1, ");
}

export const LONG_HOLD_MINUTES = 90;

const LONDON_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit" });
const LONDON_TIME = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", hour12: false });

export function longHoldLabel(leavesUtc: string, now: Date = new Date()): string {
  const t = parseUtc(leavesUtc);
  if (Number.isNaN(t)) return "";
  const when = new Date(t);
  const time = LONDON_TIME.format(when);
  const day = LONDON_DAY.format(when);
  if (day === LONDON_DAY.format(now)) return `Leaves at ${time}`;
  if (day === LONDON_DAY.format(new Date(now.getTime() + 86_400_000))) return `Leaves tomorrow at ${time}`;
  return `Leaves ${clockLabel(leavesUtc).replace(/, \d{2}:\d{2}$/, "")} at ${time}`;
}

export function stateLabel(item: AutoSendItem, now: Date = new Date()): string {
  if (item.state === "leaving_soon") {
    const mins = minutesLeft(item.leaves_utc, now);
    if (mins !== null && mins > LONG_HOLD_MINUTES) return longHoldLabel(item.leaves_utc, now);
    const left = leavesLabel(item.leaves_utc, now);
    const at = clockLabel(item.leaves_utc);
    return [left, at && `at ${at}`].filter(Boolean).join(", ");
  }
  if (item.state === "left") return item.sent_utc ? `Sent ${clockLabel(item.sent_utc)}` : "Sent";
  const when = clockLabel(item.stopped_utc);
  if (item.state === "blocked") return [(item.stopped_reason || "Not armed").replace(/\.$/, ""), when && `since ${when}`].filter(Boolean).join(", ");
  return [item.stopped_reason || "Cancelled", when && `stopped ${when}`].filter(Boolean).join(", ");
}

export function tabLabel(label: string, count: number): string {
  return `${label} (${count})`;
}

export function safeLink(href: string): string {
  return /^https:\/\//i.test(href || "") ? href : "";
}

export function parseResponse(body: unknown): AutoSendItem[] {
  const items = (body as { items?: unknown } | null)?.items;
  if (!Array.isArray(items)) return [];
  return items.filter((i): i is AutoSendItem => !!i && typeof i === "object" && ["leaving_soon", "left", "cancelled", "blocked"].includes((i as AutoSendItem).state));
}

export const canDismiss = (item: Pick<AutoSendItem, "state">): boolean => item.state === "cancelled";

export function withoutDismissed<T extends Pick<AutoSendItem, "id" | "dismissed">>(items: readonly T[], hiddenHere: ReadonlySet<string> = new Set()): T[] {
  return items.filter((i) => !i.dismissed && !hiddenHere.has(i.id));
}

export const dismissLabel = (subject: string): string => `Dismiss ${subject}`;
export const DISMISS_HINT = "Hides this row. The draft in Outlook is not touched.";
export const DISMISS_FAILED_LINE = "That row could not be dismissed. It is still here.";

export const AUTO_SEND_CHANGED = "caseforge:auto-send-changed";

export function forMatter(items: readonly AutoSendItem[], matterId: string): AutoSendItem[] {
  return items.filter((i) => i.matter_id === matterId);
}
