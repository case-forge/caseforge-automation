
export const SCROLL_DELTA_PX = 6;

export const SHOW_RUN_PX = 24;

export const BOTTOM_SNAP_PX = 2;

export const TOP_ZONE_PX = 64;

export const MIN_SCROLL_PX = 150;

export type ScrollSample = {

  top: number;

  clientHeight: number;

  scrollHeight: number;
};

export function fromBottom({ top, clientHeight, scrollHeight }: ScrollSample): number {
  return scrollHeight - clientHeight - top;
}

export function chromeAfterScroll({
  prev,
  next,
  hidden,
  chromeHeight,
  run,
}: {

  prev: ScrollSample | undefined;
  next: ScrollSample;

  hidden: boolean;

  chromeHeight: number;

  run?: number;
}): "hide" | "show" | null {
  if (next.top <= TOP_ZONE_PX) return hidden ? "show" : null;

  if (!prev || prev.clientHeight !== next.clientHeight) return null;
  const delta = next.top - prev.top;
  if (Math.abs(delta) < SCROLL_DELTA_PX) return null;
  if (delta < 0) return hidden && (run ?? delta) <= -SHOW_RUN_PX ? "show" : null;

  const maxScroll = next.scrollHeight - next.clientHeight;
  if (maxScroll < MIN_SCROLL_PX + chromeHeight) return null;
  return hidden ? null : "hide";
}

export function footerReveal(distance: number | null, footerHeight: number): number {
  if (distance === null) return footerHeight;
  return Math.min(Math.max(footerHeight - Math.max(distance - BOTTOM_SNAP_PX, 0), 0), footerHeight);
}

export function footerPlacement({
  distance,
  headerHidden,
  footerHeight,
}: {
  distance: number | null;
  headerHidden: boolean;
  footerHeight: number;
}): { flow: boolean; reveal: number } {
  if (distance === null) return { flow: true, reveal: footerHeight };
  return { flow: false, reveal: headerHidden ? footerReveal(distance, footerHeight) : 0 };
}

export function noScrollSlack(slack: number, footerInFlow: boolean, footerHeight: number): number {
  return footerInFlow ? slack + footerHeight : slack;
}

export function showBackToTop({ top, clientHeight, scrollHeight }: ScrollSample): boolean {
  const maxScroll = scrollHeight - clientHeight;
  if (maxScroll < MIN_SCROLL_PX) return false;
  return top > Math.min(300, maxScroll * 0.35);
}

export const BACK_TO_TOP_MS = 200;
export function remainingAt(progress: number): number {
  const p = Math.min(Math.max(progress, 0), 1);
  const ease = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
  return 1 - ease;
}

export function canHideHeaderFor(sample: { clientHeight: number; scrollHeight: number }, chromeHeight: number, spacer: number): boolean {
  return sample.scrollHeight - sample.clientHeight - spacer >= MIN_SCROLL_PX + chromeHeight;
}

export function overlayNeeded({ distance, headerHidden, canHideHeader }: { distance: number | null; headerHidden: boolean; canHideHeader: boolean }): boolean {
  return distance !== null && !headerHidden && !canHideHeader;
}

export function overlayFooterShown({ distance, shown }: { distance: number | null; shown: boolean }): boolean {
  if (distance === null) return false;
  return shown ? distance <= SHOW_RUN_PX : distance <= BOTTOM_SNAP_PX;
}

export function hideForFooter({ distance, headerHidden, canHideHeader }: { distance: number | null; headerHidden: boolean; canHideHeader: boolean }): boolean {
  return distance !== null && distance <= BOTTOM_SNAP_PX && !headerHidden && canHideHeader;
}
