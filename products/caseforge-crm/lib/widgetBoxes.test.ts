import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";
import { clearShowing, consumeCloseRequest, consumeRequest, reportShowing, toggleWindow } from "./cornerPrompts";
import type { CornerId } from "./cornerPrompts";
import { hearingsHost } from "./hearingsHost";
import { widgetOpen } from "./widgetOpen";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const ALL: CornerId[] = ["hearings", "whats-new", "classifier", "add-hearing"];

describe("every box toggles on its launcher", () => {
  for (const id of ALL) {
    it(`${id}: a press opens it when hidden and closes it when showing`, () => {
      reportShowing(id, false);
      toggleWindow(id);
      expect(consumeRequest(id)).toBe(true);
      reportShowing(id, true);
      toggleWindow(id);
      expect(consumeCloseRequest(id)).toBe(true);
      clearShowing(id);
    });
  }
});

describe("boxes are independent", () => {
  beforeEach(() => ALL.forEach((id) => reportShowing(id, true)));
  it("closing the classifier box asks nothing of the Hearings box, or of any other", () => {
    toggleWindow("classifier");
    expect(consumeCloseRequest("classifier")).toBe(true);
    for (const other of ALL.filter((i) => i !== "classifier")) {
      expect(consumeCloseRequest(other), other).toBe(false);
      expect(consumeRequest(other), other).toBe(false);
    }
    ALL.forEach(clearShowing);
  });
  it("hiding one box in the open-state store leaves the others open", () => {
    widgetOpen.reset();
    widgetOpen.set("hearings-rail", true);
    widgetOpen.set("status-board", true);
    widgetOpen.set("auto-sent", true);
    widgetOpen.set("classifier-prompt", false);
    expect(["hearings-rail", "status-board", "auto-sent"].every((id) => widgetOpen.isOpen(id))).toBe(true);
  });
  it("no box closes from a press or a key anywhere else on the page: no document listener, no outside-press helper", () => {
    for (const f of ["../components/WidgetBox.tsx", "../components/UpcomingRail.tsx", "../components/WhatsNew.tsx", "../components/ClassifierPrompt.tsx", "../components/AddHearingBox.tsx"]) {
      const src = read(f);
      expect(src, f).not.toMatch(/useDismiss|attachDismiss/);
      expect(src, f).not.toMatch(/document\.addEventListener\(\s*"(keydown|pointerdown|mousedown|click)"/);
    }

    expect(read("../components/WidgetBox.tsx")).toMatch(/onKeyDown=\{\(e\) => \{[^}]*Escape/);
  });
  it("the slide-out's click-beside-the-panel rule ignores every floating box", () => {
    expect(read("../components/HearingSlideOut.tsx")).toMatch(/const KEEP_OPEN = "[^"]*\.fw,/);
  });
});

describe("the Add a Hearing box", () => {
  it("hiding the box keeps every tab (the tabs live in the host, not in the box)", () => {
    hearingsHost.openCreate({ matterId: "901", clientName: "Client 901", defaults: {} });
    hearingsHost.openCreate({ matterId: "902", clientName: "Client 902", defaults: {} });
    widgetOpen.set("add-hearing", true);
    widgetOpen.set("add-hearing", false);
    expect(hearingsHost.tabs().tabs.map((t) => t.key)).toEqual(["hearing-new:901", "hearing-new:902"]);
    expect(read("../components/WidgetBox.tsx")).toMatch(/const hide = \(\) => \{[^}]*setOpen\(false\)/);
    hearingsHost.closeTabNow("hearing-new:901");
    expect(hearingsHost.tabs().tabs.map((t) => t.key)).toEqual(["hearing-new:902"]);
    hearingsHost.closeTabNow("hearing-new:902");
  });
  it("its plus is disabled at five with the tooltip, and the box is named Add a Hearing", () => {
    const src = read("../components/AddHearingBox.tsx");
    expect(src).toContain("disabled={full}");
    expect(src).toContain("TABS_FULL_HINT");
    expect(src).toContain('title="Add a Hearing"');
  });
});

describe("the boxes follow the person", () => {
  it("they are mounted at layout level, not in a page", () => {
    const layout = read("../app/layout.tsx");
    expect(layout).toContain("<WidgetLayer />");
    expect(layout).toContain("<GlobalHearings />");
    expect(read("../components/WidgetLayer.tsx")).toMatch(/WhatsNewPanel[\s\S]*ClassifierPrompt/);
    expect(read("../components/WidgetLayer.tsx")).not.toMatch(/StatusBoardBox|AutoSendBox|CourtPrepBox/);
    expect(read("../components/GlobalHearings.tsx")).toContain("<AddHearingBox />");
  });
});
