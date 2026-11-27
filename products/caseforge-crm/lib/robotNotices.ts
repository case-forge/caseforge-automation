"use client";

import { useCallback } from "react";
import { usePolledStore } from "./polledStore";
import { createPulseSlice } from "./pulse";
import type { DetailTabId, LandingTabId } from "./detailTabs";
import { BELL_DAYS } from "./notificationRules";

export interface RobotNotice {
  notice_id: string;
  kind: string;
  title: string;
  detail: string;
  matter_id: string;
  client_name: string;
  created_utc: string;
}

export interface RobotNoticesResponse {
  count: number;
  items: RobotNotice[];
}

export function tabForNotice(kind: string): "attendance" | "caseflow" | undefined {
  if (kind === "case_moved" || kind === "caseflow_step_blocked") return "caseflow";
  return kind === "attendance_note_failed" || kind === "attendance_note_unsorted" || kind === "attendance_note_bundle_pages"
    ? "attendance"
    : undefined;
}

export const CASEFLOW_BLOCK_KINDS = ["caseflow_step_blocked", "caseflow_backlog", "job_blocked"];

export function splitNotices(items: RobotNotice[]): { blocked: RobotNotice[]; other: RobotNotice[] } {
  const blocked = items.filter((n) => CASEFLOW_BLOCK_KINDS.includes(n.kind));
  return { blocked, other: items.filter((n) => !CASEFLOW_BLOCK_KINDS.includes(n.kind)) };
}

export function noticeCode(title: string): string {
  return /\(((?:CF|JOB)-[A-Z]+-\d\d)\)/.exec(title)?.[1] ?? "";
}

const SEEN_KEY = "caseforge-client-viewer:caseflow-blocks-seen";

function seenKey(editorName: string): string {
  const name = editorName.trim().toLowerCase();
  return name ? `${SEEN_KEY}:${name}` : SEEN_KEY;
}

export function loadSeenBlocks(editorName: string): string[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(seenKey(editorName)) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function storeSeenBlocks(editorName: string, ids: string[]): void {
  try {
    window.localStorage.setItem(seenKey(editorName), JSON.stringify(ids.slice(-200)));
  } catch {

  }
}

export function unseenBlocks(blocked: RobotNotice[], seen: string[]): RobotNotice[] {
  return blocked.filter((n) => !seen.includes(n.notice_id));
}

export interface OpenClientTarget {
  matterId?: string;
  tab?: DetailTabId;

  hearingId?: number;
}

export function capRobotNotices(
  items: RobotNotice[],
  now: Date = new Date(),
  days: number = BELL_DAYS,
): { shown: RobotNotice[]; more: number } {
  const cutoff = now.getTime() - days * 86_400_000;
  const shown = items.filter((n) => {
    const t = new Date(n.created_utc).getTime();
    return Number.isNaN(t) || t >= cutoff;
  });
  return { shown, more: items.length - shown.length };
}

export function ageLabel(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.round((now.getTime() - then) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function robotButtonLabel(count: number): string {
  if (count <= 0) return "Automation notices, none waiting";
  return `Automation notices, ${count} ${count === 1 ? "needs" : "need"} a person`;
}

const noticesStore = createPulseSlice<RobotNoticesResponse>((pulse) => pulse.robot_notices);

export function useRobotNotices(): {
  data: RobotNoticesResponse | null;
  dismiss: (noticeId: string) => Promise<void>;
} {
  const { data } = usePolledStore(noticesStore);

  const dismiss = useCallback(async (noticeId: string) => {
    try {
      const res = await fetch("/api/robot-notices/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notice_id: noticeId }),
      });
      if (res.ok) noticesStore.set(await res.json());
    } catch {

    }
  }, []);

  return { data, dismiss };
}
