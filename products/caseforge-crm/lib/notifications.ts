"use client";

import { usePolledStore } from "./polledStore";
import { createPulseSlice, pulseStore } from "./pulse";
import { backgroundFetch } from "./loadingBar";
import { withoutNotification } from "./notificationRules";
import type { NotificationBoardData, NotificationState, NotificationsView } from "./notificationRules";
import type { RobotNotice } from "./robotNotices";

export * from "./notificationRules";

const notificationsStore = createPulseSlice<NotificationsView>((pulse) => pulse.notifications);

export function useNotifications(): NotificationsView | null {
  return usePolledStore(notificationsStore).data;
}

export async function setNotificationState(nid: string, state: NotificationState): Promise<void> {
  const res = await fetch("/api/notifications/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nid, state }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body?.error === "string" && body.error ? body.error : "Could not save that.");
  }
  const current = notificationsStore.getSnapshot();
  if (current) notificationsStore.set(withoutNotification(current, nid, state));
  pulseStore.refresh();
}

export async function fetchNotificationBoard(): Promise<NotificationBoardData> {
  const res = await backgroundFetch("/api/notifications?scope=board", { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body?.error === "string" && body.error ? body.error : "Could not read the Notification board.");
  }
  return res.json();
}

export interface RobotBoardNotice extends RobotNotice {
  resolved_utc?: string;
  resolved_by?: string;
}

export interface OpsAlert {
  severity: string;
  category: string;
  title: string;
  next_action: string;
  kind: string;
  age_minutes: number | null;
}

export interface RobotBoardData {
  open: RobotBoardNotice[];
  resolved: RobotBoardNotice[];
  ops: { admin: boolean; available: boolean; stale: boolean; overall_severity: string; generated_at: string; alerts: OpsAlert[] };
}

export async function fetchRobotBoard(): Promise<RobotBoardData> {
  const res = await backgroundFetch("/api/notifications/robot", { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body?.error === "string" && body.error ? body.error : "Could not read the Automation notices.");
  }
  return res.json();
}

export function opsFreshness(ops: RobotBoardData["ops"]): string {
  if (!ops.admin) return "System health alerts are shown to administrators only.";
  if (!ops.available) return "The system health snapshot could not be read.";
  return ops.stale ? "The last system health check is out of date." : `System health is ${ops.overall_severity}.`;
}
