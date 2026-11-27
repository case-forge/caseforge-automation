
export const MAG_MAX = 1.55;
export const MAG_RADIUS = 120;
const GAP = 6;

export function magnifyScale(distance: number, radius: number = MAG_RADIUS, max: number = MAG_MAX): number {
  const d = Math.abs(distance);
  if (d >= radius) return 1;
  return 1 + (max - 1) * 0.5 * (1 + Math.cos((Math.PI * d) / radius));
}

export type Span = { y: number; h: number };
export type Anchor = "start" | "center" | "end";

export function freeSpan(group: { top: number; bottom: number }, obstacles: Span[], band: { min: number; max: number }): { min: number; max: number } {
  let min = band.min;
  let max = band.max;
  for (const o of obstacles) {
    if (o.y + o.h <= group.top) min = Math.max(min, o.y + o.h + GAP);
    else if (o.y >= group.bottom) max = Math.min(max, o.y - GAP);
  }
  return { min, max };
}

export function magnifyGroup(tabs: { id: string; y: number; h: number }[], pointerY: number, anchor: Anchor, limits: { min: number; max: number }): Record<string, Span> {
  const out: Record<string, Span> = {};
  if (!tabs.length) return out;
  const scales = tabs.map((t) => magnifyScale(pointerY - (t.y + t.h / 2)));
  const base = tabs.reduce((n, t) => n + t.h, 0) + (tabs.length - 1) * GAP;
  const extra = tabs.reduce((n, t, i) => n + t.h * (scales[i] - 1), 0);
  const start = tabs[0].y;
  const end = tabs[tabs.length - 1].y + tabs[tabs.length - 1].h;
  const centre = (start + end) / 2;
  let f = 1;
  if (extra > 0) {
    const room =
      anchor === "start" ? limits.max - start - base : anchor === "end" ? end - limits.min - base : Math.min(2 * (centre - limits.min), 2 * (limits.max - centre)) - base;
    f = Math.max(0, Math.min(1, room / extra));
  }
  const heights = tabs.map((t, i) => Math.round(t.h * (1 + (scales[i] - 1) * f)));
  const total = heights.reduce((n, h) => n + h, 0) + (tabs.length - 1) * GAP;
  let y = anchor === "start" ? start : anchor === "end" ? end - total : Math.round(centre - total / 2);
  tabs.forEach((t, i) => {
    out[t.id] = { y, h: heights[i] };
    y += heights[i] + GAP;
  });
  return out;
}
