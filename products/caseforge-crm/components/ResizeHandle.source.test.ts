import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const TSX = readFileSync(new URL("./ResizeHandle.tsx", import.meta.url), "utf8");

describe("the results/client divider arrows (gh#1146)", () => {
  it("draws no arrows at rest", () => {
    expect(CSS).toMatch(/\.viewer-resize-arrow \{ opacity: 0;/);
  });

  it("shows them on hover and on keyboard focus", () => {
    expect(CSS).toContain(".viewer-resize-handle:hover .viewer-resize-arrow");
    expect(CSS).toContain(".viewer-resize-handle:focus-visible .viewer-resize-arrow { opacity: 1; }");
  });

  it("keeps them shown where there is no hover (touch)", () => {
    expect(CSS).toContain("@media (hover: none) { .viewer-resize-arrow { opacity: 1; } }");
  });

  it("stays operable: a named, focusable separator that keeps its resting line", () => {
    expect(TSX).toContain('role="separator"');
    expect(TSX).toContain("tabIndex={0}");
    expect(TSX).toContain('aria-label="Resize the results and detail panels"');
    expect(TSX).toContain("viewer-resize-line");
    expect(CSS).toContain(".viewer-resize-line {");
  });
});
