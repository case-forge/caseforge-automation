import { beforeEach, describe, expect, it, vi } from "vitest";
import { formatTimeSpent, loadDefaultTime, minutesForPages, saveDefaultTime, totalMinutes } from "./anTime";

describe("totalMinutes", () => {
  it("adds hours and minutes, treating an empty box as zero", () => {
    expect(totalMinutes({ hours: "1", minutes: "5" })).toBe(65);
    expect(totalMinutes({ hours: "", minutes: "24" })).toBe(24);
    expect(totalMinutes({ hours: "2", minutes: "" })).toBe(120);
  });

  it("refuses nothing, out-of-range and non-numbers", () => {
    expect(totalMinutes({ hours: "", minutes: "" })).toBeNull();
    expect(totalMinutes({ hours: "0", minutes: "0" })).toBeNull();
    expect(totalMinutes({ hours: "1", minutes: "60" })).toBeNull();
    expect(totalMinutes({ hours: "100", minutes: "0" })).toBeNull();
    expect(totalMinutes({ hours: "24", minutes: "0" })).toBe(1440);
    expect(totalMinutes({ hours: "1.5", minutes: "0" })).toBeNull();
    expect(totalMinutes({ hours: "x", minutes: "5" })).toBeNull();
    expect(totalMinutes({ hours: "-1", minutes: "5" })).toBeNull();
  });
});

describe("formatTimeSpent", () => {
  it("prints H hour(s) MM mins, and only minutes under an hour", () => {
    expect(formatTimeSpent(24)).toBe("24 mins");
    expect(formatTimeSpent(5)).toBe("05 mins");
    expect(formatTimeSpent(60)).toBe("1 hour 00 mins");
    expect(formatTimeSpent(65)).toBe("1 hour 05 mins");
    expect(formatTimeSpent(125)).toBe("2 hours 05 mins");
  });
});

describe("pages and minutes", () => {
  it("works minutes from pages", () => {
    expect(minutesForPages(99, 2)).toBe(198);
    expect(formatTimeSpent(198)).toBe("3 hours 18 mins");
    expect(minutesForPages(0, 2)).toBeNull();
  });

  it("never comes to under six minutes", () => {
    expect(minutesForPages(1, 2)).toBe(6);
    expect(minutesForPages(3, 2)).toBe(6);
    expect(minutesForPages(4, 2)).toBe(8);
  });
});

describe("the carried-over default", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
        removeItem: (k: string) => void store.delete(k),
      },
    });
  });

  it("is remembered once set, and cleared by saving an empty value", () => {
    expect(loadDefaultTime()).toBeNull();
    saveDefaultTime({ hours: "0", minutes: "18" });
    expect(loadDefaultTime()).toEqual({ hours: "0", minutes: "18" });
    saveDefaultTime({ hours: "", minutes: "" });
    expect(loadDefaultTime()).toBeNull();
  });

  it("never stores an invalid value", () => {
    saveDefaultTime({ hours: "1", minutes: "99" });
    expect(loadDefaultTime()).toBeNull();
  });
});


import { timeFromMinutes } from "./anTime";

describe("timeFromMinutes", () => {
  it("splits minutes into the two boxes and round-trips with totalMinutes", () => {
    expect(timeFromMinutes(65)).toEqual({ hours: "1", minutes: "5" });
    expect(timeFromMinutes(24)).toEqual({ hours: "0", minutes: "24" });
    for (const n of [1, 59, 60, 61, 1439]) expect(totalMinutes(timeFromMinutes(n))).toBe(n);
  });
  it("gives empty boxes for none, zero, fractions and out-of-range", () => {
    for (const bad of [null, undefined, 0, -3, 2.5, 6000]) expect(timeFromMinutes(bad as number)).toEqual({ hours: "", minutes: "" });
  });
});
