import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

describe("a banner under the header pushes the floating boxes down", () => {
  it("BannerOffset publishes --banner-h from the banners' heights, and is mounted once with the boxes", () => {
    const offset = read("components/BannerOffset.tsx");
    expect(offset).toContain('setProperty("--banner-h"');
    expect(offset).toContain("BANNER_SELECTOR");
    expect(read("components/WidgetLayer.tsx")).toContain("<BannerOffset />");
  });

  it("every box's resting top and height allow for --banner-h", () => {
    const widgets = read("app/widgets.css");
    for (const rule of [".widget-box.fw", ".add-hearing-box.fw"]) {
      const line = widgets.split("\n").find((l) => l.startsWith(rule));
      expect(line, rule).toContain("var(--banner-h, 0px)");
    }
    expect(read("app/calendar.css").split("\n").find((l) => l.startsWith(".hearings-panel.fw"))).toContain("var(--banner-h, 0px)");
  });
});
