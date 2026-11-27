
import { AUTO_DISMISS_DAYS, statusFor } from "./notificationRules";
import type { Notification, NotificationBoardData, NotificationState, NotificationsView } from "./notificationRules";
import type { OpsAlert, RobotBoardData } from "./notifications";
import { stubAttention } from "./stubAttention";
import { stubRecentIntakes } from "./stubIntakeTray";
import { stubRobotNotices } from "./stubRobot";
import { stubStatementReplies } from "./stubStatementReplies";

const states = new Map<string, { state: NotificationState; by: string; at: string }>();

export function stubSetNotificationState(nid: string, state: string, by: string): { nid: string; state: string } | { error: string } {
  if (state !== "dismissed" && state !== "hidden" && state !== "active") return { error: "state must be one of dismissed, hidden, active" };
  if (!nid.trim()) return { error: "nid is required" };
  states.set(nid, { state, by: by.trim(), at: new Date().toISOString() });
  return { nid, state };
}

type Unplaced = Omit<Notification, "status" | "auto_dismissed" | "state_by" | "state_utc">;

function collect(): Unplaced[] {
  const out: Unplaced[] = [];
  const att = stubAttention();
  const buckets = [att.red, att.yellow, att.green, att.scope_creep ?? [], att.counsel_accepted ?? [], att.counsel_rejected ?? [], att.court_order ?? [], att.court_rejected ?? []];
  for (const row of buckets.flat()) {
    out.push({ nid: `t:${row.task_id}`, source: "attention", category: row.kind === "update" ? "task" : row.kind, created: row.created, matter_id: row.matter_id, client: row.who, item: row });
  }
  for (const row of att.obligations ?? []) {
    out.push({
      nid: `o:${row.matter_id}:${row.label}`,
      source: "obligation",
      category: "obligation",
      created: new Date(Date.now() - 2 * 86_400_000).toISOString(),
      matter_id: String(row.matter_id ?? ""),
      client: row.client,
      item: row,
    });
  }
  for (const row of stubStatementReplies().items) {
    out.push({
      nid: `s:${row.matter_id}:${row.state}:${row.recorded_utc}`,
      source: "statement",
      category: row.state === "approved" ? "statement_approved" : "statement_amend",
      created: row.recorded_utc,
      matter_id: row.matter_id,
      client: row.client_name,
      item: row,
    });
  }
  for (const row of stubRecentIntakes()) {
    out.push({ nid: `n:${row.matter_id}`, source: "new_matter", category: "new_client", created: row.created_utc, matter_id: row.matter_id, client: row.client_name, item: row });
  }
  return out;
}

export function stubNotificationBoard(): NotificationBoardData {
  const now = new Date();
  const all = collect().map((n): Notification => {
    const kept = states.get(n.nid);
    const { status, auto } = statusFor(n.created, kept?.state ?? "", now);
    return { ...n, status, auto_dismissed: auto, state_by: kept?.by ?? (auto ? "automatic" : ""), state_utc: kept?.at ?? "" } as Notification;
  });
  all.sort((a, b) => b.created.localeCompare(a.created));
  const of = (status: string) => all.filter((n) => n.status === status);
  return {
    now: now.toISOString(),
    bell_days: 3,
    auto_dismiss_days: AUTO_DISMISS_DAYS,
    counts: { bell: of("bell").length, board: of("board").length, dismissed: of("dismissed").length, hidden: of("hidden").length },
    bell: of("bell"),
    board: of("board"),
    dismissed: of("dismissed"),
    hidden: of("hidden"),
  };
}

export function stubNotifications(): NotificationsView {
  const { now, bell_days, auto_dismiss_days, counts, bell } = stubNotificationBoard();
  return { now, bell_days, auto_dismiss_days, counts, bell };
}

export function stubRobotBoard(): RobotBoardData {
  const alerts: OpsAlert[] = [
    { severity: "amber", category: "health", title: "A demo job has not run for 2 days", next_action: "Run the demo job by hand.", kind: "state", age_minutes: 2880 },
  ];
  return {
    open: stubRobotNotices().items,
    resolved: [],
    ops: { admin: true, available: true, stale: false, overall_severity: "amber", generated_at: new Date().toISOString(), alerts },
  };
}
