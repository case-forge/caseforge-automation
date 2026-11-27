
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const path = (rel: string) => fileURLToPath(new URL(rel, import.meta.url));
const read = (rel: string) => readFileSync(path(rel), "utf8");

describe("server-backed Settings tabs", () => {
  const panel = read("./SettingsGroupPanel.tsx");
  it("draws each field from the schema and keeps secrets out", () => {
    for (const type of ['"bool"', '"enum"', 'type={setting.type === "email" ? "email" : "text"}']) expect(panel).toContain(type);
    expect(panel).not.toMatch(/type="password"/);
    expect(panel).toContain("view.secrets_note");
  });
  it("shows an environment pin as read-only with the variable named", () => {
    expect(panel).toContain("Set by environment ({env})");
    expect(panel).toContain("<IconLock");
    expect(panel).toMatch(/disabled=\{!canEdit \|\| s\.locked \|\| !s\.writable \|\| saving\}/);
  });
  it("has one Save per tab that sends only what changed, and says when a restart is needed", () => {
    expect(panel.match(/>\s*\{saving \? "Saving" : "Save"\}/g)).toHaveLength(1);
    expect(panel).toContain("saveSettings(values)");
    expect(panel).toContain("Programs already running use the old value until they are restarted.");
    expect(panel).toMatch(/settings\.some\(\(s\) => s\.writable\) && canEdit/);
  });
  it("shows a refusal beside its field, or above Save when it is about the whole save", () => {
    expect(panel).toContain("fieldForError(result.message, settings)");
    expect(panel).toContain('className="settings-field-error" role="alert"');
  });
  it("makes the instructing solicitor a choice from an editable list, changed with Edit and the tab's Save", () => {
    expect(panel).toContain('setting.type === "person_choice"');
    expect(panel).toContain("options.map((c)");
    expect(panel).toContain("Add a solicitor");
    expect(panel).toMatch(/onClick=\{\(\) => setEditing\(true\)\}[\s\S]*Edit\n/);
    expect(panel).toContain("draft.length < 2");
  });
  it("has no double hyphen or em dash in on-screen text", () => {
    const text = [...panel.matchAll(/>\s*([A-Za-z][^<>{}]*?)\s*</g)].map((m) => m[1]).join("\n") + [...panel.matchAll(/"([A-Z][^"]*)"/g)].map((m) => m[1]).join("\n");
    expect(text).not.toMatch(/--|—/);
  });
});

describe("the tab icon colour lock is a Windows-tab setting, not a dot", () => {
  it("leaves no dot in the box, the styles, the helpers or the icon component", () => {
    expect(existsSync(path("./FaviconDot.source.test.ts"))).toBe(false);
    for (const file of ["./SettingsBox.tsx", "./FaviconColour.tsx", "../lib/favicon.ts", "../app/globals.css"]) {
      expect(read(file)).not.toMatch(/FaviconLockDot|favicon-dot|theme-toggle-wrap|FAVICON_LOCK_KEY|pressedLock|lockDotTip/);
    }
  });
  it("is kept in the browser: the hub has no tab icon or logo setting", () => {
    const registry = readFileSync(fileURLToPath(new URL("../../../tools/app_settings.py", import.meta.url)), "utf8");
    expect(registry).not.toMatch(/favicon_enabled|logo_hash/);
    expect(registry).toContain('_s("theme_lock", "branding", "enum"');
    expect(read("./SettingsBox.tsx")).toContain("useFaviconLock");
  });
});

describe("the layout has no branding settings", () => {
  const layout = read("../app/layout.tsx");
  it("always names the CaseForge icons and always runs the theme bootstrap", () => {
    expect(layout).toContain('icons: { icon: [{ url: "/brand-favicon.ico" }, { url: "/brand-icon.svg", type: "image/svg+xml" }] }');
    expect(layout).toContain("<FaviconColour />");
    expect(layout).not.toMatch(/forced|themeLock|loadBranding|BrandingProvider/);
    expect(existsSync(path("../app/favicon.ico"))).toBe(false);
    expect(existsSync(path("../public/brand-icon.svg"))).toBe(true);
  });
  it("lets the client change the theme with nothing to lock it", () => {
    expect(read("./ThemeToggle.tsx")).not.toContain("data-theme-locked");
  });
  it("shows only the built-in marks in the header, and has no logo upload or logo route", () => {
    const shell = read("./Shell.tsx");
    expect(shell).toContain("/caseforge-mark-dark.svg");
    expect(shell).not.toMatch(/logoSrc|useBranding/);
    expect(existsSync(path("../app/api/settings/logo/route.ts"))).toBe(false);
    expect(existsSync(path("../lib/branding.ts"))).toBe(false);
    expect(read("./SettingsPage.tsx")).not.toContain("branding");
  });
});

describe("every administrator write carries the Access identity to the hub", () => {
  it("sends through the shared proxy helpers, which forward the verified assertion, never a hand-built Remote-User header", () => {
    for (const file of ["../app/api/settings/minutes-per-page/route.ts", "../app/api/settings/scanned-docs-folder/route.ts"]) {
      const source = read(file);
      expect(source).toContain('hubPostJson(request, HUB_PATH,');
      expect(source).toContain('"PUT"');
      expect(source).not.toContain('"Remote-User"');
    }
    expect(read("../app/api/settings/route.ts")).toContain('hubPostJson(request, HUB_PATH, { values }, remoteUser, {}, "PATCH")');
    expect(read("../app/api/settings/models/route.ts")).toContain('"PUT"');
  });
});
