"use client";

import { useCallback, useSyncExternalStore } from "react";

export const C8_GUARD_STORAGE_KEY = "caseforge-client-viewer:c8-guard";

const listeners = new Set<() => void>();

export function readStoredC8Guard(raw: string | null): boolean {
  return raw !== "off";
}

function read(): boolean {
  try {
    return readStoredC8Guard(window.localStorage.getItem(C8_GUARD_STORAGE_KEY));
  } catch {
    return true;
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function useC8Guard(): [boolean, (next: boolean) => void] {
  const on = useSyncExternalStore(subscribe, read, () => true);
  const set = useCallback((next: boolean) => {
    try {
      window.localStorage.setItem(C8_GUARD_STORAGE_KEY, next ? "on" : "off");
    } catch {

    }
    listeners.forEach((l) => l());
  }, []);
  return [on, set];
}
