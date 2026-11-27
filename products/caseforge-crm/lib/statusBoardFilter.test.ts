import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe as suite, expect, it } from "vitest";
import {
  applyFilter,
  booksIn,
  carriedForward,
  defaultFilter,
  describe,
  groupsOf,
  parseStored,
  serialise,
  toggleCode,
  type BoardFilter,
} from "./statusBoardFilter";

const item = (order_codes: string[], book: string) => ({ order_codes, book });
const items = [
  item(["NMO"], "Book A - NMO-CAO"),
  item(["NMO", "PSO"], "Book A - NMO-CAO"),
  item(["CAO"], "Book A - NMO-CAO"),
  item([], "Book A - NMO-CAO"),
  item(["OO"], "Book B - Litigation"),
  item([], "Book C - Other"),
  item(["SIO"], "Care-Proceedings"),
];

suite("groups and matching", () => {
  it("puts a matter with no code, or no known code, under Other", () => {
    expect(groupsOf(item([], ""))).toEqual(["OTHER"]);
    expect(groupsOf(item(["FL401"], ""))).toEqual(["OTHER"]);
    expect(groupsOf(item(["pso", "nmo"], ""))).toEqual(["NMO", "PSO"]);
  });

  it("shows a matter when any of its codes is on", () => {
    const f: BoardFilter = { codes: ["PSO"], book: "" };
    expect(applyFilter(items, f)).toEqual([items[1]]);
  });

  it("narrows by folder as well as code", () => {
    const f: BoardFilter = { codes: ["NMO", "OO"], book: "Book B - Litigation" };
    expect(applyFilter(items, f)).toEqual([items[4]]);
  });

  it("shows nothing with no box ticked", () => {
    expect(applyFilter(items, { codes: [], book: "" })).toEqual([]);
  });
});

suite("the default", () => {
  it("is NMO and CAO in the NMO-CAO book", () => {
    const { filter, fallback } = defaultFilter(items);
    expect(filter).toEqual({ codes: ["NMO", "CAO"], book: "Book A - NMO-CAO", year: "" });
    expect(fallback).toBe(false);
    expect(applyFilter(items, filter)).toHaveLength(3);
  });

  it("falls back to everything when there is no NMO-CAO book", () => {
    const rest = items.filter((i) => !i.book.includes("NMO"));
    const { filter, fallback } = defaultFilter(rest);
    expect(fallback).toBe(true);
    expect(applyFilter(rest, filter)).toHaveLength(rest.length);
  });
});

suite("remembering and describing", () => {
  it("round-trips a stored choice, ignores junk, and ignores a saved folder", () => {
    const f: BoardFilter = { codes: ["OO", "OTHER"], book: "", year: "", month: "11" };
    expect(parseStored(serialise(f), items)).toEqual(f);
    expect(parseStored("not json", items)).toBeNull();
    expect(parseStored(null, items)).toBeNull();

    expect(parseStored('{"codes":["OO"],"book":"Book B - Litigation","year":""}', items)).toEqual({ codes: ["OO"], book: "", year: "", month: "" });
    expect(parseStored('{"codes":["OO"],"book":"Gone"}', items)?.book).toBe("");
  });

  it("toggles one code and lists books (the front page box still reads them)", () => {
    expect(toggleCode({ codes: ["NMO"], book: "" }, "CAO").codes).toEqual(["NMO", "CAO"]);
    expect(toggleCode({ codes: ["NMO", "CAO"], book: "" }, "NMO").codes).toEqual(["CAO"]);
    expect(booksIn(items)).toHaveLength(4);
  });

  it("says what is on and how many are hidden", () => {
    const text = describe(3, 7, { codes: ["NMO", "CAO"], book: "Book A - NMO-CAO" });
    expect(text).toBe("Showing 3 of 7 open matters: NMO, CAO; folder Book A - NMO-CAO. 4 hidden by these filters.");
    expect(describe(7, 7, defaultFilter([]).filter, true)).toContain("There is no NMO-CAO folder");
  });
});

