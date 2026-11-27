import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { PORTAL_FLAG, PORTAL_URL, pillFlagsToShow } from "./types";

describe("the PORTAL pill", () => {

  const helper = resolve(__dirname, "../../../tools/onboarding/pipeline/portal_courts.py");
  it.skipIf(!existsSync(helper))("opens the same address the case flow's portal helper uses", () => {
    const source = readFileSync(helper, "utf8");
    const match = source.match(/PORTAL_LOGIN_URL\s*=\s*"([^"]+)"/);
    expect(match?.[1]).toBe(PORTAL_URL);
  });
  it("shows for a portal matter and carries the address", () => {
    const shown = pillFlagsToShow({ [PORTAL_FLAG]: true }, true);
    expect(shown.map((f) => f.label)).toEqual(["PORTAL"]);
    expect(shown[0].href).toBe(PORTAL_URL);
  });
  it("is absent when the flag is off, and other pills never link", () => {
    expect(pillFlagsToShow({ [PORTAL_FLAG]: false }, true)).toEqual([]);
    expect(pillFlagsToShow({ transferred: true }, true)[0].href).toBeUndefined();
  });
});
