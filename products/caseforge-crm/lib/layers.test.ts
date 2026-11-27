import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DIALOG_Z, MENU_Z, POPUP_Z_BASE, POPUP_Z_CEILING } from "./layers";
import { MAX_STACK, popupStack, raised, stackZ } from "./popupStack";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("layers", () => {
  it("the popup stack's highest value is below the menu and the dialog layers", () => {
    expect(POPUP_Z_BASE + MAX_STACK - 1).toBe(POPUP_Z_CEILING);
    expect(POPUP_Z_CEILING).toBeLessThan(MENU_Z);
    expect(MENU_Z).toBeLessThan(DIALOG_Z);
  });
  it("many raises never pass the ceiling: the order is compacted", () => {
    let order: string[] = [];
    for (let i = 0; i < MAX_STACK + 500; i++) order = raised(order, `p${i}`);
    expect(order).toHaveLength(MAX_STACK);
    expect(Math.max(...order.map((id) => stackZ(order, id)!))).toBe(POPUP_Z_CEILING);
    popupStack.reset();
    for (let i = 0; i < 50; i++) popupStack.raise(`q${i % 3}`);
    expect(popupStack.zFor("q0")!).toBeLessThanOrEqual(POPUP_Z_CEILING);
  });
  it("the stylesheet repeats the same numbers, and the menu and dialog use them", () => {
    const css = read("../app/teasers.css");
    expect(css).toContain(`--z-popup-ceiling: ${POPUP_Z_CEILING}; --z-menu: ${MENU_Z}; --z-dialog: ${DIALOG_Z};`);
    expect(css).toMatch(/\.teasers-menu \{[^}]*z-index: var\(--z-menu\)|z-index: var\(--z-menu\); min-width: 11rem/);
    expect(read("../app/newclient.css")).toMatch(/\.new-client-backdrop \{[^}]*z-index: var\(--z-dialog/);
  });
});
