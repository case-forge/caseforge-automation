
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const banner = readFileSync(join(__dirname, "UpdateBanner.tsx"), "utf8");
const page = readFileSync(join(__dirname, "../components/Workspace.tsx"), "utf8");

describe("Refresh while an edit is open", () => {
  it("lists the unsaved forms from the shared tracker, each with Show me, in the banner (no alert)", () => {
    expect(banner).toContain("unsavedSources()");
    expect(banner).toContain("Unsaved: {describeUnsaved(source)}");
    expect(banner).toContain("onClick={() => onShow(source)}");
    expect(banner).toContain("Show me");
    expect(banner).not.toContain("window.alert");
  });

  it("says the edits are kept as drafts, then reloads without the browser's leave question", () => {
    expect(banner).toContain("Your unsaved edits are kept as drafts and come back when you open them again.");
    expect(banner).toContain("onClick={reloadKeepingDrafts}");
    expect(banner).toMatch(/if \(unsavedSources\(\)\.length === 0\) \{\s*reloadKeepingDrafts\(\);/);
  });

  it("Show me brings the form's own anchor into view, switching back to the search view when hidden", () => {
    expect(page).toContain("<UpdateBanner onShowUnsaved={showUnsaved} />");
    expect(page).toContain('[data-unsaved-source="${CSS.escape(source.id)}"]');
    expect(page).toContain('if (el.closest(".search-view"))');
  });
});

describe("session expiring soon", () => {
  it("is a plain warning that says roughly when, with no refresh instruction or button", async () => {
    const { sessionExpiringMessage } = await import("./UpdateBanner");
    expect(sessionExpiringMessage(Date.UTC(2026, 9, 22, 9, 48))).toMatch(/^Your session will expire soon, around \d\d:\d\d$/);
    expect(sessionExpiringMessage(null)).toBe("Your session will expire soon");
    expect(banner).not.toContain("Refresh to stay logged in");
    const warning = banner.slice(banner.indexOf('if (state === "session-expiring-soon")'), banner.indexOf("A new version is available"));
    expect(warning).not.toContain("<button");
  });

  it("shows the countdown in the banner, not in the header clock", () => {
    expect(banner).toContain("useSessionCountdown()");
    expect(banner).toContain('role="timer"');
    const clock = readFileSync(join(__dirname, "HeaderClock.tsx"), "utf8");
    expect(clock).not.toContain("Logging out");
    expect(clock).not.toContain("useSessionCountdown");
  });

  it("keeps the expired message as it was", () => {
    expect(banner).toContain("<strong>Your session has expired.</strong>");
    expect(banner).toContain("Reload the page to log in again.");
  });
});

describe("edit drafts follow the caseworker to another browser", () => {
  it("the Client tab and a hearing's edit mode keep a server copy", () => {
    expect(readFileSync(join(__dirname, "ClientEdits.tsx"), "utf8")).toMatch(/formId: "client-edit",\s+server: true/);
    expect(readFileSync(join(__dirname, "HearingDrawer.tsx"), "utf8")).toMatch(/formId: guardId,\s+server: true/);
  });
});
