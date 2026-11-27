import { describe, expect, it } from "vitest";
import { LEAVING_SOON_REFRESH_MS, refreshDelay } from "./autoSendStore";

describe("when Auto Send is fetched next", () => {
  it("a box just opened (or a tab just back) fetches now, if the tab is visible", () => {
    expect(refreshDelay({ hasLeavingSoon: false, visible: true, opened: true })).toBe(0);
    expect(refreshDelay({ hasLeavingSoon: true, visible: true, opened: true })).toBe(0);
  });
  it("every 30 seconds only while something is leaving soon", () => {
    expect(refreshDelay({ hasLeavingSoon: true, visible: true, opened: false })).toBe(30_000);
    expect(LEAVING_SOON_REFRESH_MS).toBe(30_000);
  });
  it("nothing polls when nothing is leaving soon", () => {
    expect(refreshDelay({ hasLeavingSoon: false, visible: true, opened: false })).toBeNull();
  });
  it("nothing polls while the tab is hidden, whatever else is true", () => {
    expect(refreshDelay({ hasLeavingSoon: true, visible: false, opened: false })).toBeNull();
    expect(refreshDelay({ hasLeavingSoon: true, visible: false, opened: true })).toBeNull();
  });
});
