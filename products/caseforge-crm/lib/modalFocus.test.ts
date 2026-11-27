import { describe, expect, it } from "vitest";
import { initialFocusTarget } from "./modalFocus";

const el = (name: string, close = false) => ({ name, dataset: close ? { dialogClose: "" } : {} }) as { name: string; dataset: DOMStringMap };

describe("where focus lands when a dialog opens", () => {
  it("skips the dialog's own close cross", () => {
    const items = [el("cross", true), el("name"), el("save")];
    expect(initialFocusTarget(items)?.name).toBe("name");
  });
  it("falls back to the cross when it is all there is, and to nothing when empty", () => {
    expect(initialFocusTarget([el("cross", true)])?.name).toBe("cross");
    expect(initialFocusTarget([])).toBeNull();
  });
});
