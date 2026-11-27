"use client";

import { useEffect, useRef, useState } from "react";
import { demoWindows, headerBottom, viewportWidth } from "@/lib/demoWindows";
import { moveByKey, nearestSlot, slotTargets, tabBand, tabHeight } from "@/lib/demoDock";
import { freeSpan, magnifyGroup } from "@/lib/dockMagnify";
import { placeTabs } from "@/lib/dockPlacement";
import type { DockSide, DockSlot } from "@/lib/demoDock";
import { minimisedTabs, useMinimisedTabs } from "@/lib/minimisedTabs";
import { dropAction, ghostStart, pullState } from "@/lib/dockGesture";
import { boxAtPointer, windowPlace } from "@/lib/windowPlace";
import { clampBox } from "@/lib/windowFit";
import { useIsPinned, windowPins } from "@/lib/windowPins";
import { countBadge, useHearingsUpcomingCount } from "@/lib/hearingsHost";
import { IconPin } from "./icons";
import { useDemoWindows } from "./DemoWindows";

type Item = { key: string; pinId: string; size: { w: number; h: number }; openAt: (x: number, y: number) => void; title: string; side: DockSide; slot: DockSlot; seq: number; restore: () => void; move: (side: DockSide, slot: DockSlot) => void };
type Drag = { key: string; mx: number; my: number; px: number; py: number; x: number; y: number; cx: number; cy: number; moved: boolean; target: { side: DockSide; slot: DockSlot } | null };

function viewport() {
  return { w: viewportWidth(), h: window.innerHeight, top: headerBottom() };
}

