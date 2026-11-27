
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./UpdateBanner.tsx", import.meta.url)), "utf8");
const CODE = SOURCE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

describe("UpdateBanner.tsx", () => {
  it("sets the stale state only through goStale, which only the access-expired path and the event call", () => {
    expect(CODE.match(/setState\("session-stale"\)/g)).toHaveLength(1);
    const calls = CODE.match(/goStale\(\)/g) ?? [];

    expect(calls).toHaveLength(3);
    expect(CODE).toContain("onSessionStale(goStale)");
    expect(CODE).toMatch(/probe === "access-expired"\) \{\s*goStale\(\);/);
  });

  it("sends a thrown fetch and an unreachable probe to the reconnecting path, not the red banner", () => {
    expect(CODE).toMatch(/catch \{\s*failed\(\);\s*\}/);
    expect(CODE).toMatch(/probe === "unreachable"\) \{\s*failed\(\);/);
  });

  it("says 'Your session has expired' once, inside the session-stale render branch", () => {
    expect(CODE.match(/Your session has expired/g)).toHaveLength(1);
    expect(CODE.indexOf("Your session has expired")).toBeGreaterThan(CODE.indexOf('state === "session-stale"'));
  });

  it("polls with redirect manual", () => {
    expect(CODE).toContain("...PROBE_INIT");
  });
});
