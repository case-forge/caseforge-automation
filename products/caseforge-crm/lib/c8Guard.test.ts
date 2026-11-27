import { describe, expect, it } from "vitest";
import { readStoredC8Guard } from "./c8Guard";

describe("the C8 guard setting", () => {
  it("is on unless it was stored as off", () => {
    expect(readStoredC8Guard(null)).toBe(true);
    expect(readStoredC8Guard("on")).toBe(true);
    expect(readStoredC8Guard("garbage")).toBe(true);
    expect(readStoredC8Guard("off")).toBe(false);
  });
});
