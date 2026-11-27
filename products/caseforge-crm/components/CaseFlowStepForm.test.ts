
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { blankStepForm } from "@/lib/pipelineForms";
import type { StepFormKind, StepFormValues } from "@/lib/pipelineForms";
import type { PipelineStep } from "@/lib/pipelineTypes";
import { CaseFlowStepFormView } from "./CaseFlowStepForm";
import type { CaseFlowStepFormViewProps } from "./CaseFlowStepForm";

const src = readFileSync(new URL("./CaseFlowStepForm.tsx", import.meta.url), "utf8");
const tab = readFileSync(new URL("./CaseFlowTab.tsx", import.meta.url), "utf8");

const STEP: PipelineStep = {
  key: "court_email",
  number: 9,
  label: "Application emailed to the court (drafted once)",
  status: "attention",
  summary: "Confirm the court before the email is drafted.",
  detail: [],
  can_run: false,
  run_label: "Draft the court email",
  variants: [],
  court_suggestions: [
    { name: "Sampletown Family Court", email: "family@example.invalid" },
    { name: "Elsewhere County Court", email: "" },
  ],
};

function render(kind: StepFormKind, over: Partial<CaseFlowStepFormViewProps> = {}, values: Partial<StepFormValues> = {}): string {
  const step = over.step ?? STEP;
  return renderToStaticMarkup(
    createElement(CaseFlowStepFormView, {
      kind,
      step,
      errors: {},
      serverError: "",
      busy: false,
      blocked: "",
      who: "Sam",
      onChange: () => {},
      onSubmit: () => {},
      onCancel: () => {},
      ...over,
      values: { ...blankStepForm(kind, step), ...values },
    }),
  );
}

const KINDS: StepFormKind[] = ["mark-done", "confirm-court", "add-recipient", "reset"];
const count = (html: string, re: RegExp) => html.match(re)?.length ?? 0;

describe("each form as it opens", () => {
  it("Mark done: the question, a note box with its limit, the button and Cancel", () => {
    const html = render("mark-done");
    expect(html).toContain('<form class="cf2-form" id="cf2-form-court_email-mark-done"');
    expect(html).toContain("Mark step 9, Application emailed to the court (drafted once), as done outside Case flow by Sam?");
    expect(html).toContain('<label for="cf2-form-court_email-mark-done-note">Note (optional)</label>');
    expect(html).toMatch(/<input id="cf2-form-court_email-mark-done-note"[^>]*maxLength="300"/);
    expect(html).toContain("0 of 300 characters");
    expect(html).toMatch(/<button type="submit" class="cf-btn cf-btn--primary cf2-run">Mark done<\/button>/);
    expect(html).toMatch(/<button type="button" class="cf-btn cf-btn--neutral cf2-reset-step">Cancel<\/button>/);
    expect(count(html, /<input /g)).toBe(1);
  });

  it("Confirm court: the first suggestion filled in, every suggestion listed, and an optional email", () => {
    const html = render("confirm-court");
    expect(html).toMatch(/<input id="cf2-form-court_email-confirm-court-court"[^>]*value="Sampletown Family Court"/);
    expect(html).toContain('aria-label="Courts the court finder suggests"');
    expect(html).toMatch(/<button type="button" class="cf-btn cf-btn--neutral cf2-suggestion" aria-pressed="true">Sampletown Family Court \(family@example\.invalid\)<\/button>/);
    expect(html).toMatch(/<button type="button" class="cf-btn cf-btn--neutral cf2-suggestion" aria-pressed="false">Elsewhere County Court \(no family email given\)<\/button>/);
    expect(html).toContain("Court&#x27;s email (optional)");
    expect(html).toContain("Record Sampletown Family Court as this matter&#x27;s court? Nothing is drafted or sent");
    expect(html).toMatch(/<button type="submit" class="cf-btn cf-btn--primary cf2-run">Confirm court<\/button>/);
  });

  it("Confirm court with no suggestion says so and starts empty", () => {
    const html = render("confirm-court", { step: { ...STEP, court_suggestions: [] } });
    expect(html).toContain("No suggestion from the court finder.");
    expect(html).not.toContain("cf2-suggestion");
    expect(html).toMatch(/<input id="cf2-form-court_email-confirm-court-court"[^>]*value=""/);
    expect(html).toContain("Choose one of the suggested courts, or type the court&#x27;s email.");
  });

  it("Add service recipient: the four kinds to choose from, a name and an email", () => {
    const html = render("add-recipient", { step: { ...STEP, key: "serve_other", number: 15 } });
    for (const kind of ["Law firm", "Hospital", "School", "Other"]) expect(html).toContain(`>${kind}</option>`);
    expect(html).toMatch(/<option value="law firm" selected="">/);
    expect(html).toContain(">Who they are</label>");
    expect(html).toContain(">Their name</label>");
    expect(html).toContain(">Their email address</label>");
    expect(html).toMatch(/<input id="cf2-form-serve_other-add-recipient-recipient"[^>]*maxLength="120"/);
    expect(html).toMatch(/<input id="cf2-form-serve_other-add-recipient-email"[^>]*maxLength="200"/);
    expect(html).toMatch(/<button type="submit" class="cf-btn cf-btn--primary cf2-run">Add recipient<\/button>/);
  });

  it("Add service recipient, filled in, says exactly who will be added", () => {
    const html = render("add-recipient", {}, { kind: "school", recipient: "Sample School", email: "office@sample.example" });
    expect(html).toContain("Add Sample School (school, office@sample.example) to serve, as Sam?");
  });

  it("Reset: the question and its promise, and no box at all", () => {
    const html = render("reset", { step: { ...STEP, status: "done" } });
    expect(html).toContain("Forget the mark on step 9,");
    expect(html).toContain("Files, folders, drafts and envelopes are NOT deleted.");
    expect(count(html, /<input |<select /g)).toBe(0);
    expect(html).toMatch(/<button type="submit" class="cf-btn cf-btn--primary cf2-run">Reset this step<\/button>/);
  });
});

