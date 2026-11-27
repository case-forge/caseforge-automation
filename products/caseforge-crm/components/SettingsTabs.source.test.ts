
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SettingsPage } from "./SettingsPage";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("Settings tabs", () => {
  const html = renderToStaticMarkup(createElement(SettingsPage));
  it("draws only This browser, selected, before the role is known", () => {
    expect(html).toContain('role="tablist"');
    expect(html).toMatch(/id="settings-tab-windows"[^>]*aria-selected="true"/);
    expect(html).toContain('role="tabpanel"');
    expect(html).toContain('aria-labelledby="settings-tab-windows"');
    for (const id of ["firm", "folders", "folder-map", "billing", "operations", "email-classifier", "special-senders"]) expect(html).not.toContain(`id="settings-tab-${id}"`);
  });
  it("is a vertical list beside the panel, a select at phone width, with arrow keys", () => {
    expect(html).toContain('aria-orientation="vertical"');
    expect(html).toContain('<select aria-label="Settings section"');

    expect((html.match(/role="tab"/g) ?? []).length).toBe(1);
    expect(html).not.toContain('id="settings-tab-models"');
    expect(html).not.toContain('id="settings-tab-links"');
    const css = read("../app/modelsettings.css");
    expect(css).toMatch(/\.settings-layout \{[^}]*grid-template-columns: 13rem/);
    expect(css).toMatch(/\.settings-tabs \{[^}]*flex-direction: column/);
    const phone = css.slice(css.indexOf("@media (max-width: 760px) {\n  .settings-layout"));
    expect(phone).toContain(".settings-tabs { display: none; }");
    expect(phone).toContain(".settings-section-select { display: block; }");
    const source = read("./SettingsPage.tsx");
    for (const key of ["ArrowDown", "ArrowUp", "Home", "End"]) expect(source).toContain(key);
    expect(source).toContain("onChange={(e) => choose(e.target.value)}");
  });
  it("lists every tab as one entry, the server-backed ones first, a developer opening on Firm", () => {
    const source = read("./SettingsPage.tsx");
    expect(source).toContain("const TABS");
    const ids = [...source.matchAll(/\{ id: "([a-z-]+)", title/g)].map((m) => m[1]);
    expect(ids).toEqual(["firm", "folders", "folder-map", "billing", "operations", "models", "email-classifier", "links", "special-senders", "system-health", "storage", "windows"]);
    expect(source).toContain('const DEFAULT_TAB = "firm"');
  });
});

describe("Models panel", () => {
  const source = read("./ModelsPanel.tsx");
  it("changes nothing without Edit, Save and the dialog's Confirm", () => {
    expect(source).toContain("view.can_edit");
    expect(source).toMatch(/\{canEdit && <th/);
    expect(source).toContain('role="dialog"');
    expect(source).toContain('aria-modal="true"');
    expect(source).toContain("Confirm change");

    const sends = [...source.matchAll(/saveRoleModel\(|resetRoleModel\(/g)].length;
    expect(sends).toBe(2);
    expect(source.indexOf("async function confirm()")).toBeLessThan(source.indexOf("saveRoleModel(row.role"));
  });
  it("offers only the row's candidates, never a free text box", () => {
    expect(source).toContain("row.candidates.map");
    expect(source).not.toMatch(/type="text"/);
  });
  it("shows the refusal beside the row and the table collapses to cards", () => {
    expect(source).toContain('className="models-error" role="alert"');
    expect(read("../app/modelsettings.css")).toMatch(/@media \(max-width: 760px\)[\s\S]*display: block/);
    expect(read("../app/layout.tsx")).toContain("modelsettings.css");
  });
  it("has no double hyphen or em dash in on-screen text", () => {
    const text = [...source.matchAll(/>\s*([A-Za-z][^<>{}]*?)\s*</g)].map((m) => m[1]).join("\n") + [...source.matchAll(/"([A-Z][^"]*)"/g)].map((m) => m[1]).join("\n");
    expect(text).not.toMatch(/--|—/);
  });
  it("draws every tab but This browser in dev mode only, from the role the server gives", () => {
    const source = read("./SettingsPage.tsx");
    expect(source).toContain('{ id: "models", title: "Models", body: <ModelsPanel />, devOnly: true }');
    expect(source).toContain('{ id: "links", title: "Links", body: <FirmLinksPanel />, devOnly: true }');
    expect(source).toContain("const isDev = useDevMode();");
    expect(source).toContain("ALL_TABS.filter((t) => isDev || !t.devOnly)");
    expect([...source.matchAll(/devOnly: true/g)].length).toBe(11);
    expect(source).toMatch(/\{ id: "windows", title: "This Browser", body: \(/);
  });
});
