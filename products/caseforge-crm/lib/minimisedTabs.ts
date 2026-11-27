
import { useSyncExternalStore } from "react";
import { nextDockSeq } from "./demoDock";
import type { DockSide, DockSlot } from "./demoDock";

export type Place = { side: DockSide; slot: DockSlot };
export type MinimisedTab = Place & { id: string; title: string; seq: number; size?: { w: number; h: number } };

export const DEFAULT_PLACE: Place = { side: "right", slot: "middle" };

export function addTab(tabs: MinimisedTab[], id: string, title: string, place: Place = DEFAULT_PLACE, seq: number = nextDockSeq(), size?: { w: number; h: number }): MinimisedTab[] {
  if (tabs.some((t) => t.id === id)) return tabs.map((t) => (t.id === id ? { ...t, title } : t));
  return [...tabs, { id, title, ...place, seq, size }];
}

export function removeTab(tabs: MinimisedTab[], id: string): MinimisedTab[] {
  return tabs.some((t) => t.id === id) ? tabs.filter((t) => t.id !== id) : tabs;
}

export function moveTab(tabs: MinimisedTab[], id: string, place: Place, seq: number = nextDockSeq()): MinimisedTab[] {
  return tabs.map((t) => (t.id === id ? { ...t, ...place, seq } : t));
}

let state: MinimisedTab[] = [];
const listeners = new Set<() => void>();
const serverSnapshot: MinimisedTab[] = [];

function set(next: MinimisedTab[]) {
  if (next === state) return;
  state = next;
  listeners.forEach((l) => l());
}

export const minimisedTabs = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  get: () => state,
  add: (id: string, title: string, place?: Place, size?: { w: number; h: number }) => set(addTab(state, id, title, place, undefined, size)),
  remove: (id: string) => set(removeTab(state, id)),
  move: (id: string, place: Place) => set(moveTab(state, id, place)),
  has: (id: string) => state.some((t) => t.id === id),
};

export function useMinimisedTabs(): MinimisedTab[] {
  return useSyncExternalStore(minimisedTabs.subscribe, minimisedTabs.get, () => serverSnapshot);
}

export function useIsMinimised(id: string): boolean {
  return useSyncExternalStore(
    minimisedTabs.subscribe,
    () => minimisedTabs.has(id),
    () => false,
  );
}
