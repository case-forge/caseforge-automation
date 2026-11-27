import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  MIN_QUERY_LENGTH,
  SWITCHER_LIMIT,
  isMacPlatform,
  isModalOpen,
  isSwitcherShortcut,
  switcherMode,
  switcherShortcutAction,
  switcherStatus,
} from "./quickSwitcher";
import type { ShortcutKey } from "./quickSwitcher";

const press = (over: Partial<ShortcutKey> = {}): ShortcutKey => ({
  key: "k",
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...over,
});

const inside = (...selectors: string[]) => ({ closest: (selector: string) => (selectors.includes(selector) ? {} : null) });
const plain = inside();

describe("the shortcut", () => {
  it("is Ctrl+K off a Mac and Cmd+K on one", () => {
    expect(isSwitcherShortcut(press({ ctrlKey: true }), false)).toBe(true);
    expect(isSwitcherShortcut(press({ metaKey: true }), true)).toBe(true);
    expect(isSwitcherShortcut(press({ key: "K", ctrlKey: true }), false)).toBe(true);
  });

  it("leaves Ctrl+K alone on a Mac, where it deletes to the end of a line", () => {
    expect(isSwitcherShortcut(press({ ctrlKey: true }), true)).toBe(false);
    expect(isSwitcherShortcut(press({ metaKey: true }), false)).toBe(false);
  });

  it("ignores K with another modifier, plain K and a held-down key", () => {
    expect(isSwitcherShortcut(press({ ctrlKey: true, shiftKey: true }), false)).toBe(false);
    expect(isSwitcherShortcut(press({ ctrlKey: true, altKey: true }), false)).toBe(false);
    expect(isSwitcherShortcut(press({ ctrlKey: true, metaKey: true }), false)).toBe(false);
    expect(isSwitcherShortcut(press(), false)).toBe(false);
    expect(isSwitcherShortcut(press({ ctrlKey: true, repeat: true }), false)).toBe(false);
    expect(isSwitcherShortcut(press({ key: "j", ctrlKey: true }), false)).toBe(false);
  });

  it("knows a Mac from its platform, or its user agent when the platform is empty", () => {
    expect(isMacPlatform("MacIntel", "")).toBe(true);
    expect(isMacPlatform("", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)")).toBe(true);
    expect(isMacPlatform("Win32", "Mozilla/5.0 (Windows NT 10.0)")).toBe(false);
    expect(isMacPlatform("Linux x86_64", undefined)).toBe(false);
  });
});

describe("what a press does", () => {
  const closed = { isMac: false, open: false, modalOpen: false };

  it("opens from anywhere, a text field included", () => {
    expect(switcherShortcutAction(press({ ctrlKey: true }), plain, closed)).toBe("open");
    expect(switcherShortcutAction(press({ ctrlKey: true }), inside("input"), closed)).toBe("open");
    expect(switcherShortcutAction(press({ ctrlKey: true }), null, closed)).toBe("open");
  });

  it("closes when it is already open", () => {
    expect(switcherShortcutAction(press({ ctrlKey: true }), plain, { ...closed, open: true })).toBe("close");
  });

  it("stays shut over a modal, such as the quick-run confirmation", () => {
    expect(switcherShortcutAction(press({ ctrlKey: true }), plain, { ...closed, modalOpen: true })).toBeNull();
  });

  it("never takes the key from a field that keeps it, or a handler that already used it", () => {
    expect(switcherShortcutAction(press({ ctrlKey: true }), inside("[data-keeps-ctrl-k]"), closed)).toBeNull();
    expect(switcherShortcutAction(press({ ctrlKey: true, defaultPrevented: true }), plain, closed)).toBeNull();
  });

  it("does nothing for any other key", () => {
    expect(switcherShortcutAction(press({ key: "Escape" }), plain, { ...closed, open: true })).toBeNull();
  });

  it("reads a modal from aria-modal", () => {
    expect(isModalOpen({ querySelector: (s: string) => (s === '[aria-modal="true"]' ? {} : null) })).toBe(true);
    expect(isModalOpen({ querySelector: () => null })).toBe(false);
    expect(isModalOpen(undefined)).toBe(false);
  });
});

describe("what it shows", () => {
  it("shows Recently viewed below two characters, as the search route refuses a shorter query", () => {
    expect(MIN_QUERY_LENGTH).toBe(2);
    expect(switcherMode("")).toBe("recent");
    expect(switcherMode(" a ")).toBe("recent");
    expect(switcherMode("ab")).toBe("search");
  });

  it("asks for a small number of matches, within the route's cap of 20", () => {
    expect(SWITCHER_LIMIT).toBeGreaterThan(0);
    expect(SWITCHER_LIMIT).toBeLessThanOrEqual(20);
  });

  it("says every empty state in words", () => {
    const base = { query: "zz", loading: false, error: null, count: 0 };
    expect(switcherStatus({ ...base, mode: "recent", query: "" })).toMatch(/Type 2 or more characters/);
    expect(switcherStatus({ ...base, mode: "recent", count: 3 })).toBeNull();
    expect(switcherStatus({ ...base, mode: "search", loading: true })).toBe("Searching…");
    expect(switcherStatus({ ...base, mode: "search" })).toBe('No clients match "zz".');
    expect(switcherStatus({ ...base, mode: "search", error: "upstream request failed" })).toBe("Search failed: upstream request failed");
    expect(switcherStatus({ ...base, mode: "search", count: 2 })).toBeNull();

    expect(switcherStatus({ ...base, mode: "search", loading: true, count: 2 })).toBeNull();
  });
});

describe("wiring (source text)", () => {
  const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

  it("goes through the page's search route and open-client path, with no search of its own", () => {
    const switcher = read("../components/QuickSwitcher.tsx");
    expect(switcher).toContain("fetchClientSearch(");
    expect(switcher).toContain("shouldFilter={false}");
    expect(switcher).toContain("vimBindings={false}");
    expect(switcher).not.toMatch(/\bfetch\(/);
    const page = read("../components/Workspace.tsx");
    expect(page).toContain("fetchClientSearch(trimmed, 20, controller.signal)");
    expect(page).toMatch(/function openFromSwitcher[\s\S]*?openClientByName\(/);
    expect(page).toContain("onOpenRecent={openRecent}");
  });

  it("shows the header's search button at phone width only", () => {
    const css = read("../app/switcher.css");
    const phone = css.slice(css.indexOf("@media (max-width: 640px)"));
    expect(css.slice(0, css.indexOf("@media"))).toContain(".switcher-phone-button { display: none; }");
    expect(phone).toContain(".switcher-phone-button { display: inline-flex;");
    expect(read("../components/Shell.tsx")).toContain('className="cf-btn cf-btn--flush header-view-button switcher-phone-button"');
  });

  it("loads the switcher only once it is first opened", () => {
    const page = read("../components/Workspace.tsx");
    expect(page).toContain('dynamic(() => import("@/components/QuickSwitcher"), { ssr: false })');
    expect(page).toContain("{switcherOpen && (");
  });
});
