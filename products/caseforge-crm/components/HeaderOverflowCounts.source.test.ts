import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");

describe("the Clients and Calendar menu entries carry their header counts", () => {
  it("both entries show the badge pill from the same counts as the header buttons, with the same accessible name", () => {
    const shell = read("./Shell.tsx");
    expect(shell).toContain("showsCount(clientReviewCount)");
    expect(shell).toContain("showsCount(reviewCount)");
    expect(shell).toContain("aria-label={clientsName}");
    expect(shell).toContain("aria-label={calendarName}");
  });
  it("the bell, Tasks, Automation notices and New client entries pass their counts", () => {
    expect(read("./AttentionBell.tsx")).toContain("count={total}");
    expect(read("./TodoHeader.tsx")).toContain("count={attention}");
    expect(read("./RobotNotices.tsx")).toContain("count={count}");
    expect(read("./NewClientButton.tsx")).toContain("count={waiting}");
  });
  it("Flagged, Starred and Client Lists show (n) in the menu", () => {
    const drawer = read("./AppDrawer.tsx");
    expect(drawer).toContain("(${count})");
    expect(drawer).toContain("(${clientReviewCount})");
  });
});
