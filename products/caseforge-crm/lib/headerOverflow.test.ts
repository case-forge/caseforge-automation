import { describe, expect, it } from "vitest";
import { COLLAPSE_ORDER, HEADER_ITEMS, PANEL_ITEMS, fitHeaderItems, sameItems } from "./headerOverflow";
import type { HeaderWidths } from "./headerOverflow";

const ALL: HeaderWidths = Object.fromEntries(HEADER_ITEMS.map((id) => [id, 40]));
const fit = (available: number, widths: HeaderWidths = ALL) => fitHeaderItems({ available, reserved: 40, gap: 8, widths });

describe("fitHeaderItems", () => {
  it("keeps every button in the header while there is room", () => {
    expect(fit(2000)).toEqual([]);
    expect(fit(424)).toEqual([]);
  });

  it("moves one item out the moment the row is a pixel short", () => {
    expect(fit(423)).toEqual(["starred"]);
  });

  it("moves the quick lists and the view switch first, the notices, then the bell, and the clock last", () => {
    expect(fit(423 - 48)).toEqual(["flagged", "starred"]);
    expect(fit(423 - 96)).toEqual(["view", "flagged", "starred"]);
    expect(fit(423 - 144)).toEqual(["view", "flagged", "starred", "newclient"]);
    expect(fit(423 - 192)).toEqual(["view", "flagged", "starred", "robot", "newclient"]);
    expect(fit(423 - 240)).toEqual(["view", "flagged", "starred", "todo", "robot", "newclient"]);
    expect(fit(423 - 288)).toEqual(["view", "flagged", "starred", "bell", "todo", "robot", "newclient"]);
    expect(fit(88)).toEqual(HEADER_ITEMS.filter((id) => id !== "clock"));
  });

  it("moves everything when not even one button fits beside the menu button", () => {
    expect(fit(87)).toEqual([...HEADER_ITEMS]);
    expect(fit(0)).toEqual([...HEADER_ITEMS]);
  });

  it("returns the moved buttons in header order, whatever order they left in", () => {
    const moved = fit(200);
    expect(moved).toEqual(HEADER_ITEMS.filter((id) => moved.includes(id)));
  });

  it("gives no room to, and never moves, a button with nothing to show", () => {
    const widths: HeaderWidths = { ...ALL, starred: 0, robot: undefined };

    expect(fit(328, widths)).toEqual([]);
    expect(fit(327, widths)).toEqual(["flagged"]);
  });

  it("brings buttons back as the header widens", () => {
    expect(fit(300).length).toBeGreaterThan(fit(400).length);
    expect(fit(424)).toEqual([]);
  });

  it("counts a wider button (one with a count badge) at its real width", () => {
    expect(fit(442, { ...ALL, bell: 60 })).toEqual(["starred"]);
  });
});

describe("the header's item lists", () => {
  it("has every button in the collapse order exactly once", () => {
    expect([...COLLAPSE_ORDER].sort()).toEqual([...HEADER_ITEMS].sort());
  });

  it("includes the flagged and starred lists, and no smiley or frowny: the one bell holds their notifications", () => {
    for (const id of ["bell", "flagged", "starred"]) expect(HEADER_ITEMS).toContain(id);
    for (const id of ["smile", "frown"]) {
      expect(HEADER_ITEMS as readonly string[]).not.toContain(id);
      expect(PANEL_ITEMS as readonly string[]).not.toContain(id);
    }
    expect(PANEL_ITEMS).toContain("bell");
  });
});

describe("sameItems", () => {
  it("compares in order", () => {
    expect(sameItems(["bell", "todo"], ["bell", "todo"])).toBe(true);
    expect(sameItems(["bell"], ["bell", "todo"])).toBe(false);
    expect(sameItems(["todo", "bell"], ["bell", "todo"])).toBe(false);
  });
});
