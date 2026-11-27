"use client";

import { usePopupZ } from "./popupStack";
import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { clampPosition, headerBottom, resizeBox, viewportWidth } from "@/lib/demoWindows";
import type { ResizeEdge } from "@/lib/demoWindows";
import { minimisedTabs, useIsMinimised } from "@/lib/minimisedTabs";
import { flightVector } from "@/lib/demoDock";
import { windowPins, useWindowLayer } from "@/lib/windowPins";
import { clampBox, sameBox } from "@/lib/windowFit";
import { dockingClass, setDockCue } from "@/lib/dockGesture";
import { boxAtPointer, windowPlace } from "@/lib/windowPlace";
import { useViewportKey } from "@/lib/useViewportKey";
import { isFullZone, resolveSnapBox, restoreFromSnap, setSnapPreview, snapFillsPage, windowGestures } from "@/lib/windowSnap";
import { gestureGuides, gestureTarget } from "@/lib/windowGesture";
import { nearestSlot } from "@/lib/demoDock";

export type Box = { x: number; y: number; w: number; h: number };

export type FloatingBox = {

  windowRef: React.RefObject<HTMLElement | null>;
  style: React.CSSProperties | undefined;
  maximised: boolean;
  minimised: boolean;
  pinned: boolean;

  windowClass: string;

  windowAttrs: { "data-window-id": string };
  minimise: () => void;
  restore: () => void;

  barProps: {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerCancel: (event: ReactPointerEvent<HTMLElement>) => void;
    onDoubleClick: (event: React.MouseEvent<HTMLElement>) => void;
  };

  gripProps: (edge: ResizeEdge) => {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: () => void;
    onPointerCancel: () => void;
  };
};

