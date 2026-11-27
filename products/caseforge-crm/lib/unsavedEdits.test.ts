import { afterEach, describe, expect, it, vi } from "vitest";
import { confirmDiscardUnsaved, confirmLeaveUnsaved, describeUnsaved, setUnsaved, unsavedLabels, unsavedSources } from "./unsavedEdits";

function stubWindow(answer: boolean) {
  const confirm = vi.fn((_message: string) => answer);
  vi.stubGlobal("window", { confirm, addEventListener: vi.fn() });
  return confirm;
}

afterEach(() => {
  setUnsaved("a", null);
  setUnsaved("b", null);
  vi.unstubAllGlobals();
});

describe("leaving unsaved edits", () => {
  it("lets you go without asking when nothing is unsaved", () => {
    const confirm = stubWindow(false);
    expect(confirmLeaveUnsaved()).toBe(true);
    expect(confirm).not.toHaveBeenCalled();
  });

  it("asks once, naming what is unsaved, and stays put on Cancel", () => {
    const confirm = stubWindow(false);
    setUnsaved("a", "Client details");
    setUnsaved("b", "Children");
    expect(confirmLeaveUnsaved()).toBe(false);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(confirm.mock.calls[0][0]).toContain("Client details; Children");
    expect(unsavedLabels()).toEqual(["Client details", "Children"]);
  });

  it("forgets what is unsaved once you agree, so a two-step move asks only once", () => {
    const confirm = stubWindow(true);
    setUnsaved("a", "Client details");
    expect(confirmLeaveUnsaved()).toBe(true);
    expect(confirmLeaveUnsaved()).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it("asks only about the sources named, and leaves the others standing", () => {
    const confirm = stubWindow(true);
    setUnsaved("a", "Client details");
    setUnsaved("b", "Hearing");
    expect(confirmLeaveUnsaved(["b"])).toBe(true);
    expect(confirm.mock.calls[0][0]).toContain("Hearing");
    expect(confirm.mock.calls[0][0]).not.toContain("Client details");
    expect(unsavedLabels()).toEqual(["Client details"]);
    expect(confirmLeaveUnsaved(["b"])).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it("stops counting an edit once it reports clean", () => {
    stubWindow(false);
    setUnsaved("a", "Client details");
    setUnsaved("a", null);
    expect(confirmLeaveUnsaved()).toBe(true);
  });
});

describe("naming which client and which form", () => {
  it("says the form, the client as the CRM shows it, and the tab", () => {
    expect(describeUnsaved({ label: "Client details", matterId: "STUB-001", clientName: "Sample Client", place: "Client tab" })).toBe(
      "Client details for Sample Client (Client tab)",
    );
  });

  it("falls back to the matter number with no name, and to the form alone with neither", () => {
    expect(describeUnsaved({ label: "Hearing", matterId: "42" })).toBe("Hearing for matter 42");
    expect(describeUnsaved({ label: "New to-do", place: "To-do list" })).toBe("New to-do (To-do list)");
    expect(describeUnsaved({ label: "New hearing" })).toBe("New hearing");
  });

  it("keeps each source's identity for Show me, and names it in the labels and the leave question", () => {
    const confirm = stubWindow(false);
    setUnsaved("a", { label: "Children", matterId: "STUB-001", clientName: "Sample Client", place: "Other Parties tab" });
    expect(unsavedSources()).toEqual([
      { id: "a", label: "Children", matterId: "STUB-001", clientName: "Sample Client", place: "Other Parties tab" },
    ]);
    expect(unsavedLabels()).toEqual(["Children for Sample Client (Other Parties tab)"]);
    confirmLeaveUnsaved();
    expect(confirm.mock.calls[0][0]).toContain("Children for Sample Client (Other Parties tab)");
    expect(confirm.mock.calls[0][0]).toContain("kept as a draft");
  });

  it("asks to discard, not to leave, when the form stays on screen", () => {
    const confirm = stubWindow(true);
    setUnsaved("a", { label: "Hearing", clientName: "Sample Client" });
    setUnsaved("b", "Client details");
    expect(confirmDiscardUnsaved(["a"])).toBe(true);
    expect(confirm.mock.calls[0][0]).toBe("Discard your unsaved changes: Hearing for Sample Client?");
    expect(unsavedLabels()).toEqual(["Client details"]);
  });
});
