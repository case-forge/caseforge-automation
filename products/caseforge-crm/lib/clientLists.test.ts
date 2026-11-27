import { describe, expect, it } from "vitest";
import { CLIENT_LISTS, listFromParam, listHref } from "./clientLists";

describe("the Client lists tabs", () => {
  it("has Duplicates, Removed and Merged, each with a reader of its own (no flag)", () => {
    for (const id of ["duplicates", "removed", "merged"]) {
      const list = CLIENT_LISTS.find((l) => l.id === id);
      expect(list, id).toBeDefined();
      expect(list?.flag).toBeUndefined();
    }
  });

  it("opens each by its address, and To check when the address names none", () => {
    expect(listFromParam("merged")).toBe("merged");
    expect(listHref("removed")).toBe("/client-lists?list=removed");
    expect(listFromParam("nonsense")).toBe("to-check");
  });
});
