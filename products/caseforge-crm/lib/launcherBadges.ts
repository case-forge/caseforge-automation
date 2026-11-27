
import { londonYmd } from "./boardCompact";
import { parseUtc } from "./matterTasks";
import { withoutDismissed } from "./autoSend";
import type { AutoSendItem } from "./autoSend";
import type { StatusBoardItem } from "./matterMilestones";
import type { WhatsNewItem } from "./whatsNew";

export const CANCELLED_BADGE_WINDOW_MS = 24 * 60 * 60 * 1000;

export type BadgeTone = "accent" | "solid";
export interface Badge {
  count: number;
  tone: BadgeTone;

  meaning: string;
}

export function wetransferBadge(items: readonly Pick<StatusBoardItem, "wetransfer_pending">[]): Badge | null {
  const count = items.filter((i) => i.wetransfer_pending === true).length;
  return count > 0 ? { count, tone: "accent", meaning: `${count} WeTransfer permission${count === 1 ? "" : "s"} needed` } : null;
}

export function recentlyStopped(item: Pick<AutoSendItem, "stopped_utc">, now: Date): boolean {
  const t = parseUtc(item.stopped_utc);
  return !Number.isNaN(t) && now.getTime() - t <= CANCELLED_BADGE_WINDOW_MS;
}

export function autoSendBadge(all: readonly AutoSendItem[], now: Date = new Date()): Badge | null {
  const items = withoutDismissed(all);
  const cancelled = items.filter((i) => i.state === "cancelled" && recentlyStopped(i, now)).length;
  if (cancelled > 0) return { count: cancelled, tone: "solid", meaning: `${cancelled} cancelled` };
  const soon = items.filter((i) => i.state === "leaving_soon").length;
  return soon > 0 ? { count: soon, tone: "accent", meaning: `${soon} leaving soon` } : null;
}

export function whatsNewTodayBadge(items: readonly Pick<WhatsNewItem, "date">[], now: Date = new Date()): Badge | null {
  const today = londonYmd(now.toISOString());
  if (!today) return null;
  const count = items.filter((i) => {
    const d = londonYmd(i.date);
    return d !== null && d[0] === today[0] && d[1] === today[1] && d[2] === today[2];
  }).length;
  return count > 0 ? { count, tone: "accent", meaning: `${count} new today` } : null;
}

export function badgedName(label: string, badge: Badge | null): string {
  return badge ? `${label}, ${badge.meaning}` : label;
}

export function tabsBadge(count: number): Badge | null {
  return count > 0 ? { count, tone: "accent", meaning: `${count} open tab${count === 1 ? "" : "s"}` } : null;
}
