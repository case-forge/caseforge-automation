
import { clampPosition, demoWindows, headerBottom, startingBox, viewportWidth } from "./demoWindows";
import type { DemoWindowId } from "./demoWindows";
import { windowPins } from "./windowPins";
import { isFullZone, restoreFromSnap, setSnapPreview, snapBox, windowGestures } from "./windowSnap";
import { gestureTarget } from "./windowGesture";

export function attachDrag(handle: HTMLElement, id: string): () => void {
  let drag: { px: number; py: number; x: number; y: number; w: number; grabX: number; grabY: number; moved: boolean } | null = null;
  const current = () => demoWindows.get().find((w) => w.id === id);
  const viewport = () => ({ w: viewportWidth(), h: window.innerHeight, top: headerBottom() });
  const down = (event: PointerEvent) => {
    const win = current();
    if (!win || windowPins.isPinned(id) || (win.maximised && !win.snapPrev) || (event.target as Element).closest("button, select, input, a, label")) return;
    handle.setPointerCapture(event.pointerId);
    const rect = handle.closest(".fw")?.getBoundingClientRect();
    const left = win.maximised ? (rect?.left ?? 0) : win.x;
    const top = win.maximised ? (rect?.top ?? 0) : win.y;
    const width = win.maximised ? (rect?.width ?? win.w) : win.w;
    drag = { px: event.clientX, py: event.clientY, x: left, y: top, w: width, grabX: width ? (event.clientX - left) / width : 0.5, grabY: event.clientY - top, moved: false };
    demoWindows.focus(id);
  };
  const move = (event: PointerEvent) => {
    if (!drag) return;
    const vp = viewport();
    const win = current();
    if (win?.snapPrev && !drag.moved) {
      if (Math.hypot(event.clientX - drag.px, event.clientY - drag.py) < 5) return;
      const back = restoreFromSnap(win.snapPrev, { x: event.clientX, y: event.clientY }, drag.grabX, drag.grabY, vp);
      demoWindows.patch(id, { ...back, maximised: false, snapPrev: null });
      drag = { ...drag, px: event.clientX, py: event.clientY, x: back.x, y: back.y, w: back.w, moved: true };
    }
    drag.moved = true;
    demoWindows.patch(id, clampPosition(drag.x + event.clientX - drag.px, drag.y + event.clientY - drag.py, drag.w, vp));
    const target = gestureTarget(event.clientX, event.clientY, vp, windowGestures(id));
    setSnapPreview(target.type === "snap" ? snapBox(target.zone, vp) : null);
  };
  const up = (event: PointerEvent) => {
    const win = current();
    const target = drag?.moved && event.type === "pointerup" ? gestureTarget(event.clientX, event.clientY, viewport(), windowGestures(id)) : { type: "none" as const };
    const zone = target.type === "snap" ? target.zone : null;
    if (zone && win) {
      const prev = win.snapPrev ?? { x: win.x, y: win.y, w: win.w, h: win.h };
      if (isFullZone(zone)) demoWindows.patch(id, { maximised: true, snapPrev: prev });
      else demoWindows.patch(id, { ...snapBox(zone, viewport()), maximised: false, snapPrev: prev });
    }
    setSnapPreview(null);
    drag = null;
  };

  const reset = (event: MouseEvent) => {
    if (windowPins.isPinned(id) || (event.target as Element).closest("button, select, input, a, label")) return;
    demoWindows.patch(id, { ...startingBox(id as DemoWindowId, viewport()), maximised: false, snapPrev: null });
  };
  handle.addEventListener("dblclick", reset);
  handle.addEventListener("pointerdown", down);
  handle.addEventListener("pointermove", move);
  handle.addEventListener("pointerup", up);
  handle.addEventListener("pointercancel", up);
  return () => {
    handle.removeEventListener("dblclick", reset);
    handle.removeEventListener("pointerdown", down);
    handle.removeEventListener("pointermove", move);
    handle.removeEventListener("pointerup", up);
    handle.removeEventListener("pointercancel", up);
  };
}

export function attachHeadingChrome(heading: HTMLElement, id: string): { host: HTMLElement; stop: () => void } {
  const host = document.createElement("span");
  host.className = "fw-actions-host";
  heading.appendChild(host);
  heading.classList.add("demo-handle");
  const stopDrag = attachDrag(heading, id);
  return {
    host,
    stop: () => {
      stopDrag();
      host.remove();
      heading.classList.remove("demo-handle");
    },
  };
}

export function attachBarTools(bar: HTMLElement): () => void {
  const tools = document.createElement("span");
  tools.className = "demo-bar-tools";
  for (const [label, id] of [["Hint", "hintToggleBtn"], ["Categories", "categoriesBtn"], ["Reset all", "resetAllBtn"]] as const) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "demo-bar-text";
    const show = () => {
      button.textContent = id === "categoriesBtn" ? `Categories: ${document.documentElement.dataset.categories === "off" ? "off" : "on"}` : label;
    };
    show();
    button.onclick = () => {
      document.getElementById(id)?.click();
      show();
    };
    tools.appendChild(button);
  }
  bar.appendChild(tools);
  return () => tools.remove();
}
