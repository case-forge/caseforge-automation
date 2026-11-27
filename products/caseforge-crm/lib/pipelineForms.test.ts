
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { sendStepForm } from "./pipeline";
import { stepRefCap } from "./pipelineTypes";
import {
  FIELD_LIMITS,
  blankStepForm,
  checkStepForm,
  closeStepForm,
  shownStepForm,
  stepFormBlockedReason,
  stepFormCopy,
  stepFormDoneMessage,
  stepFormFailedMessage,
  stepFormOffered,
  toggleStepForm,
} from "./pipelineForms";
import type { StepFormKind, StepFormValues } from "./pipelineForms";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

afterEach(() => vi.unstubAllGlobals());

function capture() {
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: JSON.parse(String(init?.body ?? "{}")) });
      return new Response(JSON.stringify({ matter_id: "9001", steps: [], events: [] }), { status: 200 });
    }),
  );
  return calls;
}

const blank: StepFormValues = { note: "", court: "", email: "", kind: "law firm", recipient: "" };
const step = { key: "court_email", number: 9, label: "Application emailed to the court", status: "attention", summary: "Confirm the court before the email is drafted." };

describe("which form a step shows", () => {
  it("offers each form only where its button is offered", () => {
    expect(stepFormOffered(step, "confirm-court")).toBe(true);
    expect(stepFormOffered(step, "mark-done")).toBe(true);
    expect(stepFormOffered(step, "add-recipient")).toBe(false);
    expect(stepFormOffered(step, "reset")).toBe(false);
    expect(stepFormOffered({ ...step, status: "done" }, "reset")).toBe(true);
    expect(stepFormOffered({ ...step, status: "done" }, "mark-done")).toBe(false);
    expect(stepFormOffered({ ...step, key: "serve_other", status: "not_needed" }, "add-recipient")).toBe(true);
  });

  it("opens one form at a time per step and leaves other steps alone", () => {
    let open: Record<string, StepFormKind> = {};
    open = toggleStepForm(open, "court_email", "mark-done");
    open = toggleStepForm(open, "serve", "mark-done");
    expect(open).toEqual({ court_email: "mark-done", serve: "mark-done" });
    open = toggleStepForm(open, "court_email", "confirm-court");
    expect(open).toEqual({ court_email: "confirm-court", serve: "mark-done" });
    open = toggleStepForm(open, "court_email", "confirm-court");
    expect(open).toEqual({ serve: "mark-done" });
    expect(closeStepForm(open, "serve")).toEqual({});
    expect(closeStepForm(open, "bundle")).toBe(open);
  });

  it("never changes the list it was given", () => {
    const open: Record<string, StepFormKind> = { serve: "mark-done" };
    toggleStepForm(open, "serve", "reset");
    closeStepForm(open, "serve");
    expect(open).toEqual({ serve: "mark-done" });
  });

  it("shows nothing while Case flow is locked, or once the step no longer offers the form", () => {
    const open: Record<string, StepFormKind> = { court_email: "mark-done" };
    expect(shownStepForm(open, step, "")).toBe("mark-done");
    expect(shownStepForm(open, step, "Locked: Case flow is not available for this client.")).toBeUndefined();
    expect(shownStepForm(open, { ...step, status: "done" }, "")).toBeUndefined();
    expect(shownStepForm({}, step, "")).toBeUndefined();
  });
});

describe("how a form opens", () => {
  it("fills in the first suggested court, and law firm as who they are", () => {
    const suggestions = [{ name: "Sampletown Family Court", email: "family@example.invalid" }, { name: "Elsewhere", email: "" }];
    expect(blankStepForm("confirm-court", { court_suggestions: suggestions }).court).toBe("Sampletown Family Court");
    expect(blankStepForm("confirm-court", {}).court).toBe("");
    expect(blankStepForm("mark-done", { court_suggestions: suggestions })).toEqual(blank);
    expect(blankStepForm("add-recipient", {}).kind).toBe("law firm");
  });
});

