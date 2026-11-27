import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("Back to Home", () => {
  it("is a plain link, so the first press does a full load of the workspace", () => {
    const code = read("./BackToHome.tsx");
    expect(code).toContain('<a href="/"');
    expect(code).not.toContain('from "next/link"');
  });

  it("an unknown address ends on a not-found page that has the way back", () => {
    const code = read("../app/not-found.tsx");
    expect(code).toContain("FirmPage");
    expect(code).toContain("Page not found");
  });
});
