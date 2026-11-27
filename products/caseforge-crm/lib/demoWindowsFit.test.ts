import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { fitWindows, initialWindows, openAll } from "@/lib/demoWindows";

describe("fitWindows: every window is wholly on screen and below the header when shown", () => {
  it("brings boxes made for a taller screen back inside a shorter one, at every height", () => {
    const made = initialWindows({ w: 1500, h: 1100, top: 63 });
    for (let h = 560; h <= 1100; h += 20) {
      for (const w of [1000, 1500, 2000]) {
        const vp = { w, h, top: 63 };
        for (const win of fitWindows(openAll(made), vp)) {
          expect(win.y, `${win.id} at ${w}x${h}`).toBeGreaterThanOrEqual(63);
          expect(win.y + 40, `${win.id} title bar at ${w}x${h}`).toBeLessThanOrEqual(h);
          expect(win.x, `${win.id} at ${w}x${h}`).toBeGreaterThanOrEqual(0);
          expect(win.x + win.w, `${win.id} at ${w}x${h}`).toBeLessThanOrEqual(w);
        }
      }
    }
  });
  it("leaves a window that already fits as the very same object", () => {
    const list = initialWindows({ w: 1500, h: 900, top: 63 });
    expect(fitWindows(list, { w: 1500, h: 900, top: 63 })[0]).toBe(list[0]);
  });
});

describe("the demo windows are drawn on the body, not inside the footer", () => {
  it("DemoWindows portals to document.body, so a transformed footer cannot become their containing block", () => {
    const src = readFileSync("components/DemoWindows.tsx", "utf8");
    expect(src).toContain("document.body,");
    expect(src).toMatch(/return createPortal\(\s*<>/);
  });
});
