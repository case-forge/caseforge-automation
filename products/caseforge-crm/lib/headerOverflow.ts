
export const HEADER_ITEMS = ["clock", "view", "flagged", "starred", "bell", "todo", "robot", "newclient"] as const;

export type HeaderItemId = (typeof HEADER_ITEMS)[number];

export const COLLAPSE_ORDER: readonly HeaderItemId[] = ["starred", "flagged", "view", "newclient", "robot", "todo", "bell", "clock"];

export const PANEL_ITEMS: readonly HeaderItemId[] = ["bell", "todo", "robot", "newclient"];

export type HeaderWidths = Partial<Record<HeaderItemId, number>>;

export function fitHeaderItems({
  available,
  reserved,
  gap,
  widths,
  hidden = [],
}: {
  available: number;
  reserved: number;
  gap: number;
  widths: HeaderWidths;

  hidden?: readonly HeaderItemId[];
}): HeaderItemId[] {
  const shown = new Set<HeaderItemId>(HEADER_ITEMS.filter((id) => (widths[id] ?? 0) > 0 && !hidden.includes(id)));
  const needed = () => {
    let total = reserved;
    for (const id of shown) total += (widths[id] ?? 0) + gap;
    return total;
  };
  const collapsed = new Set<HeaderItemId>();
  for (const id of COLLAPSE_ORDER) {
    if (needed() <= available) break;
    if (!shown.has(id)) continue;
    shown.delete(id);
    collapsed.add(id);
  }
  return HEADER_ITEMS.filter((id) => collapsed.has(id));
}

export function sameItems(a: readonly HeaderItemId[], b: readonly HeaderItemId[]): boolean {
  return a.length === b.length && a.every((id, i) => id === b[i]);
}

export const COUNT_ITEMS: readonly HeaderItemId[] = ["view", "flagged", "starred", "bell", "todo", "robot", "newclient"];

export function showsCount(count: number | undefined): count is number {
  return typeof count === "number" && count > 0;
}

export function clientsLabel(count: number): string {
  return count > 0 ? `Clients, ${count} ${count === 1 ? "client needs" : "clients need"} checking` : "Clients";
}

export function calendarLabel(count: number): string {
  return count > 0 ? `Calendar, ${count} ${count === 1 ? "hearing needs" : "hearings need"} review` : "Calendar";
}
