import { describe, expect, it } from "vitest";
import { IDLE_BEFORE_REFRESH_MS, REFRESH_AFTER_MS, shouldRefresh } from "./scheduledRefresh";

const idle = IDLE_BEFORE_REFRESH_MS;

describe("shouldRefresh", () => {
  it("reloads an idle page when a new build is running", () => {
    expect(shouldRefresh({ ageMs: 60_000, idleMs: idle, unsaved: 0, newBuild: true })).toBe(true);
  });

  it("reloads an idle page that is old, with no new build", () => {
    expect(shouldRefresh({ ageMs: REFRESH_AFTER_MS, idleMs: idle, unsaved: 0, newBuild: false })).toBe(true);
  });

  it("leaves a young page on the current build alone", () => {
    expect(shouldRefresh({ ageMs: REFRESH_AFTER_MS - 1, idleMs: idle, unsaved: 0, newBuild: false })).toBe(false);
  });

  it("never reloads while someone is using the page", () => {
    expect(shouldRefresh({ ageMs: REFRESH_AFTER_MS * 3, idleMs: idle - 1, unsaved: 0, newBuild: true })).toBe(false);
  });

  it("never reloads over unsaved changes, however old or idle", () => {
    expect(shouldRefresh({ ageMs: REFRESH_AFTER_MS * 3, idleMs: idle * 10, unsaved: 1, newBuild: true })).toBe(false);
  });
});
