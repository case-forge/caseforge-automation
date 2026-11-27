import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  PROMPT_MIN_GAP_MS,
  SAVED_NOTE,
  controlSentence,
  backlogLine,
  decideContext,
  isTypingTarget,
  isUndecided,
  holdAfterClose, holdAfterNotToday, nextLocalMidnight,
  promptAllowed,
  tabFromParam,
} from "./mailReview";
import { stubControl, stubControlSave, stubDecide, stubDecideSave } from "./stubMailReview";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("the two tabs", () => {
  it("opens Review unless Control is asked for", () => {
    expect(tabFromParam("control")).toBe("control");
    expect(tabFromParam("audit")).toBe("control");
    expect(tabFromParam("review")).toBe("review");
    expect(tabFromParam("decide")).toBe("review");
    expect(tabFromParam(null)).toBe("review");
    expect(tabFromParam("anything else")).toBe("review");
  });

  it("shows the classifier's own answer in the control question", () => {
    expect(controlSentence({ applied_route: "Counsel" })).toBe("The classifier thinks this goes to Counsel. Do you agree?");
    expect(controlSentence({ applied_route: "Review" })).toContain("could not decide");
    expect(isUndecided("")).toBe(true);
    expect(isUndecided("Court")).toBe(false);
  });

  it("explains how the classifier got to a decision item, in plain words", () => {
    const lines = decideContext({ reason: "Route not decided", model_route: "Counsel", model_conf: 0.884, rules_route: "Court", applied_route: "Court" });
    expect(lines).toEqual(["Route not decided", "The model said Counsel (88% sure).", "The rules said Court.", "Best guess so far: Court."]);
    expect(decideContext({ reason: "", model_route: "", model_conf: null, rules_route: "", applied_route: "Review" })).toEqual([]);
    expect(backlogLine(0, 0)).toBe("Nothing is waiting for a decision.");
    expect(backlogLine(1, 0.4)).toBe("1 email waiting; the oldest has waited under a day.");
    expect(backlogLine(5, 3.9)).toBe("5 emails waiting; the oldest has waited 3 days.");
  });
});

