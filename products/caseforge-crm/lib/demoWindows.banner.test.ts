import { afterEach, describe, expect, it, vi } from "vitest";
import { headerBottom } from "./demoWindows";

function page(bottoms: Record<string, number>) {
  const box = (bottom: number) => ({ getBoundingClientRect: () => ({ bottom }) });
  vi.stubGlobal("document", {
    querySelector: (selector: string) => (selector in bottoms ? box(bottoms[selector]) : null),
    querySelectorAll: (selector: string) =>
      selector
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s in bottoms)
        .map((s) => box(bottoms[s])),
  });
}

describe("headerBottom: a window opens below the header and any banner already showing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is the header's bottom when no banner shows", () => {
    page({ ".app-header": 56 });
    expect(headerBottom()).toBe(56);
  });

  it("is the new-version banner's bottom when that banner sits under the header", () => {
    page({ ".app-header": 56, ".update-banner": 98 });
    expect(headerBottom()).toBe(98);
  });

  it("counts the red session banner and the unsaved-forms notice too", () => {
    page({ ".app-header": 56, ".session-stale-wrap": 100, ".refresh-unsaved": 180 });
    expect(headerBottom()).toBe(180);
  });

  it("ignores a banner that has scrolled above the header's bottom edge", () => {
    page({ ".app-header": 56, ".update-banner": 20 });
    expect(headerBottom()).toBe(56);
  });
});
