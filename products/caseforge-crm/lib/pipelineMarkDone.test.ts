
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { canMarkDone, eventStatusWord, markDoneQuestion } from "./pipelineDisplay";
import { stubMarkDone, stubPipeline } from "./stubPipeline";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("Mark done", () => {
  it("is offered on every step that is not done", () => {
    expect(canMarkDone({ status: "todo" })).toBe(true);
    expect(canMarkDone({ status: "blocked" })).toBe(true);
    expect(canMarkDone({ status: "attention" })).toBe(true);
    expect(canMarkDone({ status: "done" })).toBe(false);
  });

  it("asks a plain question naming the step and the person", () => {
    const q = markDoneQuestion({ number: 4, label: "Witness statement drafted" }, "Sam");
    expect(q).toMatch(/^Mark step 4, Witness statement drafted, as done outside Case flow by Sam\?/);
    expect(q).toMatch(/reset undoes it/);
    expect(markDoneQuestion({ label: "Something" }, "C")).toMatch(/^Mark Something,/);
  });

  it("names the log entry it writes", () => {
    expect(eventStatusWord("outside")).toBe("Outside");
    expect(eventStatusWord("ok")).toBe("Worked");
    expect(eventStatusWord("mystery")).toBe("Note");
  });

  it("in the stub, marks the step done with who and when, logs the note, and refuses a second mark", () => {
    const out = stubMarkDone("md-1", "folder", "Alex", "unzipped by hand");
    expect("error" in out).toBe(false);
    if (!("error" in out)) {
      const step = out.steps.find((s) => s.key === "folder");
      expect(step?.status).toBe("done");
      expect(step?.outside).toBe("by_hand");
      expect(step?.summary).toMatch(/^Done outside Case flow by Alex on \d{1,2} \w+ \d{4}\.$/);
      expect(out.steps.find((s) => s.key === "statement")?.status).toBe("todo");
      expect(out.events.at(-1)).toMatchObject({ step: "folder", status: "outside", by: "Alex" });
      expect(out.events.at(-1)?.summary).toMatch(/Note: unzipped by hand$/);
    }
    expect(stubMarkDone("md-1", "folder", "C", "")).toHaveProperty("error");
    expect(stubMarkDone("md-1", "nonsense", "C", "")).toHaveProperty("error");
    expect(stubPipeline("md-2").steps.every((s) => !s.outside)).toBe(true);
  });

  it("in the tab, opens a form under the step that never asks for a name, and refreshes after", () => {
    const tab = read("../components/CaseFlowTab.tsx");
    const fn = tab.slice(tab.indexOf("async function submitForm"), tab.indexOf("async function changeMode"));
    expect(fn).toContain("sendStepForm(matterId, step.key, request)");
    expect(fn).not.toContain("storeEditorName");
    expect(fn).toContain("refresh()");
    expect(tab).toContain("canMarkDone(step) &&");
    expect(tab).toContain('{...opens(step, "mark-done", openForm)}');
    expect(tab).toContain('disabled={locked !== "" || running !== ""}');

    const toggle = tab.slice(tab.indexOf("function toggleForm"), tab.indexOf("function closeForm"));
    expect(toggle).not.toContain("sendStepForm(");
    const form = read("../components/CaseFlowStepForm.tsx");
    expect(form).not.toContain("Your name");
    expect(form).toContain("useSignedInName()");
    expect(read("./pipelineForms.ts")).toContain("markDoneQuestion(step, by)");
  });

  it("has a route that records the signed-in person and passes the note on to the hub", () => {
    const route = read("../app/api/pipeline/mark-done/route.ts");
    expect(route).toContain('"/client-viewer/pipeline/mark-done"');
    expect(route).toContain("editorFor(remoteUser)");
    expect(route).not.toContain("type your name first");
    expect(route).toContain("note: note || null");
  });
});
