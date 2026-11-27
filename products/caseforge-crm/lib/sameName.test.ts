import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { hasNamesake, nameWithSuffix, romanNumeral, sameNameHint, sameNameSuffix, sameNameTitle } from "./sameName";
import { stubSearch } from "./stub";

describe("romanNumeral", () => {
  it("is lower-case IMDb style", () => {
    expect([1, 2, 3, 4, 5, 9, 10, 14, 40, 90, 400, 1994].map(romanNumeral)).toEqual([
      "i", "ii", "iii", "iv", "v", "ix", "x", "xiv", "xl", "xc", "cd", "mcmxciv",
    ]);
  });
  it("is empty for anything that is not a positive whole number", () => {
    expect([0, -1, 1.5, Number.NaN, 4000].map(romanNumeral)).toEqual(["", "", "", "", ""]);
  });
});

describe("the suffix", () => {
  it("numbers only a name two or more different people share", () => {
    expect(sameNameSuffix({ same_name_index: 1, same_name_count: 2 })).toBe("(i)");
    expect(sameNameSuffix({ same_name_index: 2, same_name_count: 2 })).toBe("(ii)");
    expect(sameNameSuffix({ same_name_index: 3, same_name_count: 3 })).toBe("(iii)");
  });
  it("is empty for a unique name, a missing label, or a nonsense one", () => {
    expect(sameNameSuffix({ same_name_index: 1, same_name_count: 1 })).toBe("");
    expect(sameNameSuffix({})).toBe("");
    expect(sameNameSuffix(null)).toBe("");
    expect(sameNameSuffix({ same_name_index: 3, same_name_count: 2 })).toBe("");
    expect(hasNamesake({ same_name_index: 0, same_name_count: 2 })).toBe(false);
  });
  it("joins a name for one-line places", () => {
    expect(nameWithSuffix("SAMENAME", { same_name_index: 2, same_name_count: 2 })).toBe("SAMENAME (ii)");
    expect(nameWithSuffix("TESTPERSON", {})).toBe("TESTPERSON");
  });
  it("says what the number means in its tooltip", () => {
    expect(sameNameTitle({ same_name_index: 1, same_name_count: 2 })).toContain("2 different clients have this name");
    expect(sameNameTitle({ same_name_count: 1, same_name_index: 1 })).toBe("");
  });
});

describe("the birth year and reference line", () => {
  it("uses the hub's hints", () => {
    expect(sameNameHint({ same_name_index: 1, same_name_count: 2, same_name_birth_year: 1984, same_name_ref: "CaseForge-STUB-0011" })).toBe(
      "Born 1984 · Ref CaseForge-STUB-0011",
    );
  });
  it("falls back to the row's own date of birth and company reference", () => {
    expect(sameNameHint({ same_name_index: 2, same_name_count: 2, dob_iso: "1991-11-30", company_reference: "VAL9" })).toBe("Born 1991 · Ref VAL9");
  });
  it("says so when neither is on record", () => {
    expect(sameNameHint({ same_name_index: 2, same_name_count: 2 })).toBe("No birth year or reference on record");
  });
  it("is empty for a name nobody else has", () => {
    expect(sameNameHint({ same_name_index: 1, same_name_count: 1, dob_iso: "1990-01-01" })).toBe("");
  });
});

describe("stub mode", () => {
  it("has two different people called Stub Samename, numbered by the hub, and one person with two matters unnumbered", () => {
    const rows = stubSearch("samename").results;
    const same = rows.filter((r) => r.client_name === "Stub Samename");
    expect(same.map((r) => sameNameSuffix(r))).toEqual(["(i)", "(ii)"]);
    expect(same.map((r) => r.dob_iso)).toEqual(["1984-06-02", "1991-11-30"]);
    const testperson = rows.find((r) => String(r.matter_id) === "9001");
    expect(sameNameSuffix(testperson)).toBe("");
  });
});

describe("the label never matches anyone", () => {
  it("is not read by any matching or merge code in the viewer", () => {
    for (const file of ["lib/conflictCheck.ts", "components/MergeClientButton.tsx", "lib/newClient.ts"]) {
      const source = readFileSync(join(__dirname, "..", file), "utf8");
      expect(source, file).not.toMatch(/same_name_|sameName/);
    }
  });
});