describe("the states every form has", () => {
  it("never asks for a name: the press is recorded under the signed-in person", () => {
    for (const kind of KINDS) {
      const html = render(kind, { who: "" });
      expect(html, kind).not.toContain("Your name");
      expect(html, kind).not.toMatch(/-who"/);
    }
    expect(src).not.toContain("loadStoredEditorName");
    expect(src).toContain("useSignedInName()");
  });

  it("says what is wrong under the box it belongs to", () => {
    const court = render("confirm-court", { errors: { court: "Choose the court, or type its email." } }, { court: "" });
    expect(court).toMatch(/<input id="cf2-form-court_email-confirm-court-court"[^>]*aria-invalid="true"[^>]*aria-describedby="cf2-form-court_email-confirm-court-court-hint cf2-form-court_email-confirm-court-court-error"/);
    expect(court).toContain('<small class="cf2-field-error" id="cf2-form-court_email-confirm-court-court-error" role="alert">Choose the court, or type its email.</small>');
    expect(count(court, /aria-invalid="true"/g)).toBe(1);

    const recipient = render("add-recipient", { errors: { recipient: "Type their name.", email: "Type their email address." } });
    expect(recipient).toContain('role="alert">Type their name.</small>');
    expect(recipient).toContain('role="alert">Type their email address.</small>');
    expect(count(recipient, /aria-invalid="true"/g)).toBe(2);

    const note = render("mark-done", { errors: { note: "Keep the note to 300 characters or fewer." } });
    expect(note).toContain('role="alert">Keep the note to 300 characters or fewer.</small>');
  });

  it("while the request is on its way, every box and button is disabled and the button says so", () => {
    for (const kind of KINDS) {
      const html = render(kind, { busy: true });
      expect(html, kind).toContain('aria-busy="true"');
      const controls = count(html, /<(input|select|button) /g);
      expect(count(html, /<(input|select|button) [^>]*disabled=""/g), kind).toBe(controls);
      expect(html, kind).toMatch(kind === "reset" ? />Resetting\.\.\.<\/button>/ : />Saving\.\.\.<\/button>/);
    }
    expect(render("mark-done")).not.toContain("disabled");
  });

  it("shows the hub's reason in the form when the request fails, with the boxes open again", () => {
    for (const kind of KINDS) {
      const html = render(kind, { serverError: "this step is already done" });
      expect(html, kind).toContain('<p class="cf2-error" role="alert">Not done: this step is already done</p>');
      expect(html, kind).not.toContain("disabled");
      expect(html.indexOf("Not done:"), kind).toBeLessThan(html.indexOf('type="submit"'));
    }
  });

  it("holds its button, with the reason, while another step is running; Cancel still works", () => {
    const html = render("mark-done", { blocked: "A step is running." });
    expect(html).toMatch(/<button type="submit" class="cf-btn cf-btn--primary cf2-run" disabled="" title="A step is running\.">Mark done<\/button>/);
    expect(html).toContain('<small class="cf2-reason">A step is running.</small>');
    expect(html).toMatch(/<button type="button" class="cf-btn cf-btn--neutral cf2-reset-step">Cancel<\/button>/);
  });

  it("keeps what was typed on screen", () => {
    const html = render("mark-done", {}, { note: "unzipped by hand" });
    expect(html).toMatch(/value="unzipped by hand"/);
    expect(html).toContain("16 of 300 characters");
  });
});

describe("keys and focus (read from the source: not run in a browser)", () => {
  it("Enter sends and Escape cancels, but not while a request is on its way", () => {
    expect(src).toContain('if (event.key === "Escape")');
    expect(src).toContain("if (!busy) onCancel();");
    expect(src).toContain("event.currentTarget.requestSubmit();");
    expect(src).toMatch(/onSubmit=\{\(e\) => \{\s+e\.preventDefault\(\);\s+onSubmit\(\);/);
    expect(src).toContain("noValidate");
  });

  it("focus goes to the first box as the form opens, and to the box that is wrong after a refusal", () => {
    expect(src).toContain('querySelector<HTMLElement>("input, select, button[type=submit]")');
    expect(src).toContain(`querySelector<HTMLElement>('[aria-invalid="true"]')`);
    expect(src).toContain("}, [refusals]);");
  });

  it("focus goes back to the button that opened the form, or to the step when that button has gone", () => {
    expect(tab).toContain("if (opener && !opener.disabled) opener.focus();");
    expect(tab).toContain("else stepItems.current[focusBack.step]?.focus();");
    const close = tab.slice(tab.indexOf("function closeForm"), tab.indexOf("async function submitForm"));
    expect(close).toContain("setFocusBack(");
  });

  it("each form keeps its own boxes, so the tab's refresh does not clear them", () => {
    expect(tab).toContain("key={`${step.key}:${openForm}`}");
    expect(src).toContain("useState<StepFormValues>(() => blankStepForm(kind, step))");
  });
});
