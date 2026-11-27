
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const PAGE = readFileSync(fileURLToPath(new URL("../components/Workspace.tsx", import.meta.url)), "utf8");
const CSS = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");

function rule(selector: string): string {
  const start = CSS.indexOf(`${selector} {`);
  expect(start, selector).toBeGreaterThan(-1);
  return CSS.slice(start, CSS.indexOf("}", start));
}

describe("the Clients header button", () => {
  it("goes home from a quick list and focuses the search box on the clients view", () => {
    const handler = PAGE.slice(PAGE.indexOf("function handleViewChange"), PAGE.indexOf("function handleQuickListResults"));
    expect(handler).toContain('next === "search" && view === "search"');
    expect(handler).toMatch(/if \(listSource\) \{\s*goHome\(\);/);
    expect(handler).toContain('.search-input")?.focus()');
    expect(handler).toContain("setView(next)");
    expect(PAGE).toContain("onViewChange={handleViewChange}");
  });
});

describe("order pills", () => {
  it.each([".result-card-order-tag", ".detail-title-order", ".detail-order-tag"])("%s uses the New pill's colour", (selector) => {
    const block = rule(selector);
    expect(block).toContain("color: var(--accent);");
    expect(block).not.toContain("accent-solid");
    expect(block).toContain("background: var(--accent-soft);");
  });

  it("the New pill uses the same pair", () => {
    const block = rule(".result-card-new,\n.detail-title-new");
    expect(block).toContain("background: var(--accent-soft);");
    expect(block).toContain("color: var(--accent);");
  });
});
