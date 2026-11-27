import { describe, expect, it } from "vitest";
import { slotCentres } from "./demoDock";
import { GUIDE_BAND_PX, SIDE_EDGE_PX, SLOT_HALF_PX, gapZones, gestureGuides, gestureTarget, slotAt } from "./windowGesture";
import { windowGestures } from "./windowSnap";

const vp = { w: 1400, h: 900, top: 56 };
const both = { snaps: true, docks: true };
const snapOnly = { snaps: true, docks: false };
const dockOnly = { snaps: false, docks: true };
const c = slotCentres(vp);

const gap0 = (c.top + c.middle) / 2;
const gap1 = (c.middle + c.bottom) / 2;

describe("a kind that both snaps and docks: the slots are at the edge, the gaps between them snap", () => {
  it("docks over each of the three slots, on either side", () => {
    expect(gestureTarget(0, c.top, vp, both)).toEqual({ type: "dock", side: "left", slot: "top" });
    expect(gestureTarget(2, c.middle, vp, both)).toEqual({ type: "dock", side: "left", slot: "middle" });
    expect(gestureTarget(SIDE_EDGE_PX, c.bottom, vp, both)).toEqual({ type: "dock", side: "left", slot: "bottom" });
    expect(gestureTarget(vp.w - 1, c.middle, vp, both)).toEqual({ type: "dock", side: "right", slot: "middle" });
    expect(gestureTarget(vp.w - 3, c.top + SLOT_HALF_PX, vp, both)).toEqual({ type: "dock", side: "right", slot: "top" });
  });
  it("snaps to that side's half over a gap, saying which gap", () => {
    expect(gestureTarget(0, gap0, vp, both)).toEqual({ type: "snap", zone: "left", gap: 0 });
    expect(gestureTarget(0, gap1, vp, both)).toEqual({ type: "snap", zone: "left", gap: 1 });
    expect(gestureTarget(vp.w - 1, gap0, vp, both)).toEqual({ type: "snap", zone: "right", gap: 0 });
    expect(gestureTarget(vp.w - 1, c.top + SLOT_HALF_PX + 1, vp, both)).toEqual({ type: "snap", zone: "right", gap: 0 });
  });
  it("snaps to a quarter in a corner and fills the page at the top edge", () => {
    expect(gestureTarget(1, 2, vp, both)).toEqual({ type: "snap", zone: "topleft" });
    expect(gestureTarget(vp.w - 2, 30, vp, both)).toEqual({ type: "snap", zone: "topright" });
    expect(gestureTarget(2, vp.h - 2, vp, both)).toEqual({ type: "snap", zone: "bottomleft" });
    expect(gestureTarget(vp.w - 2, vp.h - 20, vp, both)).toEqual({ type: "snap", zone: "bottomright" });
    expect(gestureTarget(700, 0, vp, both)).toEqual({ type: "snap", zone: "top" });
  });
  it("does nothing away from the edge", () => {
    expect(gestureTarget(SIDE_EDGE_PX + 1, c.middle, vp, both)).toEqual({ type: "none" });
    expect(gestureTarget(700, 450, vp, both)).toEqual({ type: "none" });
  });
  it("is derived from the pointer alone: a sweep along the edge flips dock, snap, dock with nothing left over", () => {
    const along = [c.top, gap0, c.middle, gap1, c.bottom].map((y) => gestureTarget(0, y, vp, both).type);
    expect(along).toEqual(["dock", "snap", "dock", "snap", "dock"]);
    const inwards = [0, 30, 60, 200].map((x) => gestureTarget(x, c.middle, vp, both).type);
    expect(inwards).toEqual(["dock", "none", "none", "none"]);
  });
});

describe("the soft guides", () => {
  it("show six slots and two gaps per side within 72px of a side edge, for kinds that do both", () => {
    expect(gestureGuides(0, vp, both)).toEqual({ side: "left", gaps: true });
    expect(gestureGuides(GUIDE_BAND_PX, vp, both)).toEqual({ side: "left", gaps: true });
    expect(gestureGuides(vp.w - 1 - 40, vp, both)).toEqual({ side: "right", gaps: true });
    expect(gestureGuides(GUIDE_BAND_PX + 1, vp, both)).toBeNull();
    expect(gestureGuides(700, vp, both)).toBeNull();
  });
  it("dock-only kinds show the slots only at the edge, with no gap zones; snap-only kinds show none", () => {
    expect(gestureGuides(10, vp, dockOnly)).toEqual({ side: "left", gaps: false });
    expect(gestureGuides(40, vp, dockOnly)).toBeNull();
    expect(gestureGuides(0, vp, snapOnly)).toBeNull();
  });
  it("the two gap zones sit between the three slots, not over them", () => {
    const [a, b] = gapZones(vp);
    expect(a.y).toBe(c.top + SLOT_HALF_PX);
    expect(a.y + a.h).toBe(c.middle - SLOT_HALF_PX);
    expect(b.y).toBe(c.middle + SLOT_HALF_PX);
    expect(b.y + b.h).toBe(c.bottom - SLOT_HALF_PX);
    expect(slotAt(a.y + a.h / 2, vp)).toBeNull();
    expect(slotAt(c.middle, vp)).toBe("middle");
  });
});

describe("snap-only and dock-only kinds", () => {
  it("snap-only snaps within 12px of an edge, anywhere along it, and never docks", () => {
    expect(gestureTarget(0, c.middle, vp, snapOnly)).toEqual({ type: "snap", zone: "left" });
    expect(gestureTarget(0, gap0, vp, snapOnly)).toEqual({ type: "snap", zone: "left" });
    expect(gestureTarget(12, c.middle, vp, snapOnly)).toEqual({ type: "snap", zone: "left" });
    expect(gestureTarget(40, c.middle, vp, snapOnly)).toEqual({ type: "none" });
  });
  it("dock-only docks within 24px of a side edge, anywhere along it (no gaps), and never snaps", () => {
    expect(gestureTarget(0, gap0, vp, dockOnly)).toEqual({ type: "dock", side: "left", slot: "top" });
    expect(gestureTarget(24, c.middle, vp, dockOnly)).toEqual({ type: "dock", side: "left", slot: "middle" });
    expect(gestureTarget(25, c.middle, vp, dockOnly)).toEqual({ type: "none" });
    expect(gestureTarget(700, 0, vp, dockOnly)).toEqual({ type: "none" });
  });
  it("a kind that does neither gets nothing", () => {
    expect(gestureTarget(0, 450, vp, { snaps: false, docks: false })).toEqual({ type: "none" });
  });
});

describe("the gestures each window kind gets", () => {
  it("the panel and the hearing drawers do both; the cards dock only; the demo windows snap only", () => {
    for (const id of ["hearings-rail", "hearing-edit-7", "hearing-new"]) expect(windowGestures(id)).toEqual({ snaps: true, docks: true });
    for (const id of ["whats-new", "classifier-prompt"]) expect(windowGestures(id)).toEqual({ snaps: false, docks: true });
    for (const id of ["demo", "inbox", "email", "explorer", "caseflow"]) expect(windowGestures(id)).toEqual({ snaps: true, docks: false });
  });
});
