"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { WindowActions } from "./WindowActions";
import { useWindowLayer } from "@/lib/windowPins";
import { clampBox, sameBox } from "@/lib/windowFit";
import { useViewportKey } from "@/lib/useViewportKey";
import { flightVector } from "@/lib/demoDock";
import { RESIZE_EDGES, demoWindows, headerBottom, resizeBox, viewportWidth } from "@/lib/demoWindows";
import { attachBarTools, attachDrag, attachHeadingChrome } from "@/lib/windowChrome";
import type { DemoWindow } from "@/lib/demoWindows";
import { loadGame, unloadGame } from "@/lib/gameHost";
import type { GameParts } from "@/lib/gameHost";

const serverSnapshot: DemoWindow[] = [];

export function useDemoWindows(): DemoWindow[] {
  return useSyncExternalStore(demoWindows.subscribe, demoWindows.get, () => serverSnapshot);
}

const HEADING = ".panel-title, .case-board-head";

function DemoWindowView({ win, parts }: { win: DemoWindow; parts: GameParts | null }) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const grip = useRef<{ px: number; py: number; x: number; y: number; w: number; h: number } | null>(null);

  const part = parts?.get(win.id) ?? null;
  const heading = part?.querySelector<HTMLElement>(HEADING) ?? null;
  const [host, setHost] = useState<HTMLElement | null>(null);
  const { pinned, layer, zIndex } = useWindowLayer(win.id);

  const viewportKey = useViewportKey();
  useEffect(() => {
    if (win.minimised || win.maximised) return;
    const fit = clampBox(win, { w: viewportWidth(), h: window.innerHeight, top: headerBottom() });
    if (!sameBox(fit, win)) demoWindows.patch(win.id, fit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [win.minimised, win.maximised, viewportKey]);
  useEffect(() => {
    const body = bodyRef.current;
    if (part && body && part.parentElement !== body) body.appendChild(part);
    if (heading) {
      const chrome = attachHeadingChrome(heading, win.id);
      setHost(chrome.host);
      return () => {
        chrome.stop();
        setHost(null);
      };
    }
    if (barRef.current) {
      const stopDrag = attachDrag(barRef.current, win.id);
      const stopTools = win.id === "demo" && part ? attachBarTools(barRef.current) : null;
      return () => {
        stopDrag();
        stopTools?.();
      };
    }
  }, [part, heading, win.id, win.open]);

  const vpSize = typeof window === "undefined" ? { w: 1200, h: 800 } : { w: viewportWidth(), h: window.innerHeight, top: headerBottom() };
  const centre = win.maximised ? { x: vpSize.w / 2, y: vpSize.h / 2 } : { x: win.x + win.w / 2, y: win.y + win.h / 2 };
  const flight = flightVector(centre, win.side, win.slot, vpSize);
  const away = { "--away-x": `${flight.x}px`, "--away-y": `${flight.y}px` } as React.CSSProperties;
  const style = win.maximised
    ? { zIndex: zIndex ?? 900 + win.z, top: headerBottom(), ...away }
    : { left: win.x, top: win.y, width: win.w, height: win.h, zIndex: zIndex ?? 900 + win.z, ...away };

  return (
    <section
      className={`fw fw-layer-${layer}${pinned ? " fw-pinned" : ""}${win.maximised ? " fw-max" : ""}${win.minimised ? " fw-away" : ""}`}
      data-window-id={win.id}
      style={style}
      aria-hidden={win.minimised}
      aria-label={win.title}
      onPointerDown={() => demoWindows.focus(win.id)}
    >
      {!heading && (
        <div className="fw-bar" ref={barRef}>
          <span className="fw-title">{win.title}</span>
          <WindowActions id={win.id} title={win.title} pinned={pinned} onMinimise={() => demoWindows.minimise(win.id)} onClose={() => demoWindows.close(win.id)} />
        </div>
      )}
      {host && createPortal(<WindowActions id={win.id} title={win.title} pinned={pinned} onMinimise={() => demoWindows.minimise(win.id)} onClose={() => demoWindows.close(win.id)} />, host)}
      <div className="demo-window-body demo-game" ref={bodyRef}>
        {!parts && <p className="demo-window-loading">Loading the demo…</p>}
      </div>
      {!win.maximised && !pinned &&
        RESIZE_EDGES.map((edge) => (
          <div
            key={edge}
            className={`fw-grip fw-grip-${edge}`}
            aria-hidden="true"
            onPointerDown={(event) => {
              event.stopPropagation();
              event.currentTarget.setPointerCapture(event.pointerId);
              grip.current = { px: event.clientX, py: event.clientY, x: win.x, y: win.y, w: win.w, h: win.h };
            }}
            onPointerMove={(event) => {
              const g = grip.current;
              if (g) demoWindows.patch(win.id, { ...resizeBox(edge, g, event.clientX - g.px, event.clientY - g.py), snapPrev: null });
            }}
            onPointerUp={() => {
              grip.current = null;
            }}
            onPointerCancel={() => {
              grip.current = null;
            }}
          />
        ))}
    </section>
  );
}

export function DemoWindows() {
  const windows = useDemoWindows();
  const [parts, setParts] = useState<GameParts | null>(null);
  const [failed, setFailed] = useState("");
  const anyOpen = windows.some((w) => w.open);

  useEffect(() => {
    if (!anyOpen || parts) return;
    loadGame().then(setParts, (error: Error) => setFailed(error.message));
  }, [anyOpen, parts]);

  useEffect(() => {
    if (anyOpen || (!parts && !failed)) return;
    unloadGame();

    void Promise.resolve().then(() => {
      setParts(null);
      setFailed("");
    });
  }, [anyOpen, parts, failed]);

  if (typeof document === "undefined") return null;
  return createPortal(
    <>
      {windows.filter((w) => w.open).map((win) => (
        <DemoWindowView key={win.id} win={win} parts={parts} />
      ))}
      {failed && <p className="demo-window-error" role="alert">The demo could not load: {failed}</p>}
    </>,
    document.body,
  );
}
