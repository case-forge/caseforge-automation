
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { addServiceRecipient, confirmPipelineCourt } from "./pipeline";
import { canConfirmCourt, confirmCourtCheck, courtSuggestionLabel, recipientKind, serviceRecipientCheck } from "./pipelineDisplay";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

afterEach(() => vi.unstubAllGlobals());

function capture() {
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: JSON.parse(String(init?.body ?? "{}")) });
      return new Response(JSON.stringify({ matter_id: "603", steps: [], events: [] }), { status: 200 });
    }),
  );
  return calls;
}

describe("Confirm court", () => {
  it("is offered on step 9 only while a court is waiting to be confirmed", () => {
    const waiting = { key: "court_email", status: "attention", summary: "Confirm the court before the email is drafted.", court_suggestions: [] };
    expect(canConfirmCourt(waiting)).toBe(true);
    expect(canConfirmCourt({ ...waiting, summary: "x", court_suggestions: [{ name: "A", email: "" }] })).toBe(true);
    expect(canConfirmCourt({ ...waiting, summary: "Ready to draft the court email." })).toBe(false);
    expect(canConfirmCourt({ ...waiting, status: "done" })).toBe(false);
    expect(canConfirmCourt({ ...waiting, key: "serve" })).toBe(false);
  });

  it("lists each suggested court with its email, and says what will be recorded", () => {
    expect(courtSuggestionLabel({ name: "Sampletown Family Court", email: "family@justice.gov.uk" })).toBe("Sampletown Family Court (family@justice.gov.uk)");
    expect(courtSuggestionLabel({ name: "Elsewhere", email: "" })).toBe("Elsewhere (no family email given)");
    expect(confirmCourtCheck("Sampletown Family Court", "")).toMatch(/^Record Sampletown Family Court as this matter's court\? Nothing is drafted or sent/);
  });

  it("posts the court and the email to the route, never a name", async () => {
    const calls = capture();
    await confirmPipelineCourt("603", "Sampletown Family Court");
    await confirmPipelineCourt("603", "", "family@justice.gov.uk");
    expect(calls[0]).toEqual({ url: "/api/pipeline/confirm-court", body: { matter_id: "603", court: "Sampletown Family Court" } });
    expect(calls[1].body).toEqual({ matter_id: "603", court: "", email: "family@justice.gov.uk" });
  });

  it("in the tab, opens a form under step 9, which is checked before it is sent, and refreshes after", () => {
    const tab = read("../components/CaseFlowTab.tsx");
    const fn = tab.slice(tab.indexOf("async function submitForm"), tab.indexOf("async function changeMode"));
    expect(fn).toContain("sendStepForm(matterId, step.key, request)");
    expect(fn).toContain("refresh()");
    expect(tab).toContain("canConfirmCourt(step) &&");
    expect(tab).toContain('{...opens(step, "confirm-court", openForm)}');

    const form = read("../components/CaseFlowStepForm.tsx");
    expect(form).toContain("courtSuggestionLabel(s)");
    expect(form.indexOf("checkStepForm(kind, values)")).toBeLessThan(form.indexOf("await onSubmit(checked.request)"));
    expect(read("./pipelineForms.ts")).toContain("confirmCourtCheck(court, email)");
  });

  it("has a route that records the signed-in person, needs a court or email, and goes to the hub", () => {
    const route = read("../app/api/pipeline/confirm-court/route.ts");
    expect(route).toContain('"/client-viewer/pipeline/confirm-court"');
    expect(route).toContain("editorFor(remoteUser)");
    expect(route).not.toContain("type your name first");
    expect(route).toContain("choose the court, or type its email");
  });
});

describe("Add service recipient", () => {
  it("accepts only the four kinds", () => {
    expect(recipientKind(" Law  Firm ")).toBe("law firm");
    expect(recipientKind("school")).toBe("school");
    expect(recipientKind("bakery")).toBe("");
    expect(serviceRecipientCheck("school", "Sample School", "office@sample.example", "Sam")).toMatch(/^Add Sample School \(school, office@sample\.example\) to serve, as Sam\? .*nothing is sent\.$/);
  });

  it("posts the kind, name and email, never the person's name", async () => {
    const calls = capture();
    await addServiceRecipient("603", "school", "Sample School", "office@sample.example");
    expect(calls[0]).toEqual({
      url: "/api/pipeline/service-recipient",
      body: { matter_id: "603", kind: "school", name: "Sample School", email: "office@sample.example" },
    });
  });

  it("in the tab, sits on step 15 and opens a form that is checked before it is sent", () => {
    const tab = read("../components/CaseFlowTab.tsx");
    expect(tab).toContain('step.key === "serve_other" &&');
    expect(tab).toContain('{...opens(step, "add-recipient", openForm)}');
    expect(tab).toContain("Add service recipient");
    const forms = read("./pipelineForms.ts");
    expect(forms).toContain("recipientKind(values.kind)");
    expect(forms).toContain("serviceRecipientCheck(exact, name, email, by)");
  });

  it("has a route that checks the kind and records the signed-in person before going to the hub", () => {
    const route = read("../app/api/pipeline/service-recipient/route.ts");
    expect(route).toContain('"/client-viewer/pipeline/service-recipient"');
    expect(route).toContain("recipientKind(");
    expect(route).toContain("editorFor(remoteUser)");
    expect(route).not.toContain("type your name first");
  });
});
