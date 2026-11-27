import { describe, expect, it } from "vitest";
import { DOCKING_BY_DRAG_WINDOWS, SNAPPING_WINDOWS, isFullZone, restoreFromSnap, snapBox, snapZone, windowDocksByDrag, windowKind, windowSnaps, resolveSnapBox, sizedSnapBox, snapFillsPage } from "./windowSnap";

const vp = { w: 1400, h: 900, top: 56 };

describe("snapZone", () => {
  it("is null in the middle of the page", () => {
    expect(snapZone(700, 450, vp)).toBeNull();
    expect(snapZone(100, 450, vp)).toBeNull();
  });
  it("snaps the left and right edges to halves and the top edge to the whole page", () => {
    expect(snapZone(0, 450, vp)).toBe("left");
    expect(snapZone(1399, 450, vp)).toBe("right");
    expect(snapZone(700, 0, vp)).toBe("top");
  });
  it("snaps corners to quarters", () => {
    expect(snapZone(0, 0, vp)).toBe("topleft");
    expect(snapZone(1399, 5, vp)).toBe("topright");
    expect(snapZone(2, 899, vp)).toBe("bottomleft");
    expect(snapZone(1399, 880, vp)).toBe("bottomright");
    expect(snapZone(4, 40, vp)).toBe("topleft");
  });
  it("does not snap to a half on a screen too narrow for two windows, but still fills for the top", () => {
    const phone = { w: 390, h: 800, top: 56 };
    expect(snapZone(0, 400, phone)).toBeNull();
    expect(snapZone(200, 0, phone)).toBe("top");
  });
});

describe("snapBox", () => {
  it("gives halves their side, full height below the header", () => {
    expect(snapBox("left", vp)).toEqual({ x: 0, y: 56, w: 700, h: 804 });
    expect(snapBox("right", vp)).toEqual({ x: 700, y: 56, w: 700, h: 804 });
  });
  it("gives the top zone the whole page area and corners a quarter", () => {
    expect(snapBox("top", vp)).toEqual({ x: 0, y: 56, w: 1400, h: 804 });
    expect(isFullZone("top")).toBe(true);
    expect(isFullZone("left")).toBe(false);
    const q = snapBox("bottomright", vp);
    expect(q).toEqual({ x: 700, y: 56 + 804 - 402, w: 700, h: 402 });
    expect(snapBox("topleft", vp)).toEqual({ x: 0, y: 56, w: 700, h: 402 });
  });
  it("never reaches under the header or past the bottom gap", () => {
    for (const z of ["left", "right", "top", "topleft", "topright", "bottomleft", "bottomright"] as const) {
      const b = snapBox(z, vp);
      expect(b.y).toBeGreaterThanOrEqual(56);
      expect(b.y + b.h).toBeLessThanOrEqual(900 - 40);
    }
  });
});

describe("restoreFromSnap", () => {
  it("brings back the earlier size, held at the same fraction across", () => {
    const b = restoreFromSnap({ w: 400, h: 300 }, { x: 350, y: 80 }, 0.5, 12, vp);
    expect(b).toEqual({ x: 150, y: 68, w: 400, h: 300 });
  });
  it("keeps the title bar on the page", () => {
    const b = restoreFromSnap({ w: 400, h: 300 }, { x: 0, y: 0 }, 0.5, 12, vp);
    expect(b.y).toBe(56);
    expect(b.x).toBeGreaterThanOrEqual(80 - 400);
  });
});

