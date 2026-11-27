
import { useEffect, useRef } from "react";
import type { RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

export function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.getClientRects().length > 0);
}

export function wrapTarget<T>(items: readonly T[], active: T | null, backwards: boolean): T | null {
  if (items.length === 0) return null;
  const at = active === null ? -1 : items.indexOf(active);
  if (at === -1) return backwards ? items[items.length - 1] : items[0];
  if (!backwards && at === items.length - 1) return items[0];
  if (backwards && at === 0) return items[items.length - 1];
  return null;
}

export function initialFocusTarget<T extends { dataset?: DOMStringMap }>(items: readonly T[]): T | null {
  return items.find((el) => el.dataset?.dialogClose === undefined) ?? items[0] ?? null;
}

export function trapFocus(dialog: HTMLElement): () => void {
  const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  if (!dialog.contains(document.activeElement)) {
    const first = initialFocusTarget(focusableIn(dialog));
    if (first) first.focus();
    else {
      dialog.tabIndex = -1;
      dialog.focus();
    }
  }
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Tab") return;
    const inside = dialog.contains(document.activeElement);
    const next = wrapTarget(focusableIn(dialog), inside ? (document.activeElement as HTMLElement) : null, event.shiftKey);
    if (next) {
      event.preventDefault();
      next.focus();
    }
  };
  document.addEventListener("keydown", onKeyDown);
  return () => {
    document.removeEventListener("keydown", onKeyDown);
    if (opener && opener.isConnected && (document.activeElement === document.body || dialog.contains(document.activeElement))) opener.focus();
  };
}

export function useModalFocus<T extends HTMLElement>(open: boolean, existing?: RefObject<T | null>): RefObject<T | null> {
  const own = useRef<T | null>(null);
  const ref = existing ?? own;
  useEffect(() => {
    if (!open || !ref.current) return;
    return trapFocus(ref.current);
  }, [open, ref]);
  return ref;
}
