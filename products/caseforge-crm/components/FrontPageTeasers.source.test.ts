
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (p: string) => readFileSync(fileURLToPath(new URL(p, import.meta.url)), "utf8");
const PAGE = read("../components/Workspace.tsx");
const COMP = read("./FrontPageTeasers.tsx");
const LIB = read("../lib/frontPageTeasers.ts");

describe("front page teasers wiring", () => {
  it("sits above the Today board and only there", () => {
    expect(PAGE).toContain("<FrontPageTeasers />");
    expect(PAGE.indexOf("<FrontPageTeasers />")).toBeLessThan(PAGE.indexOf("<TodayBoard"));
    expect(PAGE.indexOf("<FrontPageTeasers />")).toBeGreaterThan(PAGE.indexOf("showTodayBoard(query"));
  });
  it("folds the tabs' panel out in the page (no floating box for them), fetches nothing itself and guards every storage access", () => {
    expect(COMP).toContain("toggleWindow(l.window)");
    expect(COMP).toContain('role="tablist"');
    expect(COMP).toContain('role="tabpanel"');
    expect(COMP).toContain("aria-expanded={active}");
    expect(COMP).toContain("usePresentNode(");
    expect(COMP).not.toContain("toggleWindow(t.id");
    expect(COMP).not.toContain("fetch(");
    expect((COMP.match(/localStorage/g) ?? []).length).toBe(2);
    expect((COMP.match(/try \{/g) ?? []).length).toBe(2);
  });
  it("the Status Board box ends with the Full Status Board and Export Board buttons", () => {
    const box = read("./StatusBoardBody.tsx");
    expect(box).toContain("Open Full Status Board");
    expect(box).toContain("Open Export Board");
  });
  it("registers the Producer as unavailable and the Status board against its page and the existing route", () => {
    expect(LIB).toMatch(/id: "producer"[\s\S]*?available: false/);
    expect(LIB).toContain('href: "/status-board"');
    expect(LIB).toContain('fetch("/api/status-board"');
  });
  it("has no em dash in UI text", () => {
    expect(COMP + LIB).not.toContain("—");
  });
});
