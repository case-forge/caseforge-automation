import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { PINNED_Z_BASE, UNPINNED_Z_CEILING, allows, backZ, bringForward, leaveBack, unpinToBack, layerOf, pinnedZ, pressed, sendBack, togglePinned } from "./windowPins";

describe("window pins and layers", () => {
  it("a pinned window is always on the pinned layer", () => {
    expect(layerOf(true, true)).toBe("pinned");
    expect(layerOf(false, false)).toBe("front");
    expect(layerOf(false, true)).toBe("behind");
  });
  it("a page click sends the unpinned windows back and leaves the pinned one", () => {
    const behind = sendBack(new Set(), new Set(["a", "b", "c"]), new Set(["b"]));
    expect([...behind].sort()).toEqual(["a", "c"]);
  });
  it("pressing a window brings only it forward", () => {
    const behind = bringForward(new Set(["a", "c"]), "a");
    expect([...behind]).toEqual(["c"]);
  });
  it("toggles a pin on and off", () => {
    const on = togglePinned(new Set(), "a");
    expect(on.has("a")).toBe(true);
    expect(togglePinned(on, "a").has("a")).toBe(false);
  });
});

describe("the pinned z-band", () => {
  const z = (order: string[], pins: string[], id: string) => pinnedZ(order, new Set(pins), id);
  it("an unpinned window has no pinned z, and a pinned one is in the band above 4000", () => {
    expect(z(["a"], [], "a")).toBeNull();
    expect(z(["a"], ["a"], "a")).toBe(PINNED_Z_BASE);
  });
  it("the most recently pressed of two pinned windows is in front, and nothing moves on its own", () => {
    const order = ["a", "b"];
    expect(z(order, ["a", "b"], "b")).toBeGreaterThan(z(order, ["a", "b"], "a")!);

    const after = pressed(order, "a");
    expect(z(after, ["a", "b"], "a")).toBeGreaterThan(z(after, ["a", "b"], "b")!);

    expect(pressed(after, "a")).toEqual(after);
  });
  it("unpinning the front window drops it out of the band; the other keeps its place", () => {
    const order = ["a", "b"];
    expect(z(order, ["a"], "b")).toBeNull();
    expect(z(order, ["a"], "a")).toBe(PINNED_Z_BASE);
  });
  it("a pinned window is always above every unpinned one", () => {
    expect(z(["a", "b", "c"], ["a"], "a")!).toBeGreaterThan(1000);
  });
});

describe("a pinned window is locked", () => {
  it("ignores move, resize, snap, dock and pull-off requests until it is unpinned", () => {
    for (const request of ["move", "resize", "snap", "dock", "pull-off"] as const) {
      expect(allows(true, request)).toBe(false);
      expect(allows(false, request)).toBe(true);
    }
  });
});

describe("unpinning sends a window to the back of the unpinned ones", () => {
  it("the window unpinned last is the lowest, and the others keep their relative order", () => {
    let back: string[] = [];
    back = unpinToBack(back, "a");
    back = unpinToBack(back, "b");
    expect(backZ(back, "b")!).toBeLessThan(backZ(back, "a")!);
    expect(backZ(back, "c")).toBeNull();
    const before = backZ(back, "a")!;
    back = unpinToBack(back, "c");
    expect(backZ(back, "c")!).toBeLessThan(backZ(back, "b")!);
    expect(backZ(back, "b")!).toBeLessThan(backZ(back, "a")!);
    expect(backZ(back, "a")!).toBeGreaterThan(before - 1);
  });
  it("unpinning the front window of a pinned pair puts it last; the other pinned one is untouched", () => {
    const order = pressed(pressed([], "a"), "b");
    const front = pinnedZ(order, new Set(["a", "b"]), "b")!;
    expect(front).toBeGreaterThan(pinnedZ(order, new Set(["a", "b"]), "a")!);

    const back = unpinToBack([], "b");
    expect(pinnedZ(order, new Set(["a"]), "b")).toBeNull();
    expect(backZ(back, "b")).toBe(1);
    expect(pinnedZ(order, new Set(["a"]), "a")).toBe(PINNED_Z_BASE);
  });
  it("a back z is below every normal window (cards 40 and up, demo windows 900 and up) and below the pinned band", () => {
    const z = backZ(unpinToBack([], "x"), "x")!;
    expect(z).toBeLessThan(40);
    expect(z).toBeLessThan(PINNED_Z_BASE);
  });
  it("pressing or pinning a window takes it out of the back list", () => {
    expect(leaveBack(["a", "b"], "a")).toEqual(["b"]);
    expect(backZ(leaveBack(["a", "b"], "a"), "a")).toBeNull();
  });
});

describe("pressing Pin brings the window in front of every other window", () => {
  it("a window pinned after another pinned one is in front of it, and a pin pressed again later is in front of that", () => {
    const pins = new Set(["a", "b", "c"]);
    let order = pressed([], "a");
    order = pressed(order, "b");
    order = pressed(order, "c");
    expect(pinnedZ(order, pins, "c")!).toBeGreaterThan(pinnedZ(order, pins, "b")!);
    order = pressed(order, "a");
    expect(pinnedZ(order, pins, "a")!).toBeGreaterThan(pinnedZ(order, pins, "c")!);
  });
  it("pins restored from the visit's storage (never pressed) sit under a window pinned now", () => {
    const pins = new Set(["old1", "old2", "fresh"]);
    const order = pressed([], "fresh");
    const fresh = pinnedZ(order, pins, "fresh")!;
    expect(fresh).toBeGreaterThan(pinnedZ(order, pins, "old1")!);
    expect(fresh).toBeGreaterThan(pinnedZ(order, pins, "old2")!);
  });
  it("every pinned z-index is above every unpinned window's z-index", () => {
    expect(PINNED_Z_BASE).toBeGreaterThan(UNPINNED_Z_CEILING);
    expect(pinnedZ(["x"], new Set(["x"]), "x")!).toBeGreaterThan(UNPINNED_Z_CEILING);
  });
  it("no stylesheet gives a floating window (card, rail, drawer) a z-index inside the pinned band", () => {

    for (const file of ["whatsnew.css", "reviewmail.css"]) {
      const css = readFileSync(new URL(`../app/${file}`, import.meta.url), "utf8");
      const rule = /\.(whats-new-panel|classifier-prompt)\s*\{[^}]*?z-index:\s*(\d+)/.exec(css);
      expect(rule, file).not.toBeNull();
      expect(Number(rule![2])).toBeLessThanOrEqual(UNPINNED_Z_CEILING);
    }
    const cal = readFileSync(new URL("../app/calendar.css", import.meta.url), "utf8");
    for (const m of cal.matchAll(/\.(hearing-drawer|hearings-panel\.fw)\s*\{[^}]*?z-index:\s*(\d+)/g)) {
      expect(Number(m[2])).toBeLessThanOrEqual(UNPINNED_Z_CEILING);
    }
  });
});
