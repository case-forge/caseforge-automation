
import { describe, expect, it } from "vitest";
import { markSessionStale, onSessionStale } from "./sessionStale";

describe("sessionStale (no window -- SSR/node test environment)", () => {
  it("markSessionStale does not throw without window", () => {
    expect(() => markSessionStale()).not.toThrow();
  });

  it("onSessionStale returns a no-op unsubscribe without window", () => {
    const unsubscribe = onSessionStale(() => {});
    expect(() => unsubscribe()).not.toThrow();
  });
});
