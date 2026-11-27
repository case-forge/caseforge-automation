
import { useSyncExternalStore } from "react";
import type { DockSide, DockSlot } from "./demoDock";

export const DOCK_EDGE_PX = 24;

export const PULL_OFF_PX = 80;

export const CUE_MS = 160;

export function dockSide(x: number, vpW: number, edgePx: number = DOCK_EDGE_PX): DockSide | null {
  if (x <= edgePx) return "left";
  if (x >= vpW - 1 - edgePx) return "right";
  return null;
}

export type PullState = {

  distance: number;

  pulling: boolean;

  progress: number;
};

export function pullState(x: number, vpW: number, threshold: number = PULL_OFF_PX): PullState {
  const distance = Math.max(0, Math.min(x, vpW - 1 - x));
  return { distance, pulling: distance >= threshold, progress: Math.min(1, distance / threshold) };
}

export function dropAction(x: number, vpW: number, threshold: number = PULL_OFF_PX): "pull-off" | "re-slot" {
  return pullState(x, vpW, threshold).pulling ? "pull-off" : "re-slot";
}

export function ghostStart(tab: { w: number; h: number }, win: { w: number; h: number }): { sx: number; sy: number } {
  return { sx: win.w ? tab.w / win.w : 1, sy: win.h ? tab.h / win.h : 1 };
}

export function dockingClass(docking: boolean, dragging: boolean, minimised: boolean): string {
  return docking && dragging && !minimised ? " fw-docking" : "";
}

export function cueMotion(reduced: boolean): { ms: number; moves: boolean } {
  return reduced ? { ms: 0, moves: false } : { ms: CUE_MS, moves: true };
}

export type DockCue = { side: DockSide; slot: DockSlot; title: string; on: boolean; gaps: boolean; over: "slot" | "gap" | "none"; gap: 0 | 1 };
export type DockCueInput = Omit<DockCue, "on">;
let cue: DockCue | null = null;
const listeners = new Set<() => void>();

export function setDockCue(next: DockCueInput | null): void {
  const value: DockCue | null = next ? { ...next, on: true } : cue ? { ...cue, on: false } : null;
  if (cue && value && cue.on === value.on && cue.side === value.side && cue.slot === value.slot && cue.title === value.title && cue.gaps === value.gaps && cue.over === value.over && cue.gap === value.gap) return;
  cue = value;
  listeners.forEach((l) => l());
}

export function useDockCue(): DockCue | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => cue,
    () => null,
  );
}
