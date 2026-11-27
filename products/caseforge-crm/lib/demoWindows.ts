
import { nextDockSeq } from "./demoDock";
import { clampBox, sameBox } from "./windowFit";
import type { DockSide, DockSlot } from "./demoDock";

export interface DemoWindow {
  id: string;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  open: boolean;
  minimised: boolean;
  maximised: boolean;

  side: DockSide;
  slot: DockSlot;
  dockSeq: number;

  snapPrev: { x: number; y: number; w: number; h: number } | null;

  z: number;
}

export const DEMO_WINDOWS = ["demo", "inbox", "email", "explorer", "caseflow"] as const;
export type DemoWindowId = (typeof DEMO_WINDOWS)[number];

export const WINDOW_TITLES: Record<DemoWindowId, string> = {
  demo: "Demo",
  inbox: "Inbox",
  email: "Email",
  explorer: "Explorer",
  caseflow: "Case flow",
};

export const MIN_W = 300;
export const MIN_H = 160;

type Viewport = { w: number; h: number; top?: number };

export function startingBox(id: DemoWindowId, vp: Viewport) {
  const top = (vp.top ?? 56) + 8;
  const bottom = vp.h - 56;
  const usable = Math.max(MIN_H * 2, bottom - top);
  const colW = Math.max(MIN_W, Math.floor((vp.w - 48) / 3));
  const rowH = Math.floor(usable / 2) - 8;
  const boxes: Record<DemoWindowId, { x: number; y: number; w: number; h: number }> = {
    demo: { x: 16, y: top, w: colW, h: Math.min(rowH, 300) },
    inbox: { x: 16, y: top + Math.min(rowH, 300) + 12, w: colW, h: Math.max(MIN_H, usable - Math.min(rowH, 300) - 12) },
    email: { x: 24 + colW, y: top, w: colW, h: usable },
    explorer: { x: 32 + colW * 2, y: top, w: Math.max(MIN_W, vp.w - colW * 2 - 48), h: Math.floor(usable * 0.58) },
    caseflow: { x: 32 + colW * 2, y: top + Math.floor(usable * 0.58) + 12, w: Math.max(MIN_W, vp.w - colW * 2 - 48), h: Math.max(MIN_H, Math.floor(usable * 0.42) - 12) },
  };
  return boxes[id];
}

export function initialWindows(vp: Viewport): DemoWindow[] {
  return DEMO_WINDOWS.map((id, index) => ({
    id,
    title: WINDOW_TITLES[id],
    ...startingBox(id, vp),
    open: false,
    minimised: false,
    maximised: false,
    side: "left",
    slot: "top",
    dockSeq: 0,
    snapPrev: null,
    z: index + 1,
  }));
}

export function openAll(list: DemoWindow[]): DemoWindow[] {
  const top = Math.max(0, ...list.map((w) => w.z));
  return list.map((w, index) => ({ ...w, open: true, minimised: false, z: top + 1 + index }));
}

export function fitWindows(list: DemoWindow[], viewport: Viewport): DemoWindow[] {
  return list.map((w) => {
    const fit = clampBox(w, { w: viewport.w, h: viewport.h, top: viewport.top ?? 0 });
    return sameBox(w, fit) ? w : { ...w, ...fit };
  });
}

export function toggleAll(list: DemoWindow[]): DemoWindow[] {
  return list.some((w) => w.open && !w.minimised) ? list.map((w) => ({ ...w, open: false })) : openAll(list);
}

export function dockWindow(list: DemoWindow[], id: string, place?: { side: DockSide; slot: DockSlot }): DemoWindow[] {
  const seq = nextDockSeq();
  return list.map((w) => (w.id === id ? { ...w, ...place, minimised: true, dockSeq: seq } : w));
}

export function focusWindow(list: DemoWindow[], id: string): DemoWindow[] {
  const top = Math.max(0, ...list.map((w) => w.z)) + 1;
  return list.map((w) => (w.id === id ? { ...w, z: top } : w));
}

export function patchWindow(list: DemoWindow[], id: string, patch: Partial<DemoWindow>): DemoWindow[] {
  return list.map((w) => (w.id === id ? { ...w, ...patch } : w));
}

export function clampPosition(x: number, y: number, w: number, viewport: Viewport) {
  return {
    x: Math.min(Math.max(x, 80 - w), viewport.w - 80),
    y: Math.min(Math.max(y, viewport.top ?? 0), viewport.h - 40),
  };
}

export function clampSize(w: number, h: number) {
  return { w: Math.max(MIN_W, w), h: Math.max(MIN_H, h) };
}

export type ResizeEdge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
export const RESIZE_EDGES: ResizeEdge[] = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

export function resizeBox(edge: ResizeEdge, start: { x: number; y: number; w: number; h: number }, dx: number, dy: number, minW: number = MIN_W) {
  let { x, y, w, h } = start;
  if (edge.includes("e")) w = Math.max(minW, start.w + dx);
  if (edge.includes("s")) h = Math.max(MIN_H, start.h + dy);
  if (edge.includes("w")) {
    w = Math.max(minW, start.w - dx);
    x = start.x + start.w - w;
  }
  if (edge.includes("n")) {
    h = Math.max(MIN_H, start.h - dy);
    y = Math.max(0, start.y + start.h - h);
    h = start.y + start.h - y;
  }
  return { x, y, w, h };
}

let state: DemoWindow[] = [];
const listeners = new Set<() => void>();

function set(next: DemoWindow[]) {
  state = next;
  listeners.forEach((l) => l());
}

export function viewportWidth(): number {
  return document.documentElement.clientWidth || window.innerWidth;
}

export const BANNER_SELECTOR = ".update-banner, .session-stale-wrap, .refresh-unsaved, .wetransfer-banner";

export function headerBottom(): number {
  const header = document.querySelector(".app-header")?.getBoundingClientRect().bottom ?? 56;
  const banners = Array.from(document.querySelectorAll(BANNER_SELECTOR), (el) => el.getBoundingClientRect().bottom);
  return Math.round(Math.max(header, ...banners));
}

function vp(): Viewport {
  return { w: viewportWidth(), h: window.innerHeight, top: headerBottom() };
}

export const demoWindows = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  get: () => state,
  openAll: () => set(fitWindows(openAll(state.length ? state : initialWindows(vp())), vp())),

  toggle: () => set(fitWindows(toggleAll(state.length ? state : initialWindows(vp())), vp())),
  focus: (id: string) => set(focusWindow(state, id)),
  patch: (id: string, patch: Partial<DemoWindow>) => set(patchWindow(state, id, patch)),
  minimise: (id: string) => set(dockWindow(state, id)),

  dock: (id: string, side: DockSide, slot: DockSlot) => set(dockWindow(state, id, { side, slot })),
  restore: (id: string) => set(focusWindow(patchWindow(state, id, { minimised: false }), id)),
  close: (id: string) => set(patchWindow(state, id, { open: false })),
};
