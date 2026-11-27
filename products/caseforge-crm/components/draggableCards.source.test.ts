
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("Merge and Remove on the client title", () => {
  it.each([
    ["MergeClientButton.tsx", "Merge client"],
    ["RemoveClientButton.tsx", "Remove client"],
  ])("%s is a words-only button, with no icon in the trigger", (file, words) => {
    const code = read(`./${file}`);
    const at = code.indexOf(`${words}\n      </button>`);
    expect(at).toBeGreaterThan(-1);
    const trigger = code.slice(code.lastIndexOf("<button", at), at + words.length);
    expect(trigger).toContain(words);
    expect(trigger).not.toMatch(/<Icon/);
    expect(code).toContain("cf-btn cf-btn--neutral");
    expect(code).not.toContain("cf-btn--icon");
  });
  it("keeps the danger styling on Remove only", () => {
    expect(read("./RemoveClientButton.tsx")).toContain("cf-btn cf-btn--neutral cf-btn--danger");
    expect(read("./MergeClientButton.tsx")).not.toContain("cf-btn--danger");
  });
  it("DetailPanel passes both buttons to the edit bar and no longer mounts them in the toolbar", () => {
    const code = read("./DetailPanel.tsx");
    expect(code).toContain("clientActions={");
    const bar = code.indexOf("<ClientEditBar");
    expect(bar).toBeGreaterThan(-1);
    expect(code.indexOf("<MergeClientButton")).toBeGreaterThan(bar);
    expect(code.indexOf("<RemoveClientButton")).toBeGreaterThan(bar);
    expect(code.split("<MergeClientButton").length - 1).toBe(1);
    expect(code.split("<RemoveClientButton").length - 1).toBe(1);
  });
});

describe("the Client edit bar", () => {
  it("has no stand-alone Edit button and puts Save as draft in the right-hand group", () => {
    const code = read("./ClientEdits.tsx");
    expect(code).not.toContain("IconPencil");
    expect(code).not.toContain("onClick={ed.startEdit}");
    const more = code.indexOf('<span className="client-edits-more">');
    const draft = code.indexOf("Save as draft\n");
    expect(more).toBeGreaterThan(-1);
    expect(draft).toBeGreaterThan(more);
    expect(draft).toBeLessThan(code.indexOf("{clientActions}", more));
  });
});

describe("the draggable cards", () => {
  it.each([
    ["WhatsNew.tsx", "whats-new"],
    ["ClassifierPrompt.tsx", "classifier-prompt"],
  ])("%s is a window: move, resize, expand, minimise to the shared edge tabs", (file, id) => {
    const code = read(`./${file}`);
    expect(code).toContain(`useFloatingBox("${id}"`);
    expect(code).toContain("barProps={win.barProps}");
    expect(code).toContain("onMinimise={win.minimise}");
    expect(code).toContain("win.gripProps(edge)");
    expect(code).toContain("<CardBar");
    expect(code).toContain("fw fw-card");
  });
  it("keeps Escape on the bar from closing the classifier card", () => {
    expect(read("../lib/useDraggableCard.ts")).toContain("event.stopPropagation()");
    expect(read("../lib/useDraggableCard.ts")).toContain("setPointerCapture");
  });
});

describe("the section edit icons", () => {
  it("SectionEditButton is a square-pen icon button labelled Edit <section>", () => {
    const code = read("./SectionEditButton.tsx");
    expect(code).toContain("<IconEdit");
    expect(code).toContain("aria-label={`Edit ${section}`}");
    expect(code).toContain("ed.startEdit()");
    expect(read("./icons.tsx")).toContain('name="square-pen"');
  });

  it("DetailPanel gives exactly five headings the edit icon, each with a data-section", () => {
    const code = read("./DetailPanel.tsx");
    const headings = code.match(/<h3 className="detail-section-title detail-section-title--with-edit"[^>]*>/g) ?? [];
    expect(headings).toHaveLength(5);
    for (const heading of headings) expect(heading).toMatch(/data-section="\w+"/);
    expect(code.split("<SectionEditButton").length - 1).toBe(5);
  });
});
