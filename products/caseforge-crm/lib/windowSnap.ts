
import { useSyncExternalStore } from "react";
import { MIN_W, clampPosition } from "./demoWindows";
import { windowDockOn, windowSnapOn } from "./windowBehaviour";

export type WindowKind = "demo" | "hearing-drawer" | "hearings-panel" | "whats-new" | "classifier" | "blocked";

export function windowKind(id: string): WindowKind {
  if (id.startsWith("hearing-")) return "hearing-drawer";
  if (id === "hearings-rail") return "hearings-panel";
  if (id === "whats-new") return "whats-new";
  if (id === "classifier-prompt") return "classifier";
  if (id === "caseflow-blocked") return "blocked";
  return "demo";
}

export const SNAPPING_WINDOWS: Record<WindowKind, boolean> = {
  demo: true,
  "hearing-drawer": true,
  "hearings-panel": true,
  "whats-new": false,
  classifier: false,
  blocked: false,
};

export const DOCKING_BY_DRAG_WINDOWS: Record<WindowKind, boolean> = {
  demo: false,
  "hearing-drawer": true,
  "hearings-panel": true,
  "whats-new": true,
  classifier: true,
  blocked: true,
};

export const SNAP_FILLS_PAGE: Record<WindowKind, boolean> = {
  demo: true,
  "hearing-drawer": false,
  "hearings-panel": false,
  "whats-new": false,
  classifier: false,
  blocked: false,
};
export const snapFillsPage = (id: string): boolean => SNAP_FILLS_PAGE[windowKind(id)];

export const windowSnaps = (id: string): boolean => SNAPPING_WINDOWS[windowKind(id)];
export const windowDocksByDrag = (id: string): boolean => DOCKING_BY_DRAG_WINDOWS[windowKind(id)];

export const windowGestures = (id: string): { snaps: boolean; docks: boolean } => ({
  snaps: windowSnaps(id) && windowSnapOn(),
  docks: windowDocksByDrag(id) && windowDockOn(),
});

export type SnapZone = "left" | "right" | "top" | "topleft" | "topright" | "bottomleft" | "bottomright";
export type Box = { x: number; y: number; w: number; h: number };

type Viewport = { w: number; h: number; top: number; gap?: number };

export const EDGE_PX = 12;
export const CORNER_PX = 72;
export const FOOTER_GAP_PX = 40;

export function snapZone(x: number, y: number, vp: Viewport, edgePx: number = EDGE_PX): SnapZone | null {
  const nearL = x <= edgePx;
  const nearR = x >= vp.w - 1 - edgePx;
  const nearT = y <= edgePx;
  const nearB = y >= vp.h - 1 - edgePx;
  const roomForTwo = vp.w >= MIN_W * 2;
  const alongTop = y <= CORNER_PX;
  const alongBottom = y >= vp.h - 1 - CORNER_PX;
  let zone: SnapZone | null = null;
  if ((nearL && (nearT || alongTop)) || (nearT && x <= CORNER_PX)) zone = "topleft";
  else if ((nearR && (nearT || alongTop)) || (nearT && x >= vp.w - 1 - CORNER_PX)) zone = "topright";
  else if ((nearL && (nearB || alongBottom)) || (nearB && x <= CORNER_PX)) zone = "bottomleft";
  else if ((nearR && (nearB || alongBottom)) || (nearB && x >= vp.w - 1 - CORNER_PX)) zone = "bottomright";
  else if (nearL) zone = "left";
  else if (nearR) zone = "right";
  else if (nearT) zone = "top";
  if (zone && zone !== "top" && !roomForTwo) return null;
  return zone;
}

export function snapBox(zone: SnapZone, vp: Viewport): Box {
  const gap = vp.gap ?? FOOTER_GAP_PX;
  const height = Math.max(0, vp.h - vp.top - gap);
  const halfW = Math.floor(vp.w / 2);
  const halfH = Math.floor(height / 2);
  const left = zone === "left" || zone === "topleft" || zone === "bottomleft";
  const right = zone === "right" || zone === "topright" || zone === "bottomright";
  const topHalf = zone === "topleft" || zone === "topright";
  const bottomHalf = zone === "bottomleft" || zone === "bottomright";
  const w = left || right ? halfW : vp.w;
  const x = right ? vp.w - halfW : 0;
  const h = topHalf || bottomHalf ? halfH : height;
  const y = bottomHalf ? vp.top + height - halfH : vp.top;
  return { x, y, w, h };
}

export function sizedSnapBox(zone: SnapZone, vp: Viewport, size: { w: number; h: number }, pointerY: number): Box {
  const gap = vp.gap ?? FOOTER_GAP_PX;
  const w = Math.min(size.w, vp.w);
  const h = Math.min(size.h, Math.max(0, vp.h - vp.top - gap));
  const left = zone === "left" || zone === "topleft" || zone === "bottomleft";
  const right = zone === "right" || zone === "topright" || zone === "bottomright";
  const x = left ? 0 : right ? vp.w - w : Math.round((vp.w - w) / 2);
  const lowest = Math.max(vp.top, vp.h - gap - h);
  const y = zone === "topleft" || zone === "topright" || zone === "top" ? vp.top : zone === "bottomleft" || zone === "bottomright" ? lowest : Math.min(Math.max(Math.round(pointerY - 16), vp.top), lowest);
  return { x, y, w, h };
}

export function resolveSnapBox(id: string, zone: SnapZone, vp: Viewport, size: { w: number; h: number }, pointerY: number): Box {
  return snapFillsPage(id) ? snapBox(zone, vp) : sizedSnapBox(zone, vp, size, pointerY);
}

export const isFullZone = (zone: SnapZone): boolean => zone === "top";

export function restoreFromSnap(prev: { w: number; h: number }, pointer: { x: number; y: number }, grabX: number, grabY: number, vp: Viewport): Box {
  const at = clampPosition(pointer.x - prev.w * grabX, pointer.y - grabY, prev.w, { w: vp.w, h: vp.h, top: vp.top });
  return { ...at, w: prev.w, h: prev.h };
}

let preview: Box | null = null;
const listeners = new Set<() => void>();

export function setSnapPreview(next: Box | null): void {
  const same = preview === next || (preview && next && preview.x === next.x && preview.y === next.y && preview.w === next.w && preview.h === next.h);
  if (same) return;
  preview = next;
  listeners.forEach((l) => l());
}

export function useSnapPreview(): Box | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => preview,
    () => null,
  );
}
