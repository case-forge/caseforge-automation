import { describe, expect, it } from "vitest";
import { EDGE, MAX_STEP, edgeScrollStep } from "./dragEdgeScroll";

describe("edgeScrollStep", () => {
  it("does nothing in the middle", () => {
    expect(edgeScrollStep(500, 0, 1000)).toBe(0);
    expect(edgeScrollStep(EDGE, 0, 1000)).toBe(0);
    expect(edgeScrollStep(1000 - EDGE, 0, 1000)).toBe(0);
  });
  it("scrolls towards the end near the right edge, faster the closer it is", () => {
    const near = edgeScrollStep(990, 0, 1000);
    const far = edgeScrollStep(930, 0, 1000);
    expect(far).toBeGreaterThan(0);
    expect(near).toBeGreaterThan(far);
    expect(near).toBeLessThanOrEqual(MAX_STEP);
  });
  it("scrolls towards the start near the left edge", () => {
    expect(edgeScrollStep(10, 0, 1000)).toBeLessThan(0);
    expect(edgeScrollStep(-50, 0, 1000)).toBe(-MAX_STEP);
  });
  it("is safe for an empty or odd box", () => {
    expect(edgeScrollStep(5, 10, 10)).toBe(0);
    expect(edgeScrollStep(Number.NaN, 0, 100)).toBe(0);
  });
});
