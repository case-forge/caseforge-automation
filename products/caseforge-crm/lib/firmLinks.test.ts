import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildFirmLinks, FIRM_LINKS, isTailnetOnly, logoSrc } from "./firmLinks";

const here = (rel: string) => fileURLToPath(new URL(rel, import.meta.url));
const read = (rel: string) => readFileSync(here(rel), "utf8");

describe("firmLinks", () => {
  it("is the services the system runs on and nothing else (the apps are in the apps menu)", () => {
    expect(buildFirmLinks(undefined).map((l) => l.label)).toEqual(["Cloudflare", "GitHub", "OpenRouter", "Tailscale", "GlitchTip", "Healthchecks.io", "Claude", "Claude API", "Entra", "App registrations", "Azure"]);
  });

  it("has no built-in address for the self-hosted Healthchecks tile, so no deployment links to another's box", () => {
    expect(FIRM_LINKS.map((l) => l.label)).not.toContain("Healthchecks");
    expect(read("./firmDefaults.ts")).not.toMatch(/healthchecks:/);
  });

  it("opens OpenRouter on its activity page", () => {
    expect(FIRM_LINKS.find((l) => l.label === "OpenRouter")?.href).toBe("https://openrouter.ai/workspaces/default/activity");
  });

  it("has the Umami tile only when its address is set, and only for an http(s) address", () => {
    for (const unset of [undefined, "", "  ", "javascript:alert(1)", "not a url"]) {
      expect(buildFirmLinks(unset).map((l) => l.label)).not.toContain("Umami");
    }
    const set = buildFirmLinks("https://stats.example.org");
    expect(set.map((l) => l.label)).toEqual([...["Cloudflare", "GitHub", "OpenRouter", "Tailscale", "GlitchTip", "Healthchecks.io", "Claude", "Claude API", "Entra", "App registrations", "Azure"], "Umami"]);
    expect(set[set.length - 1]).toMatchObject({ href: "https://stats.example.org", description: "Website and app analytics", logo: "umami.svg", mono: true });
  });

  it("has a label, an absolute address and a description for every link, none twice", () => {
    for (const l of FIRM_LINKS) {
      expect(l.description.length).toBeGreaterThan(0);
      expect(() => new URL(l.href)).not.toThrow();
    }
    expect(new Set(FIRM_LINKS.map((l) => l.href)).size).toBe(FIRM_LINKS.length);
    expect(new Set(FIRM_LINKS.map((l) => l.label)).size).toBe(FIRM_LINKS.length);
  });

  it("marks 100.x and ts.net addresses as tailnet only, and nothing else", () => {
    expect(isTailnetOnly(`http://${["100", "64", "0", "1"].join(".")}:8140`)).toBe(true);
    expect(isTailnetOnly("http://box.example.ts.net:8000")).toBe(true);
    expect(isTailnetOnly("https://openrouter.ai")).toBe(false);
    expect(isTailnetOnly("https://example.com/ts.net")).toBe(false);
    expect(isTailnetOnly("not a url")).toBe(false);

    for (const link of FIRM_LINKS.filter((l) => isTailnetOnly(l.href))) expect(["GlitchTip", "Healthchecks"]).toContain(link.label);
  });

  it("serves every logo from a static file in public/, never from another host, and each is in NOTICE", () => {
    const notice = readFileSync(here("../../../NOTICE"), "utf8");
    for (const l of buildFirmLinks("https://stats.example.org").filter((x) => x.logo)) {
      expect(logoSrc(l)).toMatch(/^\/link-logos\/[a-z]+\.svg$/);
      expect(existsSync(here(`../public${logoSrc(l)}`)), l.label).toBe(true);
      expect(notice, l.label).toContain(l.logo as string);
      const svg = readFileSync(here(`../public${logoSrc(l)}`), "utf8");
      expect(svg).not.toMatch(/https?:\/\/(?!www\.w3\.org)/);
    }
  });
});

describe("FirmLinksPanel and the Links tab", () => {
  const panel = read("../components/FirmLinksPanel.tsx");
  it("opens every link in a new tab without opener or referrer", () => {
    expect(panel).toContain('target="_blank"');
    expect(panel).toContain('rel="noopener noreferrer"');
  });
  it("is dev mode only (the services the system runs on); Special senders stays shown to everyone", () => {
    const page = read("../components/SettingsPage.tsx");
    expect(page).toContain('{ id: "links", title: "Links", body: <FirmLinksPanel />, devOnly: true }');
    expect(page).toContain('{ id: "special-senders", title: "Special Senders", body: <SpecialSendersPanel />, devOnly: true }');
  });
  it("draws the first letter on a chip for a link with no logo of its own", () => {
    expect(panel).toContain("firm-link-icon--letter");
    expect(panel).toContain("link.label.charAt(0)");
    expect(FIRM_LINKS.filter((l) => !l.logo).map((l) => l.label)).toEqual([]);
    expect(FIRM_LINKS.filter((l) => ["cloud.svg", "grid.svg", "shield.svg"].includes(l.logo ?? "")).map((l) => l.label)).toEqual(["Entra", "App registrations", "Azure"]);
  });
});
