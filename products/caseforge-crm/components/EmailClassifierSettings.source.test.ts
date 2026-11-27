
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { EmailClassifierView } from "@/lib/emailClassifier";
import { ClassifierLists } from "./EmailClassifierSettings";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

const view: EmailClassifierView = {
  lists: {
    court_domains: { default: ["court.example"], added: ["own.example"], removed: [], effective: [] },
    gp_keywords: { default: ["repeat prescription"], added: [], removed: ["repeat prescription"], effective: [] },
  },
  audit: [{ at: "27 Oct", who: "a@b.example", summary: "Changed the lists" }],
};
const draw = (canEdit: boolean, errors: Record<string, string> = {}) =>
  renderToStaticMarkup(createElement(ClassifierLists, { view, canEdit, errors, onSave: async () => true }));

describe("Email classifier settings", () => {
  it("is its own section of the Settings page", () => {
    expect(read("./SettingsPage.tsx")).toContain('{ id: "email-classifier", title: "Email Classifier", body: <div className="settings-group"><EmailClassifierSettings /></div>, devOnly: true }');
  });
  it("shows an administrator closed built-in lists, named buttons, removable chips and an add box", () => {
    const html = draw(true);
    expect(html).toContain("<details");
    expect(html).not.toContain("<details open");
    expect(html).toContain('aria-label="Stop using court.example"');
    expect(html).toContain('aria-label="Use again repeat prescription"');
    expect(html).toContain('aria-label="Remove own.example"');
    expect(html).toContain('for="eclf-add-court_domains"');
    expect(html).toContain("Courts");
    expect(html).toContain("GPs");
    expect(html).toContain("Recent changes");
    expect(html).toContain("27 Oct · a@b.example · Changed the lists");
  });
  it("shows the hub's message as an alert under the add box", () => {
    expect(draw(true, { court_domains: "That is not a domain" })).toMatch(/role="alert"[^>]*>That is not a domain/);
  });
  it("is read-only for a non-administrator, with a one-line note", () => {
    const html = draw(false);
    expect(html).not.toContain("Stop using");
    expect(html).not.toContain('aria-label="Remove');
    expect(html).not.toContain("<input");
    expect(html).toContain("Not in use");
    expect(html).toContain("Only an administrator can change these lists");
  });
  it("uses Lucide icons and the cf-btn classes, keeps the input's edge and puts no outline on the boxes", () => {
    const source = read("./EmailClassifierSettings.tsx");
    expect(source).toContain('from "./icons"');
    expect(source).not.toMatch(/<svg/);
    expect(source).toContain("cf-btn cf-btn--primary");
    expect(source).not.toContain("disabled=");
    const css = read("../app/emailclassifier.css");
    expect(css).toMatch(/\.eclf-group \{[^}]*border: none/);
    expect(css).toMatch(/\.eclf-input \{[^}]*border: 1px solid/);
    expect(css).toContain("focus-visible");
    expect(read("../app/layout.tsx")).toContain('import "./emailclassifier.css"');
  });
});
