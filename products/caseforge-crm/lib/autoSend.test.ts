import { describe, expect, it } from "vitest";
import { clockLabel, groupItems, leavesLabel, minutesLeft, parseResponse, safeLink, stateLabel, tabLabel } from "./autoSend";
import type { AutoSendItem } from "./autoSend";

const NOW = new Date("2026-11-10T12:00:00Z");
const item = (over: Partial<AutoSendItem>): AutoSendItem => ({
  id: "x", matter_id: "1", client_name: "A", subject: "s", recipients: [], class: "c", state: "left",
  armed_utc: "", leaves_utc: "", sent_utc: "", stopped_utc: "", stopped_reason: "", body_text: "", outlook_link: "", sharepoint_link: "",
  ...over,
});

describe("minutesLeft and leavesLabel", () => {
  it("rounds up and never goes negative", () => {
    expect(minutesLeft("2026-11-10T12:02:30Z", NOW)).toBe(3);
    expect(minutesLeft("2026-11-10T11:50:00Z", NOW)).toBe(0);
    expect(minutesLeft("", NOW)).toBeNull();
  });
  it("words it", () => {
    expect(leavesLabel("2026-11-10T12:03:00Z", NOW)).toBe("Leaves in 3 min");
    expect(leavesLabel("2026-11-10T11:59:00Z", NOW)).toBe("Leaving now");
    expect(leavesLabel("", NOW)).toBe("");
  });
});

describe("groupItems", () => {
  it("splits by state, soonest first for leaving soon, newest first otherwise", () => {
    const g = groupItems([
      item({ id: "a", state: "leaving_soon", leaves_utc: "2026-11-10T12:10:00Z" }),
      item({ id: "b", state: "leaving_soon", leaves_utc: "2026-11-10T12:05:00Z" }),
      item({ id: "c", state: "left", sent_utc: "2026-11-10T09:00:00Z" }),
      item({ id: "d", state: "left", sent_utc: "2026-11-10T10:00:00Z" }),
      item({ id: "e", state: "cancelled", stopped_utc: "2026-11-10T08:00:00Z" }),
    ]);
    expect(g.leaving_soon.map((i) => i.id)).toEqual(["b", "a"]);
    expect(g.left.map((i) => i.id)).toEqual(["d", "c"]);
    expect(g.cancelled.map((i) => i.id)).toEqual(["e"]);
  });
});

describe("labels", () => {
  it("writes the clock in London time", () => {
    expect(clockLabel("2026-11-10T14:05:00Z")).toBe("10 Nov, 14:05");
    expect(clockLabel("nope")).toBe("");
  });
  it("reads a long hold (the court chaser, held to 08:00) as a clock time, not minutes", () => {
    const evening = new Date("2026-11-10T21:00:00Z");
    expect(stateLabel(item({ state: "leaving_soon", leaves_utc: "2026-11-11T08:00:00Z" }), evening)).toBe("Leaves tomorrow at 08:00");
    expect(stateLabel(item({ state: "leaving_soon", leaves_utc: "2026-11-10T23:00:00Z" }), evening)).toBe("Leaves at 23:00");
    expect(stateLabel(item({ state: "leaving_soon", leaves_utc: "2026-11-14T08:00:00Z" }), evening)).toBe("Leaves 14 Nov at 08:00");
    expect(stateLabel(item({ state: "leaving_soon", leaves_utc: "2026-11-10T22:15:00Z" }), evening)).toMatch(/^Leaves in 75 min/);
  });
  it("labels each state", () => {
    expect(stateLabel(item({ state: "leaving_soon", leaves_utc: "2026-11-10T12:03:00Z" }), NOW)).toBe("Leaves in 3 min, at 10 Nov, 12:03");
    expect(stateLabel(item({ state: "left", sent_utc: "2026-11-10T09:00:00Z" }), NOW)).toBe("Sent 10 Nov, 09:00");
    expect(stateLabel(item({ state: "cancelled", stopped_utc: "2026-11-10T09:00:00Z", stopped_reason: "Draft missing" }), NOW)).toBe("Draft missing, stopped 10 Nov, 09:00");
    expect(stateLabel(item({ state: "cancelled" }), NOW)).toBe("Cancelled");
  });
  it("puts the count in the tab", () => expect(tabLabel("Left", 4)).toBe("Left (4)"));
});

describe("safeLink and parseResponse", () => {
  it("keeps https links only", () => {
    expect(safeLink("https://x.test/a")).toBe("https://x.test/a");
    expect(safeLink("javascript:alert(1)")).toBe("");
    expect(safeLink("")).toBe("");
  });
  it("tolerates odd bodies", () => {
    expect(parseResponse(null)).toEqual([]);
    expect(parseResponse({ items: "no" })).toEqual([]);
    expect(parseResponse({ items: [{ state: "left" }, { state: "bogus" }, null] })).toHaveLength(1);
  });
});

import { DISMISS_HINT, canDismiss, dismissLabel, withoutDismissed } from "./autoSend";
import { autoSendBadge } from "./launcherBadges";

describe("dismissing a cancelled row", () => {
  const row = (id: string, state: "leaving_soon" | "left" | "cancelled", extra: Record<string, unknown> = {}) =>
    ({ id, matter_id: "1", client_name: "A", subject: `Subject ${id}`, recipients: [], class: "", state, armed_utc: "", leaves_utc: "", sent_utc: "", stopped_utc: "2026-11-01T08:00:00Z", stopped_reason: "", body_text: "", outlook_link: "", sharepoint_link: "", ...extra }) as never;
  it("only a cancelled row has Dismiss", () => {
    expect(canDismiss(row("1", "cancelled"))).toBe(true);
    expect(canDismiss(row("2", "leaving_soon"))).toBe(false);
    expect(canDismiss(row("3", "left"))).toBe(false);
  });
  it("a dismissed row (by the hub or just now here) is gone from the list and the group", () => {
    const items = [row("1", "cancelled"), row("2", "cancelled", { dismissed: true }), row("3", "cancelled")];
    expect(withoutDismissed(items, new Set(["3"])).map((i: { id: string }) => i.id)).toEqual(["1"]);
    expect(groupItems(items).cancelled.map((i) => i.id).sort()).toEqual(["1", "3"]);
  });
  it("dismissed rows count for neither the badge count nor its fill", () => {
    const now = new Date("2026-11-01T09:00:00Z");
    expect(autoSendBadge([row("1", "cancelled", { dismissed: true }), row("2", "leaving_soon")], now)).toMatchObject({ tone: "accent", count: 1 });
    expect(autoSendBadge([row("1", "cancelled", { dismissed: true })], now)).toBeNull();
  });
  it("says what it does", () => {
    expect(dismissLabel("Subject 1")).toBe("Dismiss Subject 1");
    expect(DISMISS_HINT).toBe("Hides this row. The draft in Outlook is not touched.");
  });
});
