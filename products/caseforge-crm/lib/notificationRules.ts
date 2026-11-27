
import { bellItemTone, isSoftComplaint, obligationTone } from "./attention";
import { matchSender } from "./specialSenderRules";
import type { SpecialSender } from "./specialSenderRules";
import type { BellTone } from "./attention";
import type { AttentionItem, AttentionObligation } from "./types";
import type { IntakeItem } from "./intakeTrayTypes";
import type { StatementReply } from "./statementRepliesTypes";

export const BELL_DAYS = 3;
export const AUTO_DISMISS_DAYS = 7;

export type NotificationStatus = "bell" | "board" | "dismissed" | "hidden";
export type NotificationState = "dismissed" | "hidden" | "active";

interface Base {
  nid: string;
  category: string;
  created: string;
  matter_id: string;
  client: string;
  status: NotificationStatus;

  auto_dismissed: boolean;
  state_by: string;
  state_utc: string;
}
export type Notification = Base &
  (
    | { source: "attention"; item: AttentionItem }
    | { source: "obligation"; item: AttentionObligation }
    | { source: "statement"; item: StatementReply }
    | { source: "new_matter"; item: IntakeItem }
  );

export interface NotificationCounts {
  bell: number;
  board: number;
  dismissed: number;
  hidden: number;
}

export interface NotificationsView {
  now: string;
  bell_days: number;
  auto_dismiss_days: number;
  counts: NotificationCounts;
  bell: Notification[];
}

export interface NotificationBoardData extends NotificationsView {
  board: Notification[];
  dismissed: Notification[];
  hidden: Notification[];
}

export type BoardTab = "active" | "dismissed" | "hidden";
export const BOARD_TABS: { key: BoardTab; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "dismissed", label: "Dismissed" },
  { key: "hidden", label: "Hidden" },
];

export type BoardSide = "human" | "robot";

export function statusFor(created: string, state: NotificationState | "", now: Date = new Date()): { status: NotificationStatus; auto: boolean } {
  if (state === "dismissed") return { status: "dismissed", auto: false };
  if (state === "hidden") return { status: "hidden", auto: false };
  const then = new Date(created).getTime();
  const age = Number.isNaN(then) ? 0 : now.getTime() - then;
  const day = 86_400_000;
  if (age <= BELL_DAYS * day) return { status: "bell", auto: false };
  if (state !== "active" && age > AUTO_DISMISS_DAYS * day) return { status: "dismissed", auto: true };
  return { status: "board", auto: false };
}

const CATEGORY_WORDS: Record<string, string> = {
  complaint: "Complaint",
  soft_complaint: "Status chase",
  switchboard: "Switchboard",
  task: "Update",
  scope_creep: "Scope creep",
  settlement: "Settlement",
  new_client: "New client",
  obligation: "Aged obligation",
  counsel_accepted: "✓ Counsel accepted",
  counsel_rejected: "✕ Counsel declined",
  court_order: "✓ Court order received",
  court_rejected: "✕ Court rejected",
  statement_approved: "✓ Statement approved",
  statement_amend: "✎ Wants changes",
};

export function categoryWords(category: string): string {
  return CATEGORY_WORDS[category] ?? "Notification";
}

export function notificationTone(n: Notification): BellTone {
  switch (n.source) {
    case "attention":
      return bellItemTone(n.item);
    case "obligation":
      return obligationTone(n.item.urgency);
    case "statement":
      return n.item.state === "approved" ? "green" : "red";
    case "new_matter":
      return "green";
  }
}

export function notificationTitle(n: Notification): string {
  if (n.source === "attention") return n.item.who.trim() || n.item.subject.trim() || "Unknown sender";
  if (n.source === "obligation") return n.item.client.trim() || "Unknown client";
  return n.client.trim() || (n.matter_id ? `Matter ${n.matter_id}` : "Unknown client");
}

export function daysOld(created: string, now: Date = new Date()): number | null {
  const then = new Date(created).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((now.getTime() - then) / 86_400_000));
}

export function orderForBell(list: Notification[]): Notification[] {
  const soft = (n: Notification) => n.category === "soft_complaint" || n.category === "switchboard";
  const rest = list.filter((n) => n.category !== "complaint" && !soft(n));
  return [...list.filter((n) => n.category === "complaint"), ...rest, ...list.filter(soft)];
}

const ALWAYS_URGENT_KINDS = ["settlement", "counsel_accepted", "counsel_rejected", "court_order", "court_rejected"];

export function ringsBell(n: Notification): boolean {
  if (n.source !== "attention") return true;
  const item = n.item;
  if (item.kind === "new_client") return true;
  if (item.kind === "complaint" && !isSoftComplaint(item)) return true;
  if (ALWAYS_URGENT_KINDS.includes(item.kind)) return true;
  if ((item.label ?? "").trim().toUpperCase() === "NEW REFERRAL") return true;
  return item.importance === "high";
}

