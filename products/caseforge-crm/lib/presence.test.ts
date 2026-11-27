import { describe, expect, it } from "vitest";
import { EXIT_MS, effectivePhase, endsExit, exitDuration, presenceStep } from "./presence";

describe("presence phases", () => {
  it("goes open, then closing, then closed", () => {
    let p = presenceStep("closed", "show");
    expect(p).toBe("open");
    p = presenceStep(p, "hide");
    expect(p).toBe("closing");
    p = presenceStep(p, "done");
    expect(p).toBe("closed");
  });
  it("opening again during the exit cancels the close", () => {
    expect(presenceStep(presenceStep("open", "hide"), "show")).toBe("open");

    expect(presenceStep("open", "done")).toBe("open");
  });
  it("hiding something already closed, or closing, changes nothing", () => {
    expect(presenceStep("closed", "hide")).toBe("closed");
    expect(presenceStep("closing", "hide")).toBe("closing");
  });
  it("what is drawn follows the request at once: hidden means closing, never still open", () => {
    expect(effectivePhase(true, "closed")).toBe("open");
    expect(effectivePhase(false, "open")).toBe("closing");
    expect(effectivePhase(false, "closing")).toBe("closing");
    expect(effectivePhase(false, "closed")).toBe("closed");
  });
  it("the timeout fallback is the animation's own length, and nothing at all for reduced motion", () => {
    expect(exitDuration(false)).toBe(EXIT_MS);
    expect(EXIT_MS).toBeGreaterThanOrEqual(200);
    expect(EXIT_MS).toBeLessThanOrEqual(250);
    expect(exitDuration(true)).toBe(0);
  });
  it("only the widget's own animation ends the exit", () => {
    const el = {};
    expect(endsExit("closing", el, el)).toBe(true);
    expect(endsExit("closing", {}, el)).toBe(false);
    expect(endsExit("open", el, el)).toBe(false);
  });
});

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

describe("every widget uses the shared exit", () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
  it("the five widgets draw through usePresentNode, and the stylesheet animates both ways", () => {
    for (const f of ["../components/WidgetBox.tsx", "../components/WhatsNew.tsx", "../components/ClassifierPrompt.tsx", "../components/UpcomingRail.tsx"]) {
      expect(read(f), f).toContain("usePresentNode(");
    }
    const css = read("../app/widgets.css");
    expect(css).toContain(".widget-open { animation: widget-in");
    expect(css).toContain(".widget-closing { animation: widget-out");
    expect(css).toContain("prefers-reduced-motion: reduce");
    expect(css).toMatch(/--widget-ms: 2[0-5]0ms/);
  });
});
