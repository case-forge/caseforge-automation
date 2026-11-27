import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const dir = (rel: string) => fileURLToPath(new URL(rel, import.meta.url));
const read = (rel: string) => readFileSync(dir(rel), "utf8");
const sources = (rel: string) =>
  readdirSync(dir(rel))
    .filter((f) => /\.(tsx?|css)$/.test(f) && !/\.test\./.test(f))
    .map((f) => [f, readFileSync(dir(`${rel}/${f}`), "utf8")] as const);

describe("the window title bar buttons", () => {
  const actions = read("./WindowActions.tsx");
  it("are Minimise, Pin and Close, with labels, tooltips and a pressed state on the pin", () => {
    for (const label of ["Minimise ${title}", "Pin ${title}", "Close ${title}"]) expect(actions).toContain(label);
    expect(actions).toContain("aria-pressed={pinned}");
    expect(actions).toContain("<IconPin filled={pinned}");
    expect(actions).toContain("cf-btn cf-btn--icon");
  });
  it("every window uses them: the shared bar, the demo windows and the demo panel headings", () => {
    expect(read("./CardBar.tsx")).toContain("<WindowActions");
    expect(read("./DemoWindows.tsx")).toContain("<WindowActions");
  });
  it("there is no maximise or expand button, and no traffic-light dot, anywhere", () => {
    for (const [file, code] of [...sources("../components"), ...sources("../lib"), ...sources("../app")]) {
      expect(code, file).not.toMatch(/toggleMaximise|onExpand|fw-light|demo-light|Fill the page/);
    }
  });
  it("the card windows pass their id and pin to the bar (the hearing slide-out is not a window: no bar, no pin)", () => {
    for (const file of ["./WhatsNew.tsx", "./ClassifierPrompt.tsx"]) {
      const code = read(file);
      expect(code).toContain("pinned={win.pinned}");
      expect(code).toContain("{...win.windowAttrs}");
    }
  });
  it("What's New has only the title-bar Close: no separate Got it button", () => {
    const code = read("./WhatsNew.tsx");
    expect(code).not.toContain("Got it");
    expect(code).not.toContain("whats-new-close");
    expect(code).toContain("onClose={dismiss}");
  });
  it("a remembered or restored box is fitted back onto the screen, for the hook and the demo windows", () => {
    expect(read("../lib/useFloatingBox.ts")).toContain("clampBox(box,");
    expect(read("./DemoWindows.tsx")).toContain("clampBox(win,");
  });
  it("pinned means locked: no drag, no resize grips, no tab drag or arrow moves, and a default cursor", () => {
    expect(read("../lib/windowChrome.ts")).toContain("windowPins.isPinned(id)");
    const hook = read("../lib/useFloatingBox.ts");
    expect(hook.match(/windowPins\.isPinned\(id\)/g)?.length).toBeGreaterThanOrEqual(3);
    expect(read("./DemoWindows.tsx")).toContain("!win.maximised && !pinned");
    for (const file of ["./WhatsNew.tsx", "./ClassifierPrompt.tsx", "./UpcomingRail.tsx"]) expect(read(file)).toContain("!win.pinned && RESIZE_EDGES");
    expect(read("./MinimisedTabs.tsx")).toContain("if (isPinned(item.pinId)) return;");
    expect(read("../app/windows.css")).toContain(".fw-pinned .fw-bar");
  });
  it("the hearings panel is a window, not a sidebar: no rail layout, no edge tab, no page space reserved", () => {
    const css = read("../app/calendar.css");
    expect(css).not.toMatch(/\.hearings-rail\s*[{,\[:]|hearings-rail-tab|hearings-rail-panel|hearings-rail-head|data-rail/);
    expect(css).toContain(".hearings-panel.fw");
    expect(read("./Workspace.tsx")).not.toContain("data-rail");
    expect(read("./MinimisedTabs.tsx")).not.toContain("hearings-rail-tab");
    expect(read("./UpcomingRail.tsx")).toContain("useFloatingBox(RAIL_WINDOW_ID");
    expect(read("./UpcomingRail.tsx")).not.toContain("Open the calendar");
  });
  it("windows are opaque: no layer drops them under the page, short fades, and every cue is cleared when a drag ends", () => {
    const css = read("../app/windows.css");
    expect(css).not.toMatch(/fw-layer-behind\s*\{/);
    for (const m of css.matchAll(/\.fw(?:-away)?\s*\{[^}]*opacity\s+([0-9.]+)s/g)) expect(Number(m[1])).toBeLessThanOrEqual(0.12);
    const hook = read("../lib/useFloatingBox.ts");
    expect(hook).toContain("dockingClass(docking, dragging, minimised)");

    expect(read("../lib/windowPins.ts")).not.toContain("behind = sendBack(");
    expect(hook.match(/setDragging\(false\)/g)?.length).toBeGreaterThanOrEqual(4);
    expect(hook).toContain('window.addEventListener("pointerup", clear)');
    expect(hook).toContain('window.addEventListener("blur", clear)');
  });
  it("titles are never shortened, windows have a minimum width from their title, and the classifier fits its three buttons on one line", () => {
    const bar = read("./CardBar.tsx");
    expect(bar).not.toContain("titleFallbacks");
    expect(bar).toContain('setProperty("--fw-min-w"');
    expect(bar).toContain("minWidthFor(");
    expect(read("../app/windows.css")).toContain("var(--fw-min-w");
    expect(read("../lib/useFloatingBox.ts")).toContain("resizeBox(edge, g.box, event.clientX - g.px, event.clientY - g.py, minW)");
    expect(read("../app/reviewmail.css")).toContain("width: min(28rem, calc(100vw - 32px))");
  });
  it("a scrollbar that appears never moves content: stable gutters on every scroller that can grow, and one viewport width", () => {
    const css = read("../app/globals.css");
    expect(css).toContain("scrollbar-gutter: stable;");
    for (const selector of [".page,", ".hearing-drawer-body,", ".hearings-rail-body,", ".fw-card > .fw-body,", ".demo-window-body,"]) expect(css).toContain(selector);
    expect(css).toContain("@supports not (scrollbar-gutter: stable)");
    for (const file of ["../lib/useFloatingBox.ts", "../lib/windowChrome.ts", "./MinimisedTabs.tsx", "./SnapPreview.tsx", "./DemoWindows.tsx"]) {
      const code = read(file);
      expect(code, file).not.toContain("window.innerWidth");
      expect(code, file).toContain("viewportWidth()");
    }
  });
  it("snapping and dock-by-drag come from the one table in lib/windowSnap.ts, not from per-component flags", () => {
    const hook = read("../lib/useFloatingBox.ts");
    expect(hook).toContain("gestureTarget(event.clientX, event.clientY, vp, windowGestures(id))");
    expect(read("../lib/windowChrome.ts")).toContain("windowGestures(id)");
    for (const file of ["./WhatsNew.tsx", "./ClassifierPrompt.tsx", "./UpcomingRail.tsx", "./HearingDrawer.tsx"]) expect(read(file)).not.toMatch(/useFloatingBox\([^)]*"(card|window)"\)/);
  });
});
