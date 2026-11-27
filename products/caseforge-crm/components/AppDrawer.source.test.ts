
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./AppDrawer.tsx", import.meta.url)), "utf8");
const LISTS = readFileSync(fileURLToPath(new URL("../lib/clientLists.ts", import.meta.url)), "utf8");
const CODE = SOURCE.replace(/\/\*[\s\S]*?\*\//g, "");

describe("AppDrawer.tsx quick lists", () => {
  it("has one Frequent callers entry covering both caller flags, and no Persistent callers entry", () => {
    expect(LISTS).toContain('flag: "persistent_caller,persistent_caller_respondent"');
    expect(LISTS.match(/label: "Frequent callers"/g)).toHaveLength(1);
    expect(LISTS).not.toContain("Persistent callers");
    expect(CODE).not.toContain("loadFrequentCallers");
  });

  it("has Transferred and Dropped out lists, each from its own stored flag", () => {
    for (const [id, flag, label] of [["transferred", "transferred", "Transferred"], ["dropped-out", "dropped_out", "Dropped out"], ["billed", "billed", "Billed"]]) {
      expect(LISTS).toContain(`{ id: "${id}", label: "${label}", flag: "${flag}" }`);
    }
  });

  it("makes Client Lists a link to the Client lists page, not a dropdown, with the To check count; Flagged and Starred join it when the header has no room", () => {
    expect(CODE).toContain('<Link href="/client-lists"');
    expect(CODE).toContain("clientReviewCount > 0");
    expect(CODE).not.toContain("listsOpen");
    expect(CODE).not.toContain("aria-expanded");
    expect(CODE).not.toContain("app-drawer-folder-toggle");
    expect(CODE).toContain('(id === "flagged" || id === "starred") && showInMenu(id)');
    expect(CODE).toContain("href={listHref(id)}");
  });

  it("styles the entries as uniform square tiles, two to a row with an odd last tile centred", () => {
    const css = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");
    const tiles = css.slice(css.indexOf(".app-drawer-quick-lists {"), css.indexOf(".app-drawer-divider"));
    expect(tiles).toContain("justify-content: center");
    expect(tiles).toContain("flex: 0 0 calc(50% - 0.1rem)");
    expect(tiles).toContain("flex-direction: column");
    expect(tiles).not.toContain("grid-template-columns");
  });

  it("pages the Concluded list on the Client lists page", () => {
    expect(LISTS).toContain('{ id: "concluded", label: "Concluded" }');
    const lists = readFileSync(fileURLToPath(new URL("./ClientLists.tsx", import.meta.url)), "utf8");
    expect(lists).toContain("loadConcludedPage(0)");
    expect(lists).toContain("loadConcludedPage(next)");
    expect(lists).toMatch(/onLoadMore=\{next !== null/);
  });

  it("has no Assignments tile, no Assignment Board tile and no Categories row: the status board's category does the work", () => {
    expect(CODE).not.toContain("OPEN_ASSIGNMENTS_EVENT");
    expect(CODE).not.toContain("<span>Assignments</span>");
    expect(CODE).not.toContain("<span>Categories</span>");
    expect(CODE).not.toContain("Assignment Board");
    expect(CODE).not.toContain("/assignment-board");
  });

  it("has no Today, Removed and Merged Clients, System Health or What's New tile: each lives somewhere else", () => {
    for (const gone of ['href="/today"', 'href="/removed"', 'href="/system-health"', "notification-board#whats-new", "Removed and Merged Clients", "System Health", "What&apos;s New"]) {
      expect(CODE, gone).not.toContain(gone);
    }
    expect(CODE).not.toContain("APP_LINKS");
  });

  it("has E-signatures, Chambers Finder, BundleTool and Envelope Guide as tiles beside Settings", () => {
    const tiles = CODE.slice(CODE.indexOf('<div className="app-drawer-quick-lists">'), CODE.indexOf('<div className="app-drawer-theme"'));
    for (const [label, href] of [
      ["E-Signatures", 'firmUrl("sign")'],
      ["Chambers Finder", "https://caseforge.uk/chambers-finder"],
      ["BundleTool", "https://caseforge.uk/bundletool"],
      ["Envelope Guide", "https://caseforge.uk/envelope-guide"],
    ]) {
      expect(tiles, label).toContain(`<span>${label}</span>`);
      expect(tiles, label).toContain(href);
    }
    expect(tiles.indexOf("<span>Settings</span>")).toBeLessThan(tiles.indexOf("<span>E-Signatures</span>"));
  });

  it("has no list of apps under the tiles: no APP_LINKS, no divider after them, no link to the apps dashboard", () => {
    expect(CODE).not.toContain("APP_LINKS");
    expect(CODE).not.toContain('firmUrl("apps")');
    expect(CODE).not.toContain("app-drawer-item");
    expect(CODE).not.toContain("maskImage");
    expect(CODE).not.toContain("CRM (This App)");
    expect(CODE).not.toContain('firmUrl("train")');
  });

  it("puts Demo (Home on the demo) then Vergil straight after Client Lists, and Help, Theme and Settings last", () => {
    const order = [
      "<span>Client Lists",
      'IS_DEMO ? "Home" : "Demo"',
      "<span>Vergil</span>",
      "<span>E-Signatures</span>",
      "<span>BundleTool</span>",
      "<span>Chambers Finder</span>",
      "<span>Envelope Guide</span>",
      "<HelpMenuEntry />",
      'className="app-drawer-theme"',
      "<span>Settings</span>",
    ].map((needle) => {
      const at = CODE.indexOf(needle);
      expect(at, needle).toBeGreaterThan(-1);
      return at;
    });
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it("swaps the Demo tile for Home on the demo: the demo instance on the live site, Home and the live CRM on the demo", () => {
    expect(CODE).toContain('IS_DEMO ? firmUrl("crm") : firmUrl("demo")');
    expect(CODE).toContain("IS_DEMO ? <IconHome");
    expect(CODE).toContain("<IconGraduationCap");
    expect(SOURCE).toContain('import { IS_DEMO } from "./HeaderClock"');
  });

  it("links Vergil to the chat host with a speech bubble", () => {
    expect(CODE).toContain('href={firmUrl("chat")}');
    expect(CODE).toContain("<IconMessage");
  });

  it("no longer lists Secretary", () => {
    expect(CODE).not.toContain('firmUrl("secretary")');
    expect(CODE).not.toContain('label: "Secretary"');
  });

  it("opens every link in the menu in a new tab, never the same page", () => {

    const tags = CODE.match(/<(a|Link)\b[^>]*>/g) ?? [];
    expect(tags.length).toBeGreaterThanOrEqual(4);
    for (const tag of tags) {
      expect(tag, tag).toContain('target="_blank"');
      expect(tag, tag).toContain('rel="noopener noreferrer"');
    }
    expect(CODE).not.toMatch(/window\.location|location\.href|router\.push/);
  });

  const appbarPath = fileURLToPath(new URL("../../../deploy/appbar/appbar.html", import.meta.url));
  it.skipIf(!existsSync(appbarPath))("opens every link in the shared app bar in a new tab", () => {
    const html = readFileSync(appbarPath, "utf8");
    const menu = html.slice(html.indexOf('class="cf-appbar-menu"'));
    const tags = menu.match(/<a\b[^>]*>/g) ?? [];
    expect(tags).toHaveLength(5);
    for (const tag of tags) {
      expect(tag, tag).toContain('target="_blank"');
      expect(tag, tag).toContain('rel="noopener noreferrer"');
    }
  });
});

describe("notification Done, Dismiss and Hide buttons", () => {
  const css = readFileSync(fileURLToPath(new URL("../app/attention.css", import.meta.url)), "utf8");
  it("take a darker fill than the neutral panel in light mode only, and keep the neutral fill in dark mode", () => {
    expect(css).toContain(".attention-item-done:not(:disabled) { background: var(--hover-fill); }");
    expect(css).toContain(':root:not([data-theme="light"]) .attention-item-done:not(:disabled) { background: var(--panel); }');
    expect(css).toContain(':root[data-theme="dark"] .attention-item-done:not(:disabled) { background: var(--panel); }');
  });

  it("leaves the demo windows to the header's DEMO button, which toggles them and never only opens them", () => {
    const clock = readFileSync(fileURLToPath(new URL("./HeaderClock.tsx", import.meta.url)), "utf8");
    expect(clock).toContain("demoWindows.toggle()");
    expect(clock).not.toContain("demoWindows.openAll()");
    expect(CODE).not.toContain("demoWindows.openAll()");
  });

  it("unloads the game once no demo window is open, so the next press starts a fresh game", () => {
    const windows = readFileSync(fileURLToPath(new URL("./DemoWindows.tsx", import.meta.url)), "utf8");
    const effect = windows.slice(windows.indexOf("if (anyOpen || (!parts && !failed)) return;"));
    expect(effect.indexOf("unloadGame();")).toBeGreaterThan(0);
    expect(effect.indexOf("unloadGame();")).toBeLessThan(effect.indexOf("setParts(null)"));
  });
});
