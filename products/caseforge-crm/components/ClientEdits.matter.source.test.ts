import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { CATEGORY_PILL_FLAGS, PILL_FLAGS } from "@/lib/types";

const EDITS = readFileSync(fileURLToPath(new URL("./ClientEdits.tsx", import.meta.url)), "utf8");
const PANEL = readFileSync(fileURLToPath(new URL("./DetailPanel.tsx", import.meta.url)), "utf8");

describe("the Matter box's matter dropdown, while editing", () => {
  it("sits beside the five tick boxes in the Matter field and takes the same flag state", () => {
    expect(PANEL).toMatch(/<InlineOrderTypes \/>\s*<InlineMatterSelect\s+flags=\{flags\}/);
    expect(EDITS).toContain("export function InlineMatterSelect");
    expect(EDITS).toContain("if (!ed?.editing) return null;");
  });

  it("offers exactly the new client button's matters, and choosing one adds its pill without clearing any other", () => {
    expect(EDITS).toContain('CATEGORY_PILL_FLAGS.filter((flag) => flag.name.startsWith("cat_"))');
    expect(EDITS).toMatch(/postFlag\(matterId, flag, on\)/);
    expect(EDITS).not.toMatch(/for \(const choice of MATTER_CHOICES\)/);
    expect(EDITS).toContain("`Remove ${choice.label}`");
    const cats = CATEGORY_PILL_FLAGS.filter((f) => f.name.startsWith("cat_")).map((f) => f.label);
    expect(cats).toContain("Litigation");
    expect(cats).toHaveLength(10);
  });

  it("has no 'Other matter' pill anywhere", () => {
    expect(PILL_FLAGS.map((f) => f.name)).not.toContain("ncf_other");
    expect(PILL_FLAGS.map((f) => f.label)).not.toContain("Other matter");
  });
});
