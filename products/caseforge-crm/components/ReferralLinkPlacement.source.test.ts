
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./DetailPanel.tsx", import.meta.url)), "utf8");

describe("DetailPanel header row", () => {
  it("puts the referral link left of the client number", () => {
    const referral = SOURCE.indexOf('<span className="detail-title-referral">');
    const number = SOURCE.indexOf("<MatterNumberArrows matterId={matterId}");
    expect(referral).toBeGreaterThan(-1);
    expect(number).toBeGreaterThan(-1);
    expect(referral).toBeLessThan(number);
  });
});
