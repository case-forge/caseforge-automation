import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("merge direction", () => {
  const code = readFileSync(new URL("./MergeClientButton.tsx", import.meta.url), "utf8");

  it("previews the typed matter as from and the opened client as into", () => {
    expect(code).toContain("?from=${encodeURIComponent(awayId)}&into=${encodeURIComponent(keepId)}");
  });

  it("posts the previewed from and into, so Swap changes which is kept", () => {
    expect(code).toContain("from_matter_id: preview.from.matter_id");
    expect(code).toContain("into_matter_id: preview.into.matter_id");
    expect(code).toContain("Swap: keep matter {preview.from.matter_id} instead");
  });
});
