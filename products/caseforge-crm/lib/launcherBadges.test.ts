import { describe, expect, it } from "vitest";
import { tabsBadge, CANCELLED_BADGE_WINDOW_MS, autoSendBadge, badgedName, recentlyStopped, wetransferBadge, whatsNewTodayBadge } from "./launcherBadges";
import type { AutoSendItem } from "./autoSend";

const mail = (state: AutoSendItem["state"], stopped = ""): AutoSendItem => ({
  id: "1", matter_id: "1", client_name: "A", subject: "", recipients: [], class: "", state,
  armed_utc: "", leaves_utc: "", sent_utc: "", stopped_utc: stopped, stopped_reason: "", body_text: "", outlook_link: "", sharepoint_link: "",
});

describe("Status Board badge", () => {
  it("counts the WeTransfer clients and is off at zero", () => {
    expect(wetransferBadge([{ wetransfer_pending: true }, { wetransfer_pending: false }, {}, { wetransfer_pending: true }])?.count).toBe(2);
    expect(wetransferBadge([{}, { wetransfer_pending: false }])).toBeNull();
  });
});

describe("Auto Send badge", () => {
  const now = new Date("2026-11-01T09:00:00Z");
  it("orange beats yellow, and shows the cancelled count", () => {
    const b = autoSendBadge([mail("leaving_soon"), mail("leaving_soon"), mail("cancelled", "2026-11-01T08:00:00Z")], now);
    expect(b).toMatchObject({ tone: "solid", count: 1 });
  });
  it("yellow with the leaving-soon count when nothing is cancelled", () => {
    expect(autoSendBadge([mail("leaving_soon"), mail("leaving_soon"), mail("left")], now)).toMatchObject({ tone: "accent", count: 2 });
  });
  it("left emails and nothing at all give no badge", () => {
    expect(autoSendBadge([mail("left")], now)).toBeNull();
    expect(autoSendBadge([mail("blocked", "2026-11-01T08:00:00Z"), mail("blocked")], now)).toBeNull();
    expect(autoSendBadge([mail("blocked"), mail("leaving_soon")], now)).toMatchObject({ tone: "accent", count: 1 });
    expect(autoSendBadge([], now)).toBeNull();
  });
  it("a cancelled email counts for 24 hours only, across month and year boundaries", () => {
    expect(CANCELLED_BADGE_WINDOW_MS).toBe(86_400_000);
    expect(recentlyStopped(mail("cancelled", "2026-10-31T09:30:00Z"), now)).toBe(true);
    expect(recentlyStopped(mail("cancelled", "2026-10-31T08:59:00Z"), now)).toBe(false);
    expect(recentlyStopped(mail("cancelled", "2025-12-31T23:00:00Z"), new Date("2026-01-02T23:30:00Z"))).toBe(false);
    expect(recentlyStopped(mail("cancelled", "2025-12-31T23:00:00Z"), new Date("2026-01-01T09:00:00Z"))).toBe(true);
    expect(recentlyStopped(mail("cancelled", ""), now)).toBe(false);
  });
  it("an old stop does not hide a leaving-soon badge", () => {
    expect(autoSendBadge([mail("cancelled", "2026-09-30T08:00:00Z"), mail("leaving_soon")], now)).toMatchObject({ tone: "accent", count: 1 });
  });
});

describe("What's New badge", () => {
  it("counts notes dated today in London, across a London midnight", () => {

    const now = new Date("2026-06-06T10:00:00Z");
    const items = [{ date: "2026-06-05T23:30:00Z" }, { date: "2026-06-06" }, { date: "2026-06-05T22:00:00Z" }, { date: "nonsense" }];
    expect(whatsNewTodayBadge(items, now)?.count).toBe(2);
  });
  it("is off when none is today, including the day before in September and November", () => {
    expect(whatsNewTodayBadge([{ date: "2026-09-30" }], new Date("2026-10-01T12:00:00Z"))).toBeNull();
    expect(whatsNewTodayBadge([{ date: "2026-10-31" }], new Date("2026-11-01T12:00:00Z"))).toBeNull();
    expect(whatsNewTodayBadge([{ date: "2026-11-01" }], new Date("2026-11-01T12:00:00Z"))?.count).toBe(1);
  });
});

describe("accessible name", () => {
  it("includes the count and the meaning", () => {
    expect(badgedName("Auto Send", autoSendBadge([mail("cancelled", "2026-11-01T08:00:00Z"), mail("cancelled", "2026-11-01T08:30:00Z")], new Date("2026-11-01T09:00:00Z")))).toBe("Auto Send, 2 cancelled");
    expect(badgedName("Auto Send", null)).toBe("Auto Send");
  });
});

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

describe("badge colours in the stylesheet", () => {
  const css = readFileSync(fileURLToPath(new URL("../app/teasers.css", import.meta.url)), "utf8");
  const base = readFileSync(fileURLToPath(new URL("../app/windows.css", import.meta.url)), "utf8");
  it(".window-count.window-count--solid sets a background and colour that differ from the base badge, and out-ranks it", () => {
    const rule = css.match(/\.window-count\.window-count--solid \{([^}]*)\}/);
    expect(rule, "a doubled selector, so the base .window-count rule cannot win").not.toBeNull();
    const bg = rule![1].match(/background: ([^;]+);/)?.[1];
    expect(bg).toBeTruthy();
    expect(rule![1]).toMatch(/color:/);
    expect(base.match(/\.window-count \{[^}]*background: ([^;]+);/)![1]).not.toBe(bg);
  });
  it("leaving soon adds no colour rule, and the amber, red, yellow and orange modifiers are gone", () => {
    expect(css).not.toMatch(/window-count--(soon|cancelled)/);
    expect(css).not.toContain("--as-badge");
  });
});

describe("Add a Hearing badge", () => {
  it("shows the number of open tabs, none at zero", () => {
    expect(tabsBadge(0)).toBeNull();
    expect(badgedName("Add a Hearing", tabsBadge(1))).toBe("Add a Hearing, 1 open tab");
    expect(badgedName("Add a Hearing", tabsBadge(3))).toBe("Add a Hearing, 3 open tabs");
  });
});
