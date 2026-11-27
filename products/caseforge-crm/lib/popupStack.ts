"use client";

import { useSyncExternalStore } from "react";
import { POPUP_Z_BASE, POPUP_Z_CEILING } from "./layers";

export { POPUP_Z_BASE };

export const MAX_STACK = POPUP_Z_CEILING - POPUP_Z_BASE + 1;

export function raised(order: readonly string[], id: string): string[] {

  return [...order.filter((o) => o !== id), id].slice(-MAX_STACK);
}

export function removed(order: readonly string[], id: string): string[] {
  return order.filter((o) => o !== id);
}

export function stackZ(order: readonly string[], id: string): number | null {
  const at = order.indexOf(id);
  return at < 0 ? null : POPUP_Z_BASE + at;
}

let order: string[] = [];
let version = 0;
let listening = false;
const listeners = new Set<() => void>();

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
      const popup = target?.closest<HTMLElement>("[data-popup-id], [data-window-id]");
      const id = popup?.dataset.popupId ?? popup?.dataset.windowId;
      if (id && order[order.length - 1] !== id) popupStack.raise(id);
    },
    true,
  );
}

export const popupStack = {
  raise(id: string) {
    order = raised(order, id);
    emit();
  },
  drop(id: string) {
    if (!order.includes(id)) return;
    order = removed(order, id);
    emit();
  },
  zFor: (id: string) => stackZ(order, id),
  subscribe(listener: () => void) {
    listen();
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  version: () => version,

  reset() {
    order = [];
    emit();
  },
};

export function usePopupZ(id: string): number | null {
  useSyncExternalStore(popupStack.subscribe, popupStack.version, () => 0);
  return popupStack.zFor(id);
}
