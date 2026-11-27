
import { nearestSlot, slotCentres } from "./demoDock";
import type { DockSide, DockSlot } from "./demoDock";
import { DOCK_EDGE_PX, dockSide } from "./dockGesture";
import { snapZone } from "./windowSnap";
import type { SnapZone } from "./windowSnap";

export const SIDE_EDGE_PX = 24;

export const GUIDE_BAND_PX = 72;

export const SLOT_HALF_PX = 36;

type Viewport = { w: number; h: number; top: number };

export type GestureTarget =
  | { type: "snap"; zone: SnapZone;   gap?: 0 | 1 }
  | { type: "dock"; side: DockSide; slot: DockSlot }
  | { type: "none" };

export function slotAt(y: number, vp: Viewport): DockSlot | null {
  const centres = slotCentres(vp);
  for (const slot of ["top", "middle", "bottom"] as const) if (Math.abs(y - centres[slot]) <= SLOT_HALF_PX) return slot;
  return null;
}

export function gapZones(vp: Viewport): { y: number; h: number }[] {
  const c = slotCentres(vp);
  return [
    { y: c.top + SLOT_HALF_PX, h: Math.max(0, c.middle - c.top - 2 * SLOT_HALF_PX) },
    { y: c.middle + SLOT_HALF_PX, h: Math.max(0, c.bottom - c.middle - 2 * SLOT_HALF_PX) },
  ];
}

export function gestureTarget(x: number, y: number, vp: Viewport, kind: { snaps: boolean; docks: boolean }): GestureTarget {
  if (kind.snaps && kind.docks) {
    const zone = snapZone(x, y, vp, SIDE_EDGE_PX);
    if (!zone) return { type: "none" };
    if (zone !== "left" && zone !== "right") return { type: "snap", zone };
    const slot = slotAt(y, vp);
    if (slot) return { type: "dock", side: zone, slot };
    return { type: "snap", zone, gap: y < slotCentres(vp).middle ? 0 : 1 };
  }
  if (kind.snaps) {
    const zone = snapZone(x, y, vp);
    return zone ? { type: "snap", zone } : { type: "none" };
  }
  if (kind.docks) {
    const side = dockSide(x, vp.w, DOCK_EDGE_PX);
    return side ? { type: "dock", side, slot: nearestSlot(x, y, vp).slot } : { type: "none" };
  }
  return { type: "none" };
}

export type GestureGuides = { side: DockSide;   gaps: boolean };

export function gestureGuides(x: number, vp: Viewport, kind: { snaps: boolean; docks: boolean }): GestureGuides | null {
  if (!kind.docks) return null;
  const side: DockSide = x < vp.w / 2 ? "left" : "right";
  const distance = Math.min(x, vp.w - 1 - x);
  if (kind.snaps) return distance <= GUIDE_BAND_PX ? { side, gaps: true } : null;
  return distance <= DOCK_EDGE_PX ? { side, gaps: false } : null;
}
