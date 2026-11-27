import { describe, expect, it } from "vitest";
import { BOTTOM_SNAP_PX, MIN_SCROLL_PX, SHOW_RUN_PX, TOP_ZONE_PX, canHideHeaderFor, chromeAfterScroll, footerPlacement, footerReveal, hideForFooter, noScrollSlack, overlayFooterShown, overlayNeeded, remainingAt, showBackToTop } from "./hideOnScroll";

const pane = (top: number, clientHeight = 500, scrollHeight = 2000) => ({ top, clientHeight, scrollHeight });
const CHROME = 100;

describe("footerReveal at the bottom", () => {
  it("is fully out within the snap distance, so a fractional scrollTop cannot make it flip", () => {
    expect(footerReveal(0.7, 40)).toBe(40);
    expect(footerReveal(-0.2, 40)).toBe(40);
    expect(footerReveal(BOTTOM_SNAP_PX, 40)).toBe(40);
    expect(footerReveal(BOTTOM_SNAP_PX + 10, 40)).toBe(30);
  });
});

describe("chromeAfterScroll", () => {
  it("keeps a hidden header away while a scroll up is still a wobble", () => {
    expect(chromeAfterScroll({ prev: pane(800), next: pane(780), hidden: true, chromeHeight: CHROME })).toBeNull();
    expect(chromeAfterScroll({ prev: pane(800), next: pane(770), hidden: true, chromeHeight: CHROME, run: -(SHOW_RUN_PX - 1) })).toBeNull();
  });

  it("hides the header and footer when a long pane is scrolled down", () => {
    expect(chromeAfterScroll({ prev: pane(200), next: pane(260), hidden: false, chromeHeight: CHROME })).toBe("hide");
  });

  it("brings them back on any real scroll up", () => {
    expect(chromeAfterScroll({ prev: pane(800), next: pane(780), hidden: true, chromeHeight: CHROME, run: -SHOW_RUN_PX })).toBe("show");
  });

  it("always shows the header near the top", () => {
    expect(chromeAfterScroll({ prev: pane(300), next: pane(TOP_ZONE_PX), hidden: true, chromeHeight: CHROME })).toBe("show");
    expect(chromeAfterScroll({ prev: pane(10), next: pane(40), hidden: false, chromeHeight: CHROME })).toBeNull();
  });

  it("ignores a nudge smaller than the threshold", () => {
    expect(chromeAfterScroll({ prev: pane(400), next: pane(403), hidden: false, chromeHeight: CHROME })).toBeNull();
    expect(chromeAfterScroll({ prev: pane(400), next: pane(397), hidden: true, chromeHeight: CHROME })).toBeNull();
  });

  it("takes the first sample, or one where the pane changed height, as a baseline", () => {
    expect(chromeAfterScroll({ prev: undefined, next: pane(400), hidden: false, chromeHeight: CHROME })).toBeNull();

    expect(chromeAfterScroll({ prev: pane(1500, 500), next: pane(1400, 600), hidden: true, chromeHeight: CHROME })).toBeNull();
  });

  it("never hides for a pane that would stop scrolling once they are gone", () => {
    const short = (top: number) => pane(top, 500, 500 + MIN_SCROLL_PX + CHROME - 1);
    expect(chromeAfterScroll({ prev: short(100), next: short(200), hidden: false, chromeHeight: CHROME })).toBeNull();
  });

  it("leaves things alone when they are already in the wanted state", () => {
    expect(chromeAfterScroll({ prev: pane(200), next: pane(260), hidden: true, chromeHeight: CHROME })).toBeNull();
    expect(chromeAfterScroll({ prev: pane(800), next: pane(780), hidden: false, chromeHeight: CHROME })).toBeNull();
  });
});

describe("footerReveal (the footer comes up with the scroll)", () => {
  const FOOT = 40;
  it("is tucked away until the last footer's-height of the pane", () => {
    expect(footerReveal(500, FOOT)).toBe(0);
    expect(footerReveal(FOOT + BOTTOM_SNAP_PX, FOOT)).toBe(0);
  });
  it("comes up one pixel for every pixel scrolled", () => {
    const d = BOTTOM_SNAP_PX;
    expect(footerReveal(30 + d, FOOT)).toBe(10);
    expect(footerReveal(20 + d, FOOT)).toBe(20);
    expect(footerReveal(10 + d, FOOT)).toBe(30);
  });
  it("is whole at the bottom, and never more", () => {
    expect(footerReveal(0, FOOT)).toBe(FOOT);
    expect(footerReveal(-3, FOOT)).toBe(FOOT);
  });
  it("is continuous: neighbouring scroll positions differ by at most a pixel", () => {
    for (let d = 60; d > -5; d--) expect(Math.abs(footerReveal(d, FOOT) - footerReveal(d - 1, FOOT))).toBeLessThanOrEqual(1);
  });
  it("is whole when there is no pane that scrolls", () => {
    expect(footerReveal(null, FOOT)).toBe(FOOT);
  });
});

describe("showBackToTop (the caseforge.uk rule)", () => {
  it("stays away when there is little to scroll", () => {
    expect(showBackToTop(pane(140, 500, 640))).toBe(false);
  });
  it("shows past 300px on a long pane", () => {
    expect(showBackToTop(pane(300))).toBe(false);
    expect(showBackToTop(pane(301))).toBe(true);
  });
  it("shows past 35% of a shorter pane", () => {

    expect(showBackToTop(pane(70, 500, 700))).toBe(false);
    expect(showBackToTop(pane(71, 500, 700))).toBe(true);
  });
});

