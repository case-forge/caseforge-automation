import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(new URL("../app/boxes.css", import.meta.url), "utf8");
const LAYOUT = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const GLOBALS = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

describe("paper look: lift, no outline", () => {
  it("draws no outline on a box: no edge token, no ring", () => {
    expect(CSS).not.toContain("--box-edge");
    expect(CSS).not.toContain("0 0 0 1px");
  });

  it("has a two-layer lift, resting, hover and floating, in both themes", () => {
    for (const token of ["--box-lift", "--box-lift-hover", "--box-lift-pop"]) {
      expect(CSS.match(new RegExp(`${token}: [^;]+, [^;]+;`, "g"))).toHaveLength(3);
    }
  });

  it("puts the lift on the top-level containers", () => {
    for (const cls of [".result-card", ".detail-card", ".today-section", ".board-col", ".attention-panel", ".app-drawer-menu", ".switcher"]) {
      expect(CSS).toContain(`${cls},`);
    }
    expect(CSS).toContain("box-shadow: var(--box-lift);");
    expect(CSS).toContain("box-shadow: var(--box-lift-pop);");
  });

  it("leaves nested elements flat: no cards inside a column, tiles inside the pane, or buttons", () => {
    for (const cls of [".assign-card", ".detail-field", ".todo-row", ".cf-btn", ".edit-input"]) {
      expect(CSS).not.toContain(cls);
    }
  });

  it("is imported last so its single-class rules win, and the drawer keeps no dark override of its own", () => {
    expect(LAYOUT.trimEnd().split("\n").filter((l) => l.startsWith("import \"./")).pop()).toBe('import "./boxes.css";');
    expect(GLOBALS).not.toContain("rgba(255, 255, 255, 0.08)");
  });
});
