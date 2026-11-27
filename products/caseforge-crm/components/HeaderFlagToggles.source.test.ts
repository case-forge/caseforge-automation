
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./HeaderFlagToggles.tsx", import.meta.url)), "utf8");

describe("HeaderFlagToggles.tsx source", () => {
  it("clears its open-matter marker on unmount so a late answer is dropped", () => {
    expect(SOURCE).toMatch(/useEffect\(\(\) => \(\) => \{\s*openMatter\.current = "";\s*\}, \[\]\)/);
  });
});
