import { describe, expect, it } from "vitest";
import { badgedTitle, isTailnetHost, tabTitle } from "./tabTitle";

const LIVE = "crm.example.test";

const TAILNET_ADDRESS = ["100", "64", "0", "1"].join(".");
const TAILNET = "box.example.ts.net:3010";

describe("tabTitle", () => {
  it("is plain Home on the live host, and pages keep their own title", () => {
    expect(tabTitle(false, LIVE)).toEqual({ default: "Home", template: "%s" });
    expect(tabTitle(false, null)).toEqual({ default: "Home", template: "%s" });
  });

  it("says Demo in stub mode on any non-tailnet host", () => {
    expect(tabTitle(true, "demo.example.test")).toEqual({ default: "Demo", template: "Demo %s" });
    expect(tabTitle(true, "localhost:3010")).toEqual({ default: "Demo", template: "Demo %s" });
  });

  it("puts Tailnet in front on a tailnet name or address", () => {
    expect(tabTitle(false, TAILNET)).toEqual({ default: "Tailnet Home", template: "Tailnet %s" });
    expect(tabTitle(true, `${TAILNET_ADDRESS}:3011`)).toEqual({ default: "Tailnet Demo", template: "Tailnet Demo %s" });
  });

  it("does not treat localhost or a look-alike as the tailnet", () => {
    expect(isTailnetHost("localhost:3010")).toBe(false);
    for (const host of ["ts.net.example.test", "1000.1.1.1", "100.1.1.1.example.com", "notlocalhost"]) {
      expect(isTailnetHost(host)).toBe(false);
    }
  });
});

describe("badgedTitle", () => {
  it("puts the unread count in front while it is above zero", () => {
    expect(badgedTitle("Home", 3)).toBe("(3) Home");
    expect(badgedTitle("Tailnet Demo", 12)).toBe("(12) Tailnet Demo");
  });
  it("replaces an earlier count and drops it at zero", () => {
    expect(badgedTitle("(3) Home", 5)).toBe("(5) Home");
    expect(badgedTitle("(3) Home", 0)).toBe("Home");
    expect(badgedTitle("Scans", 0)).toBe("Scans");
  });
});