describe("remainingAt", () => {
  it("runs from all the way to nothing, ease in and out", () => {
    expect(remainingAt(0)).toBe(1);
    expect(remainingAt(0.5)).toBeCloseTo(0.5);
    expect(remainingAt(1)).toBe(0);
    expect(remainingAt(2)).toBe(0);
    expect(remainingAt(0.25)).toBeGreaterThan(0.75);
  });
});

const FOOT = 40;

describe("footerPlacement (the page is never pulled under a visible header)", () => {
  it("shows the footer whole, in the flow, when nothing scrolls", () => {
    expect(footerPlacement({ distance: null, headerHidden: false, footerHeight: FOOT })).toEqual({ flow: true, reveal: FOOT });
  });
  it("reveals nothing while the header is visible and something scrolls, wherever the pane is", () => {
    for (const distance of [500, FOOT, 30, 10, 0, -3]) {
      expect(footerPlacement({ distance, headerHidden: false, footerHeight: FOOT })).toEqual({ flow: false, reveal: 0 });
    }
  });
  it("follows the scroll while the header is hidden", () => {
    expect(footerPlacement({ distance: 30 + BOTTOM_SNAP_PX, headerHidden: true, footerHeight: FOOT })).toEqual({ flow: false, reveal: 10 });
    expect(footerPlacement({ distance: 0, headerHidden: true, footerHeight: FOOT })).toEqual({ flow: false, reveal: FOOT });
  });
  it("never pulls up (reveal with the footer out of the flow) unless the header is hidden", () => {
    for (const headerHidden of [true, false]) {
      for (const distance of [null, 200, 40, 20, 0]) {
        const placed = footerPlacement({ distance, headerHidden, footerHeight: FOOT });
        if (!headerHidden && !placed.flow) expect(placed.reveal).toBe(0);
      }
    }
  });
});

describe("noScrollSlack (no flip-flop between flow and scrolling)", () => {
  it("is the plain slack while the footer is out of the flow", () => {
    expect(noScrollSlack(4, false, FOOT)).toBe(4);
  });
  it("adds the footer's room while it is in the flow", () => {
    expect(noScrollSlack(4, true, FOOT)).toBe(4 + FOOT);
  });
  it("is stable: overflow only the footer's room caused keeps flow, real overflow leaves it and stays out", () => {
    const slack = 4;
    const judge = (overflowWithoutFooter: number, flow: boolean) => {
      const overflowNow = overflowWithoutFooter + (flow ? FOOT : 0);
      return overflowNow <= noScrollSlack(slack, flow, FOOT);
    };
    for (let overflow = 0; overflow < 200; overflow++) {
      const enters = judge(overflow, false);

      if (enters) expect(judge(overflow, true)).toBe(true);

      else expect(judge(overflow, true)).toBe(false);
    }
  });
});

describe("panes too short to hide the header get the footer as an overlay at the bottom", () => {
  const short = { clientHeight: 800, scrollHeight: 890 };
  it("a pane that cannot hide the header needs the overlay; one that can keeps the usual reveal", () => {
    expect(canHideHeaderFor(short, 63, 0)).toBe(false);
    expect(canHideHeaderFor({ clientHeight: 800, scrollHeight: 800 + MIN_SCROLL_PX + 63 }, 63, 0)).toBe(true);
    expect(overlayNeeded({ distance: 10, headerHidden: false, canHideHeader: false })).toBe(true);

    expect(overlayNeeded({ distance: 10, headerHidden: false, canHideHeader: true })).toBe(false);
    expect(overlayNeeded({ distance: 10, headerHidden: true, canHideHeader: false })).toBe(false);
    expect(overlayNeeded({ distance: null, headerHidden: false, canHideHeader: false })).toBe(false);
  });
  it("the spacer's own room is not counted as overflow, so the mode does not flip when the spacer is added", () => {
    const withSpacer = { clientHeight: 800, scrollHeight: 890 + 40 };
    expect(canHideHeaderFor(withSpacer, 63, 40)).toBe(canHideHeaderFor(short, 63, 0));
  });
  it("is hidden while scrolling down, revealed within the bottom snap, and hidden again only after more than 24px up", () => {
    for (const distance of [90, 40, SHOW_RUN_PX + 1, BOTTOM_SNAP_PX + 1]) expect(overlayFooterShown({ distance, shown: false })).toBe(false);
    for (const distance of [BOTTOM_SNAP_PX, 1, 0, -2]) expect(overlayFooterShown({ distance, shown: false })).toBe(true);
    expect(overlayFooterShown({ distance: SHOW_RUN_PX, shown: true })).toBe(true);
    expect(overlayFooterShown({ distance: SHOW_RUN_PX + 1, shown: true })).toBe(false);
    expect(overlayFooterShown({ distance: null, shown: true })).toBe(false);
  });
  it("does not oscillate", () => {
    for (let distance = -3; distance < 80; distance += 0.5) {
      for (const shown of [false, true]) {
        const once = overlayFooterShown({ distance, shown });
        expect(overlayFooterShown({ distance, shown: once })).toBe(once);
      }
    }
  });
  it("a long pane that reaches its bottom with the header still showing hides the header, as any scroll down does", () => {
    expect(hideForFooter({ distance: 0, headerHidden: false, canHideHeader: true })).toBe(true);
    expect(hideForFooter({ distance: 30, headerHidden: false, canHideHeader: true })).toBe(false);
    expect(hideForFooter({ distance: 0, headerHidden: true, canHideHeader: true })).toBe(false);
    expect(hideForFooter({ distance: 0, headerHidden: false, canHideHeader: false })).toBe(false);
    expect(hideForFooter({ distance: null, headerHidden: false, canHideHeader: true })).toBe(false);
  });
});
