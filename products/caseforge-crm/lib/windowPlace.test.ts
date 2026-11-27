import { describe, expect, it } from "vitest";
import { boxAtPointer, windowPlace } from "./windowPlace";
import { clampBox } from "./windowFit";

describe("window placed where a tab was dropped", () => {
  it("is taken once", () => {
    windowPlace.request("w", { x: 400, y: 300 });
    expect(windowPlace.take("w")).toEqual({ x: 400, y: 300 });
    expect(windowPlace.take("w")).toBeNull();
  });
  it("holds its title bar under the pointer, centred across", () => {
    expect(boxAtPointer({ x: 500, y: 200 }, 400, 300)).toEqual({ x: 300, y: 184, w: 400, h: 300 });
  });
  it("is fitted onto the screen when dropped near an edge", () => {
    const vp = { w: 1300, h: 900, top: 63 };
    const fit = clampBox(boxAtPointer({ x: 90, y: 10 }, 480, 300), vp);
    expect(fit.x).toBe(0);
    expect(fit.y).toBe(63);
  });
});