describe("the occasional prompt", () => {
  const hour = PROMPT_MIN_GAP_MS;
  it("is at most one an hour", () => {
    expect(promptAllowed({ lastShownAt: 0, snoozeUntil: 0 }, hour, false)).toBe(true);
    expect(promptAllowed({ lastShownAt: 1000, snoozeUntil: 0 }, 1000 + hour - 1, false)).toBe(false);
    expect(promptAllowed({ lastShownAt: 1000, snoozeUntil: 0 }, 1000 + hour, false)).toBe(true);
  });

  it("never shows while someone is typing", () => {
    expect(promptAllowed({ lastShownAt: 0, snoozeUntil: 0 }, hour * 5, true)).toBe(false);
    expect(isTypingTarget({ tagName: "TEXTAREA" } as Element)).toBe(true);
    expect(isTypingTarget({ tagName: "INPUT", type: "text" } as unknown as Element)).toBe(true);
    expect(isTypingTarget({ tagName: "INPUT", type: "checkbox" } as unknown as Element)).toBe(false);
    expect(isTypingTarget({ tagName: "DIV", isContentEditable: true } as unknown as Element)).toBe(true);
    expect(isTypingTarget({ tagName: "BUTTON" } as unknown as Element)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });

  it("Not today holds until tomorrow morning, whatever time it is", () => {
    const evening = new Date(2026, 9, 25, 21, 30).getTime();
    const tomorrow = nextLocalMidnight(evening);
    expect(new Date(tomorrow).getDate()).toBe(26);
    expect(new Date(tomorrow).getHours()).toBe(0);
    expect(promptAllowed({ lastShownAt: 0, snoozeUntil: tomorrow }, tomorrow - 1, false)).toBe(false);
    expect(promptAllowed({ lastShownAt: 0, snoozeUntil: tomorrow }, tomorrow, false)).toBe(true);
  });
});

describe("the demo fixtures", () => {
  it("are synthetic and move on when answered", () => {
    const first = stubControl(null);
    expect(first.item?.job_id).toBeTruthy();
    expect(JSON.stringify(first)).not.toMatch(/@(?!example\.test)/);
    stubControlSave(first.item!.job_id, "agree");
    expect(stubControl(null).answered).toBe(1);
    const decide = stubDecide(0);
    expect(decide.total).toBe(3);
    stubDecideSave(decide.item!.job_id);
    expect(stubDecide(0).total).toBe(2);
  });
});

describe("each tab shows only its own pool", () => {
  it("never puts a review-pool item under control, or the reverse", () => {
    for (const pool of ["control", "review"] as const) {
      const view = stubControl(null, pool);
      expect(view.total).toBeGreaterThan(0);
      expect(view.item?.pool).toBe(pool);
      for (const row of view.items) expect(stubControl(row.n, pool).item?.pool).toBe(pool);
    }
    expect(stubControl(null, "control").total + stubControl(null, "review").total).toBe(stubControl(null).total);
    expect(stubControl(2, "review").item).toBeNull();
    expect(stubControl(1, "control").item).toBeNull();
  });

  it("the Control tab asks for the control pool, the Review tab adds the review pool under its queue", () => {
    const strip = (t: string) => t.replace(/\/\*[\s\S]*?\*\//g, "");
    const control = strip(read("../components/MailControlTab.tsx"));
    expect(control).toContain('<MailBatchCheck pool="control" />');
    expect(control).not.toContain('pool="review"');
    const review = read("../components/MailReviewTab.tsx");
    expect(review).toContain('<MailBatchCheck pool="review" />');
    expect(review).not.toContain('pool="control"');
    expect(review).toContain("Filed, but the classifier was not sure");
    expect(control).toContain('review: "review-batch"');
  });
});

describe("the components", () => {
  const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("render email text as text, never as HTML", () => {
    for (const file of ["../components/MailEmailCard.tsx", "../components/MailReviewTab.tsx", "../components/MailControlTab.tsx", "../components/ClassifierPrompt.tsx", "../app/review-mail/page.tsx"]) {
      expect(strip(read(file))).not.toContain("dangerouslySetInnerHTML");
    }
  });

  it("is one page with an accessible tablist and the URL carries the tab", () => {
    const page = strip(read("../app/review-mail/page.tsx"));
    expect(page).toContain('role="tablist"');
    expect(page).toContain('role="tab"');
    expect(page).toContain('role="tabpanel"');
    expect(page).toContain("aria-selected");
    expect(page).toContain('searchParams.set("tab"');
    expect(page).toContain("ArrowRight");
  });

  it("mounts the prompt in the layout-level widget layer, so it stays when the page changes", () => {
    expect(read("../components/WidgetLayer.tsx")).toContain("<ClassifierPrompt />");
    expect(read("../app/template.tsx")).not.toContain("ClassifierPrompt");
    expect(read("../app/layout.tsx")).toContain("<WidgetLayer />");
  });

  it("keeps the prompt's memory in try/catch and skips the review page itself", () => {
    const lib = read("./mailReview.ts");
    expect(lib.match(/window\.localStorage/g)?.length).toBe(2);
    expect(lib.match(/try \{/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
    expect(read("../components/ClassifierPrompt.tsx")).toContain('startsWith("/review-mail")');
    expect(read("../components/ClassifierPrompt.tsx")).toContain("Not today");
  });

  it("the decision tab says the route will be applied by the mail worker, and why an email may stay held", () => {
    expect(read("../components/MailReviewTab.tsx")).toContain("SAVED_NOTE");
    expect(SAVED_NOTE).toContain("applied by the mail worker within about a minute");
    expect(SAVED_NOTE).toContain("still held");
    expect(SAVED_NOTE).not.toContain("not been moved");
  });
});

describe("how the prompt is held", () => {
  const evening = new Date(2026, 9, 25, 21, 30).getTime();
  it("the cross waits out only the hour", () => {
    const m = holdAfterClose(evening);
    expect(promptAllowed(m, evening + 60 * 60 * 1000 - 1, false)).toBe(false);
    expect(promptAllowed(m, evening + 60 * 60 * 1000, false)).toBe(true);
  });
  it("Not today holds until tomorrow", () => {
    const m = holdAfterNotToday(evening);
    expect(promptAllowed(m, evening + 2 * 60 * 60 * 1000, false)).toBe(false);
    expect(promptAllowed(m, nextLocalMidnight(evening), false)).toBe(true);
  });
});
