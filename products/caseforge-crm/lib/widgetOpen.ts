"use client";

import { useSyncExternalStore } from "react";

export const OPEN_STORAGE_KEY = "caseforge-client-viewer:open-boxes-v1";

export function parseOpen(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const data = JSON.parse(raw);
    return Array.isArray(data) ? data.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function withOpen(open: readonly string[], id: string, show: boolean): string[] {
  const rest = open.filter((o) => o !== id);
  return show ? [...rest, id] : rest;
}

let open: string[] = [];
let loaded = false;
const listeners = new Set<() => void>();

function load() {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    open = parseOpen(window.sessionStorage.getItem(OPEN_STORAGE_KEY));
  } catch {
    open = [];
  }
}

export const widgetOpen = {
  isOpen(id: string): boolean {
    load();
    return open.includes(id);
  },
  set(id: string, show: boolean) {
    load();
    if (open.includes(id) === show) return;
    open = withOpen(open, id, show);
    try {
      window.sessionStorage.setItem(OPEN_STORAGE_KEY, JSON.stringify(open));
    } catch {

    }
    listeners.forEach((l) => l());
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },

  reset() {
    open = [];
    loaded = true;
    listeners.forEach((l) => l());
  },
};

export function usePersistedOpen(id: string): [boolean, (next: boolean) => void] {
  const isOpen = useSyncExternalStore(widgetOpen.subscribe, () => widgetOpen.isOpen(id), () => false);
  return [isOpen, (next) => widgetOpen.set(id, next)];
}
