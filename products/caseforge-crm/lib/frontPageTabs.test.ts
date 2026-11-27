import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { arrowTarget, pressTab, rememberedTab, rememberTab, shownTab, tabStop } from "./frontPageTabs";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const TABS = ["status-board", "auto-sent", "court-prep"];

describe("the front page tabs fold a panel out in the page", () => {
  it("a press opens a tab, a second press folds it away, another tab switches: one open at a time", () => {
    expect(pressTab("", "status-board")).toBe("status-board");
    expect(pressTab("status-board", "status-board")).toBe("");
    expect(pressTab("status-board", "auto-sent")).toBe("auto-sent");
  });
  it("a tab switched off in the cog menu is closed, and the tab stop is the open tab or else the first", () => {
    expect(shownTab("court-prep", TABS)).toBe("court-prep");
    expect(shownTab("court-prep", ["status-board", "auto-sent"])).toBe("");
    expect(tabStop("", TABS)).toBe("status-board");
    expect(tabStop("auto-sent", TABS)).toBe("auto-sent");
    expect(tabStop("", [])).toBe("");
  });
  it("arrow keys move along the tabs and wrap; Home and End go to the ends; other keys do nothing", () => {
    expect(arrowTarget(TABS, "status-board", "ArrowRight")).toBe("auto-sent");
    expect(arrowTarget(TABS, "court-prep", "ArrowRight")).toBe("status-board");
    expect(arrowTarget(TABS, "status-board", "ArrowLeft")).toBe("court-prep");
    expect(arrowTarget(TABS, "auto-sent", "Home")).toBe("status-board");
    expect(arrowTarget(TABS, "auto-sent", "End")).toBe("court-prep");
    expect(arrowTarget(TABS, "auto-sent", "Enter")).toBeNull();
    expect(arrowTarget([], "x", "ArrowRight")).toBeNull();
  });
  it("the open tab is remembered for the visit", () => {
    rememberTab("auto-sent");
    expect(rememberedTab()).toBe("auto-sent");
    rememberTab("");
    expect(rememberedTab()).toBe("");
  });
  it("is a real tab list: tabs with aria-selected and aria-expanded, one tab panel, keyboard handled", () => {
    const src = read("../components/FrontPageTeasers.tsx");
    expect(src).toContain('role="tablist"');
    expect(src).toContain('role="tab"');
    expect(src).toContain('role="tabpanel"');
    expect(src).toContain("aria-selected={active}");
    expect(src).toContain("aria-expanded={active}");
    expect(src).toContain("onKeyDown={(e) => onTabKey(e, t.id)}");
    expect(src).toContain("tabIndex={t.id === stop ? 0 : -1}");
  });
  it("the panel is in the page flow, not a floating window: no WidgetBox, no drag, and the three boxes are gone", () => {
    const src = read("../components/FrontPageTeasers.tsx");
    expect(src).not.toMatch(/WidgetBox|useFloatingBox|CardBar/);
    for (const gone of ["StatusBoardBox", "AutoSendBox", "CourtPrepBox"]) {
      expect(read("../components/WidgetLayer.tsx")).not.toContain(gone);
    }
    expect(read("./cornerPrompts.ts")).not.toMatch(/"status-board"|"auto-sent"|"court-prep"/);

    expect(read("../components/GlobalHearings.tsx")).toContain("consumeRequest(");
  });
  it("the fold animates its height, is not positioned over the page, and stops for reduced motion", () => {
    const css = read("../app/teasers.css");
    expect(css).toMatch(/@keyframes tabfold-in \{ from \{ grid-template-rows: 0fr;/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\) \{ \.tabfold-open, \.tabfold-closing \{ animation: none; \} \}/);
    const fold = css.split("\n").filter((l) => l.startsWith(".tabfold"));
    expect(fold.join("\n")).not.toMatch(/position: (absolute|fixed)/);

    expect(css).toMatch(/\.front-tab\[aria-selected="true"\],[\s\S]*?z-index: 2; background: var\(--card\)/);

    expect(css).toMatch(/\.teasers-tabs \{ order: 2;[^}]*margin-bottom: -2px; position: relative; z-index: 2; \}/);
    expect(css).toContain("filter: drop-shadow(0 -1px 3px var(--tab-shadow)); clip-path: inset(-12px -16px 0 -16px);");
    expect(css).not.toMatch(/\.front-tab[^{]*\{[^}]*box-shadow/);

    expect(css).toContain('.front-tab[aria-selected="false"]:hover:not(:disabled) { border-radius: var(--radius-sm); }');
    expect(css).toMatch(/\.tabfold-panel \{[\s\S]*?background: var\(--card\)/);
  });
  it("the fold's timing matches the shared exit (lib/presence.ts) so the closing panel unmounts as it finishes", () => {
    expect(read("./presence.ts")).toContain("export const EXIT_MS = 220;");
    expect(read("../app/widgets.css")).toContain("--widget-ms: 220ms;");
    expect(read("../app/teasers.css")).toContain("tabfold-out var(--widget-ms, 220ms)");
  });
});