export function urgentOnly(view: NotificationsView): NotificationsView {
  const bell = view.bell.filter(ringsBell);
  const moved = view.bell.length - bell.length;
  if (moved === 0) return view;
  return { ...view, bell, counts: { ...view.counts, bell: Math.max(0, view.counts.bell - moved), board: view.counts.board + moved } };
}

export function complaintCount(list: Notification[]): number {
  return list.filter((n) => n.category === "complaint").length;
}

export function notificationsLabel(bell: number, complaints: number, older: number): string {
  if (bell === 0) return older > 0 ? `Notifications, none new, ${older} more on the board` : "Notifications, none open";
  const parts = [`${bell} new`];
  if (complaints > 0) parts.push(`${complaints} ${complaints === 1 ? "complaint" : "complaints"}`);
  if (older > 0) parts.push(`${older} more on the board`);
  return `Notifications, ${parts.join(", ")}`;
}

export function statusLine(n: Notification): string {
  if (n.status === "dismissed") {
    if (n.auto_dismissed) return `Dismissed automatically after ${AUTO_DISMISS_DAYS} days`;
    return n.state_by ? `Dismissed by ${n.state_by}` : "Dismissed";
  }
  if (n.status === "hidden") return n.state_by ? `Hidden by ${n.state_by}` : "Hidden";
  return "";
}

export function specialSender(n: Notification, senders: SpecialSender[]): { sender: SpecialSender; rank: number } | null {
  return matchSender(senders, { senderDomain: n.source === "attention" ? n.item.sender_domain : undefined, newClient: n.category === "new_client" });
}

export type NotificationSort = "newest" | "special" | "category";
export const NOTIFICATION_SORTS: { key: NotificationSort; label: string }[] = [
  { key: "newest", label: "Newest first" },
  { key: "special", label: "Special senders first" },
  { key: "category", label: "Category" },
];

function newestFirst(a: Notification, b: Notification): number {
  const x = new Date(a.created).getTime();
  const y = new Date(b.created).getTime();
  return (Number.isNaN(y) ? 0 : y) - (Number.isNaN(x) ? 0 : x);
}

export function sortNotifications(rows: Notification[], sort: NotificationSort, senders: SpecialSender[] = []): Notification[] {
  const out = [...rows];
  if (sort === "special") {
    const rank = (n: Notification) => specialSender(n, senders)?.rank ?? senders.length;
    return out.sort((a, b) => rank(a) - rank(b) || newestFirst(a, b));
  }
  if (sort === "category") return out.sort((a, b) => categoryWords(a.category).localeCompare(categoryWords(b.category), "en-GB") || newestFirst(a, b));
  return out.sort(newestFirst);
}

export function boardRows(data: NotificationBoardData | null, tab: BoardTab, filter = "", sort: NotificationSort = "newest", senders: SpecialSender[] = []): Notification[] {
  if (!data) return [];
  const rows = tab === "active" ? data.board : tab === "dismissed" ? data.dismissed : data.hidden;
  const wanted = filter.trim().toLowerCase();
  const shown = !wanted ? rows : rows.filter((n) => notificationTitle(n).toLowerCase().includes(wanted) || n.matter_id.includes(wanted) || n.client.toLowerCase().includes(wanted));
  return sortNotifications(shown, sort, senders);
}

export function tabCount(data: NotificationBoardData | null, tab: BoardTab): number {
  if (!data) return 0;
  return tab === "active" ? data.counts.board : tab === "dismissed" ? data.counts.dismissed : data.counts.hidden;
}

export function rowActions(status: NotificationStatus): { label: string; state: NotificationState; title: string }[] {
  const dismiss = { label: "Dismiss", state: "dismissed" as const, title: "Dealt with: take it off your bell. It stays on the board under Dismissed. Nothing is sent or deleted." };
  const hide = { label: "Hide", state: "hidden" as const, title: "Out of the way for now: take it off your bell. It stays on the board under Hidden." };
  const putBack = { label: "Put back", state: "active" as const, title: "Return it to your bell or the board's Active list." };
  if (status === "dismissed") return [putBack, { ...hide }];
  if (status === "hidden") return [putBack, { ...dismiss }];
  return [dismiss, hide];
}

export function withoutNotification(view: NotificationsView, nid: string, to: NotificationState): NotificationsView {
  const gone = view.bell.find((n) => n.nid === nid);
  if (!gone) return view;
  const counts = { ...view.counts, bell: Math.max(0, view.counts.bell - 1) };
  if (to === "dismissed") counts.dismissed += 1;
  else if (to === "hidden") counts.hidden += 1;
  else counts.board += 1;
  return { ...view, counts, bell: view.bell.filter((n) => n.nid !== nid) };
}
