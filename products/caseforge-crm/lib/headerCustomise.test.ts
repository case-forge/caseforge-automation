import { describe, expect, it } from "vitest";
import { CUSTOMISE_ITEMS, hiddenHeaderItems, parseHidden, serialiseHidden, storageKeyFor, toggleHidden } from "./headerCustomise";
import { HEADER_ITEMS, fitHeaderItems } from "./headerOverflow";
import type { HeaderWidths } from "./headerOverflow";

describe("hidden header items: read, write, merge", () => {
  it("offers every header item, with Clients and Calendar as two switches", () => {
    for (const id of HEADER_ITEMS) if (id !== "view") expect(CUSTOMISE_ITEMS).toContain(id);
    expect(CUSTOMISE_ITEMS).toContain("clients");
    expect(CUSTOMISE_ITEMS).toContain("calendar");
  });

  it("round-trips, and ignores unknown ids and bad data", () => {
    expect(parseHidden(serialiseHidden(["clock", "bell"]))).toEqual(["bell", "clock"]);
    expect(parseHidden('["bell","nonsense",3]')).toEqual(["bell"]);
    expect(parseHidden("not json")).toEqual([]);
    expect(parseHidden('{"bell":true}')).toEqual([]);
    expect(parseHidden(null)).toEqual([]);
  });

  it("toggles one item on and off", () => {
    const hidden = toggleHidden([], "todo");
    expect(hidden).toEqual(["todo"]);
    expect(toggleHidden(hidden, "todo")).toEqual([]);
  });

  it("keeps one key per signed-in name, and none without a name", () => {
    expect(storageKeyFor("user-a")).not.toBe(storageKeyFor("user-b"));
    expect(storageKeyFor(" user-a ")).toBe(storageKeyFor("USER-A"));
    expect(storageKeyFor("")).toBeNull();
  });

  it("hides the view switch as a whole only when both buttons are hidden", () => {
    expect(hiddenHeaderItems(["clients"])).toEqual([]);
    expect(hiddenHeaderItems(["clients", "calendar", "clock"])).toEqual(["clock", "view"]);
  });

});

describe("hidden items and the overflow fit", () => {
  const widths: HeaderWidths = Object.fromEntries(HEADER_ITEMS.map((id) => [id, 40]));
  const fit = (available: number, hidden: (typeof HEADER_ITEMS)[number][]) => fitHeaderItems({ available, reserved: 40, gap: 8, widths, hidden });

  it("gives hidden items no room, so fewer others have to leave", () => {
    expect(fit(423, [])).toEqual(["starred"]);
    expect(fit(423, ["clock"])).toEqual([]);
  });

  it("never reports a hidden item as moved by width", () => {
    expect(fit(88, ["bell", "starred"])).not.toContain("bell");
    expect(fit(88, ["bell", "starred"])).not.toContain("starred");
  });
});
