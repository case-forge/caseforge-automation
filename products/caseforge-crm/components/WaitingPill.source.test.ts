import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (name: string) => readFileSync(new URL(name, import.meta.url), "utf8");

describe("the waiting pill is placed where the owner asked", () => {
  it("is not on the Case Flow tab at all: who we wait on is on the Today board", () => {
    const tab = read("./CaseFlowTab.tsx");
    expect(tab).not.toContain("<WaitingPill");
    expect(tab).not.toContain("cf2-waiting");
  });

  it("has a Client Lists entry for each state, and is plain text on the Today board", () => {
    expect(read("../lib/clientLists.ts")).toContain("...WAITING_LISTS.map");
    expect(read("./TodayBoard.tsx")).not.toContain("<WaitingPill");
  });

  it("is among the last two sections of the Today board", () => {

    expect(read("../lib/todayBoard.ts")).toContain('"waiting_court"');
  });
});
