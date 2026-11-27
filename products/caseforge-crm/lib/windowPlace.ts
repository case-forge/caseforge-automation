
const pending = new Map<string, { x: number; y: number }>();

export const windowPlace = {
  request(id: string, at: { x: number; y: number }) {
    pending.set(id, at);
  },
  take(id: string): { x: number; y: number } | null {
    const at = pending.get(id) ?? null;
    pending.delete(id);
    return at;
  },
};

export function boxAtPointer(at: { x: number; y: number }, w: number, h: number): { x: number; y: number; w: number; h: number } {
  return { x: Math.round(at.x - w / 2), y: Math.round(at.y - 16), w, h };
}
