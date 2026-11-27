import { describe, expect, it } from "vitest";
import { addDays, axisPounds, barHeight, dayCount, formatPounds, londonToday, niceStep, presetRange, rangeProblem, yScale } from "./billingChart";

describe("London days", () => {
  it("uses the London date, not UTC, late on a summer evening", () => {
    expect(londonToday(new Date("2026-07-01T23:30:00Z"))).toBe("2026-07-02");
    expect(londonToday(new Date("2026-01-01T23:30:00Z"))).toBe("2026-01-01");
  });
  it("adds days across a clock change without drifting", () => {
    expect(addDays("2026-03-28", 2)).toBe("2026-03-30");
    expect(addDays("2026-10-25", 1)).toBe("2026-10-26");
    expect(dayCount("2026-10-24", "2026-10-26")).toBe(3);
  });
  it("makes a preset that ends today and spans exactly that many days", () => {
    const r = presetRange(30, "2026-10-25");
    expect(r).toEqual({ from: "2026-09-26", to: "2026-10-25" });
    expect(dayCount(r.from, r.to)).toBe(30);
  });
});

describe("rangeProblem", () => {
  it("accepts a good range and names each fault", () => {
    expect(rangeProblem({ from: "2026-10-01", to: "2026-10-02" })).toBeNull();
    expect(rangeProblem({ from: "", to: "2026-10-02" })).toMatch(/both dates/);
    expect(rangeProblem({ from: "2026-10-03", to: "2026-10-02" })).toMatch(/not be after/);
    expect(rangeProblem({ from: "2025-01-01", to: "2026-10-02" })).toMatch(/at most 366/);
    expect(rangeProblem({ from: "2025-10-02", to: "2026-10-02" })).toBeNull();
  });
});

describe("money", () => {
  it("formats pounds and pence, and whole pounds on the axis", () => {
    expect(formatPounds(123456)).toBe("£1,234.56");
    expect(formatPounds(0)).toBe("£0.00");
    expect(axisPounds(150000)).toBe("£1,500");
  });
});

describe("scale", () => {
  it("gives a round top above the tallest bar, starting at zero", () => {
    const s = yScale([1080, 4300]);
    expect(s.ticks[0]).toBe(0);
    expect(s.top).toBeGreaterThanOrEqual(4300);
    expect(s.ticks.at(-1)).toBe(s.top);
  });
  it("copes with all zero", () => {
    const s = yScale([0, 0]);
    expect(s.top).toBeGreaterThan(0);
    expect(niceStep(0)).toBe(100);
  });
  it("never draws a non-zero bar thinner than 2px, nor a zero bar", () => {
    expect(barHeight(1, 100000, 200)).toBe(2);
    expect(barHeight(0, 100000, 200)).toBe(0);
    expect(barHeight(50000, 100000, 200)).toBe(100);
  });
});