export function useFloatingBox(id: string, title: string): FloatingBox {
  const windowRef = useRef<HTMLElement | null>(null);
  const [box, setBox] = useState<Box | null>(() => (typeof window === "undefined" ? null : windowPins.savedBox(id)));
  const { layer, pinned, zIndex: ownZ } = useWindowLayer(id);

  const stacked = usePopupZ(id);
  const zIndex = ownZ ?? (layer === "front" ? stacked : null);
  const [maximised, setMaximised] = useState(false);
  const minimised = useIsMinimised(id);
  const drag = useRef<{ px: number; py: number; box: Box; grabX: number; grabY: number; moved: boolean } | null>(null);

  const [snapPrev, setSnapPrev] = useState<Box | null>(null);

  const [flight, setFlight] = useState<{ x: number; y: number } | null>(null);
  const grip = useRef<{ px: number; py: number; box: Box } | null>(null);

  const [docking, setDocking] = useState(false);

  const [dragging, setDragging] = useState(false);

  const viewportKey = useViewportKey();
  useEffect(() => {
    if (!box || minimised || maximised) return;
    const fit = clampBox(box, { w: viewportWidth(), h: window.innerHeight, top: headerBottom() });
    if (!sameBox(fit, box)) setBox(fit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minimised, maximised, viewportKey, box === null]);

  useEffect(() => {
    if (minimised) return;
    const at = windowPlace.take(id);
    if (!at) return;
    const el = windowRef.current;
    const w = el?.offsetWidth ?? box?.w ?? 480;
    const h = el?.offsetHeight ?? box?.h ?? 320;
    setSnapPrev(null);
    setMaximised(false);
    setBox(clampBox(boxAtPointer(at, w, h), { w: viewportWidth(), h: window.innerHeight, top: headerBottom() }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minimised]);

  useEffect(() => {
    if (!dragging) return;
    const clear = () => {
      drag.current = null;
      setDragging(false);
      setDocking(false);
      setDockCue(null);
      setSnapPreview(null);
    };
    window.addEventListener("pointerup", clear);
    window.addEventListener("pointercancel", clear);
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("pointerup", clear);
      window.removeEventListener("pointercancel", clear);
      window.removeEventListener("blur", clear);
    };
  }, [dragging]);
  useEffect(() => {
    if (minimised) {
      setDocking(false);
      setDragging(false);
    }
  }, [minimised]);

  useEffect(() => {
    if (box) windowPins.saveBox(id, box);
  }, [box, id]);

  useEffect(() => () => minimisedTabs.remove(id), [id]);

  const measure = useCallback((): Box => {
    const rect = windowRef.current?.getBoundingClientRect();
    return { x: rect?.left ?? 0, y: rect?.top ?? 0, w: rect?.width ?? 480, h: rect?.height ?? 400 };
  }, []);

  const interactive = (event: ReactPointerEvent<HTMLElement>) => !!(event.target as Element).closest("button, a, input, select, textarea");

  const barProps: FloatingBox["barProps"] = {
    onPointerDown(event) {
      if (windowPins.isPinned(id) || (maximised && !snapPrev) || interactive(event) || (event.pointerType === "mouse" && event.button !== 0)) return;
      const start = measure();
      drag.current = { px: event.clientX, py: event.clientY, box: maximised ? start : (box ?? start), grabX: start.w ? (event.clientX - start.x) / start.w : 0.5, grabY: event.clientY - start.y, moved: false };
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {

      }
    },
    onPointerMove(event) {
      const start = drag.current;
      if (!start) return;
      const vp = { w: viewportWidth(), h: window.innerHeight, top: headerBottom() };
      if (snapPrev && !start.moved) {
        if (Math.hypot(event.clientX - start.px, event.clientY - start.py) < 5) return;
        const back = restoreFromSnap(snapPrev, { x: event.clientX, y: event.clientY }, start.grabX, start.grabY, vp);
        setMaximised(false);
        setSnapPrev(null);
        setBox(back);
        drag.current = { ...start, px: event.clientX, py: event.clientY, box: back, moved: true };
        return;
      }
      start.moved = true;
      setDragging(true);
      const at = clampPosition(start.box.x + event.clientX - start.px, start.box.y + event.clientY - start.py, start.box.w, vp);
      setBox({ ...start.box, ...at });

      const kind = windowGestures(id);
      const target = gestureTarget(event.clientX, event.clientY, vp, kind);
      const guides = gestureGuides(event.clientX, vp, kind);
      setSnapPreview(target.type === "snap" ? resolveSnapBox(id, target.zone, vp, { w: start.box.w, h: start.box.h }, event.clientY) : null);
      setDockCue(
        guides
          ? {
              side: guides.side,
              slot: target.type === "dock" ? target.slot : nearestSlot(event.clientX, event.clientY, vp).slot,
              title,
              gaps: guides.gaps,
              over: target.type === "dock" ? "slot" : target.type === "snap" && target.gap !== undefined ? "gap" : "none",
              gap: target.type === "snap" ? (target.gap ?? 0) : 0,
            }
          : null,
      );
      setDocking(target.type === "dock");
    },
    onPointerUp(event) {
      const start = drag.current;
      drag.current = null;
      setSnapPreview(null);
      setDockCue(null);
      setDocking(false);
      setDragging(false);
      if (!start?.moved) return;
      const vp = { w: viewportWidth(), h: window.innerHeight, top: headerBottom() };
      const target = gestureTarget(event.clientX, event.clientY, vp, windowGestures(id));
      if (target.type === "dock") {

        const rect = windowRef.current?.getBoundingClientRect();
        if (rect) setFlight(flightVector({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }, target.side, target.slot, vp));
        minimisedTabs.add(id, title, { side: target.side, slot: target.slot }, rect ? { w: rect.width, h: rect.height } : undefined);
        return;
      }
      if (target.type !== "snap") return;
      setSnapPrev(snapPrev ?? start.box);
      if (isFullZone(target.zone) && snapFillsPage(id)) setMaximised(true);
      else setBox(resolveSnapBox(id, target.zone, vp, { w: start.box.w, h: start.box.h }, event.clientY));
    },
    onPointerCancel() {
      drag.current = null;
      setDragging(false);
      setDockCue(null);
      setDocking(false);
      setSnapPreview(null);
    },

    onDoubleClick(event) {
      if (windowPins.isPinned(id)) return;
      if (interactive(event as unknown as ReactPointerEvent<HTMLElement>)) return;
      windowPins.clearBox(id);
      setBox(null);
      setSnapPrev(null);
      setMaximised(false);
    },
  };

  const gripProps: FloatingBox["gripProps"] = (edge) => ({
    onPointerDown(event) {
      event.stopPropagation();
      if (windowPins.isPinned(id)) return;
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {

      }
      grip.current = { px: event.clientX, py: event.clientY, box: box ?? measure() };
    },
    onPointerMove(event) {
      const g = grip.current;
      if (g) {
        setSnapPrev(null);

        const minW = windowRef.current ? parseFloat(getComputedStyle(windowRef.current).minWidth) || 0 : 0;
        setBox(resizeBox(edge, g.box, event.clientX - g.px, event.clientY - g.py, minW));
      }
    },
    onPointerUp() {
      grip.current = null;
    },
    onPointerCancel() {
      grip.current = null;
    },
  });

  const away = { ...(flight ? { "--away-x": `${flight.x}px`, "--away-y": `${flight.y}px` } : {}), ...(zIndex !== null ? { zIndex } : {}) } as React.CSSProperties;
  const style: React.CSSProperties | undefined = maximised
    ? { top: headerBottom(), ...away }
    : box
      ? { left: box.x, top: box.y, width: box.w, height: box.h, right: "auto", bottom: "auto", ...away }
      : away;

  return {
    windowRef,
    style,
    maximised,
    minimised,
    pinned,
    windowClass: `fw-layer-${layer}${dockingClass(docking, dragging, minimised)}${pinned ? " fw-pinned" : ""}${maximised ? " fw-max" : ""}${minimised ? " fw-away" : ""}`,
    windowAttrs: { "data-window-id": id },
    minimise: () => {
      const sized = windowRef.current;
      minimisedTabs.add(id, title, undefined, sized ? { w: sized.offsetWidth, h: sized.offsetHeight } : undefined);
      const tab = minimisedTabs.get().find((t) => t.id === id);
      const rect = windowRef.current?.getBoundingClientRect();
      if (tab && rect) setFlight(flightVector({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }, tab.side, tab.slot, { w: viewportWidth(), h: window.innerHeight, top: headerBottom() }));
    },
    restore: () => minimisedTabs.remove(id),
    barProps,
    gripProps,
  };
}
