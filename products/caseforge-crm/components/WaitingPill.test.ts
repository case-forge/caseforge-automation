import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { WaitingPill } from "./WaitingPill";

describe("WaitingPill", () => {
  it.each([
    ["client", "WAITING FOR CLIENT"],
    ["court", "WAITING FOR COURT"],
    ["counsel", "WAITING FOR COUNSEL"],
  ] as const)("says %s in capitals and announces itself", (state, text) => {
    const html = renderToStaticMarkup(createElement(WaitingPill, { state }));
    expect(html).toContain(text);
    expect(html).toContain('role="status"');
    expect(html).toContain(`data-waiting="${state}"`);
    expect(html).not.toContain("data-compact");
  });

  it("is the same words in the small form used on cards and the Today board", () => {
    const html = renderToStaticMarkup(createElement(WaitingPill, { state: "court", compact: true }));
    expect(html).toContain("WAITING FOR COURT");
    expect(html).toContain('data-compact="true"');
  });
});
