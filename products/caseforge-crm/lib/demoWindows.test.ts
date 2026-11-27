import { describe, expect, it } from "vitest";
import { DEMO_WINDOWS, toggleAll, clampPosition, clampSize, focusWindow, resizeBox, initialWindows, openAll, patchWindow } from "./demoWindows";

const vp = { w: 1400, h: 900 };

describe("demo windows", () => {
  it("has the five windows, all closed to begin with", () => {
    const list = initialWindows(vp);
    expect(list.map((w) => w.id)).toEqual([...DEMO_WINDOWS]);
    expect(list.every((w) => !w.open)).toBe(true);
  });

  it("starts each window on the page and gives them room", () => {
    for (const w of initialWindows(vp)) {
      expect(w.x).toBeGreaterThanOrEqual(0);
      expect(w.y).toBeGreaterThanOrEqual(0);
      expect(w.x + w.w).toBeLessThanOrEqual(vp.w + 1);
      expect(w.w).toBeGreaterThanOrEqual(300);
      expect(w.h).toBeGreaterThanOrEqual(160);
    }
  });

  it("opens every window, brings a minimised one back, and keeps a stacking order", () => {
    const minimised = patchWindow(initialWindows(vp), "inbox", { minimised: true });
    const opened = openAll(minimised);
    expect(opened.every((w) => w.open && !w.minimised)).toBe(true);
    expect(new Set(opened.map((w) => w.z)).size).toBe(5);
  });

  it("puts the window pressed last in front", () => {
    const list = openAll(initialWindows(vp));
    const focused = focusWindow(list, "inbox");
    const inbox = focused.find((w) => w.id === "inbox")!;
    expect(focused.filter((w) => w.id !== "inbox").every((w) => w.z < inbox.z)).toBe(true);
  });

  it("keeps the title bar on the page and the size above a minimum", () => {
    expect(clampPosition(-5000, -50, 1000, vp)).toEqual({ x: -920, y: 0 });
    expect(clampPosition(5000, 5000, 1000, vp)).toEqual({ x: 1320, y: 860 });
    expect(clampSize(10, 10)).toEqual({ w: 300, h: 160 });
  });
});

describe("resizeBox", () => {
  const start = { x: 100, y: 100, w: 500, h: 400 };
  it("pulls the right and bottom edges without moving the window", () => {
    expect(resizeBox("e", start, 50, 99)).toEqual({ x: 100, y: 100, w: 550, h: 400 });
    expect(resizeBox("s", start, 99, -50)).toEqual({ x: 100, y: 100, w: 500, h: 350 });
  });
  it("pulls the left and top edges, keeping the opposite side fixed", () => {
    expect(resizeBox("w", start, -40, 0)).toEqual({ x: 60, y: 100, w: 540, h: 400 });
    expect(resizeBox("n", start, 0, 60)).toEqual({ x: 100, y: 160, w: 500, h: 340 });
  });
  it("never goes below the minimum size and keeps the far side still", () => {
    const box = resizeBox("nw", start, 900, 900);
    expect(box.w).toBe(300);
    expect(box.x + box.w).toBe(600);
    expect(box.h).toBe(160);
    expect(box.y + box.h).toBe(500);
  });
  it("lets a corner pull both ways", () => {
    expect(resizeBox("se", start, 20, 30)).toEqual({ x: 100, y: 100, w: 520, h: 430 });
  });
});

describe("the DEMO button pressed again", () => {
  it("leaves no window open, a tab included, so the game unloads, and keeps positions and sizes", () => {
    const opened = openAll(initialWindows(vp)).map((w, i) => ({ ...w, minimised: i === 1 }));
    const closed = toggleAll(opened);
    expect(closed.some((w) => w.open)).toBe(false);
    expect(closed.map(({ x, y, w, h }) => ({ x, y, w, h }))).toEqual(opened.map(({ x, y, w, h }) => ({ x, y, w, h })));
  });

  it("opens all five again on the next press, none of them minimised", () => {
    const reopened = toggleAll(toggleAll(openAll(initialWindows(vp))));
    expect(reopened.every((w) => w.open && !w.minimised)).toBe(true);
  });
});
