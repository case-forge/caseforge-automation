"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { FaviconColour } from "./favicon";

export const FAVICON_LOCK_STORAGE_KEY = "caseforge-client-viewer:favicon-lock";

const listeners = new Set<() => void>();

export function readStoredFaviconLock(raw: string | null): FaviconColour | null {
  return raw === "black" || raw === "white" ? raw : null;
}

export function faviconLock(): FaviconColour | null {
  try {
    return readStoredFaviconLock(window.localStorage.getItem(FAVICON_LOCK_STORAGE_KEY));
  } catch {
    return null;
  }
}

function setLock(colour: FaviconColour | null): void {
  try {
    if (colour) window.localStorage.setItem(FAVICON_LOCK_STORAGE_KEY, colour);
    else window.localStorage.removeItem(FAVICON_LOCK_STORAGE_KEY);
  } catch {

  }
  listeners.forEach((l) => l());
}

export function subscribeFaviconLock(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function useFaviconLock(): [FaviconColour | null, (colour: FaviconColour | null) => void] {
  const locked = useSyncExternalStore(subscribeFaviconLock, faviconLock, () => null);
  const set = useCallback((colour: FaviconColour | null) => setLock(colour), []);
  return [locked, set];
}