suite("the page", () => {
  const page = readFileSync(fileURLToPath(new URL("../app/status-board/page.tsx", import.meta.url)), "utf8");
  it("guards every localStorage access and keeps the client and number columns", () => {
    expect(page.match(/localStorage/g)?.length).toBe(2);
    expect(page).toMatch(/try \{\s*stored = window\.localStorage/);
    expect(page).toMatch(/try \{\s*window\.localStorage\.setItem\(STORAGE_KEY/);
    expect(page).toContain("Client{arrow");
    expect(page).toContain("No.{arrow");
  });
});

import { MONTHS, defaultYear, matchesFilter, pageDefaultFilter, periodWords, yearsIn } from "./statusBoardFilter";
import { boardMonth } from "./matterMilestones";

suite("year and month lookups", () => {
  const at = (date_joined: string) => ({ order_codes: ["NMO"], book: "B", date_joined });
  const rows = [at("2026-09-30"), at("2026-10-01"), at("2026-10-31"), at("2026-11-01"), at("2026-12-31"), at("2027-01-01"), at("2025-12-31"), at("")];
  const f = (year: string, month: string): BoardFilter => ({ codes: ["NMO"], book: "", year, month });
  const dates = (flt: BoardFilter) => applyFilter(rows, flt).map((r) => r.date_joined);

  it("lists the months January to December", () => {
    expect(MONTHS).toHaveLength(12);
    expect(MONTHS[0]).toEqual({ value: "01", label: "January" });
    expect(MONTHS[11]).toEqual({ value: "12", label: "December" });
  });
  it("reads the month in London time", () => {
    expect(boardMonth("2026-09-30T23:30:00Z")).toBe("10");
    expect(boardMonth("2026-10-31T23:30:00Z")).toBe("10");
    expect(boardMonth("2026-12-31T23:30:00Z")).toBe("12");
    expect(boardMonth("2026-12-31")).toBe("12");
    expect(boardMonth("")).toBe("");
  });
  it("a month inside a year, across month and year boundaries; a matter with no date is never hidden", () => {
    expect(dates(f("2026", "10"))).toEqual(["2026-10-01", "2026-10-31", ""]);
    expect(dates(f("2026", "09"))).toEqual(["2026-09-30", ""]);
    expect(dates(f("2026", "11"))).toEqual(["2026-11-01", ""]);
    expect(dates(f("2026", "12"))).toEqual(["2026-12-31", ""]);
    expect(dates(f("2027", "01"))).toEqual(["2027-01-01", ""]);
    expect(dates(f("2026", "01"))).toEqual([""]);
  });
  it("all months in a year, all years in a month, and everything", () => {
    expect(dates(f("2026", ""))).toEqual(["2026-09-30", "2026-10-01", "2026-10-31", "2026-11-01", "2026-12-31", ""]);
    expect(dates(f("", "12"))).toEqual(["2026-12-31", "2025-12-31", ""]);
    expect(dates(f("", ""))).toHaveLength(8);
  });
  it("a month never matches the wrong year's same month", () => {
    expect(matchesFilter(at("2025-12-31"), f("2026", "12"))).toBe(false);
    expect(matchesFilter(at("2026-12-31"), f("2026", "12"))).toBe(true);
  });
  it("offers the referral years newest first, and the default is this year, all months", () => {
    expect(yearsIn(rows)).toEqual(["2027", "2026", "2025"]);
    expect(defaultYear(rows, new Date("2026-11-10T12:00:00Z"))).toBe("2026");
    expect(pageDefaultFilter(rows, new Date("2026-11-10T12:00:00Z"))).toEqual({ codes: ["NMO", "CAO"], book: "", year: "2026", month: "" });
  });
  it("says the period in words", () => {
    expect(periodWords("2026", "11")).toBe("November 2026");
    expect(periodWords("2027", "01")).toBe("January 2027");
    expect(periodWords("2026", "")).toBe("2026");
    expect(periodWords("", "12")).toBe("December in any year");
    expect(periodWords("", "")).toBe("");
    expect(describe(2, 8, f("2026", "11"))).toContain("referred in November 2026");
    expect(describe(8, 8, f("", ""))).not.toContain("referred");
  });
  it("a stored year of all years, a bad month and a vanished year are read safely", () => {
    expect(parseStored('{"codes":["NMO"],"year":"","month":"13"}', rows)).toMatchObject({ year: "", month: "" });
    expect(parseStored('{"codes":["NMO"],"year":"1999","month":"02"}', rows, new Date("2026-11-10T12:00:00Z"))).toMatchObject({ year: "2026", month: "02" });
  });
});

suite("carry forward: a client still waiting to sign stays in later periods until they sign", () => {
  const base = { order_codes: ["NMO"], book: "" };
  const waiting = { ...base, date_joined: "2026-09-01", initial_ws: "", milestones: { contacted: "2026-09-03T10:00:00Z" } };
  const signed = { ...waiting, initial_ws: "2026-09-20T10:00:00Z" };
  const later = { ...waiting, date_joined: "2026-12-01" };

  it("shows an earlier unsigned client in a later month and a later year, never a signed one or one referred after", () => {
    const nov = { codes: ["NMO" as const], book: "", year: "2026", month: "11" };
    expect(carriedForward(waiting, nov)).toBe(true);
    expect(matchesFilter(waiting, nov)).toBe(true);
    expect(matchesFilter(signed, nov)).toBe(false);
    expect(matchesFilter(later, nov)).toBe(false);
    expect(matchesFilter(waiting, { codes: ["NMO"], book: "", year: "2027", month: "" })).toBe(true);
    expect(matchesFilter(waiting, { codes: ["NMO"], book: "", year: "2025", month: "" })).toBe(false);
  });
  it("still obeys the order types and the folder", () => {
    expect(matchesFilter(waiting, { codes: ["CAO"], book: "", year: "2026", month: "11" })).toBe(false);
    expect(matchesFilter(waiting, { codes: ["NMO"], book: "Book A", year: "2026", month: "11" })).toBe(false);
  });
  it("says how many are carried forward", () => {
    expect(describe(3, 10, { codes: ["NMO"], book: "", year: "2026", month: "11" }, false, 0, 1)).toContain("1 referred earlier is carried forward until they sign.");
    expect(describe(3, 10, { codes: ["NMO"], book: "", year: "2026", month: "11" }, false, 0, 0)).not.toContain("carried forward");
  });
});
