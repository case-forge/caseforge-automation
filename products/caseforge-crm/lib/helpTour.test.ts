import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { HEADER_HELP_STEPS, HELP_STEPS } from "./helpTour";

describe("help tour", () => {
  it("gives every step a title and an explanation, and only the welcome card has no target", () => {
    expect(HELP_STEPS.length).toBeGreaterThan(0);
    for (const step of HELP_STEPS) {
      expect(step.title.trim()).not.toBe("");
      expect(step.text.trim()).not.toBe("");
    }
    expect(HELP_STEPS.filter((s) => !s.selector)).toHaveLength(1);
  });

  it("explains every demo window and the window buttons", () => {
    const titles = HELP_STEPS.map((s) => s.title);
    for (const name of ["Demo", "Inbox", "Email", "Explorer", "Case flow"]) expect(titles).toContain(`Window: ${name}`);
    expect(titles).toContain("Moving the windows");
  });

  it("is offered in the apps menu in every mode, with no Demo Windows entry (the DEMO button shows and hides them)", () => {
    const menu = readFileSync(new URL("../components/AppDrawer.tsx", import.meta.url), "utf8");
    expect(menu).toContain("<HelpMenuEntry />");
    expect(menu).not.toContain("IS_DEMO && <HelpMenuEntry");
    expect(menu).not.toContain("Demo Windows");
  });

  it("replaces the clock with DEMO in stub mode", () => {
    const clock = readFileSync(new URL("../components/HeaderClock.tsx", import.meta.url), "utf8");
    expect(clock).toContain('process.env.NEXT_PUBLIC_CASEFORGE_DEMO === "1"');
    const config = readFileSync(new URL("../next.config.ts", import.meta.url), "utf8");
    expect(config).toContain("NEXT_PUBLIC_CASEFORGE_DEMO");
  });

  it("has no Help button in the header; outside the demo the menu's Help tours the header buttons", () => {
    const shell = readFileSync(new URL("../components/Shell.tsx", import.meta.url), "utf8");
    expect(shell).not.toContain("HelpMenuEntry");
    const tour = readFileSync(new URL("../components/HelpTour.tsx", import.meta.url), "utf8");
    expect(tour).toContain("IS_DEMO ? HELP_STEPS : HEADER_HELP_STEPS");
    expect(tour).not.toContain("header-help-button");

    for (const step of [...HELP_STEPS, ...HEADER_HELP_STEPS]) expect(step.selector ?? "").not.toContain("help");
    expect(tour).toContain("availableHelpSteps(document, true, list)");
    for (const step of HEADER_HELP_STEPS) {
      expect(step.title.trim()).not.toBe("");
      expect(step.text.length).toBeLessThan(200);
    }
  });

  it("says the logo returns to the Today folder and the Referral Info line opens the referral document", () => {
    const text = (title: string) => HEADER_HELP_STEPS.find((s) => s.title === title)?.text ?? "";
    expect(text("CaseForge logo")).toContain("Today folder");
    expect(text("Referral Info")).toMatch(/referral document/);
    expect(HEADER_HELP_STEPS.find((s) => s.title === "Referral Info")?.selector).toBeTruthy();
  });

  it("describes the one bell and the Notification board, and has no smiley or frowny step left", () => {
    for (const list of [HELP_STEPS, HEADER_HELP_STEPS]) {
      const titles = list.map((s) => s.title);
      expect(titles).not.toContain("Smiley");
      expect(titles).not.toContain("Frowny");
      expect(titles).toContain("Menu: Notification Board");
    }
    const bell = HEADER_HELP_STEPS.find((s) => s.title === "Notifications bell")?.text ?? "";
    expect(bell).toContain("last 3 days");
    expect(bell).toContain("Notification board");
    const board = HEADER_HELP_STEPS.find((s) => s.title === "Menu: Notification Board")?.text ?? "";
    for (const word of ["Active", "Dismissed", "Hidden", "7 days", "Automation"]) expect(board).toContain(word);
  });

  it("lights the applicant line and every apps-menu line, in both tours", () => {
    for (const list of [HELP_STEPS, HEADER_HELP_STEPS]) {
      const titles = list.map((s) => s.title);
      for (const t of ["Referral Info", "Menu: Case Flow Board", "Menu: Settings", "Menu: Home"]) expect(titles).toContain(t);
      for (const step of list.filter((s) => s.title.startsWith("Menu: "))) {
        expect(step.openMenu).toBe(true);
        expect(step.selector).toBeTruthy();
      }
    }
  });
});
