
import { describe, expect, it } from "vitest";
import { MAX_EDITOR_LENGTH, TAILNET_EDITOR, displayNameFor, editorFor } from "./editor";

const WORKERS = ["Alex", "Sam"] as const;

describe("displayNameFor", () => {
  it("is the worker whose first name starts the email", () => {
    expect(displayNameFor("alex@example.test", WORKERS)).toBe("Alex");
    expect(displayNameFor("ALEX.smith@example.test", WORKERS)).toBe("Alex");
    expect(displayNameFor("sam_jones@example.test", WORKERS)).toBe("Sam");
    expect(displayNameFor("sam-jones@example.test", WORKERS)).toBe("Sam");
    expect(displayNameFor("sam+crm@example.test", WORKERS)).toBe("Sam");
  });

  it("is the email itself when no worker matches", () => {
    expect(displayNameFor("office@example.test", WORKERS)).toBe("office@example.test");
    expect(displayNameFor("  alexandra@example.test ", WORKERS)).toBe("alexandra@example.test");
    expect(displayNameFor("alex@example.test", [])).toBe("alex@example.test");
  });

  it("is never longer than every hub actor field allows", () => {
    expect(displayNameFor(`${"x".repeat(80)}@example.test`, WORKERS)).toHaveLength(MAX_EDITOR_LENGTH);
  });

  it("is empty for an empty email", () => {
    expect(displayNameFor("   ", WORKERS)).toBe("");
  });
});

describe("editorFor", () => {
  it("names the signed-in person", () => {
    expect(editorFor("sam@example.test", WORKERS)).toBe("Sam");
    expect(editorFor("office@example.test", WORKERS)).toBe("office@example.test");
  });

  it("is tailnet with no Access identity", () => {
    expect(editorFor(null, WORKERS)).toBe(TAILNET_EDITOR);
    expect(editorFor(undefined, WORKERS)).toBe(TAILNET_EDITOR);
    expect(editorFor("  ", WORKERS)).toBe(TAILNET_EDITOR);
    expect(TAILNET_EDITOR).toBe("tailnet");
  });
});