export function MinimisedTabs() {
  const windows = useDemoWindows();
  const others = useMinimisedTabs();
  const isPinned = useIsPinned();
  const upcoming = useHearingsUpcomingCount();
  const [drag, setDrag] = useState<Drag | null>(null);
  const [vpSize, setVpSize] = useState({ w: 1200, h: 800, top: 56 });

  const [hover, setHover] = useState<{ key: string; y: number } | null>(null);
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const refocus = useRef<string | null>(null);

  useEffect(() => {
    const measure = () => {
      const next = viewport();
      setVpSize((old) => (old.w === next.w && old.h === next.h && old.top === next.top ? old : next));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("resize", measure);
    };
  }, []);

  useEffect(() => {
    if (refocus.current) refs.current.get(refocus.current)?.focus();
    refocus.current = null;
  });

  const items: Item[] = [
    ...windows
      .filter((w) => w.open && w.minimised)
      .map((w) => ({ key: `demo:${w.id}`, pinId: w.id, size: { w: w.w, h: w.h }, openAt: (x: number, y: number) => {
        const fit = clampBox(boxAtPointer({ x, y }, w.w, w.h), viewport());
        demoWindows.patch(w.id, { ...fit, snapPrev: null, maximised: false });
        demoWindows.restore(w.id);
        windowPins.bringForward(w.id);
      }, title: w.title, side: w.side, slot: w.slot, seq: w.dockSeq, restore: () => {
        demoWindows.restore(w.id);
        windowPins.bringForward(w.id);
      }, move: (side: DockSide, slot: DockSlot) => demoWindows.dock(w.id, side, slot) })),
    ...others.map((t) => ({ key: `tab:${t.id}`, pinId: t.id, size: t.size ?? { w: 420, h: 300 }, openAt: (x: number, y: number) => {
        windowPlace.request(t.id, { x, y });
        minimisedTabs.remove(t.id);
        windowPins.bringForward(t.id);
      }, title: t.title, side: t.side, slot: t.slot, seq: t.seq, restore: () => {
        minimisedTabs.remove(t.id);
        windowPins.bringForward(t.id);
      }, move: (side: DockSide, slot: DockSlot) => minimisedTabs.move(t.id, { side, slot }) })),
  ];
  if (!items.length) return null;
  const placed = placeTabs(items.map((i) => ({ id: i.key, side: i.side, slot: i.slot, seq: i.seq, h: tabHeight(i.title) })), vpSize);

  const draggedItem = drag?.moved ? items.find((i) => i.key === drag.key) : undefined;
  const pulling = !!(drag?.moved && pullState(drag.mx, vpSize.w).pulling);

  const reduced = typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const hovered = hover && !drag?.moved && !reduced ? items.find((i) => i.key === hover.key) : undefined;
  let shown = placed;
  if (hover && hovered) {
    const group = items.filter((i) => i.side === hovered.side && i.slot === hovered.slot).sort((a, b) => a.seq - b.seq).map((i) => ({ id: i.key, y: placed[i.key].y, h: placed[i.key].h }));
    const top = Math.min(...group.map((g) => g.y));
    const bottom = Math.max(...group.map((g) => g.y + g.h));
    const others = items.filter((i) => i.side === hovered.side && i.slot !== hovered.slot).map((i) => ({ y: placed[i.key].y, h: placed[i.key].h }));
    const limits = freeSpan({ top, bottom }, others, tabBand(vpSize));
    shown = { ...placed, ...magnifyGroup(group, hover.y, hovered.slot === "top" ? "start" : hovered.slot === "bottom" ? "end" : "center", limits) };
  }

  return (
    <>
      {draggedItem && drag && (
        <div className="fw-pull-ghost-layer" aria-hidden="true">
          <div
            className={`fw-pull-ghost${pulling ? " fw-pull-ghost-on" : ""}`}
            style={{ left: drag.mx - draggedItem.size.w / 2, top: drag.my - 16, width: draggedItem.size.w, height: draggedItem.size.h, ["--tab-sx" as string]: ghostStart({ w: 28, h: tabHeight(draggedItem.title) }, draggedItem.size).sx, ["--tab-sy" as string]: ghostStart({ w: 28, h: tabHeight(draggedItem.title) }, draggedItem.size).sy }}
          >
            <span className="fw-pull-ghost-title">{draggedItem.title}</span>
          </div>
        </div>
      )}
      {drag?.moved && !pulling && (
        <div className="fw-tab-targets" aria-hidden="true">
          {slotTargets(vpSize).map((t) => (
            <span
              key={`${t.side}-${t.slot}`}
              className={`fw-tab-target fw-tab-target-${t.side}${drag.target?.side === t.side && drag.target.slot === t.slot ? " fw-tab-target-on" : ""}`}
              style={{ top: t.y - 36 }}
            />
          ))}
        </div>
      )}
      {items.map((item) => {
        const dragging = drag?.key === item.key && drag.moved;
        const height = shown[item.key].h;
        const style = dragging ? { left: drag.cx, top: drag.cy, height, zIndex: 7300 } : { [item.side]: 0, top: shown[item.key].y, height };
        return (
          <button
            key={item.key}
            ref={(el) => {
              if (el) refs.current.set(item.key, el);
              else refs.current.delete(item.key);
            }}
            type="button"
            className={`fw-tab fw-tab-${item.side}${dragging ? " fw-tab-dragging" : ""}${dragging && pulling ? " fw-tab-pulled" : ""}`}
            style={style}
            title={isPinned(item.pinId) ? `Open ${item.title} (pinned: unpin it to move)` : `Open ${item.title}. Drag, or use the arrow keys, to move this tab.`}
            aria-label={item.pinId === "hearings-rail" && countBadge(upcoming) ? `Open ${item.title}, ${upcoming} upcoming hearings` : `Open ${item.title}`}
            onPointerDown={(event) => {
              if (isPinned(item.pinId)) return;
              event.currentTarget.setPointerCapture(event.pointerId);
              const r = event.currentTarget.getBoundingClientRect();
              setDrag({ key: item.key, mx: event.clientX, my: event.clientY, px: event.clientX, py: event.clientY, x: r.left, y: r.top, cx: r.left, cy: r.top, moved: false, target: null });
            }}
            onPointerLeave={() => setHover(null)}
            onPointerMove={(event) => {
              if (event.pointerType === "mouse" && !drag) setHover({ key: item.key, y: event.clientY });
              if (!drag || drag.key !== item.key) return;
              const dx = event.clientX - drag.px;
              const dy = event.clientY - drag.py;
              if (!drag.moved && Math.hypot(dx, dy) < 6) return;
              setDrag({ ...drag, mx: event.clientX, my: event.clientY, cx: drag.x + dx, cy: drag.y + dy, moved: true, target: nearestSlot(event.clientX, event.clientY, vpSize) });
            }}
            onPointerUp={(event) => {
              if (drag?.key === item.key && drag.moved && dropAction(event.clientX, vpSize.w) === "pull-off") {

                item.openAt(event.clientX, event.clientY);
                window.setTimeout(() => setDrag(null), 0);
                setDrag({ ...drag, moved: false, target: null, cx: -9999 });
                return;
              }
              if (drag?.key === item.key && drag.moved && drag.target) {
                item.move(drag.target.side, drag.target.slot);
                refocus.current = item.key;

                window.setTimeout(() => setDrag(null), 0);
                setDrag({ ...drag, moved: false, target: null, cx: -9999 });
                return;
              }
              setDrag(null);
            }}
            onPointerCancel={() => setDrag(null)}
            onClick={() => {
              if (!drag?.moved && drag?.cx !== -9999) item.restore();
            }}
            onKeyDown={(event) => {
              if (!event.key.startsWith("Arrow") || isPinned(item.pinId)) return;
              event.preventDefault();
              const to = moveByKey(item.side, item.slot, event.key);
              if (to.side !== item.side || to.slot !== item.slot) {
                item.move(to.side, to.slot);
                refocus.current = item.key;
              }
            }}
          >
            {isPinned(item.pinId) && <IconPin filled className="fw-tab-pin" aria-hidden="true" />}
            <span className="fw-tab-title">{item.title}</span>
            {item.pinId === "hearings-rail" && countBadge(upcoming) && (
              <span className="window-count fw-tab-count" role="img" aria-label={`${upcoming} upcoming hearings`}>
                {upcoming}
              </span>
            )}
          </button>
        );
      })}
    </>
  );
}
