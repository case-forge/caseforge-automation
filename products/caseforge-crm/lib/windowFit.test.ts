import { describe, expect, it } from "vitest";
import { clampBox, sameBox } from "./windowFit";

const vp = { w: 1300, h: 900, top: 63 };

describe("clampBox", () => {
  it("leaves a box that is already on screen alone", () => {
    const box = { x: 200, y: 120, w: 480, h: 300 };
    expect(sameBox(clampBox(box, vp), box)).toBe(true);
  });
  it("brings back a box dragged half off the left edge", () => {
    const fit = clampBox({ x: -240, y: 300, w: 480, h: 232 }, vp);
    expect(fit.x).toBe(0);
    expect(fit.w).toBe(480);
  });
  it("brings back a box off the right edge, above the header and below the bottom", () => {
    expect(clampBox({ x: 1200, y: 10, w: 480, h: 300 }, vp)).toEqual({ x: 820, y: 63, w: 480, h: 300 });
    expect(clampBox({ x: 400, y: 880, w: 480, h: 300 }, vp)).toEqual({ x: 400, y: 600, w: 480, h: 300 });
  });
  it("shrinks a box only when the screen is smaller than it", () => {
    const fit = clampBox({ x: 0, y: 63, w: 800, h: 900 }, { w: 390, h: 700, top: 63 });
    expect(fit.w).toBe(390);
    expect(fit.h).toBe(637);
    expect(fit.x).toBe(0);
    expect(fit.y).toBe(63);
  });
  it("is stable: fitting a fitted box changes nothing", () => {
    const once = clampBox({ x: -999, y: 5000, w: 600, h: 400 }, vp);
    expect(sameBox(clampBox(once, vp), once)).toBe(true);
  });
});
