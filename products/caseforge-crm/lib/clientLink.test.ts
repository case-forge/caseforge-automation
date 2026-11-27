import { describe, expect, it } from "vitest";
import { clientHref, legacyViewPage, parseClientLink } from "./clientLink";

describe("clientHref", () => {
  it("searches by name alone when the matter is unknown", () => {
    expect(clientHref("  Jo Bloggs ")).toBe("/clients?q=Jo+Bloggs");
  });
  it("carries the matter, tab and hearing", () => {
    expect(clientHref("Jo Bloggs", { matterId: "614", tab: "hearings", hearingId: 7 })).toBe("/clients/614/hearings?q=Jo+Bloggs&hearing=7");
  });
  it("drops tab and hearing without a matter", () => {
    expect(clientHref("Jo", { tab: "caseflow" })).toBe("/clients?q=Jo");
  });
});

describe("parseClientLink", () => {
  it("reads the older /?q=..&matter=..&tab=.. link", () => {
    const href = "/?q=Ann+O%27Neil&matter=9&tab=caseflow";
    expect(parseClientLink(href.slice(1))).toEqual({ query: "Ann O'Neil", target: { matterId: "9", tab: "caseflow", hearingId: undefined } });
  });
  it("ignores a tab that does not exist and a matter that is not a number", () => {
    expect(parseClientLink("?q=A&matter=5&tab=nope").target?.tab).toBeUndefined();
    expect(parseClientLink("?q=A&matter=abc").target).toBeNull();
  });
  it("has no target without a name", () => {
    expect(parseClientLink("?matter=5")).toEqual({ query: "", target: null });
  });
});

describe("legacyViewPage", () => {
  it("sends the three moved views to their pages, and the retired board view nowhere", () => {
    expect(legacyViewPage("board")).toBeNull();
    expect(legacyViewPage("scans")).toBe("/scans");
    expect(legacyViewPage("notifications")).toBe("/notification-board");
    expect(legacyViewPage("calendar")).toBeNull();
    expect(legacyViewPage(null)).toBeNull();
  });
});
