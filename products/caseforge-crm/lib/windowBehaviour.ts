"use client";

import { useCallback, useSyncExternalStore } from "react";

export const WINDOW_SNAP_STORAGE_KEY = "caseforge-client-viewer:window-snap";
export const WINDOW_DOCK_STORAGE_KEY = "caseforge-client-viewer:window-dock";

const listeners = new Set<() => void>();

export function readStoredWindowGesture(raw: string | null): boolean {
  return raw !== "off";
}

function readKey(key: string): boolean {
  try {
    return readStoredWindowGesture(window.localStorage.getItem(key));
  } catch {
    return true;
  }
}

export const windowSnapOn = (): boolean => readKey(WINDOW_SNAP_STORAGE_KEY);
export const windowDockOn = (): boolean => readKey(WINDOW_DOCK_STORAGE_KEY);

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function useGesture(key: string): [boolean, (next: boolean) => void] {
  const on = useSyncExternalStore(subscribe, () => readKey(key), () => true);
  const set = useCallback(
    (next: boolean) => {
      try {
        window.localStorage.setItem(key, next ? "on" : "off");
      } catch {

      }
      listeners.forEach((l) => l());
    },
    [key],
  );
  return [on, set];
}

export const useWindowSnap = (): [boolean, (next: boolean) => void] => useGesture(WINDOW_SNAP_STORAGE_KEY);
export const useWindowDock = (): [boolean, (next: boolean) => void] => useGesture(WINDOW_DOCK_STORAGE_KEY);
