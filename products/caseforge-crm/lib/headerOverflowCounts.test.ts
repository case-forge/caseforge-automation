import { describe, expect, it } from "vitest";
import { COUNT_ITEMS, HEADER_ITEMS, PANEL_ITEMS, calendarLabel, clientsLabel, showsCount } from "./headerOverflow";

describe("a count in the header is a count in the menu entry", () => {
  it("every header item that can leave carries a count, and every panel item is one of them", () => {
    expect([...COUNT_ITEMS].sort()).toEqual([...HEADER_ITEMS].filter((id) => id !== "clock").sort());
    for (const id of PANEL_ITEMS) expect(COUNT_ITEMS).toContain(id);
  });
  it("shows a count only above zero", () => {
    expect(showsCount(0)).toBe(false);
    expect(showsCount(undefined)).toBe(false);
    expect(showsCount(3)).toBe(true);
  });
  it("names the Clients and Calendar entries with the visible label first and the count after", () => {
    expect(clientsLabel(0)).toBe("Clients");
    expect(clientsLabel(1)).toBe("Clients, 1 client needs checking");
    expect(clientsLabel(2)).toBe("Clients, 2 clients need checking");
    expect(calendarLabel(0)).toBe("Calendar");
    expect(calendarLabel(1)).toBe("Calendar, 1 hearing needs review");
    expect(calendarLabel(4)).toBe("Calendar, 4 hearings need review");
  });
});
