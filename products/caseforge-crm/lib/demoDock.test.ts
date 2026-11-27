import { describe, expect, it } from "vitest";
import { TAB_GAP, flightVector, layoutTabs, moveByKey, nearestSlot, slotTargets, tabHeight } from "./demoDock";
import type { DockTab } from "./demoDock";
import { dockWindow, initialWindows, openAll, toggleAll } from "./demoWindows";

const vp = { w: 1400, h: 900, top: 56 };
const tab = (id: string, side: DockTab["side"], slot: DockTab["slot"], seq: number, title = "Inbox"): DockTab => ({ id, side, slot, seq, h: tabHeight(title) });

function noOverlap(tabs: DockTab[], ys: Record<string, number>) {
  for (const side of ["left", "right"] as const) {
    const col = tabs.filter((t) => t.side === side).sort((a, b) => ys[a.id] - ys[b.id]);
    for (let i = 1; i < col.length; i++) expect(ys[col[i].id]).toBeGreaterThanOrEqual(ys[col[i - 1].id] + col[i - 1].h + TAB_GAP);
  }
}

describe("nearestSlot", () => {
  it("picks the side by half of the page and the slot by closeness", () => {
    expect(nearestSlot(100, 80, vp)).toEqual({ side: "left", slot: "top" });
    expect(nearestSlot(1300, 450, vp)).toEqual({ side: "right", slot: "middle" });
    expect(nearestSlot(900, 880, vp)).toEqual({ side: "right", slot: "bottom" });
  });
  it("has six targets, three a side", () => {
    expect(slotTargets(vp)).toHaveLength(6);
  });
});

describe("moveByKey", () => {
  it("changes side and slot, stopping at the ends", () => {
    expect(moveByKey("left", "top", "ArrowRight")).toEqual({ side: "right", slot: "top" });
    expect(moveByKey("right", "top", "ArrowUp")).toEqual({ side: "right", slot: "top" });
    expect(moveByKey("right", "top", "ArrowDown")).toEqual({ side: "right", slot: "middle" });
    expect(moveByKey("left", "bottom", "ArrowDown")).toEqual({ side: "left", slot: "bottom" });
  });
});

describe("layoutTabs", () => {
  it("stacks tabs sharing a slot in dock order without overlap", () => {
    const tabs = [tab("a", "left", "top", 2), tab("b", "left", "top", 1), tab("c", "left", "top", 3, "Case flow")];
    const ys = layoutTabs(tabs, vp);
    expect(ys.b).toBeLessThan(ys.a);
    expect(ys.a).toBeLessThan(ys.c);
    noOverlap(tabs, ys);
  });
  it("keeps slot order top, middle, bottom and clear of each other", () => {
    const tabs = [tab("a", "right", "bottom", 1), tab("b", "right", "top", 2), tab("c", "right", "middle", 3)];
    const ys = layoutTabs(tabs, vp);
    expect(ys.b).toBeLessThan(ys.c);
    expect(ys.c).toBeLessThan(ys.a);
    noOverlap(tabs, ys);
  });
  it("never lies over a blocked span such as the hearings tab", () => {
    const blocked = { left: [{ y: 60, h: 120 }], right: [] };
    const tabs = [tab("a", "left", "top", 1), tab("b", "left", "top", 2)];
    const ys = layoutTabs(tabs, vp, blocked);
    for (const t of tabs) expect(ys[t.id] >= 60 + 120 || ys[t.id] + t.h <= 60).toBe(true);
    noOverlap(tabs, ys);
  });
  it("pushes a crowded column back up inside the page", () => {
    const tabs = ["a", "b", "c", "d", "e"].map((id, i) => tab(id, "left", "bottom", i, "Case flow"));
    const ys = layoutTabs(tabs, { w: 1400, h: 700, top: 56 });
    for (const t of tabs) expect(ys[t.id] + t.h).toBeLessThanOrEqual(700 - 56);
    noOverlap(tabs, ys);
  });
  it("starts below the header", () => {
    expect(layoutTabs([tab("a", "left", "top", 1)], { w: 1400, h: 900, top: 120 }).a).toBeGreaterThanOrEqual(128);
  });
});

describe("docking in the store", () => {
  it("minimising keeps the last side and slot and queues after earlier tabs", () => {
    let list = openAll(initialWindows(vp));
    list = dockWindow(list, "inbox");
    list = dockWindow(list, "email", { side: "right", slot: "middle" });
    list = dockWindow(list, "inbox");
    const by = (id: string) => list.find((w) => w.id === id)!;
    expect(by("email")).toMatchObject({ minimised: true, side: "right", slot: "middle" });
    expect(by("inbox")).toMatchObject({ minimised: true, side: "left", slot: "top" });
    expect(by("inbox").dockSeq).toBeGreaterThan(by("email").dockSeq);
  });
  it("the DEMO button closes everything while any window shows, and reopens all (tabs too) otherwise", () => {
    let list = openAll(initialWindows(vp));
    list = dockWindow(list, "inbox");
    expect(toggleAll(list).every((w) => !w.open)).toBe(true);
    const allTabs = list.map((w) => dockWindow(list, w.id)).reduce((_, l) => l);
    const everyTab = ["demo", "inbox", "email", "explorer", "caseflow"].reduce((l, id) => dockWindow(l, id), list);
    expect(everyTab.every((w) => w.minimised)).toBe(true);
    expect(allTabs).toBeTruthy();
    expect(toggleAll(everyTab).every((w) => w.open && !w.minimised)).toBe(true);
  });
});

describe("flightVector", () => {
  const centre = { x: 700, y: 400 };
  it("flies left for a left tab and right for a right tab", () => {
    expect(flightVector(centre, "left", "middle", vp).x).toBeLessThan(0);
    expect(flightVector(centre, "right", "middle", vp).x).toBeGreaterThan(0);
  });
  it("flies up to a top slot and down to a bottom slot", () => {
    expect(flightVector(centre, "left", "top", vp).y).toBeLessThan(0);
    expect(flightVector(centre, "right", "bottom", vp).y).toBeGreaterThan(0);
  });
  it("ends on the tab's edge", () => {
    expect(700 + flightVector(centre, "right", "top", vp).x).toBe(1400 - 14);
  });
});
