import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(new URL("./Glyphs.tsx", import.meta.url), "utf8");
const TODO = readFileSync(new URL("./TodoParts.tsx", import.meta.url), "utf8");
const BILLING = readFileSync(new URL("./DetailPanel.tsx", import.meta.url), "utf8");
const TAB = readFileSync(new URL("./CaseFlowTab.tsx", import.meta.url), "utf8");

describe("drawn marks replace text symbols", () => {
  it("draws the sync level as an icon and bars, four of them, from the numeric level", () => {
    expect(SOURCE).toContain("SYNC_BARS = 4");
    expect(SOURCE).toContain("IconDna");
    expect(TAB).not.toContain("🧬");
  });
  it("maps every pipeline status shape to an icon", () => {
    for (const shape of ["●", "○", "▲", "■", "◇", "◌"]) expect(SOURCE).toContain(`"${shape}"`);
  });
  it("uses a bin, not a cross, for deleting a to-do, and icons for star, sun and pencil", () => {
    expect(TODO).toContain("IconTrash");
    expect(TODO).toContain("IconPencil");
    expect(TODO).toContain("IconStar");
    expect(TODO).toContain("IconSun");
    expect(TODO).toContain("<IconSun filled={");
    for (const glyph of ["★", "☆", "☀", "✎", "✕"]) expect(TODO).not.toContain(glyph);
  });
  it("gives Print and Export CSV in Billing the same neutral button as Print in the To-do list", () => {
    expect(BILLING).toContain('className="cf-btn cf-btn--neutral" onClick={() => window.print()}');
    expect(BILLING).toContain('className="cf-btn cf-btn--neutral"\n          href=');
  });
  it("gives the edit fields, the matter dropdown and the to-do fields a page-tone well with a visible edge", () => {
    const css = readFileSync(new URL("../app/glyphs.css", import.meta.url), "utf8");
    for (const selector of [".edit-input", ".case-select", ".todo-add-input", ".todo-search"]) expect(css).toContain(selector);
    expect(css).toContain("background: var(--bg);");
    expect(css).toContain("--field-edge");
  });
});
