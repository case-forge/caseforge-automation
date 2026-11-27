import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const GLOBALS = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const BUTTONS = readFileSync(new URL("../app/buttons.css", import.meta.url), "utf8");

describe("one control height", () => {
  it("defines the standard and the dense height once, as tokens", () => {
    expect(GLOBALS.match(/--control-h: [0-9.]+rem;/g)?.length).toBe(1);
    expect(GLOBALS.match(/--control-h-sm: [0-9.]+rem;/g)?.length).toBe(1);
  });

  it("applies them to buttons and single-line boxes instead of per-control padding", () => {
    expect(BUTTONS).toContain("min-height: var(--control-h);");
    expect(BUTTONS).toContain(".cf-btn--small { min-height: var(--control-h-sm);");
    expect(GLOBALS).toContain(".edit-input:not(textarea) { height: var(--control-h);");
  });
});
