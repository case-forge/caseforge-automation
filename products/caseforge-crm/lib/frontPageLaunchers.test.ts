import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { LAUNCHERS, visibleLaunchers } from "./frontPageLaunchers";
import { availableTeasers, parseChoice, serialiseChoice, toggleShown, visibleTeasers } from "./frontPageTeasers";
import { consumeRequest, isClosed, markClosed, requestOpen } from "./cornerPrompts";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

const OWNER: Record<string, string> = {
  hearings: "../components/GlobalHearings.tsx",
  "whats-new": "../components/WhatsNew.tsx",
  classifier: "../components/ClassifierPrompt.tsx",
  "add-hearing": "../components/WidgetBox.tsx",
};

describe("front page launchers", () => {
  it("names the launchers in Title Case, each opening its own window, Add a Hearing last", () => {
    expect(LAUNCHERS.map((l) => [l.label, l.window])).toEqual([
      ["Hearings Panel", "hearings"],
      ["What's New", "whats-new"],
      ["Improve Classifier", "classifier"],
      ["Add a Hearing", "add-hearing"],
    ]);
  });
  it("always offers the Hearings Panel: there is no setting for it, only the cog's switch", () => {
    expect(visibleLaunchers([])).toHaveLength(4);
    expect(visibleLaunchers([]).map((l) => l.id)).toContain("hearings");
    expect(visibleLaunchers(["whats-new"]).map((l) => l.id)).toEqual(["hearings", "classifier", "add-hearing"]);
  });
  it("the Hearings Panel setting is gone: nothing reads or writes the old preference", () => {
    for (const file of ["../components/Workspace.tsx", "../components/GlobalHearings.tsx", "../components/FrontPageTeasers.tsx", "../components/SettingsBox.tsx", "../components/UpcomingRail.tsx", "./frontPageLaunchers.ts", "./useHearings.ts"]) {
      const code = read(file);
      expect(code, file).not.toMatch(/useUpcomingPanel|upcoming-panel|UPCOMING_PANEL|upcomingPanel/);
    }
  });
  it("pressing a launcher toggles its window (a second press closes it) and aria-expanded follows", () => {
    const src = read("../components/FrontPageTeasers.tsx");
    expect(src).toContain("toggleWindow(l.window)");
    expect(src).toContain("aria-expanded={showing}");
  });
  it("the cog lists seven items: the Status Board, Auto Send, Court Prep and the four launchers, each with a switch", () => {
    const ids = [...availableTeasers().map((t) => t.id), ...LAUNCHERS.map((l) => l.id)];
    expect(ids).toEqual(["status-board", "auto-sent", "court-prep", "hearings", "whats-new", "classifier", "add-hearing"]);
    const row = read("../components/FrontPageTeasers.tsx");
    expect(row).toContain("LAUNCHERS.map((l) => (");
    expect(row).toContain("toggleShown(choice, l.id)");
  });
  it("an old saved choice still works, new items default to shown, and a launcher can be switched off and back", () => {
    const old = parseChoice('{"hidden":["status-board"],"open":""}');
    expect(visibleTeasers(old).map((t) => t.id)).toEqual(["auto-sent", "court-prep"]);
    expect(visibleLaunchers(old.hidden)).toHaveLength(4);
    const off = toggleShown(parseChoice(null), "classifier");
    expect(visibleLaunchers(parseChoice(serialiseChoice(off)).hidden).map((l) => l.id)).toEqual(["hearings", "whats-new", "add-hearing"]);
    expect(visibleLaunchers(toggleShown(off, "classifier").hidden)).toHaveLength(4);

    expect(visibleLaunchers(parseChoice('{"hidden":["whats-new"],"open":""}').hidden).map((l) => l.id)).toContain("add-hearing");
  });
  it("a request reopens a window that was closed, and is acted on once", () => {
    markClosed("whats-new");
    expect(isClosed("whats-new")).toBe(true);
    requestOpen("whats-new");
    expect(isClosed("whats-new")).toBe(false);
    expect(consumeRequest("whats-new")).toBe(true);
    expect(consumeRequest("whats-new")).toBe(false);
  });
  it("every launcher has a window that listens for it, so none does nothing", () => {
    for (const launcher of LAUNCHERS) {
      const owner = OWNER[launcher.window];
      expect(owner, `no owner listed for ${launcher.window}`).toBeTruthy();

      expect(owner.endsWith("WidgetBox.tsx") ? read(owner) : read(owner)).toContain(owner.endsWith("WidgetBox.tsx") ? "consumeRequest(corner)" : `consumeRequest("${launcher.window}")`);
    }
  });
});

describe("Add a Hearing has one way in", () => {
  it("the launcher and every existing entry point (calendar button, client Hearings tab, attendance note) open the same box through the host", () => {
    for (const f of ["../components/CalendarView.tsx", "../components/MatterHearings.tsx", "../components/AttendanceNoteForm.tsx"]) expect(read(f), f).toContain("hearingsHost.openCreate(");
    expect(read("./hearingsHost.ts")).toContain('requestOpen("add-hearing")');
    expect(read("../components/AddHearingBox.tsx")).toContain('corner="add-hearing"');
  });
});
