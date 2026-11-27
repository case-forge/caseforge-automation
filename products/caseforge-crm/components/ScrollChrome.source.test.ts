
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const SOURCE = read("./ScrollChrome.tsx");
const PAGE = read("../components/Workspace.tsx");
const CSS = read("../app/globals.css");

describe("ScrollChrome.tsx source", () => {
  it("hears every pane's scroll through one capture listener on .page, never the window", () => {
    expect(SOURCE).toMatch(/page\.addEventListener\("scroll", onScroll, \{ capture: true, passive: true \}\)/);
    expect(SOURCE).not.toMatch(/window\.addEventListener\("scroll"/);
    expect(PAGE).toMatch(/<main className="page" id="main-content" tabIndex={-1} ref={pageRef}>/);
    expect(PAGE).toMatch(/<ScrollChrome shellRef=\{shellRef\} pageRef=\{pageRef\} resetKey=/);
  });

  it("does not hide the header while a field in it has focus or one of its menus is open", () => {
    expect(SOURCE).toMatch(/HEADER_FIELD = 'input, textarea, select/);
    expect(SOURCE).toMatch(/HEADER_OPEN = 'details\[open\], \[aria-expanded="true"\]'/);
    expect(SOURCE).toMatch(/headerMove === "hide" && !headerBusy\(\)/);
  });

  it("jumps straight to the top under prefers-reduced-motion", () => {
    expect(SOURCE).toMatch(/if \(reducedMotion\(\)\) \{\s*el\.scrollTop = 0;/);
  });

  it("names the button for assistive tech and hides it with the hidden attribute", () => {
    expect(SOURCE).toMatch(/aria-label="Return to top"/);
    expect(CSS).toMatch(/\.back-to-top\[hidden\] \{ display: none; \}/);
  });

  it("slides the header away when hidden, and lays the footer out below the window until the scroll reveals it", () => {
    expect(CSS).toMatch(/\.app-shell\[data-chrome="hidden"\] > \.app-header \{ margin-top: calc\(-1 \* var\(--chrome-header-h/);
    expect(CSS).toMatch(/\.app-shell > \.app-footer \{ margin-bottom: calc\(var\(--chrome-pull\) - var\(--chrome-footer-h/);

    expect(CSS).toMatch(/\.app-shell > \.page \{ margin-top: calc\(-1 \* var\(--chrome-pull\)\); \}/);
  });

  it("has no timed slide on the footer: the scroll position is the animation", () => {
    expect(CSS).not.toMatch(/\.app-footer \{ transition/);
    expect(CSS).not.toMatch(/data-footer/);
    expect(SOURCE).not.toMatch(/data-footer|pinToBottom|footerAfterScroll/);
  });

  it("never lets the window scroll, whose scrollbar would shift the header buttons sideways", () => {
    expect(CSS).toMatch(/@media screen \{\s*\.app-shell \{ overflow: clip; \}\s*\}/);

    expect(CSS).not.toMatch(/\.app-shell\[data-chrome="hidden"\] \{ overflow/);
  });

  it("shows the whole footer when nothing on the view scrolls, and follows the scrolled pane otherwise", () => {
    expect(SOURCE).toMatch(/firstScroller\(page, slack\)/);
    expect(SOURCE).toMatch(/noScrollSlack\(BOTTOM_SLACK, flow, footerHeight\(\)\)/);
    expect(SOURCE).toMatch(/place\(owner \? fromBottom\(sample\(owner\)\) : null\)/);
    expect(SOURCE).toMatch(/place\(fromBottom\(next\)\)/);
  });
});

describe("the footer reveal never pulls the page under a visible header", () => {

  const stripped = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  function declarations(selector: string): string {
    const out: string[] = [];
    for (const m of stripped.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (m[1].split(",").some((s) => s.trim() === selector)) out.push(m[2]);
    }
    return out.join(";");
  }

  it("pulls the page up by --chrome-pull only, never by the raw reveal", () => {
    expect(declarations(".app-shell > .page")).toMatch(/margin-top:\s*calc\(-1 \* var\(--chrome-pull\)\)/);
    expect(declarations(".app-shell > .page")).not.toContain("--chrome-footer-r");
    expect(declarations(".app-shell > .app-footer")).not.toContain("--chrome-footer-r");
  });

  it("--chrome-pull is 0 by default and fed from the reveal only under data-chrome=hidden", () => {
    expect(declarations(".app-shell")).toMatch(/--chrome-pull:\s*0px/);
    const users = [...stripped.matchAll(/([^{}]+)\{[^{}]*--chrome-footer-r[^{}]*\}/g)].map((m) => m[1].trim());

    const feeds = users.filter((selector) => !/back-to-top|hearings-rail/.test(selector));
    expect(feeds).toEqual(['.app-shell[data-chrome="hidden"]']);
  });

  it("caps the pull at the header's height, which a hidden header gives back", () => {
    expect(declarations('.app-shell[data-chrome="hidden"]')).toMatch(
      /--chrome-pull:\s*min\(var\(--chrome-footer-r, 0px\), var\(--chrome-header-h/,
    );
  });

  it("shows the footer whole in the flow with no pull-up", () => {
    expect(declarations('.app-shell[data-chrome-footer="flow"] > .app-footer')).toMatch(/margin-bottom:\s*0/);
  });

  it("ScrollChrome reveals only through footerPlacement, never footerReveal directly", () => {
    expect(SOURCE).toContain("footerPlacement(");
    expect(SOURCE).not.toMatch(/\bfooterReveal\b/);
  });
});

describe("the overlay footer for panes too short to hide the header", () => {
  it("is fixed and slid with a transform, never in the flow, and only under data-gap-footer", () => {
    expect(CSS).toMatch(/\.app-shell\[data-gap-footer\] > \.app-footer \{[^}]*position: fixed;[^}]*transform: translateY\(100%\)/);
    expect(CSS).toMatch(/\.app-shell\[data-gap-footer\]\[data-gap-footer-shown\] > \.app-footer \{ transform: none; \}/);
  });
  it("gives the scrolling pane a static spacer as tall as the footer, so the last row can be scrolled clear of it", () => {
    expect(CSS).toMatch(/\[data-gap-room\]::after \{[^}]*height: var\(--chrome-footer-h/);
    expect(SOURCE).toContain('"data-gap-room"');
  });
  it("is decided by the pure functions, not by the header threshold", () => {
    expect(SOURCE).toContain("overlayNeeded(");
    expect(SOURCE).toContain("overlayFooterShown(");
    expect(SOURCE).toContain("hideForFooter(");
  });
});
