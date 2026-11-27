import { describe, expect, it } from "vitest";
import { countdown, countdownText } from "./todoCountdown";

const NOW = new Date("2026-09-25T12:00:00Z");

describe("countdown", () => {
  it("counts down in days, hours and minutes", () => {
    const c = countdown("2026-09-27T15:15:00Z", NOW);
    expect(c).toMatchObject({ overdue: false, label: "02:03:15", long: "2 days, 3 hours, 15 minutes" });
    expect(countdownText(c!)).toBe("Due in 02:03:15");
  });

  it("counts up once overdue", () => {
    const c = countdown("2026-09-25T11:55:40Z", NOW)!;
    expect(c.overdue).toBe(true);
    expect(countdownText(c)).toBe("Overdue 00:00:04");
    expect(countdownText(countdown("2026-09-23T10:30:00Z", NOW)!)).toBe("Overdue 02:01:30");
  });

  it("is overdue at the exact moment, and uses singular units", () => {
    expect(countdown("2026-09-25T12:00:00Z", NOW)!.overdue).toBe(true);
    expect(countdown("2026-09-26T13:01:00Z", NOW)!.long).toBe("1 day, 1 hour, 1 minute");
  });

  it("is null for a bad date", () => {
    expect(countdown("soon", NOW)).toBeNull();
  });
});
