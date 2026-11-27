import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const src = readFileSync(new URL("./CaseFlowTab.tsx", import.meta.url), "utf8");

describe("Case Flow lock", () => {
  it("shows a lock icon with the reason and disables the switch, the steps and every step button, Reset included", () => {
    expect(src).toContain("<IconLock");
    expect(src).toContain("lockedReason(data)");
    expect(src).toMatch(/className="cf-btn cf-btn--segment cf2-mode"[^>]*disabled=\{locked !== ""\}/);
    expect(src).toMatch(/runBlockedReason\(\{[^}]*locked[^}]*\}\)/);

    expect(src.match(/disabled=\{locked !== ""/g)?.length ?? 0).toBeGreaterThanOrEqual(5);
    expect(src).toMatch(/className="cf-btn cf-btn--neutral cf2-reset-step"\s+disabled=\{locked !== "" \|\| running !== ""\}/);
  });
  it("never lets the mode change while locked", () => {
    expect(src).toMatch(/next === data\.mode \|\| lockedReason\(data\)/);
  });
});

describe("Case Flow padlock position", () => {
  it("sits to the right of the Manual/Auto switch", () => {
    expect(src.indexOf('className="cf-segment cf2-modes"')).toBeLessThan(src.indexOf('className="cf2-lock"'));
  });
});
