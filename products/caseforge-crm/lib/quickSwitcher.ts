
import { useEffect, useRef } from "react";

export const MIN_QUERY_LENGTH = 2;

export const SWITCHER_DEBOUNCE_MS = 200;

export const SWITCHER_LIMIT = 8;

export type ShortcutKey = {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  repeat?: boolean;
  defaultPrevented?: boolean;
};

export type ShortcutTarget = { closest(selector: string): unknown } | null | undefined;

export function isMacPlatform(platform: string | undefined, userAgent: string | undefined): boolean {
  return /Mac|iPhone|iPad|iPod/i.test(platform || userAgent || "");
}

export function isSwitcherShortcut(event: ShortcutKey, isMac: boolean): boolean {
  if (event.key.toLowerCase() !== "k") return false;
  if (event.altKey || event.shiftKey || event.repeat) return false;
  return isMac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
}

export function switcherShortcutAction(
  event: ShortcutKey,
  target: ShortcutTarget,
  state: { isMac: boolean; open: boolean; modalOpen: boolean },
): "open" | "close" | null {
  if (!isSwitcherShortcut(event, state.isMac)) return null;
  if (state.open) return "close";

  if (event.defaultPrevented) return null;
  if (target?.closest("[data-keeps-ctrl-k]")) return null;

  if (state.modalOpen) return null;
  return "open";
}

export function isModalOpen(doc: { querySelector(selector: string): unknown } | undefined): boolean {
  return Boolean(doc?.querySelector('[aria-modal="true"]'));
}

export type SwitcherMode = "recent" | "search";

export function switcherMode(query: string): SwitcherMode {
  return query.trim().length < MIN_QUERY_LENGTH ? "recent" : "search";
}

export function switcherStatus(state: {
  mode: SwitcherMode;
  query: string;
  loading: boolean;
  error: string | null;
  count: number;
}): string | null {
  if (state.mode === "recent") {
    return state.count === 0 ? "Type 2 or more characters to search. Clients you open appear here." : null;
  }
  if (state.error) return `Search failed: ${state.error}`;
  if (state.count > 0) return null;
  if (state.loading) return "Searching…";
  return `No clients match "${state.query.trim()}".`;
}

export function useSwitcherShortcut(open: boolean, setOpen: (next: boolean) => void): void {
  const openRef = useRef(open);
  useEffect(() => {
    openRef.current = open;
  }, [open]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const isMac = isMacPlatform(window.navigator.platform, window.navigator.userAgent);
    const onKeyDown = (event: KeyboardEvent) => {
      const action = switcherShortcutAction(event, event.target as Element | null, {
        isMac,
        open: openRef.current,
        modalOpen: isModalOpen(document),
      });
      if (!action) return;

      event.preventDefault();
      setOpen(action === "open");
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setOpen]);
}