describe("the checks before a form is sent", () => {
  it("never asks for a name, and never sends one: the server records the signed-in person", () => {
    for (const kind of ["mark-done", "confirm-court", "add-recipient", "reset", "require-service"] as StepFormKind[]) {
      const out = checkStepForm(kind, { ...blank, court: "A court", recipient: "Sample School", email: "office@sample.example" });
      expect(out).toHaveProperty("request");
      expect(JSON.stringify(out)).not.toMatch(/"(who|by)"/);
    }
  });

  it("Mark done: the note is optional, trimmed, and at most 300 characters", () => {
    expect(checkStepForm("mark-done", blank)).toEqual({ request: { kind: "mark-done" } });
    expect(checkStepForm("mark-done", { ...blank, note: "   " })).toEqual({ request: { kind: "mark-done" } });
    expect(checkStepForm("mark-done", { ...blank, note: " unzipped by hand " })).toEqual({ request: { kind: "mark-done", note: "unzipped by hand" } });
    expect(FIELD_LIMITS.note).toBe(300);
    expect(checkStepForm("mark-done", { ...blank, note: "x".repeat(300) })).toHaveProperty("request.note", "x".repeat(300));
    expect(checkStepForm("mark-done", { ...blank, note: "x".repeat(301) })).toEqual({ errors: { note: "Keep the note to 300 characters or fewer." } });
  });

  it("Confirm court: needs the court or its email, and sends the email only when one is typed", () => {
    expect(checkStepForm("confirm-court", blank)).toEqual({ errors: { court: "Choose the court, or type its email." } });
    expect(checkStepForm("confirm-court", { ...blank, court: " Sampletown Family Court " })).toEqual({
      request: { kind: "confirm-court", court: "Sampletown Family Court" },
    });
    expect(checkStepForm("confirm-court", { ...blank, email: " family@example.invalid " })).toEqual({
      request: { kind: "confirm-court", court: "", email: "family@example.invalid" },
    });
    expect(checkStepForm("confirm-court", { ...blank, court: "x".repeat(201) })).toHaveProperty("errors.court", "Keep the court's name to 200 characters or fewer.");
    expect(checkStepForm("confirm-court", { ...blank, court: "A", email: "x".repeat(201) })).toHaveProperty("errors.email", "Keep the email to 200 characters or fewer.");
  });

  it("Add service recipient: needs one of the four kinds, a name and an email, and says every one that is missing", () => {
    expect(checkStepForm("add-recipient", { ...blank, kind: "bakery" })).toEqual({
      errors: { kind: "Say law firm, hospital, school or other.", recipient: "Type their name.", email: "Type their email address." },
    });
    expect(checkStepForm("add-recipient", { ...blank, kind: " School ", recipient: " Sample School ", email: " office@sample.example " })).toEqual({
      request: { kind: "add-recipient", recipientKind: "school", name: "Sample School", email: "office@sample.example" },
    });
    expect(checkStepForm("add-recipient", { ...blank, recipient: "x".repeat(121), email: "a@sample.example" })).toHaveProperty("errors.recipient", "Keep the name to 120 characters or fewer.");
  });

  it("Reset: needs nothing typed", () => {
    expect(checkStepForm("reset", blank)).toEqual({ request: { kind: "reset" } });
  });

  it("keeps to the lengths the routes cut to", () => {
    expect(read("../app/api/pipeline/mark-done/route.ts")).toContain(`.slice(0, ${FIELD_LIMITS.note})`);
    const court = read("../app/api/pipeline/confirm-court/route.ts");
    expect(court).toContain(`String(payload.court ?? "").trim().slice(0, ${FIELD_LIMITS.court})`);
    expect(court).toContain(`String(payload.email ?? "").trim().slice(0, ${FIELD_LIMITS.email})`);
    const recipient = read("../app/api/pipeline/service-recipient/route.ts");
    expect(recipient).toContain(`String(payload.name ?? "").trim().slice(0, ${FIELD_LIMITS.recipient})`);
    expect(recipient).toContain(`String(payload.email ?? "").trim().slice(0, ${FIELD_LIMITS.email})`);
  });
});

