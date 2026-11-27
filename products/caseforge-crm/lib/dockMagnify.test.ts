import { describe, expect, it } from "vitest";
import { MAG_MAX, MAG_RADIUS, freeSpan, magnifyGroup, magnifyScale } from "./dockMagnify";

const tabs = [
  { id: "a", y: 100, h: 80 },
  { id: "b", y: 186, h: 80 },
  { id: "c", y: 272, h: 80 },
];
const wide = { min: 0, max: 900 };

describe("magnifyScale", () => {
  it("is the maximum at the pointer, 1 at the radius and beyond, and falls smoothly between", () => {
    expect(magnifyScale(0)).toBeCloseTo(MAG_MAX, 5);
    expect(magnifyScale(MAG_RADIUS)).toBe(1);
    expect(magnifyScale(MAG_RADIUS * 3)).toBe(1);
    const mid = magnifyScale(MAG_RADIUS / 2);
    expect(mid).toBeGreaterThan(1);
    expect(mid).toBeLessThan(MAG_MAX);
    expect(magnifyScale(-30)).toBe(magnifyScale(30));
  });
  it("never rises as the pointer moves away", () => {
    let last = Infinity;
    for (let d = 0; d <= MAG_RADIUS; d += 10) {
      const s = magnifyScale(d);
      expect(s).toBeLessThanOrEqual(last);
      last = s;
    }
  });
});

describe("magnifyGroup", () => {
  it("grows the hovered tab most and its neighbours less, with no overlap", () => {
    const out = magnifyGroup(tabs, 226, "start", wide);
    expect(out.b.h).toBeGreaterThan(out.a.h);
    expect(out.b.h).toBeGreaterThan(out.c.h);
    expect(out.a.h).toBeGreaterThanOrEqual(80);
    expect(out.b.y).toBeGreaterThanOrEqual(out.a.y + out.a.h + 6);
    expect(out.c.y).toBeGreaterThanOrEqual(out.b.y + out.b.h + 6);
  });
  it("leaves the group as it was when the pointer is far away", () => {
    const out = magnifyGroup(tabs, 800, "start", wide);
    expect(out.a).toEqual({ y: 100, h: 80 });
    expect(out.c).toEqual({ y: 272, h: 80 });
  });
  it("keeps the anchor: top group fixed at its start, bottom at its end, middle at its centre", () => {
    expect(magnifyGroup(tabs, 226, "start", wide).a.y).toBe(100);
    const end = magnifyGroup(tabs, 226, "end", wide);
    expect(end.c.y + end.c.h).toBe(352);
    const mid = magnifyGroup(tabs, 226, "center", wide);
    const first = mid.a;
    const last = mid.c;
    expect(Math.abs((first.y + last.y + last.h) / 2 - 226)).toBeLessThanOrEqual(1);
  });
  it("caps the growth so the group stays inside its room", () => {
    const tight = { min: 100, max: 360 };
    const out = magnifyGroup(tabs, 226, "start", tight);
    expect(out.c.y + out.c.h).toBeLessThanOrEqual(360);
    const none = magnifyGroup(tabs, 226, "start", { min: 100, max: 352 });
    expect(none.a).toEqual({ y: 100, h: 80 });
    expect(none.c).toEqual({ y: 272, h: 80 });
  });
});

describe("freeSpan", () => {
  it("stops at the nearest obstacle above and below, and at the band otherwise", () => {
    const span = freeSpan({ top: 300, bottom: 400 }, [{ y: 100, h: 60 }, { y: 500, h: 60 }, { y: 600, h: 40 }], { min: 64, max: 850 });
    expect(span).toEqual({ min: 166, max: 494 });
    expect(freeSpan({ top: 300, bottom: 400 }, [], { min: 64, max: 850 })).toEqual({ min: 64, max: 850 });
  });
});
