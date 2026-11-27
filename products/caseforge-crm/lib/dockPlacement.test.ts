import { describe, expect, it } from "vitest";
import { TAB_GAP, tabHeight } from "./demoDock";
import type { DockTab } from "./demoDock";
import { MIN_TAB_H, placeTabs } from "./dockPlacement";

const vp = { w: 1400, h: 900, top: 56 };
const tab = (id: string, slot: DockTab["slot"], seq: number, title = "Inbox", side: DockTab["side"] = "left"): DockTab => ({ id, side, slot, seq, h: tabHeight(title) });
const centre = (p: { y: number; h: number }) => p.y + p.h / 2;

function clear(ids: string[], placed: Record<string, { y: number; h: number }>) {
  const sorted = ids.map((id) => placed[id]).sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i++) expect(sorted[i].y).toBeGreaterThanOrEqual(sorted[i - 1].y + sorted[i - 1].h + TAB_GAP);
}

describe("placeTabs", () => {
  it("gives the tabs of a group one length", () => {
    const p = placeTabs([tab("a", "top", 1, "Inbox"), tab("b", "top", 2, "Case flow")], vp);
    expect(p.a.h).toBe(p.b.h);
  });
  it("keeps the middle group centred as it grows, two tabs and three", () => {
    const mid = (vp.h - 56 + vp.top + 8) / 2;
    const two = placeTabs([tab("a", "middle", 1), tab("b", "middle", 2)], vp);
    expect((centre(two.a) + centre(two.b)) / 2).toBeCloseTo(mid, 0);
    clear(["a", "b"], two);
    const three = placeTabs([tab("a", "middle", 1), tab("b", "middle", 2), tab("c", "middle", 3)], vp);
    expect(Math.abs(centre(three.b) - mid)).toBeLessThanOrEqual(1);
    clear(["a", "b", "c"], three);
  });
  it("grows the top group downwards and the bottom group upwards", () => {
    const top = placeTabs([tab("a", "top", 1), tab("b", "top", 2)], vp);
    expect(top.a.y).toBe(64);
    expect(top.b.y).toBeGreaterThan(top.a.y);
    const bottom = placeTabs([tab("a", "bottom", 1), tab("b", "bottom", 2)], vp);
    expect(bottom.b.y + bottom.b.h).toBe(900 - 56);
    expect(bottom.a.y).toBeLessThan(bottom.b.y);
  });
  it("shrinks tabs rather than overlapping another slot's group", () => {
    const tabs = ["a", "b", "c", "d"].map((id, i) => tab(id, "top", i, "Case flow")).concat(["e", "f", "g"].map((id, i) => tab(id, "middle", i + 9, "Case flow")));
    const p = placeTabs(tabs, vp);
    expect(p.a.h).toBeLessThan(tabHeight("Case flow"));
    clear(["a", "b", "c", "d", "e", "f", "g"], p);
  });
  it("shrinks a group to fit above the hearings tab", () => {
    const blocked = { left: [{ y: 300, h: 60 }], right: [] };
    const p = placeTabs([tab("a", "top", 1), tab("b", "top", 2)], vp, blocked);
    expect(p.b.y + p.b.h + TAB_GAP).toBeLessThanOrEqual(300);
    expect(p.a.h).toBeGreaterThanOrEqual(MIN_TAB_H);
  });
  it("pushes tabs clear of the hearings tab when even the shortest do not fit", () => {
    const blocked = { left: [{ y: 70, h: 200 }], right: [] };
    const p = placeTabs([tab("a", "top", 1), tab("b", "top", 2)], vp, blocked);
    for (const id of ["a", "b"]) expect(p[id].y >= 270 + TAB_GAP || p[id].y + p[id].h + TAB_GAP <= 70).toBe(true);
    clear(["a", "b"], p);
  });
  it("places the two sides independently", () => {
    const p = placeTabs([tab("a", "middle", 1, "Inbox", "left"), tab("b", "middle", 2, "Inbox", "right")], vp);
    expect(p.a.y).toBe(p.b.y);
  });
});
