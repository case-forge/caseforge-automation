import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const path = (p: string) => fileURLToPath(new URL(p, import.meta.url));
const read = (p: string) => readFileSync(path(p), "utf8");

describe("the retired Case flow board", () => {
  it("is not in the apps menu", () => {
    const drawer = read("./AppDrawer.tsx");
    expect(drawer).not.toContain("/case-board");
    expect(drawer).not.toContain("Case Flow Board");
  });

  it("has no page, component or proxy route left", () => {
    expect(existsSync(path("../app/case-board/page.tsx"))).toBe(false);
    expect(existsSync(path("../app/api/case-board/route.ts"))).toBe(false);
    expect(existsSync(path("../app/api/case-board/remove/route.ts"))).toBe(false);
    expect(existsSync(path("./CaseBoard.tsx"))).toBe(false);
  });

  it("leaves the matter's own Case Flow tab with its sync marks", () => {
    expect(read("./CaseFlowTab.tsx")).toContain('from "@/lib/syncMark"');
  });
});
