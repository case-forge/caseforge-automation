import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SHELL = readFileSync(fileURLToPath(new URL("./Shell.tsx", import.meta.url)), "utf8");

describe("the header's Clients and Calendar buttons", () => {
  it("are two always-visible, icon-only buttons in one measured group, not one button that swaps", () => {
    expect(SHELL).toContain('className="header-view-switch" data-header-measure=""');
    expect(SHELL).toContain('onClick={() => onViewChange("search")}');
    expect(SHELL).toContain('onClick={() => onViewChange("calendar")}');
    expect(SHELL).not.toContain('onViewChange(view !== "search" ? "search" : "calendar")');
    expect(SHELL).not.toContain("header-view-label");
    expect(SHELL).toContain('title="Clients"');
    expect(SHELL).toContain('title="Calendar"');
  });

  it("mark the open view, give the Clients button a person and no magnifying glass, and keep both badges", () => {
    expect(SHELL).toContain('aria-current={view === "search" ? "page" : undefined}');
    expect(SHELL).toContain('aria-current={view === "calendar" ? "page" : undefined}');
    expect(SHELL).toContain("<IconPerson");
    expect(SHELL).toMatch(/\{clientReviewCount > 0 && \(/);
    expect(SHELL).toMatch(/\{reviewCount > 0 && \(/);
  });

  it("start each accessible name with the visible label", () => {
    expect(SHELL).toContain("clientsLabel(clientReviewCount)");
    expect(readFileSync(new URL("../lib/headerOverflow.ts", import.meta.url), "utf8")).toMatch(/`Clients, \$\{count\}/);
    expect(SHELL).toContain("calendarLabel(reviewCount)");
  });

  it("show both as rows in the apps menu when the header cannot hold them", () => {
    expect(SHELL).toMatch(/collapsed\.includes\("view"\)[\s\S]*Clients[\s\S]*Calendar/);
  });
});
