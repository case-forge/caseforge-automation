import { describe, expect, it } from "vitest";
import { readStoredClassifierPrompts } from "./classifierPrompts";

describe("the Show classifier prompts setting", () => {
  it("is off unless it was stored as on", () => {
    expect(readStoredClassifierPrompts(null)).toBe(false);
    expect(readStoredClassifierPrompts("on")).toBe(true);
    expect(readStoredClassifierPrompts("garbage")).toBe(false);
    expect(readStoredClassifierPrompts("off")).toBe(false);
  });
});
