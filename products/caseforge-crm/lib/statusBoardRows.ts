"use client";

import { useSyncExternalStore } from "react";
import type { StatusBoardItem, StatusBoardResponse } from "./matterMilestones";
import { startVisiblePoll } from "./visiblePoll";

export const ROWS_POLL_MS = 60_000;

let rows: StatusBoardItem[] | null = null;
let stopPoll: (() => void) | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

export async function refreshStatusBoardRows(): Promise<void> {
  try {
    const res = await fetch("/api/status-board", { cache: "no-store" });
    if (!res.ok) return;
    const body = (await res.json()) as StatusBoardResponse;
    rows = Array.isArray(body.items) ? body.items : [];
    emit();
  } catch {

  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (!stopPoll && typeof window !== "undefined") stopPoll = startVisiblePoll(() => void refreshStatusBoardRows(), ROWS_POLL_MS);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && stopPoll) {
      stopPoll();
      stopPoll = null;
    }
  };
}

export function useStatusBoardRows(): StatusBoardItem[] | null {
  return useSyncExternalStore(subscribe, () => rows, () => null);
}
