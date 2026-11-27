
import { DOCK_SIDES, DOCK_SLOTS, TAB_GAP, layoutTabs, tabBand } from "./demoDock";
import type { DockSide, DockTab, Span } from "./demoDock";

export const MIN_TAB_H = 44;
export type PlacedTab = { y: number; h: number };
type Viewport = { w: number; h: number; top?: number };

const clash = (y: number, h: number, s: Span) => y < s.y + s.h + TAB_GAP && y + h + TAB_GAP > s.y;

function groupBoxes(tabs: DockTab[], side: DockSide, vp: Viewport, scale: number) {
  const { min, max } = tabBand(vp);
  const boxes: { ids: string[]; y: number; h: number; len: number }[] = [];
  for (const slot of DOCK_SLOTS) {
    const group = tabs.filter((t) => t.side === side && t.slot === slot).sort((a, b) => a.seq - b.seq);
    if (!group.length) continue;
    const natural = Math.max(...group.map((t) => t.h));
    const len = Math.max(MIN_TAB_H, Math.round(natural * scale));
    const total = group.length * len + (group.length - 1) * TAB_GAP;
    const y = slot === "top" ? min : slot === "middle" ? Math.round((min + max) / 2 - total / 2) : max - total;
    boxes.push({ ids: group.map((t) => t.id), y, h: total, len });
  }
  return boxes;
}

export function placeTabs(tabs: DockTab[], vp: Viewport, blocked: Record<DockSide, Span[]> = { left: [], right: [] }): Record<string, PlacedTab> {
  const { min, max } = tabBand(vp);
  const out: Record<string, PlacedTab> = {};
  for (const side of DOCK_SIDES) {
    const mine = tabs.filter((t) => t.side === side);
    if (!mine.length) continue;
    let done = false;
    for (let step = 0; step <= 20 && !done; step++) {
      const boxes = groupBoxes(tabs, side, vp, 1 - step * 0.05);
      const fits = boxes.every(
        (b, i) => b.y >= min && b.y + b.h <= max && (i === 0 || b.y >= boxes[i - 1].y + boxes[i - 1].h + TAB_GAP) && !blocked[side].some((s) => clash(b.y, b.h, s)),
      );
      if (!fits) continue;
      for (const b of boxes) b.ids.forEach((id, i) => (out[id] = { y: b.y + i * (b.len + TAB_GAP), h: b.len }));
      done = true;
    }
    if (done) continue;
    const lens = new Map(groupBoxes(tabs, side, vp, 0).flatMap((b) => b.ids.map((id) => [id, b.len] as const)));
    const ys = layoutTabs(mine.map((t) => ({ ...t, h: lens.get(t.id) ?? MIN_TAB_H })), vp, blocked);
    for (const t of mine) out[t.id] = { y: ys[t.id], h: lens.get(t.id) ?? MIN_TAB_H };
  }
  return out;
}
