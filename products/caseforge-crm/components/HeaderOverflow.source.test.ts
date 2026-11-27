
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { HEADER_ITEMS } from "@/lib/headerOverflow";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const strip = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const shell = strip(read("./Shell.tsx"));
const header = shell.slice(shell.indexOf('<header className="app-header"'), shell.indexOf("</header>"));
const css = read("../app/globals.css");

describe("header branding", () => {
  it("shows the logo only, with no CRM lettering", () => {
    expect(header).not.toMatch(/\bCRM\b/);
    expect(shell).not.toContain("app-header-title");
    expect(css).not.toContain(".app-header-title");
    expect(header.match(/caseforge-mark-(dark|light)\.svg/g)).toHaveLength(2);
  });

  it("names the app in full on hover and for screen readers", () => {
    expect(shell).toContain('export const APP_NAME = "Client Relationship Manager";');
    expect(header).toContain('className="cf-btn cf-btn--icon app-header-brand" aria-label={`${APP_NAME}: back to today`} title={`${APP_NAME} - back to today`}');
  });

  it("makes the logo a button back to the Today screen, and keeps the apps menu button", () => {

    const brand = header.slice(header.indexOf("app-header-brand"), header.indexOf("</button>", header.indexOf("app-header-brand")));
    expect(brand).toContain("caseforge-mark-light.svg");
    expect(brand).toContain("onClick={onGoHome}");
    const page = readFileSync(fileURLToPath(new URL("../components/Workspace.tsx", import.meta.url)), "utf8");
    const goHome = page.slice(page.indexOf("function goHome()"), page.indexOf("function handleQuickListResults"));
    for (const call of ['setQuery("")', "setListSource(null)", "setSelectedMatch(null)", 'setView("search")']) expect(goHome).toContain(call);
    expect(page).toContain("onGoHome={goHome}");
    expect(header).toContain("<AppDrawer");
  });

  it("holds the logo at the left and never shrinks it", () => {
    expect(css).toMatch(/\.cf-btn\.app-header-brand \{[^}]*flex-shrink: 0/);
  });
});

describe("theme picker", () => {
  it("is in the apps menu between Help and Settings, last, once, and nowhere in the header", () => {
    expect(shell).not.toContain("ThemeToggle");
    const drawer = strip(read("./AppDrawer.tsx"));
    expect(drawer).toContain("<ThemeToggle />");
    expect(drawer.indexOf("<span>Settings</span>")).toBeGreaterThan(0);
    expect(drawer.indexOf("<ThemeToggle />")).toBeLessThan(drawer.indexOf("<span>Settings</span>"));
    expect(drawer.indexOf("<ThemeToggle />")).toBeGreaterThan(drawer.indexOf("<HelpMenuEntry />"));
    expect(drawer.indexOf("<HelpMenuEntry />")).toBeGreaterThan(drawer.indexOf("<span>Envelope Guide</span>"));
    expect(strip(read("./SettingsBox.tsx"))).not.toContain("ThemeToggle");
    expect(strip(read("./SettingsBox.tsx"))).toContain("<DefaultTimeSetting />");
    expect(read("./AttendanceNoteForm.tsx")).not.toContain("saveDefaultTime");
  });
});

describe("header overflow", () => {
  it("gives every header button a place that can move into the apps menu", () => {
    for (const id of HEADER_ITEMS) expect(header, id).toContain(`<HeaderItem id="${id}">`);
  });

  it("leaves no button in the header outside such a place, bar the apps menu", () => {
    const actions = header.slice(header.indexOf("app-header-actions"));
    const provided = actions.slice(actions.indexOf("<HeaderOverflowProvider"), actions.indexOf("</HeaderOverflowProvider>"));
    const after = actions.slice(actions.indexOf("</HeaderOverflowProvider>"));
    expect(after.match(/<[A-Z]\w+/g)).toEqual(["<AppDrawer"]);
    for (const line of provided.split("\n").filter((l) => /^ {10}</.test(l))) {
      expect(line.trim()).toMatch(/^<\/?HeaderItem/);
    }
  });

  it("offers a menu entry from each panel button, and marks each button for measuring", () => {
    for (const name of ["AttentionBell", "TodoHeader", "RobotNotices"]) {
      const text = strip(read(`./${name}.tsx`));
      expect(text, name).toContain("<HeaderOverflowEntry");
      expect(text, name).toContain('data-header-measure=""');
      expect(text, name).toContain("useDismiss(open, () => setOpen(false), rootRef, entryRef)");
    }
    expect(shell.match(/data-header-measure=""/g)).toHaveLength(3);
  });

  it("shows Flagged, Starred and the view switch in the menu only when their buttons have left the header", () => {
    const drawer = strip(read("./AppDrawer.tsx"));
    expect(drawer).toContain('(id === "flagged" || id === "starred") && showInMenu(id)');
    expect(shell).toContain('onViewChange && (collapsed.includes("view") && !hidden.includes("clients"))');
    expect(shell).toContain('onViewChange && (collapsed.includes("view") && !hidden.includes("calendar"))');
  });

  it("is measured, not a fixed breakpoint, and never wraps or scrolls the header", () => {
    expect(css).not.toContain(".header-collapsible");
    expect(css).not.toContain("app-drawer-compact");
    expect(css).toMatch(/\.header-item\[data-collapsed="true"\] \[data-header-measure\] \{[^}]*visibility: hidden/);
    const overflow = strip(read("./HeaderOverflow.tsx"));
    expect(overflow).toContain("new ResizeObserver(measure)");
    expect(overflow).toContain("fitHeaderItems(");
  });

  it("keeps the apps menu inside the window", () => {
    expect(css).toMatch(/\.app-drawer-menu \{[^}]*max-width: calc\(100vw - 1\.5rem\)[^}]*max-height: calc\(100dvh - 4\.5rem\)[^}]*overflow-y: auto/);
  });
});