describe("what a form says", () => {
  it("Mark done names the step and the person, and says you until a name is known", () => {
    expect(stepFormCopy("mark-done", step, blank, "Sam")).toMatchObject({ title: "Mark done", submit: "Mark done", busy: "Saving..." });
    expect(stepFormCopy("mark-done", step, blank, "Sam").explain).toMatch(/^Mark step 9, Application emailed to the court, as done outside Case flow by Sam\?/);
    expect(stepFormCopy("mark-done", step, blank, "").explain).toContain("by you?");
  });

  it("Confirm court says what will be recorded, as it is typed", () => {
    expect(stepFormCopy("confirm-court", step, blank, "Sam").explain).toMatch(/^Choose one of the suggested courts, or type the court's email\./);
    expect(stepFormCopy("confirm-court", step, { ...blank, court: "Sampletown Family Court", email: "family@example.invalid" }, "Sam").explain).toMatch(
      /^Record Sampletown Family Court with the email family@example\.invalid as this matter's court\? Nothing is drafted or sent/,
    );
  });

  it("Add service recipient says who will be added once the form is filled in", () => {
    expect(stepFormCopy("add-recipient", step, blank, "Sam").explain).toMatch(/^Add a law firm, hospital, school or someone else to serve\./);
    expect(stepFormCopy("add-recipient", step, { ...blank, kind: "school", recipient: "Sample School", email: "office@sample.example" }, "Sam").explain).toMatch(
      /^Add Sample School \(school, office@sample\.example\) to serve, as Sam\?/,
    );
  });

  it("Reset keeps its promise that nothing is deleted", () => {
    const copy = stepFormCopy("reset", step, blank, "Sam");
    expect(copy).toMatchObject({ submit: "Reset this step", busy: "Resetting..." });
    expect(copy.explain).toContain("Files, folders, drafts and envelopes are NOT deleted");
  });

  it("says what happened, or that it did not when the hub gives no reason", () => {
    expect(stepFormDoneMessage({ kind: "mark-done" })).toBe("Marked done outside Case flow.");
    expect(stepFormDoneMessage({ kind: "confirm-court", court: "A" })).toBe("Court confirmed. The court email can now be drafted.");
    expect(stepFormDoneMessage({ kind: "add-recipient", recipientKind: "school", name: "Sample School", email: "e" })).toBe(`Sample School added. ${stepRefCap("serve_other")} can now draft their email.`);
    expect(stepFormDoneMessage({ kind: "reset" })).toMatch(/Nothing was deleted\.$/);
    expect(stepFormFailedMessage("mark-done")).toBe("Could not mark the step done.");
    expect(stepFormFailedMessage("confirm-court")).toBe("Could not confirm the court.");
    expect(stepFormFailedMessage("add-recipient")).toBe("Could not add the recipient.");
    expect(stepFormFailedMessage("reset")).toBe("Could not reset the step.");
  });

  it("holds its button while another step is running, but not for its own request", () => {
    expect(stepFormBlockedReason({ running: "", busy: false })).toBe("");
    expect(stepFormBlockedReason({ running: "serve:", busy: false })).toBe("A step is running.");
    expect(stepFormBlockedReason({ running: "court_email:mark-done", busy: true })).toBe("");
  });
});

describe("what a checked form sends", () => {
  it("goes to the same routes, with no name in any body", async () => {
    const calls = capture();
    await sendStepForm("9001", "folder", { kind: "mark-done", note: "unzipped by hand" });
    await sendStepForm("9001", "folder", { kind: "mark-done" });
    await sendStepForm("9001", "court_email", { kind: "confirm-court", court: "Sampletown Family Court" });
    await sendStepForm("9001", "court_email", { kind: "confirm-court", court: "", email: "family@example.invalid" });
    await sendStepForm("9001", "serve_other", { kind: "add-recipient", recipientKind: "school", name: "Sample School", email: "office@sample.example" });
    await sendStepForm("9001", "folder", { kind: "reset" });
    expect(calls).toEqual([
      { url: "/api/pipeline/mark-done", body: { matter_id: "9001", step: "folder", note: "unzipped by hand" } },
      { url: "/api/pipeline/mark-done", body: { matter_id: "9001", step: "folder" } },
      { url: "/api/pipeline/confirm-court", body: { matter_id: "9001", court: "Sampletown Family Court" } },
      { url: "/api/pipeline/confirm-court", body: { matter_id: "9001", court: "", email: "family@example.invalid" } },
      { url: "/api/pipeline/service-recipient", body: { matter_id: "9001", kind: "school", name: "Sample School", email: "office@sample.example" } },
      { url: "/api/pipeline/reset-step", body: { matter_id: "9001", step: "folder" } },
    ]);
  });

  it("passes the hub's reason on when it refuses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "this step is already done" }), { status: 422 })));
    await expect(sendStepForm("9001", "folder", { kind: "mark-done" })).rejects.toThrow("this step is already done");
  });
});

describe("no browser dialog in the Case flow tab", () => {
  it("has no prompt, confirm or alert in the tab, its form, or the pipeline library", () => {
    for (const file of ["../components/CaseFlowTab.tsx", "../components/CaseFlowStepForm.tsx", "./pipeline.ts", "./pipelineDisplay.ts", "./pipelineForms.ts"]) {
      expect(read(file), file).not.toMatch(/\b(prompt|confirm|alert)\(/);
    }
  });
});

describe("the personal service form", () => {
  it("is offered on the referrer step only while it reads not needed", () => {
    expect(stepFormOffered({ key: "serve", label: "x", status: "not_needed" }, "require-service")).toBe(true);
    expect(stepFormOffered({ key: "serve", label: "x", status: "todo" }, "require-service")).toBe(false);
    expect(stepFormOffered({ key: "serve_other", label: "x", status: "not_needed" }, "require-service")).toBe(false);
  });

  it("needs nothing typed and sends only the kind", () => {
    const values = blankStepForm("require-service", {});
    expect(checkStepForm("require-service", values)).toEqual({ request: { kind: "require-service" } });
  });
});
