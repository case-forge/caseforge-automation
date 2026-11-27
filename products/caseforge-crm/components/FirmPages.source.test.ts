
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { FirmPage } from "./FirmPage";
import { CLIENT_LISTS, listFromParam, listHref } from "../lib/clientLists";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

const PAGES = [
  { dir: "notification-board", view: "NotificationBoardPage", href: "/notification-board", wide: false },
  { dir: "scans", view: "ScansPage", href: "/scans", wide: true },
];

describe("firm-wide pages", () => {
  for (const p of PAGES) {
    it(`${p.href} renders its board inside the shared frame, with a title`, () => {
      const page = read(`../app/${p.dir}/page.tsx`);
      expect(page).toContain(`<${p.view} />`);
      expect(page).toContain(p.wide ? "<FirmPage wide>" : "<FirmPage>");
      expect(page).toMatch(/export const metadata = \{ title: "[A-Za-z() ]+" \}/);
      expect(page).not.toContain('"use client"');
    });
    it(`the apps menu opens ${p.href} in a new tab`, () => {
      const drawer = read("./AppDrawer.tsx");
      const at = drawer.indexOf(`href="${p.href}"`);
      expect(at).toBeGreaterThan(0);
      expect(drawer.slice(at, at + 120)).toContain('target="_blank" rel="noopener noreferrer"');
    });
  }

  it("the Client lists page holds every client list, each reachable by ?list=, and the menu links each", () => {
    expect(read("../app/client-lists/page.tsx")).toContain("<ClientLists initial=");
    expect(read("./AppDrawer.tsx")).toContain('<Link href="/client-lists"');
    expect(CLIENT_LISTS.map((l) => l.id)).toEqual([
      "to-check", "concluded", "flagged", "starred", "frequent-callers", "transferred", "dropped-out", "billed", "private",
      "duplicates", "removed", "merged", "waiting-client", "waiting-court", "waiting-counsel",
    ]);
    for (const l of CLIENT_LISTS) expect(listFromParam(l.id)).toBe(l.id);
    expect(listFromParam("nonsense")).toBe("to-check");
    expect(listFromParam(null)).toBe("to-check");
    expect(listHref("to-check")).toBe("/client-lists");
    expect(listHref("dropped-out")).toBe("/client-lists?list=dropped-out");
    expect(CLIENT_LISTS.find((l) => l.id === "waiting-court")?.flag).toBe("waiting_court");
  });

  it("every flag list is read through the flagged-matters route and shown as tabs", () => {
    const lists = read("./ClientLists.tsx");
    expect(lists).toContain("loadFlagList(list.flag");
    expect(lists).toContain("CLIENT_LISTS.map(");
  });

  it("Settings is a page of its own, linked from the menu, with a place to add sections", () => {
    expect(read("../app/settings/page.tsx")).toContain("<SettingsPage />");
    expect(read("./AppDrawer.tsx")).toContain('href="/settings"');
    expect(read("./AppDrawer.tsx")).not.toContain("settingsOpen");
    expect(read("./AppDrawer.tsx")).not.toContain("SettingsBox");
    expect(read("./SettingsPage.tsx")).toContain("const TABS");

    expect(read("./SettingsPage.tsx")).toContain('id: "system-health"');
    expect(read("./SettingsPage.tsx")).toContain("<SystemHealthPanel />");
    expect(existsSync(fileURLToPath(new URL("../app/system-health", import.meta.url)))).toBe(false);

    expect(read("./SettingsBox.tsx")).not.toContain("UpcomingPanel");
    expect(read("./Workspace.tsx")).not.toContain("useUpcomingPanel");
  });

  it("What's New is the home page card only: no menu entry, no page, no section on the Notification board", () => {
    expect(read("./FirmPageViews.tsx")).not.toContain("WhatsNew");
    expect(read("./AppDrawer.tsx")).not.toContain("whats-new");
    expect(read("./WhatsNew.tsx")).not.toContain("WhatsNewSection");
    expect(read("./WhatsNew.tsx")).toContain("storeSeen(currentEditorName(), newest)");
    expect(existsSync(fileURLToPath(new URL("../app/whats-new", import.meta.url)))).toBe(false);
    expect(read("../components/WidgetLayer.tsx")).toContain("<WhatsNewPanel />");
    expect(read("../app/layout.tsx")).toContain("<WidgetLayer />");
    expect(read("../components/Workspace.tsx")).not.toContain("<WhatsNewPanel />");
    expect(read("./AttentionBell.tsx")).toContain('href="/notification-board"');
  });

  it("the frame has a way back to the clients and a main landmark", () => {
    const html = renderToStaticMarkup(createElement(FirmPage, { wide: true, children: createElement("h1", null, "X") }));
    expect(html).toContain("<main");
    expect(html).toContain('class="firm-page firm-page--wide"');
    expect(html).toContain('href="/"');
    expect(html).toContain("Back to Home");
  });

  it("boards that pick a client open it at the client route in a new tab", () => {
    const views = read("./FirmPageViews.tsx");
    expect(views.match(/openClientInNewTab\(/g)!.length).toBeGreaterThanOrEqual(1);
    expect(read("../lib/clientLink.ts")).toContain('"_blank", "noopener,noreferrer"');
  });

  it("the client page keeps none of the moved views", () => {
    const page = read("../components/Workspace.tsx");
    for (const gone of ["CaseBoard", "ScansView", "NotificationBoardView", "AssignmentBoardView", "AssignmentBoardPage", "showConcluded", "loadMoreConcluded", "showClientReviewTab", "onClientReviewTab"]) {
      expect(page, gone).not.toContain(gone);
    }
    for (const file of ["./Shell.tsx", "./AppDrawer.tsx", "./AttentionBell.tsx"]) {
      expect(read(file), file).not.toMatch(/onShow(Board|Scans|Assignments|Notifications|ClientReview|Concluded)/);
    }
    expect(read("./Shell.tsx")).toContain('export type AppView = "search" | "calendar";');
  });

  it("an old ?view= bookmark is sent to the page that replaced it, and ?q= still selects a matter", () => {
    const page = read("../components/Workspace.tsx");
    expect(page).toContain("legacyViewPage(requested)");
    expect(page).toContain("window.location.replace(moved)");
    expect(page).toContain("parseClientLink(window.location.search)");
  });

  it("the Today board is the landing screen of the client page only: no /today page", () => {
    expect(existsSync(fileURLToPath(new URL("../app/today", import.meta.url)))).toBe(false);
    expect(read("../components/Workspace.tsx")).toContain("showTodayBoard(query, listSource, selectedMatch !== null)");
  });
});
