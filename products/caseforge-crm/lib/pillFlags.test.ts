import { describe, expect, it } from "vitest";
import { pillFlagsToShow } from "./types";

describe("pillFlagsToShow", () => {
  const flags = { cat_nmo_cao: true, transferred: true, billed: false };
  it("shows a category pill when the matter has no order tag", () => {
    expect(pillFlagsToShow(flags, false).map((f) => f.name)).toEqual(["transferred", "cat_nmo_cao"]);
  });
  it("drops the category pill once an order tag says it, but keeps the status pills", () => {
    expect(pillFlagsToShow(flags, true).map((f) => f.name)).toEqual(["transferred"]);
  });
  it("keeps CARE beside the name even when the matter has order tags", () => {
    const care = { cat_care_proceedings: true, cat_nmo_cao: true, transferred: true };
    expect(pillFlagsToShow(care, true).map((f) => f.label)).toEqual(["Transferred", "CARE"]);
  });
  it("is empty with no flags", () => {
    expect(pillFlagsToShow(undefined, true)).toEqual([]);
  });
});
