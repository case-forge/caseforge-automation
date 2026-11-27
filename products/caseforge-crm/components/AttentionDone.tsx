"use client";

import { useState } from "react";
import { canComplete } from "@/lib/attention";
import { completeAttentionItem } from "@/lib/useAttention";
import type { AttentionItem } from "@/lib/types";

export interface DoneState {
  error: string;
  busyId: string;
  done: (taskId: string) => Promise<void>;
}

export function useAttentionDone(): DoneState {
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  async function done(taskId: string) {
    setError("");
    setBusyId(taskId);
    try {
      await completeAttentionItem(taskId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not mark that done.");
    } finally {
      setBusyId("");
    }
  }

  return { error, busyId, done };
}

export function DoneBar({ state, items }: { state: DoneState; items: AttentionItem[] }) {
  if (!items.some(canComplete)) return null;
  return (
    <>
      {state.error && (
        <p className="todo-error" role="alert">
          {state.error}
        </p>
      )}
    </>
  );
}

export function DoneButton({ item, state }: { item: AttentionItem; state: DoneState }) {
  if (!canComplete(item)) return null;
  return (
    <button
      type="button"
      className="cf-btn cf-btn--neutral cf-btn--small attention-item-done"
      disabled={state.busyId === item.task_id}
      onClick={() => void state.done(item.task_id)}
    >
      Done
    </button>
  );
}
