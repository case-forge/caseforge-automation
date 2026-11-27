
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const ARROWS = read("./MatterNumberArrows.tsx");
const PANEL = read("./DetailPanel.tsx");
const PAGE = read("../components/Workspace.tsx");

describe("MatterNumberArrows.tsx", () => {
  it("uses the Lucide chevrons and has a client-number box between the arrows", () => {
    expect(ARROWS).toContain("IconChevronLeft");
    expect(ARROWS).toContain("IconChevronRight");
    expect(ARROWS).toMatch(/\{arrow\("prev"\)\}\s*<input[^>]*className="matter-number-current"/);
    expect(ARROWS).toContain("Client no.");
    expect(ARROWS).toContain("fetchMatterByNumber");
  });

  it("labels each arrow from ARROW_LABELS and turns it off at the end", () => {
    expect(ARROWS).toContain("ARROW_LABELS[dir].title");
    expect(ARROWS).toContain("ARROW_LABELS[dir].end");
    expect(ARROWS).toContain("disabled={atEnd[dir] || busy !== null}");
  });

  it("listens for [ and ] once, through keyDirection, and removes the listener", () => {
    expect(ARROWS).toContain('window.addEventListener("keydown", onKey)');
    expect(ARROWS).toContain('window.removeEventListener("keydown", onKey)');
    expect(ARROWS).toContain("keyDirection(event)");
  });
});

describe("where the arrows sit", () => {
  it("is the client header, opening through the page's openByNumber", () => {
    expect(PANEL).toContain("<MatterNumberArrows matterId={matterId} onOpenMatter={onOpenMatter} />");
    expect(PAGE).toContain("onOpenMatter={openByNumber}");
    expect(PAGE).toMatch(/function openByNumber\(match: ClientMatch\) \{\s*if \(!confirmLeaveUnsaved\(\)\) return;/);
  });
});
