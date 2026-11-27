
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConflictCheck } from "@/lib/conflictCheck";
import type { CaseReviewAnswer } from "@/lib/caseReviewTypes";
import { stubConflictCheck } from "@/lib/stubConflict";
import { DEMO_PRINCIPAL } from "@/lib/stubFirm";

const state: { check: ConflictCheck | null; error: string; busy: boolean } = { check: null, error: "", busy: false };

vi.mock("@/lib/conflictCheck", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/conflictCheck")>();
  return {
    ...actual,
    useConflictCheck: () => ({ check: state.check, error: state.error, setCheck: () => {}, setError: () => {} }),
  };
});

vi.mock("react", async (importActual) => {
  const actual = await importActual<typeof import("react")>();

  const useState = ((initial: unknown) => {
    const pair = actual.useState(initial);
    return typeof initial === "boolean" && state.busy ? [true, pair[1]] : pair;
  }) as typeof actual.useState;
  return { ...actual, useState, default: { ...actual, useState } };
});

const { ConflictCheckPanel } = await import("./ConflictCheckPanel");

const NONE: Record<string, CaseReviewAnswer> = {};
const CLEARED = { r_opening_conflict: { value: "yes" } } as unknown as Record<string, CaseReviewAnswer>;

function render(opts: { answers?: Record<string, CaseReviewAnswer> } = {}): string {
  return renderToStaticMarkup(
    createElement(ConflictCheckPanel, { matterId: "9002", answers: opts.answers ?? NONE }),
  );
}

function text(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/\s+/g, " ");
}

beforeEach(() => {
  state.check = null;
  state.error = "";
  state.busy = false;
});

describe("ConflictCheckPanel", () => {
  it("while loading, says so, with no notice, no matches and no error", () => {
    const html = render();
    expect(html).toContain("Loading the conflict check...");
    expect(html).not.toContain("aud-conflict-notice");
    expect(html).not.toContain("aud-conflict-matches");
    expect(html).not.toContain('role="alert"');
    expect(html).toContain('data-level="info"');

    expect(html).toMatch(/<button[^>]*class="cf-btn cf-btn--primary cf2-run"[^>]*disabled=""[^>]*title="Loading the conflict check\."[^>]*>Run the conflict check<\/button>/);
    expect(html).not.toContain("cf2-reason");
  });

  it("never asks for a name: once loaded the button can be pressed", () => {
    state.check = stubConflictCheck("9001");
    const html = render();
    expect(html).not.toContain("Type your name first.");
    expect(html).not.toContain("cf2-reason");
    expect(html).not.toMatch(/<button[^>]*class="cf2-run"[^>]*disabled=""/);
  });

  it("while a run is in progress, shows Checking... and disables the button, with no reason line", () => {
    state.check = stubConflictCheck("9003");
    state.busy = true;
    const html = render();
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*title="Checking\."[^>]*>Checking\.\.\.<\/button>/);
    expect(html).not.toContain("cf2-reason");
  });

  it("never checked (9001): warns that no check has been run, with no run line", () => {
    state.check = stubConflictCheck("9001");
    const html = render();
    expect(html).toContain('data-level="warn"');
    expect(html).toContain('role="status"');
    expect(html).toContain("No conflict check has been run for this client.");
    expect(html).toContain(">Run the conflict check</button>");
    expect(html).not.toContain("Loading the conflict check");
    expect(html).not.toContain("aud-conflict-matches");
    expect(html).not.toContain("Run by");
  });

  it("never checked but the forms say cleared: raises an alert", () => {
    state.check = stubConflictCheck("9001");
    const html = render({ answers: CLEARED });
    expect(html).toContain('role="alert"');
    expect(html).toContain("The forms already say the conflict check is cleared.");
  });

  it("no matches (9003): says none found, lists the gap and the run line, and offers Run it again", () => {
    state.check = stubConflictCheck("9003");
    const html = render();
    const t = text(html);
    expect(html).toContain("No matches found.");
    expect(html).toContain('data-level="warn"');
    expect(t).toContain("matched on name alone");
    expect(html).not.toContain("aud-conflict-matches");
    expect(t).toContain(`Run by ${DEMO_PRINCIPAL} on 10 September 2026. Compared with 3 other clients and 2 other parties on file.`);
    expect(html).toContain(">Run it again</button>");
  });

  it("possible matches (9002): alert headline, one line per match with strength, matter and reasons", () => {
    state.check = stubConflictCheck("9002");
    const html = render();
    const t = text(html);
    expect(html).toContain('role="alert"');
    expect(html).toContain("1 possible match to read before the conflict row is answered.");
    expect(html.match(/<li class="aud-conflict-match"/g)).toHaveLength(2);
    expect(html).toContain('data-strength="strong"');
    expect(html).toContain('data-strength="weak"');
    expect(t).toContain("Strong Respondent on this matter: Sam Stubrespondent may be Samuel Stubrespondent, client in another matter (260601/03FL, closed).");
    expect(t).toContain("Matched on: similar name, same date of birth.");
    expect(t).toContain("This client may be Second Stubperson, respondent in another matter (261001/01FL). Our client there: Stub Testperson.");

    expect(html).not.toMatch(/@|\+44|\b0\d{9,10}\b|\d{2}\/\d{2}\/\d{4}|\d{4}-\d{2}-\d{2}(?!T)/);
  });

  it("possible matches while the forms say cleared: adds the disagreement line", () => {
    state.check = stubConflictCheck("9002");
    expect(render({ answers: CLEARED })).toContain("The forms say the conflict check is cleared while possible matches are listed.");
  });

  it("a stale check with held-back matches: says to run it again and counts what is not listed", () => {
    state.check = { ...stubConflictCheck("9002"), stale: true, held_back: 1 };
    const html = render();
    expect(html).toContain("The people recorded on this matter have changed since this check was run. Run it again.");

    expect(html).toContain("1 weaker match is not listed.");
    expect(html).not.toContain("1 weaker matches");
  });

  it("an error: shows it as an alert, with no loading line", () => {
    state.error = "Could not load the conflict check.";
    const html = render();
    expect(html).toContain('<p class="cf2-error" role="alert">Could not load the conflict check.</p>');
    expect(html).not.toContain("Loading the conflict check");
    expect(html).not.toContain("aud-conflict-notice");
  });
});
