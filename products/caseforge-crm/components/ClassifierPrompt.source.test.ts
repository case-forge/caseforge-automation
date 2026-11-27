import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const prompt = readFileSync(new URL("./ClassifierPrompt.tsx", import.meta.url), "utf8");

describe("the classifier prompt", () => {
  it("closes by the red light of the shared title bar, which also holds the C/R badge and the question mark", () => {
    expect(prompt).toContain("<CardBar");
    expect(prompt).toContain("onClose={closeCard}");
    expect(prompt).toContain("<IconHelp");
    expect(prompt).toContain("classifier-badge--");
    expect(prompt).not.toMatch(/[×✕✖]/);
  });
  it("is titled Help improve email classifier, always the one full title, never shortened", () => {
    expect(prompt).toContain('title="Help improve email classifier"');
    expect(prompt).not.toContain("titleFallbacks");
    expect(prompt).not.toContain("Improve classifier\"]");
    expect(prompt).not.toContain("A quick question about our email");
  });
  it("has no mute, points to Settings for off for good, and links to the email itself", () => {
    expect(prompt).not.toContain("Mute for");
    expect(prompt).not.toContain("muteUntil");
    expect(prompt).toContain("Turn these off");
    expect(prompt).toContain("safeEmailLink(item.weblink)");
  });
  it("shows From, To, Cc (when there is one) and Subject, and its three actions are one size of button", () => {
    for (const label of ["From", "To", "Cc", "Subject"]) expect(prompt).toContain(`classifier-prompt-label">${label}</span>`);
    expect(prompt).toContain("{item.cc && (");
    expect(prompt).not.toContain("Check more mail<span");
    expect(prompt).toContain("Check more mail");
    expect(prompt.match(/cf-btn cf-btn--neutral cf-btn--small/g)?.length).toBeGreaterThanOrEqual(3);
  });
  it("closes, presses Escape and says Not today in one way, and gives the email back", () => {
    expect(prompt).toContain("onClose={closeCard}");
    expect(prompt).toContain('e.key === "Escape" && item) dismiss()');
    expect(prompt).toContain("holdAfterClose(Date.now())");
    expect(prompt).toContain("holdAfterNotToday(Date.now())");
    expect(prompt).toContain("onClick={notToday}");
    expect(prompt).toContain("Close (asks again in an hour)");
    expect(prompt).toContain('action: "control_release"');
  });
  it("never asks on its own when the setting is off, but still opens when the menu asks", () => {
    expect(prompt).toContain("if (!enabled) return;");
    expect(prompt).toContain("!classifierPromptsOn()");
    expect(prompt).toContain('if (!consumeRequest("classifier")) return;');
    expect(prompt).toContain("const shownNow = !!(item || thanks || empty);");
  });
  it("turns the questions off or on from the card itself; off closes the card", () => {
    expect(prompt).toContain("onClick={toggleEnabled}");
    expect(prompt).toContain('enabled ? "Turn these off" : "Turn these on"');
    expect(prompt).toMatch(/if \(enabled\) \{\s+setEnabled\(false\);\s+dismiss\(\);/);
  });
});

describe("the classifier prompt and the corner", () => {
  it("no longer waits for What's new, opens on a menu request, and explains why it asks", () => {
    expect(prompt).not.toContain("isWhatsNewOpen");
    expect(prompt).toContain('useOpenRequests("classifier")');
    expect(prompt).toContain("Why am I being asked?");
  });
});
