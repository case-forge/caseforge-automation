import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { categoryWords } from "../lib/notificationRules";
import { robotButtonLabel } from "../lib/robotNotices";

const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");

describe("notice kind labels are shown with a capital", () => {
  it("the New client pill and the Automation switch and notices read with a capital", () => {
    expect(categoryWords("new_client")).toBe("New client");
    expect(read("./NotificationRow.tsx")).toContain('<span className="attention-item-pill">New client</span>');
    expect(read("./NotificationBoard.tsx")).toContain('{ key: "robot", label: "Automation" }');
    expect(robotButtonLabel(2)).toMatch(/^Automation notices/);
  });
  it("no shown sentence about notices says automation notice(s) in lower case", () => {
    for (const file of ["./NotificationBoard.tsx", "../lib/notifications.ts", "./RobotNotices.tsx", "../lib/robotNotices.ts"]) {
      const shown = read(file).split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l));
      for (const line of shown) expect(line, file).not.toMatch(/\bautomation notices?\b/);
    }
  });
  it("the help tour calls the bell's new client entries New client", () => {
    expect(read("../lib/helpTour.ts")).toContain("New client notices");
  });
});
