
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("To check", () => {
  it("has no Refresh button on the search row", () => {
    const page = read("../components/Workspace.tsx");
    expect(page).not.toContain("view-tabs-refresh");
    expect(page).not.toMatch(/>\s*Refresh\s*</);
  });

  it("re-reads the queue on a visible-tab timer", () => {
    expect(read("../lib/fieldReviewQueue.ts")).toContain("startVisiblePoll");
  });

  it("has no Search button: typing already searches", () => {
    const page = read("../components/Workspace.tsx");
    const group = page.slice(page.indexOf('className="view-tabs"'), page.indexOf("</RecentlyViewedMenu>") > 0 ? page.indexOf("</RecentlyViewedMenu>") : page.indexOf("<RecentlyViewedMenu"));
    expect(group).not.toMatch(/>\s*Search\s*</);
    expect(group).not.toContain("onClick={showSearchTab}>");
  });

  it("is reached from the menu's Client Lists folder, with its count on the To Check entry, not a button on the search row", () => {
    const page = read("../components/Workspace.tsx");
    expect(page).not.toContain("aria-pressed={onClientReviewTab}");
    const drawer = read("./AppDrawer.tsx");
    expect(drawer).toContain('<Link href="/client-lists"');
    expect(drawer).toContain("Client Lists{clientReviewCount > 0");
    expect(drawer).not.toContain("to check)");
  });

  it("shows Recent as the clock alone, with a name for screen readers and a tooltip", () => {
    const menu = read("./RecentlyViewedMenu.tsx");
    const button = menu.slice(menu.indexOf('aria-expanded={open}') - 80, menu.indexOf("{open && ("));
    expect(button).toContain("<IconClock");
    expect(button).toContain('aria-label="Recently viewed"');
    expect(button).toContain('title="Recently viewed"');
    expect(button).not.toMatch(/>\s*Recent\s*</);
    expect(button).toContain("view-tab--icon");
  });
});
