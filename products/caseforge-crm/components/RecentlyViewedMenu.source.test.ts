
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const strip = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

describe("Recently viewed placement", () => {
  it("is on the search row, in the same group as Search and To check", () => {
    const page = read("../components/Workspace.tsx");
    const group = page.slice(page.indexOf('className="view-tabs"'), page.indexOf("</div>", page.indexOf('className="view-tabs"')));
    expect(group).toContain("<RecentlyViewedMenu");
  });

  it("is gone from the header and the apps menu", () => {
    expect(strip(read("./Shell.tsx"))).not.toContain("Recently viewed");
    expect(strip(read("./AppDrawer.tsx"))).not.toContain("Recently viewed");
  });

  it("lists the stored recent clients, offers the old list view, and closes on Escape or an outside press", () => {
    const menu = read("./RecentlyViewedMenu.tsx");
    expect(menu).toContain("loadRecentlyViewed()");
    expect(menu).toContain("Show as list");
    expect(menu).toContain("useDismiss(open, () => setOpen(false), rootRef)");
  });
});

describe("Recent opens any client", () => {
  it("puts the recent list in the results and selects the clicked client at its own index", () => {
    const page = read("../components/Workspace.tsx");
    expect(page).toContain("recentSelection(all, match)");
    expect(page).toContain('handleQuickListResults(matches, "Recently viewed")');
    expect(page).toContain("matchKey(matches[index], index)");
  });
});
