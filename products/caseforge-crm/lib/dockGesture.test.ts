import { describe, expect, it } from "vitest";
import { CUE_MS, DOCK_EDGE_PX, PULL_OFF_PX, cueMotion, dockingClass, dockSide, dropAction, ghostStart, pullState } from "./dockGesture";

const W = 1300;

describe("dockSide", () => {
  it("docks only within the edge zone", () => {
    expect(dockSide(0, W)).toBe("left");
    expect(dockSide(DOCK_EDGE_PX, W)).toBe("left");
    expect(dockSide(DOCK_EDGE_PX + 1, W)).toBeNull();
    expect(dockSide(W - 1, W)).toBe("right");
    expect(dockSide(W - 1 - DOCK_EDGE_PX, W)).toBe("right");
    expect(dockSide(650, W)).toBeNull();
  });
});

describe("pullState", () => {
  it("is not pulling inside the threshold, from either edge", () => {
    expect(pullState(PULL_OFF_PX - 1, W).pulling).toBe(false);
    expect(pullState(W - 1 - (PULL_OFF_PX - 1), W).pulling).toBe(false);
  });
  it("is pulling at and past the threshold, from either edge", () => {
    expect(pullState(PULL_OFF_PX, W).pulling).toBe(true);
    expect(pullState(650, W).pulling).toBe(true);
    expect(pullState(W - 1 - PULL_OFF_PX, W).pulling).toBe(true);
  });
  it("builds progress from 0 at the edge to 1 at the threshold and holds there", () => {
    expect(pullState(0, W).progress).toBe(0);
    expect(pullState(PULL_OFF_PX / 2, W).progress).toBeCloseTo(0.5, 5);
    expect(pullState(PULL_OFF_PX * 4, W).progress).toBe(1);
  });
  it("reverses: moving back inside the threshold is no longer pulling", () => {
    expect(pullState(PULL_OFF_PX + 40, W).pulling).toBe(true);
    expect(pullState(PULL_OFF_PX - 40, W).pulling).toBe(false);
  });
});

describe("dropAction", () => {
  it("a short drag near the edge re-slots the tab; a long one pulls the window off", () => {
    expect(dropAction(20, W)).toBe("re-slot");
    expect(dropAction(PULL_OFF_PX - 1, W)).toBe("re-slot");
    expect(dropAction(PULL_OFF_PX, W)).toBe("pull-off");
    expect(dropAction(700, W)).toBe("pull-off");
  });
});

describe("cue geometry and motion", () => {
  it("the ghost starts at the tab's size relative to the window's", () => {
    expect(ghostStart({ w: 28, h: 100 }, { w: 400, h: 300 })).toEqual({ sx: 0.07, sy: 100 / 300 });
  });
  it("has no motion with reduced motion, and a transition of at most 200ms otherwise", () => {
    expect(cueMotion(true)).toEqual({ ms: 0, moves: false });
    expect(cueMotion(false).moves).toBe(true);
    expect(CUE_MS).toBeLessThanOrEqual(200);
    expect(cueMotion(false).ms).toBeLessThanOrEqual(200);
  });
});

describe("a window is opaque unless a drag is announcing a dock", () => {
  it("the docking class needs the cue, a drag in progress, and the window on screen", () => {
    expect(dockingClass(true, true, false)).toBe(" fw-docking");

    expect(dockingClass(true, false, false)).toBe("");
    expect(dockingClass(false, true, false)).toBe("");

    expect(dockingClass(true, true, true)).toBe("");
  });
});
