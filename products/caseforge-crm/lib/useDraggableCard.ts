"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, RefObject } from "react";

export type Offset = { right: number; bottom: number };
type Size = { w: number; h: number };

export const DEFAULT_OFFSET: Offset = { right: 16, bottom: 16 };

export const EDGE_PX = 8;
export const KEY_STEP_PX = 16;
export const KEY_STEP_SHIFT_PX = 64;

export const NARROW_VIEWPORT_PX = 480;

export const WHATS_NEW_POSITION_KEY = "caseforge-client-viewer:card-position:whats-new";
export const CLASSIFIER_POSITION_KEY = "caseforge-client-viewer:card-position:classifier-prompt";

export function clampOffset(offset: Offset, card: Size, view: Size): Offset {
  const limit = (room: number) => Math.max(EDGE_PX, room - EDGE_PX);
  return {
    right: Math.min(Math.max(offset.right, EDGE_PX), limit(view.w - card.w)),
    bottom: Math.min(Math.max(offset.bottom, EDGE_PX), limit(view.h - card.h)),
  };
}

export function dragOffset(start: { x: number; y: number; offset: Offset }, now: { x: number; y: number }): Offset {
  return { right: start.offset.right - (now.x - start.x), bottom: start.offset.bottom - (now.y - start.y) };
}

export type KeyAction = { type: "move"; offset: Offset } | { type: "reset" } | null;

export function keyAction(key: string, shift: boolean, offset: Offset): KeyAction {
  const step = shift ? KEY_STEP_SHIFT_PX : KEY_STEP_PX;
  switch (key) {
    case "ArrowLeft":
      return { type: "move", offset: { ...offset, right: offset.right + step } };
    case "ArrowRight":
      return { type: "move", offset: { ...offset, right: offset.right - step } };
    case "ArrowUp":
      return { type: "move", offset: { ...offset, bottom: offset.bottom + step } };
    case "ArrowDown":
      return { type: "move", offset: { ...offset, bottom: offset.bottom - step } };
    case "Escape":
      return { type: "reset" };
    default:
      return null;
  }
}

export function isNarrow(viewWidth: number): boolean {
  return viewWidth < NARROW_VIEWPORT_PX;
}

export function toFractions(offset: Offset, view: Size): { x: number; y: number } {
  return { x: offset.right / view.w, y: offset.bottom / view.h };
}

export function fromFractions(fractions: { x: number; y: number }, view: Size): Offset {
  return { right: fractions.x * view.w, bottom: fractions.y * view.h };
}

type StoreLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function browserStore(): StoreLike | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readStoredFractions(key: string, store: StoreLike | null = browserStore()): { x: number; y: number } | null {
  try {
    const raw = store?.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { x?: unknown; y?: unknown };
    const { x, y } = parsed;
    if (typeof x !== "number" || typeof y !== "number" || !Number.isFinite(x) || !Number.isFinite(y)) return null;
    if (x < 0 || x > 1 || y < 0 || y > 1) return null;
    return { x, y };
  } catch {
    return null;
  }
}

export function writeStoredFractions(key: string, fractions: { x: number; y: number }, store: StoreLike | null = browserStore()): void {
  try {
    store?.setItem(key, JSON.stringify(fractions));
  } catch {

  }
}

export function clearStoredFractions(key: string, store: StoreLike | null = browserStore()): void {
  try {
    store?.removeItem(key);
  } catch {

  }
}

export type DraggableCard<T extends HTMLElement> = {

  cardRef: RefObject<T | null>;

  style: { right: number; bottom: number } | undefined;

  barProps: {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerCancel: (event: ReactPointerEvent<HTMLElement>) => void;
    onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
    onDoubleClick: () => void;
  };
};

export function useDraggableCard<T extends HTMLElement>(storageKey: string): DraggableCard<T> {
  const cardRef = useRef<T | null>(null);
  const [offset, setOffset] = useState<Offset | null>(null);
  const offsetRef = useRef<Offset | null>(null);
  const drag = useRef<{ pointerId: number; x: number; y: number; offset: Offset } | null>(null);

  const place = useCallback((next: Offset | null) => {
    offsetRef.current = next;
    setOffset(next);
  }, []);

  const view = (): Size => ({ w: window.innerWidth, h: window.innerHeight });
  const cardSize = (): Size => {
    const rect = cardRef.current?.getBoundingClientRect();
    return { w: rect?.width ?? 0, h: rect?.height ?? 0 };
  };
  const current = (): Offset => offsetRef.current ?? DEFAULT_OFFSET;
  const save = (next: Offset) => writeStoredFractions(storageKey, toFractions(next, view()));
  const reset = () => {
    clearStoredFractions(storageKey);
    place(null);
  };

  useEffect(() => {
    const settle = () => {
      if (drag.current) return;
      if (isNarrow(window.innerWidth)) {
        place(null);
        return;
      }
      const stored = readStoredFractions(storageKey);
      const wanted = stored ? fromFractions(stored, view()) : offsetRef.current;
      place(wanted ? clampOffset(wanted, cardSize(), view()) : null);
    };
    settle();
    window.addEventListener("resize", settle);
    window.addEventListener("orientationchange", settle);
    const watcher = typeof ResizeObserver === "undefined" || !cardRef.current ? null : new ResizeObserver(settle);
    if (watcher && cardRef.current) watcher.observe(cardRef.current);
    return () => {
      window.removeEventListener("resize", settle);
      window.removeEventListener("orientationchange", settle);
      watcher?.disconnect();
    };
  }, [storageKey, place]);

  const stopDrag = (event: ReactPointerEvent<HTMLElement>) => {
    if (!drag.current || drag.current.pointerId !== event.pointerId) return;
    drag.current = null;
    document.body.classList.remove("card-dragging");
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {

    }
    if (offsetRef.current) save(offsetRef.current);
  };

  const barProps: DraggableCard<T>["barProps"] = {
    onPointerDown(event) {
      if (isNarrow(window.innerWidth) || (event.pointerType === "mouse" && event.button !== 0)) return;

      if ((event.target as Element).closest("button, a, input, select, textarea, [role='tooltip']")) return;
      drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, offset: current() };
      document.body.classList.add("card-dragging");
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {

      }
    },
    onPointerMove(event) {
      const start = drag.current;
      if (!start || start.pointerId !== event.pointerId) return;
      place(clampOffset(dragOffset(start, { x: event.clientX, y: event.clientY }), cardSize(), view()));
    },
    onPointerUp: stopDrag,
    onPointerCancel: stopDrag,
    onKeyDown(event) {

      if (isNarrow(window.innerWidth) || event.target !== event.currentTarget) return;
      const action = keyAction(event.key, event.shiftKey, current());
      if (!action) return;

      event.preventDefault();
      event.stopPropagation();
      if (action.type === "reset") {
        reset();
        return;
      }
      const next = clampOffset(action.offset, cardSize(), view());
      place(next);
      save(next);
    },
    onDoubleClick: reset,
  };

  return { cardRef, style: offset ?? undefined, barProps };
}