describe("which windows snap, and which dock by drag", () => {
  it("names each window's kind from its id", () => {
    expect(windowKind("inbox")).toBe("demo");
    expect(windowKind("caseflow")).toBe("demo");
    expect(windowKind("hearing-edit-42")).toBe("hearing-drawer");
    expect(windowKind("hearing-new")).toBe("hearing-drawer");
    expect(windowKind("hearings-rail")).toBe("hearings-panel");
    expect(windowKind("whats-new")).toBe("whats-new");
    expect(windowKind("classifier-prompt")).toBe("classifier");
    expect(windowKind("caseflow-blocked")).toBe("blocked");
  });
  it("the demo windows snap only, the two cards dock only, the panel and the hearing drawers do both", () => {
    expect(SNAPPING_WINDOWS).toEqual({ demo: true, "hearing-drawer": true, "hearings-panel": true, "whats-new": false, classifier: false, blocked: false });
    expect(DOCKING_BY_DRAG_WINDOWS).toEqual({ demo: false, "hearing-drawer": true, "hearings-panel": true, "whats-new": true, classifier: true, blocked: true });
    expect(windowSnaps("email")).toBe(true);
    expect(windowDocksByDrag("email")).toBe(false);
    for (const id of ["hearing-edit-1", "hearing-new", "hearings-rail"]) {
      expect(windowSnaps(id)).toBe(true);
      expect(windowDocksByDrag(id)).toBe(true);
    }
    for (const id of ["whats-new", "classifier-prompt"]) {
      expect(windowSnaps(id)).toBe(false);
      expect(windowDocksByDrag(id)).toBe(true);
    }
  });
  it("every kind does at least one of the two, so none is left without an edge gesture", () => {
    for (const kind of Object.keys(SNAPPING_WINDOWS) as (keyof typeof SNAPPING_WINDOWS)[]) expect(SNAPPING_WINDOWS[kind] || DOCKING_BY_DRAG_WINDOWS[kind]).toBe(true);
  });
});

describe("snapping at the window's own size", () => {
  const size = { w: 360, h: 500 };
  it("goes flush to the side it snaps to, at the drop height, kept on screen", () => {
    expect(sizedSnapBox("left", vp, size, 300)).toEqual({ x: 0, y: 284, w: 360, h: 500 });
    expect(sizedSnapBox("right", vp, size, 300)).toEqual({ x: 1400 - 360, y: 284, w: 360, h: 500 });
    expect(sizedSnapBox("left", vp, size, 5).y).toBe(56);
    expect(sizedSnapBox("left", vp, size, 890).y).toBe(360);
  });
  it("goes flush to a corner, and centred flush to the top edge, without filling", () => {
    expect(sizedSnapBox("topleft", vp, size, 500)).toEqual({ x: 0, y: 56, w: 360, h: 500 });
    expect(sizedSnapBox("topright", vp, size, 500)).toEqual({ x: 1040, y: 56, w: 360, h: 500 });
    expect(sizedSnapBox("bottomleft", vp, size, 100)).toEqual({ x: 0, y: 360, w: 360, h: 500 });
    expect(sizedSnapBox("bottomright", vp, size, 100)).toEqual({ x: 1040, y: 360, w: 360, h: 500 });
    expect(sizedSnapBox("top", vp, size, 100)).toEqual({ x: 520, y: 56, w: 360, h: 500 });
  });
  it("is never bigger than the screen allows", () => {
    const box = sizedSnapBox("left", { w: 300, h: 500, top: 56 }, { w: 900, h: 900 }, 200);
    expect(box.w).toBe(300);
    expect(box.h).toBe(404);
  });
  it("only the demo windows fill the page; the panel and the hearing drawers keep their size", () => {
    expect(snapFillsPage("inbox")).toBe(true);
    for (const id of ["hearings-rail", "hearing-edit-3", "hearing-new"]) expect(snapFillsPage(id)).toBe(false);
    expect(resolveSnapBox("inbox", "left", vp, size, 300)).toEqual({ x: 0, y: 56, w: 700, h: 804 });
    expect(resolveSnapBox("hearings-rail", "left", vp, size, 300)).toEqual({ x: 0, y: 284, w: 360, h: 500 });
    expect(resolveSnapBox("hearing-edit-3", "top", vp, size, 300)).toEqual({ x: 520, y: 56, w: 360, h: 500 });
  });
});
