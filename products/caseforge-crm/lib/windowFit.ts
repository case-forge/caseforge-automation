
export type FitBox = { x: number; y: number; w: number; h: number };
type Viewport = { w: number; h: number; top: number };

const SMALLEST_W = 240;
const SMALLEST_H = 120;

export function clampBox(box: FitBox, vp: Viewport): FitBox {
  const w = Math.max(Math.min(box.w, vp.w), Math.min(SMALLEST_W, vp.w));
  const roomH = Math.max(0, vp.h - vp.top);
  const h = Math.max(Math.min(box.h, roomH), Math.min(SMALLEST_H, roomH));
  const x = Math.min(Math.max(box.x, 0), Math.max(0, vp.w - w));
  const y = Math.min(Math.max(box.y, vp.top), Math.max(vp.top, vp.h - h));
  return { x, y, w, h };
}

export function sameBox(a: FitBox, b: FitBox): boolean {
  return a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
}
