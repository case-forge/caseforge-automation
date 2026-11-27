
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { stubAmendPrepare, stubPipeline } from "@/lib/stubPipeline";
import type { Pipeline, PipelineStep } from "@/lib/pipelineTypes";
import { CaseFlowAmendPanel } from "./CaseFlowAmendPanel";

const tab = readFileSync(new URL("./CaseFlowTab.tsx", import.meta.url), "utf8");

function amendStep(p: Pipeline): PipelineStep {
  const step = p.steps.find((s) => s.key === "amend");
  if (!step) throw new Error("no amend step");
  return step;
}

function render(step: PipelineStep, opts: { locked?: string; running?: string } = {}): string {
  return renderToStaticMarkup(
    createElement(CaseFlowAmendPanel, {
      matterId: "amend-view",
      step,
      locked: opts.locked ?? "",
      running: opts.running ?? "",
      setRunning: () => {},
      setData: () => {},
      refresh: () => {},
    }),
  );
}

describe("CaseFlowAmendPanel", () => {
  it("with no round open, shows one button and no paste box, so the row stays short", () => {
    const html = render(amendStep(stubPipeline("amend-view-1")));
    expect(html).toContain("Paste the client&#x27;s email asking for changes");
    expect(html).not.toContain("<textarea");
    expect(html).not.toContain("Prepare the amended statement");
    expect(html).not.toMatch(/rounds so far/i);
  });

  it("opens the paste box, filled in, when the client's amend note is on record", () => {
    const step = amendStep(stubPipeline("amend-view-6"));
    const hinted: PipelineStep = { ...step, amend: { ...step.amend!, email_hint: "Paragraph 4 is wrong." } };
    const html = render(hinted);
    expect(html).toContain("The client&#x27;s email asking for changes");
    expect(html).toContain("Paragraph 4 is wrong.");
    expect(html).toContain("Prepare the amended statement");
    expect(html).toMatch(/a minute or two/);
    expect(html).toMatch(/Nothing is saved or sent until you approve/);
  });

  it("shows no form when a round cannot be started; the step's detail says why", () => {
    const step = amendStep(stubPipeline("amend-view-7"));
    const blocked: PipelineStep = { ...step, amend: { ...step.amend!, can_start: false, start_blocked: "The signed statement is on file." } };
    const html = render(blocked);
    expect(html).not.toContain("<textarea");
    expect(html).not.toContain("<button");
  });

  it("is disabled with the lock reason for a locked client", () => {
    const html = render(amendStep(stubPipeline("amend-view-2")), { locked: "Locked: no worker." });
    expect(html).toContain("Locked: no worker.");
    expect(html).toContain("disabled");
  });

  it("shows a prepared round: paragraphs, badges, keep boxes, questions, database updates, and both buttons", () => {
    const p = stubAmendPrepare("amend-view-3", "Sam", "Please change it.");
    if ("error" in p) throw new Error(p.error);
    const html = render(amendStep(p));
    expect(html).toContain("Paragraph 4");
    expect(html).toContain("New paragraph (added at the end)");
    expect(html).toContain("<del>");
    expect(html).toContain("<ins>");
    expect(html).toContain("REVIEW");
    expect(html).toContain("Editorialising");
    expect(html).toContain("Facts not read");
    expect(html.match(/type="checkbox"/g)?.length).toBe(4);
    expect(html.match(/>Edit</g)?.length).toBe(4);
    expect(html).not.toContain("Your text for this paragraph");
    expect(html).toContain("Keep the original");
    expect(html).toContain("Your answers to the client&#x27;s questions (go into the email)");
    expect(html).toContain("Asks for advice");
    expect(html).toContain("Not applied. Change them on the Client tab if they are right; the signed statement wins.");
    expect(html).toContain("Approve: save the statement and draft the email");
    expect(html).toContain("Discard this round");
    expect(html).not.toContain("Prepare the amended statement");
  });

  it("offers to draft the email only, for a round whose statement is saved", () => {
    const p = stubAmendPrepare("amend-view-4", "Sam", "Change it.");
    if ("error" in p) throw new Error(p.error);
    const step = amendStep(p);
    const saved: PipelineStep = { ...step, amend: { ...step.amend!, open: { ...step.amend!.open!, status: "saved" } } };
    const html = render(saved);
    expect(html).toContain("Draft email (the statement is already saved)");
    expect(html).not.toContain("Your text for this paragraph");

    expect(html).not.toContain("Discard this round");
  });

  it("labels a hand-edited paragraph of a saved round and shows the proposal it replaced", () => {
    const p = stubAmendPrepare("amend-view-8", "Sam", "Change it.");
    if ("error" in p) throw new Error(p.error);
    const step = amendStep(p);
    const open = step.amend!.open!;
    const paragraphs = open.paragraphs.map((x, n) => (n === 0 ? { ...x, edited: true, model_after: x.after, after: "My own words." } : x));
    const saved: PipelineStep = { ...step, amend: { ...step.amend!, open: { ...open, status: "saved", paragraphs } } };
    const html = render(saved);
    expect(html).toContain("Edited by you");
    expect(html).toContain("Written by you; the proposal was:");
    expect(html).toContain("My own words");
  });

  it("says when the client is flagged", () => {
    const step = amendStep(stubPipeline("amend-view-5"));
    const flagged: PipelineStep = { ...step, amend: { ...step.amend!, rounds: 3, flagged: true } };
    expect(render(flagged)).toContain("Round 3: this client is flagged (3 or more rounds).");
  });

  it("is shown by the tab under step 6 only, never for a demo step, and the step has no run button", () => {
    expect(tab).toContain('!step.game && step.key === "amend" && step.amend && (');
    expect(tab).toContain('step.key === "amend" || step.status === "not_needed" ? []');
  });
});
