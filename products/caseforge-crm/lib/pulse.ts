
import { backgroundFetch } from "./loadingBar";
import { createPolledStore } from "./polledStore";
import type { PolledStore } from "./polledStore";
import type { AttentionResponse } from "./types";
import type { RobotNoticesResponse } from "./robotNotices";
import type { StatementReplies } from "./statementRepliesTypes";
import type { NotificationsView } from "./notificationRules";

export interface Pulse {
  attention?: AttentionResponse | null;
  flag_counts?: { counts?: { flagged?: number; starred?: number } } | null;
  robot_notices?: RobotNoticesResponse | null;
  statement_replies?: StatementReplies | null;

  notifications?: NotificationsView | null;

  pending_new_clients?: { unsent: number; overdue?: number; waiting: number } | null;

  errors?: string[];
}

export const PULSE_MS = 60_000;

const REFRESH_EVENTS = ["caseforge:flags-changed", "caseforge:robot-notices-changed", "caseforge:statement-replies-changed"];

export async function fetchPulse(): Promise<Pulse> {
  const res = await backgroundFetch("/api/pulse", { cache: "no-store" });
  if (!res.ok) throw new Error("Could not load the notifications.");
  return res.json();
}

export const pulseStore = createPolledStore<Pulse>({ fetch: fetchPulse, intervalMs: PULSE_MS, events: REFRESH_EVENTS });

export function createPulseSlice<T>(select: (pulse: Pulse) => T | null | undefined): PolledStore<T> {
  let lastPulse: Pulse | null = null;
  let lastValue: T | null = null;
  let override: { pulse: Pulse | null; value: T } | null = null;

  function current(): T | null {
    const pulse = pulseStore.getSnapshot();
    if (override && override.pulse === pulse) return override.value;
    if (pulse !== lastPulse) {
      lastPulse = pulse;
      const picked = pulse ? select(pulse) : null;
      if (picked !== null && picked !== undefined) lastValue = picked;
    }
    return lastValue;
  }

  return {
    subscribe: pulseStore.subscribe,
    getSnapshot: current,
    refresh: pulseStore.refresh,
    set(next: T) {
      override = { pulse: pulseStore.getSnapshot(), value: next };
      pulseStore.set(pulseStore.getSnapshot() ?? {});
    },
  };
}
