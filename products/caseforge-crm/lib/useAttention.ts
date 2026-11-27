"use client";

import { withoutItem } from "./attention";
import { pulseStore, createPulseSlice } from "./pulse";
import { usePolledStore } from "./polledStore";
import type { AttentionResponse } from "./types";

const attentionStore = createPulseSlice<AttentionResponse>((pulse) => pulse.attention);

export async function refreshAttention(): Promise<void> {
  pulseStore.refresh();
}

export function useAttention(): AttentionResponse | null {
  return usePolledStore(attentionStore).data;
}

export async function completeAttentionItem(taskId: string): Promise<void> {
  const res = await fetch("/api/clients/attention/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body?.error === "string" && body.error ? body.error : "Could not mark that done.");
  }
  const current = attentionStore.getSnapshot();
  if (current) attentionStore.set(withoutItem(current, taskId));
  void refreshAttention();
}
