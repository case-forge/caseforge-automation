import { describe, expect, it } from "vitest";
import { COUNTDOWN_MS, countdownLabel } from "./sessionExpiry";

const END = 1_800_000_000_000;

describe("countdownLabel", () => {
  it("is quiet when Access is not in front of the request", () => {
    expect(countdownLabel(null, END)).toBeNull();
  });

  it("is quiet before the last five minutes", () => {
    expect(countdownLabel(END, END - COUNTDOWN_MS - 1000)).toBeNull();
  });

  it("starts at 5:00 and counts down in minutes and seconds", () => {
    expect(countdownLabel(END, END - COUNTDOWN_MS)).toBe("5:00");
    expect(countdownLabel(END, END - 61_000)).toBe("1:01");
    expect(countdownLabel(END, END - 9_000)).toBe("0:09");
  });

  it("rounds a part second up so it never shows 0:00 before the end", () => {
    expect(countdownLabel(END, END - 400)).toBe("0:01");
  });

  it("is quiet once the session has ended", () => {
    expect(countdownLabel(END, END)).toBeNull();
    expect(countdownLabel(END, END + 5000)).toBeNull();
  });
});
