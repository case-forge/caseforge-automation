
export function pressTab(open: string, pressed: string): string {
  return open === pressed ? "" : pressed;
}

export function shownTab(open: string, visible: readonly string[]): string {
  return visible.includes(open) ? open : "";
}

export function tabStop(open: string, visible: readonly string[]): string {
  return visible.includes(open) ? open : (visible[0] ?? "");
}

export function arrowTarget(visible: readonly string[], current: string, key: string): string | null {
  if (visible.length === 0) return null;
  const at = Math.max(0, visible.indexOf(current));
  if (key === "ArrowRight") return visible[(at + 1) % visible.length];
  if (key === "ArrowLeft") return visible[(at - 1 + visible.length) % visible.length];
  if (key === "Home") return visible[0];
  if (key === "End") return visible[visible.length - 1];
  return null;
}

let visitOpen = "";

export function rememberedTab(): string {
  return visitOpen;
}

export function rememberTab(id: string): void {
  visitOpen = id;
}
