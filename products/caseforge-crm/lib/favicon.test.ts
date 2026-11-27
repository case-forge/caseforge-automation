import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { faviconColour, faviconHref, isMarkedTab, isPreviewHost, MARKED_COLOURS, recolourMark, svgDataHref } from "./favicon";

describe("favicon colour", () => {
  it("is white on a dark theme and black on a light one", () => {
    expect(faviconColour("dark")).toBe("white");
    expect(faviconColour("light")).toBe("black");
  });

  it("points at the shipped files, with a version so a changed icon is fetched again", () => {
    expect(faviconHref("white")).toBe("/caseforge-favicon-white.svg?v=6");
    expect(faviconHref("black")).toBe("/caseforge-favicon-black.svg?v=6");
  });

  it("marks a tailnet address and the demo, never the live site", () => {
    expect(isMarkedTab("100.64.0.2", false)).toBe(true);
    expect(isMarkedTab("box.tail1234.ts.net", false)).toBe(true);
    expect(isMarkedTab("demo.example.test", true)).toBe(true);
    expect(isMarkedTab("crm.example.test", false)).toBe(false);
  });

  it("recolours the one black mark as it loads: blue on a light theme, yellow on a dark one, no second file", () => {
    const svg = readFileSync(fileURLToPath(new URL("../public/caseforge-favicon-black.svg", import.meta.url)), "utf8");
    expect(svg).toContain('fill="#000000"');
    for (const theme of ["light", "dark"] as const) {
      const out = recolourMark(svg, MARKED_COLOURS[theme]);
      expect(out).toContain(`fill="${MARKED_COLOURS[theme]}"`);
      expect(out).not.toContain('fill="#000000"');
      expect(decodeURIComponent(svgDataHref(out).replace("data:image/svg+xml,", ""))).toBe(out);
    }
    expect(MARKED_COLOURS).toEqual({ light: "#2563eb", dark: "#facc15" });
    expect(existsSync(fileURLToPath(new URL("../public/caseforge-favicon-preview-light.png", import.meta.url)))).toBe(false);
  });
});

describe("isPreviewHost", () => {
  it("is true for Tailscale's 100.64.0.0/10 range, .ts.net names and short machine names", () => {
    expect(isPreviewHost("100.64.0.1")).toBe(true);
    expect(isPreviewHost("100.127.255.254")).toBe(true);
    expect(isPreviewHost("Box.Tail1234.TS.NET")).toBe(true);
    expect(isPreviewHost("dev-laptop")).toBe(true);
  });

  it("is false for the live site, localhost and addresses outside the range", () => {
    expect(isPreviewHost("")).toBe(false);
    expect(isPreviewHost("localhost")).toBe(false);
    expect(isPreviewHost("100.63.0.1")).toBe(false);
    expect(isPreviewHost("100.128.0.1")).toBe(false);
    expect(isPreviewHost("10.0.0.5")).toBe(false);
    expect(isPreviewHost("crm.example.com")).toBe(false);
  });
});
