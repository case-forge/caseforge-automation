
export const EDGE = 90;
export const MAX_STEP = 28;

export function edgeScrollStep(pointer: number, start: number, end: number, edge: number = EDGE, max: number = MAX_STEP): number {
  if (!(end > start) || !Number.isFinite(pointer)) return 0;
  const band = Math.min(edge, (end - start) / 2);
  if (pointer < start + band) return -Math.ceil((max * Math.min(1, (start + band - pointer) / band)));
  if (pointer > end - band) return Math.ceil(max * Math.min(1, (pointer - (end - band)) / band));
  return 0;
}
