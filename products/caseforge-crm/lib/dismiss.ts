
import { useEffect, useRef } from "react";
import type { RefObject } from "react";

export type DismissReason = "outside" | "escape";

type Root = { contains(node: Node | null): boolean } | null | undefined;

export type DismissHost = {
  addEventListener(type: string, listener: (event: Event) => void): void;
  removeEventListener(type: string, listener: (event: Event) => void): void;
};

export function isOutside(target: unknown, roots: readonly Root[]): boolean {
  return !roots.some((root) => root != null && root.contains(target as Node | null));
}

export function attachDismiss(host: DismissHost, getRoots: () => readonly Root[], onDismiss: (reason: DismissReason) => void): () => void {
  const onPointerDown = (event: Event) => {
    if (isOutside(event.target, getRoots())) onDismiss("outside");
  };
  const onKeyDown = (event: Event) => {
    if ((event as KeyboardEvent).key === "Escape") onDismiss("escape");
  };
  host.addEventListener("pointerdown", onPointerDown);
  host.addEventListener("keydown", onKeyDown);
  return () => {
    host.removeEventListener("pointerdown", onPointerDown);
    host.removeEventListener("keydown", onKeyDown);
  };
}

export function useDismiss(
  open: boolean,
  onDismiss: (reason: DismissReason) => void,
  ...refs: RefObject<Element | null>[]
): void {
  const latest = useRef({ onDismiss, refs });
  useEffect(() => {
    latest.current = { onDismiss, refs };
  });
  useEffect(() => {
    if (!open) return;
    return attachDismiss(
      document,
      () => latest.current.refs.map((ref) => ref.current),
      (reason) => latest.current.onDismiss(reason),
    );
  }, [open]);
}
