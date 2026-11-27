import { useCallback, useSyncExternalStore } from "react";
import { runInBackground } from "./loadingBar";
import { startVisiblePoll } from "./visiblePoll";

export interface PolledStore<T> {
  subscribe: (listener: () => void) => () => void;
  getSnapshot: () => T | null;
  refresh: () => void;

  set: (next: T) => void;
}

export function createPolledStore<T>(options: {
  fetch: () => Promise<T>;
  intervalMs: number;
  events?: string[];
}): PolledStore<T> {
  const listeners = new Set<() => void>();
  let data: T | null = null;
  let loading = false;
  let again = false;
  let stopPoll: (() => void) | null = null;
  const events = options.events ?? [];

  async function load(): Promise<void> {
    if (loading) {

      again = true;
      return;
    }
    loading = true;
    try {
      do {
        again = false;
        try {
          data = await runInBackground(options.fetch);
          listeners.forEach((listener) => listener());
        } catch {

        }
      } while (again);
    } finally {
      loading = false;
    }
  }

  function refresh(): void {
    void load();
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    if (listeners.size === 1) {
      stopPoll = startVisiblePoll(refresh, options.intervalMs);
      for (const name of events) window.addEventListener(name, refresh);
    }
    return () => {
      listeners.delete(listener);
      if (listeners.size === 0) {
        stopPoll?.();
        stopPoll = null;
        for (const name of events) window.removeEventListener(name, refresh);
      }
    };
  }

  function set(next: T): void {
    data = next;
    listeners.forEach((listener) => listener());
  }

  return { subscribe, getSnapshot: () => data, refresh, set };
}

export function usePolledStore<T>(store: PolledStore<T>): { data: T | null; refresh: () => void } {
  const data = useSyncExternalStore(store.subscribe, store.getSnapshot, () => null);
  const refresh = useCallback(() => store.refresh(), [store]);
  return { data, refresh };
}
