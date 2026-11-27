
export type DockSide = "left" | "right";
export type DockSlot = "top" | "middle" | "bottom";
export const DOCK_SIDES: DockSide[] = ["left", "right"];
export const DOCK_SLOTS: DockSlot[] = ["top", "middle", "bottom"];

export const TAB_W = 28;
export const TAB_GAP = 6;

type Viewport = { w: number; h: number; top?: number };
export type Span = { y: number; h: number };

let seqCounter = 0;

export function nextDockSeq(): number {
  return ++seqCounter;
}

export interface DockTab {
  id: string;
  side: DockSide;
  slot: DockSlot;

  seq: number;
  h: number;
}

export function tabHeight(title: string): number {
  return Math.min(176, Math.round(30 + title.length * 8.5));
}

export function tabBand(vp: Viewport) {
  return { min: (vp.top ?? 56) + 8, max: vp.h - 56 };
}

export function slotCentres(vp: Viewport): Record<DockSlot, number> {
  const { min, max } = tabBand(vp);
  return { top: min + 40, middle: Math.round((min + max) / 2), bottom: max - 40 };
}

export function slotTargets(vp: Viewport) {
  const centres = slotCentres(vp);
  return DOCK_SIDES.flatMap((side) => DOCK_SLOTS.map((slot) => ({ side, slot, x: side === "left" ? 0 : vp.w, y: centres[slot] })));
}

export function nearestSlot(x: number, y: number, vp: Viewport): { side: DockSide; slot: DockSlot } {
  const centres = slotCentres(vp);
  let slot: DockSlot = "top";
  for (const s of DOCK_SLOTS) if (Math.abs(y - centres[s]) < Math.abs(y - centres[slot])) slot = s;
  return { side: x < vp.w / 2 ? "left" : "right", slot };
}

export function moveByKey(side: DockSide, slot: DockSlot, key: string): { side: DockSide; slot: DockSlot } {
  const at = DOCK_SLOTS.indexOf(slot);
  if (key === "ArrowLeft") return { side: "left", slot };
  if (key === "ArrowRight") return { side: "right", slot };
  if (key === "ArrowUp") return { side, slot: DOCK_SLOTS[Math.max(0, at - 1)] };
  if (key === "ArrowDown") return { side, slot: DOCK_SLOTS[Math.min(DOCK_SLOTS.length - 1, at + 1)] };
  return { side, slot };
}

const overlaps = (y: number, h: number, s: Span) => y < s.y + s.h + TAB_GAP && y + h + TAB_GAP > s.y;

export function layoutTabs(tabs: DockTab[], vp: Viewport, blocked: Record<DockSide, Span[]> = { left: [], right: [] }): Record<string, number> {
  const { min, max } = tabBand(vp);
  const out: Record<string, number> = {};
  for (const side of DOCK_SIDES) {
    const column: { id: string; h: number; y: number }[] = [];
    for (const slot of DOCK_SLOTS) {
      const group = tabs.filter((t) => t.side === side && t.slot === slot).sort((a, b) => a.seq - b.seq);
      const total = group.reduce((n, t) => n + t.h, 0) + Math.max(0, group.length - 1) * TAB_GAP;
      let y = slot === "top" ? min : slot === "middle" ? Math.round((min + max) / 2 - total / 2) : max - total;
      for (const t of group) {
        column.push({ id: t.id, h: t.h, y });
        y += t.h + TAB_GAP;
      }
    }
    let prevEnd = -Infinity;
    for (const c of column) {
      c.y = Math.max(c.y, prevEnd + TAB_GAP, min);
      for (let again = true; again; ) {
        again = false;
        for (const b of blocked[side]) if (overlaps(c.y, c.h, b)) { c.y = b.y + b.h + TAB_GAP; again = true; }
      }
      prevEnd = c.y + c.h;
    }
    let nextStart = max;
    for (let i = column.length - 1; i >= 0; i--) {
      const c = column[i];
      if (c.y + c.h > nextStart) {
        c.y = nextStart - c.h;
        for (let again = true; again; ) {
          again = false;
          for (const b of blocked[side]) if (overlaps(c.y, c.h, b)) { c.y = b.y - TAB_GAP - c.h; again = true; }
        }
      }
      nextStart = c.y - TAB_GAP;
    }
    for (const c of column) out[c.id] = c.y;
  }
  return out;
}

export function flightVector(centre: { x: number; y: number }, side: DockSide, slot: DockSlot, vp: Viewport): { x: number; y: number } {
  const targetX = side === "left" ? TAB_W / 2 : vp.w - TAB_W / 2;
  return { x: Math.round(targetX - centre.x), y: Math.round(slotCentres(vp)[slot] - centre.y) };
}
