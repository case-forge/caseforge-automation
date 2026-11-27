"use client";

import { useEffect, useSyncExternalStore } from "react";

export type Layer = "pinned" | "front" | "behind";

export function layerOf(pinned: boolean, behind: boolean): Layer {
  return pinned ? "pinned" : behind ? "behind" : "front";
}

export function sendBack(behind: ReadonlySet<string>, registered: ReadonlySet<string>, pinned: ReadonlySet<string>): Set<string> {
  const next = new Set(behind);
  for (const id of registered) if (!pinned.has(id)) next.add(id);
  return next;
}

export function bringForward(behind: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(behind);
  next.delete(id);
  return next;
}

export type Request = "move" | "resize" | "snap" | "dock" | "pull-off";

export function allows(pinned: boolean, request: Request): boolean {
  void request;
  return !pinned;
}

export function backZ(sentBack: readonly string[], id: string): number | null {
  const at = sentBack.lastIndexOf(id);
  return at < 0 ? null : 1 + (sentBack.length - 1 - at);
}

export function unpinToBack(sentBack: readonly string[], id: string): string[] {
  return [...sentBack.filter((s) => s !== id), id];
}

export function leaveBack(sentBack: readonly string[], id: string): string[] {
  return sentBack.filter((s) => s !== id);
}

export const PINNED_Z_BASE = 4000;

export const UNPINNED_Z_CEILING = 3999;

export function pinnedZ(order: readonly string[], pinned: ReadonlySet<string>, id: string): number | null {
  if (!pinned.has(id)) return null;

  const ranked = [...[...pinned].filter((p) => !order.includes(p)), ...order.filter((o) => pinned.has(o))];
  return PINNED_Z_BASE + ranked.lastIndexOf(id);
}

export function pressed(order: readonly string[], id: string): string[] {
  return [...order.filter((o) => o !== id), id];
}

export function togglePinned(pinned: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(pinned);
  if (!next.delete(id)) next.add(id);
  return next;
}

const STORAGE_KEY = "caseforge-client-viewer:pinned-windows";
let pinned: Set<string> = new Set();
let behind: Set<string> = new Set();
let order: string[] = [];
let sentBack: string[] = [];
const registered = new Set<string>();
type SavedBox = { x: number; y: number; w: number; h: number };
const boxes = new Map<string, SavedBox>();
export const BOXES_STORAGE_KEY = "caseforge-client-viewer:window-boxes";

export function parseBoxes(raw: string | null): Record<string, SavedBox> {
  if (!raw) return {};
  try {
    const data = JSON.parse(raw) as Record<string, Partial<SavedBox>>;
    const out: Record<string, SavedBox> = {};
    for (const [id, b] of Object.entries(data ?? {})) {
      if (b && [b.x, b.y, b.w, b.h].every((n) => typeof n === "number" && Number.isFinite(n))) out[id] = b as SavedBox;
    }
    return out;
  } catch {
    return {};
  }
}

function saveBoxes() {
  try {
    window.sessionStorage.setItem(BOXES_STORAGE_KEY, JSON.stringify(Object.fromEntries(boxes)));
  } catch {

  }
}
const listeners = new Set<() => void>();
let version = 0;
let loaded = false;
let listening = false;

function load() {
  if (loaded) return;
  loaded = true;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (raw) pinned = new Set((JSON.parse(raw) as unknown[]).filter((v): v is string => typeof v === "string"));
  } catch {

  }
  try {
    for (const [id, b] of Object.entries(parseBoxes(window.sessionStorage.getItem(BOXES_STORAGE_KEY)))) boxes.set(id, b);
  } catch {

  }
}

function emit() {
  version += 1;
  listeners.forEach((l) => l());
}

function listen() {
  if (listening || typeof document === "undefined") return;
  listening = true;
  document.addEventListener(
    "pointerdown",
    (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      const win = target.closest<HTMLElement>("[data-window-id]");
      if (win) {
        windowPins.bringForward(win.dataset.windowId ?? "");
      }
    },
    true,
  );
}

export const windowPins = {
  subscribe(listener: () => void) {
    load();
    listen();
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  version: () => version,
  isPinned: (id: string) => {
    load();
    return pinned.has(id);
  },
  isBehind: (id: string) => behind.has(id),
  toggle(id: string) {
    load();
    pinned = togglePinned(pinned, id);
    if (pinned.has(id)) {
      behind = bringForward(behind, id);
      order = pressed(order, id);
      sentBack = leaveBack(sentBack, id);
    } else {

      sentBack = unpinToBack(sentBack, id);
    }
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...pinned]));
    } catch {

    }
    emit();
  },
  bringForward(id: string) {
    if (!id) return;
    const wasSentBack = sentBack.includes(id);
    const wasBehind = behind.has(id);
    const wasFront = order[order.length - 1] === id;
    if (!wasBehind && !wasSentBack && (!pinned.has(id) || wasFront)) return;
    sentBack = leaveBack(sentBack, id);
    behind = bringForward(behind, id);
    order = pressed(order, id);
    emit();
  },

  zFor: (id: string) => pinnedZ(order, pinned, id) ?? backZ(sentBack, id),
  register(id: string) {
    registered.add(id);
    return () => {
      registered.delete(id);
    };
  },

  saveBox(id: string, box: SavedBox) {
    boxes.set(id, box);
    saveBoxes();
  },
  savedBox: (id: string) => {
    load();
    return boxes.get(id) ?? null;
  },
  clearBox(id: string) {
    boxes.delete(id);
    saveBoxes();
  },
};

export function useWindowLayer(id: string): { layer: Layer; pinned: boolean; zIndex: number | null } {
  useSyncExternalStore(windowPins.subscribe, windowPins.version, () => 0);
  useEffect(() => windowPins.register(id), [id]);
  const isPinned = windowPins.isPinned(id);
  return { layer: layerOf(isPinned, windowPins.isBehind(id)), pinned: isPinned, zIndex: windowPins.zFor(id) };
}

export function useIsPinned(): (id: string) => boolean {
  useSyncExternalStore(windowPins.subscribe, windowPins.version, () => 0);
  return (id) => windowPins.isPinned(id);
}
