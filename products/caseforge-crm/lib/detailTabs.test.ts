import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { carriedTab, drawerSwitchTab, landingTab, tabCount } from "./detailTabs";

describe("landing on the Hearings and Updates tabs", () => {
  it("sends each link to its own tab", () => {
    expect(landingTab("updates")).toBe("updates");
    expect(landingTab("hearings")).toBe("hearings");
  });

  it("leaves every other landing where it was", () => {
    expect(landingTab("attendance")).toBe("attendance");
    expect(landingTab("caseflow")).toBe("caseflow");
  });

  it("opens a client from a Calendar hearing, and from the Today board, on the Hearings tab at that hearing", () => {
    const page = readFileSync(fileURLToPath(new URL("../components/Workspace.tsx", import.meta.url)), "utf8");
    const fromHearing = page.slice(page.indexOf("function openClientFromHearing"), page.indexOf("function openClientByName"));
    expect(fromHearing).toContain('openClientByName(key, { matterId: String(hearing.matter_id), tab: "hearings", hearingId: hearing.hearing_id })');
    expect(page).toContain("openClientByName(name, matterId ? { matterId, tab, hearingId } : undefined)");

    expect(page).toContain("hearingId: target?.hearingId");
    expect(page).toContain("hearingId: pendingOpen.hearingId");
  });
});

describe("a tab's count", () => {
  it("is nothing at zero", () => {
    expect(tabCount("Hearings", 0, "upcoming hearing", "upcoming hearings")).toEqual({ count: 0 });
  });

  it("is a number with the noun in words", () => {
    expect(tabCount("Hearings", 2, "upcoming hearing", "upcoming hearings")).toEqual({ count: 2, ariaLabel: "Hearings, 2 upcoming hearings" });
    expect(tabCount("Updates", 1, "open update", "open updates")).toEqual({ count: 1, ariaLabel: "Updates, 1 open update" });
  });
});

describe("the tab carries over from client to client", () => {
  const MAIN = ["client", "details", "caseflow", "attendance", "todo"] as const;
  const EXTRA = ["vergil", "scanner", "billing", "hearings"] as const;
  const ALL = [...MAIN, ...EXTRA];

  it("opens the next client on the tab the last one was on", () => {
    expect(carriedTab("caseflow", ALL)).toBe("caseflow");
    expect(carriedTab("attendance", ALL)).toBe("attendance");
    expect(carriedTab("billing", ALL)).toBe("billing");
  });

  it("falls back to the leftmost tab when there was none, or this client has no such tab", () => {
    expect(carriedTab(null, ALL)).toBe("client");
    expect(carriedTab(undefined, ALL)).toBe("client");
    expect(carriedTab("caseflow", ["client", "details"])).toBe("client");
  });

  it("the Extra details switch returns to the last tab used on the page it opens, not the leftmost", () => {
    expect(drawerSwitchTab({ onExtraPage: true, lastMain: "caseflow", lastExtra: "billing", mainTabs: MAIN, extraTabs: EXTRA })).toBe("caseflow");
    expect(drawerSwitchTab({ onExtraPage: false, lastMain: "caseflow", lastExtra: "billing", mainTabs: MAIN, extraTabs: EXTRA })).toBe("billing");
  });

  it("the switch falls back to its page's first tab when nothing was used there yet", () => {
    expect(drawerSwitchTab({ onExtraPage: true, lastMain: null, lastExtra: "billing", mainTabs: MAIN, extraTabs: EXTRA })).toBe("client");
    expect(drawerSwitchTab({ onExtraPage: false, lastMain: "details", lastExtra: null, mainTabs: MAIN, extraTabs: EXTRA })).toBe("vergil");
  });

  it("DetailPanel starts on the carried tab and the switch uses drawerSwitchTab, never a hard-coded \"client\"", () => {
    const panel = readFileSync(fileURLToPath(new URL("../components/DetailPanel.tsx", import.meta.url)), "utf8");
    expect(panel).toMatch(/useState<FixedTab>\(\(\) => carriedTab\(tabMemory\.tab, ALL_IDS\)\)/);
    expect(panel).toMatch(/setDetailTab\(drawerSwitchTab\(\{/);
    expect(panel).not.toMatch(/setDetailTab\(onExtraPage \? "client"/);
  });
});
