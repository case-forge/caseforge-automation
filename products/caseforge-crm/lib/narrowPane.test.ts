import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { NARROW_LAYOUT_MAX_PX, narrowPane } from "./narrowPane";

describe("narrowPane", () => {
  it("shows the results when no client is open", () => {
    expect(narrowPane({ clientOpen: false, showClient: false, resultsCollapsed: false })).toBe("results");
    expect(narrowPane({ clientOpen: false, showClient: true, resultsCollapsed: false })).toBe("results");
  });

  it("shows the client once one is opened", () => {
    expect(narrowPane({ clientOpen: true, showClient: true, resultsCollapsed: false })).toBe("detail");
  });

  it("goes back to the results after Back, with the client still selected", () => {
    expect(narrowPane({ clientOpen: true, showClient: false, resultsCollapsed: false })).toBe("results");
  });

  it("shows the client panel when the list was folded away, so the screen is never blank", () => {
    expect(narrowPane({ clientOpen: false, showClient: false, resultsCollapsed: true })).toBe("detail");
    expect(narrowPane({ clientOpen: true, showClient: false, resultsCollapsed: true })).toBe("detail");
  });

  it("matches the breakpoint in globals.css", () => {
    const css = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");
    expect(css).toContain(`@media (max-width: ${NARROW_LAYOUT_MAX_PX}px)`);
  });
});
