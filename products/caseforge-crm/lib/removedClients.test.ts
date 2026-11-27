import { describe, expect, it } from "vitest";
import {
  changeRows,
  detailRows,
  conflictLabel,
  mergeConfirmed,
  mergeMoveLines,
  pickAll,
  picksBody,
  removeConfirmed,
  removedStateLabel,
  isMergeRow,
  undoExplanation,
  undoActionFor,
  type MergePreview,
  type RemovedClient,
} from "./removedClients";

const row = (patch: Partial<RemovedClient>): RemovedClient => ({
  matter_id: "1",
  client_name: "Testa Fakename",
  reason: "Duplicate",
  removed_by: "CO",
  removed_utc: "2026-10-15T10:00:00Z",
  state: "removed",
  merged_into: "",
  merged_into_name: "",
  folder_moved: true,
  restored_by: "",
  restored_utc: "",
  purged_utc: "",
  purge_note: "",
  can_undo: true,
  ...patch,
});

describe("removeConfirmed", () => {
  it("needs the client's name, ignoring case and spacing", () => {
    expect(removeConfirmed("  testa   FAKENAME ", "Testa Fakename")).toBe(true);
    expect(removeConfirmed("Testa Fakenam", "Testa Fakename")).toBe(false);
    expect(removeConfirmed("", "")).toBe(false);
  });
});

describe("removedStateLabel", () => {
  it("says a real client past the window is a tombstone, never purged", () => {
    expect(removedStateLabel(row({ can_undo: false }))).toContain("never purged");
    expect(removedStateLabel(row({ state: "purged" }))).toBe("Purged");
    expect(removedStateLabel(row({ state: "restored", restored_by: "CO" }))).toBe("Restored by CO");
  });
});

describe("merge", () => {
  const preview: MergePreview = {
    from: { matter_id: "1", client_name: "Dupa Clientone" },
    into: { matter_id: "2", client_name: "Dupa Client-One" },
    refusals: [],
    moves: [
      { label: "Hearings", table: "matter_hearings", move: 2, stay: 0 },
      { label: "Flags", table: "matter_flags", move: 1, stay: 1 },
    ],
    folder: { action: "none" },
  };

  it("lists what moves and what stays", () => {
    expect(mergeMoveLines(preview)).toEqual(["Hearings: 2 move", "Flags: 1 move, 1 stay on matter 1 (matter 2 already has its own)"]);
  });

  it("says how many stage dates are added to the kept client", () => {
    const dates: MergePreview = {
      ...preview,
      moves: [{ label: "Stage dates (the earlier kept)", table: "stage_dates", move: 0, stay: 0, added: 3, added_tables: ["matter_milestones"] }],
    };
    expect(mergeMoveLines(dates)).toEqual(["Stage dates (the earlier kept): 3 added to matter 2 from matter 1"]);
  });

  it("says what is filled in from the merged-away client, and what differs and stays", () => {
    const filled: MergePreview = {
      ...preview,
      moves: [{ label: "Details filled in", table: "fills", move: 0, stay: 0, fill: 2, fill_columns: ["people.email_primary"], conflicts: ["people.dob_iso"] }],
    };
    expect(mergeMoveLines(filled)).toEqual([
      "Details filled in: 2 empty on matter 2 filled from matter 1 (people.email_primary); differs, matter 2's kept unless you choose matter 1's: people.dob_iso",
    ]);
  });

  it("needs both names typed, and no refusal", () => {
    expect(mergeConfirmed(preview, "dupa clientone", "Dupa Client-One")).toBe(true);
    expect(mergeConfirmed(preview, "Dupa Clientone", "Dupa Clientone")).toBe(false);
    expect(mergeConfirmed({ ...preview, refusals: ["One is a test client"] }, "Dupa Clientone", "Dupa Client-One")).toBe(false);
    expect(mergeConfirmed(null, "a", "b")).toBe(false);
  });

  it("sends only the picks that differ from the defaults, and the shortcuts set every field", () => {
    const withChoices: MergePreview = {
      ...preview,
      choices: {
        conflicts: [
          { id: "people.dob_iso", column: "people.dob_iso", a: "1990-04-16", b: "1990-03-15", choice: "b" },
          { id: "people.phone_primary", column: "people.phone_primary", a: "0111", b: "0222", choice: "b" },
        ],
        second_applicants: [
          { id: "second_applicant:13", party_id: 13, b_party_id: 21, name: "Applicant A", dob: "1985-05-05", b_name: "Applicant A", b_dob: "1985-06-06", choice: "keep" },
        ],
      },
    };
    expect(picksBody(withChoices, {})).toEqual({ "second_applicant:13": "discard" });
    expect(picksBody(withChoices, { "second_applicant:13": "keep" })).toEqual({ "second_applicant:13": "keep" });
    expect(picksBody(withChoices, { "people.dob_iso": "a", "people.phone_primary": "b", "second_applicant:13": "discard" })).toEqual({
      "people.dob_iso": "a",
      "second_applicant:13": "discard",
    });
    expect(pickAll(withChoices, "a", { "second_applicant:13": "discard" })).toEqual({
      "people.dob_iso": "a",
      "people.phone_primary": "a",
      "second_applicant:13": "discard",
    });
    expect(picksBody(withChoices, pickAll(withChoices, "b", { "people.dob_iso": "a" }))).toEqual({ "second_applicant:13": "discard" });
    expect(picksBody(null, { x: "a" })).toEqual({});
    expect(conflictLabel("people.dob_iso")).toBe("Date of birth (client)");
    expect(conflictLabel("matter_parties.email_primary")).toBe("Email (party)");
  });

  it("undoes a merge by its own route and labels it", () => {
    const merged = row({ state: "merged", merged_into: "2" });
    expect(undoActionFor(merged)).toBe("undo-merge");
    expect(undoActionFor(row({}))).toBe("undo");
    expect(removedStateLabel(merged)).toBe("Merged into matter 2");
  });
});

describe("changeRows", () => {
  const preview = {
    from: { matter_id: "623" }, into: { matter_id: "607" }, refusals: [], moves: [], folder: {},
    choices: {
      fills: [{ id: "fill:people.email_primary#1", column: "people.email_primary", party: false, new: "a@example.com" }],
      conflicts: [{ id: "people.dob_iso", column: "people.dob_iso", a: "1990-04-16", b: "1990-03-15", choice: "b" as const }],
      second_applicants: [],
    },
  };
  it("lists a fill always, and an overwrite only once A's value is picked", () => {
    expect(changeRows(preview, {}).map((r) => r.overwrites)).toEqual([false]);
    const rows = changeRows(preview, { "people.dob_iso": "a" });
    expect(rows[1]).toMatchObject({ before: "1990-03-15", after: "1990-04-16", overwrites: true });
  });
});

describe("detailRows", () => {
  const preview = {
    from: { matter_id: "623" }, into: { matter_id: "607" }, refusals: [], moves: [], folder: {},
    choices: {
      fills: [{ id: "fill:people.email_primary#1", column: "people.email_primary", party: false, new: "a@example.com" }],
      conflicts: [{ id: "people.dob_iso", column: "people.dob_iso", a: "1990-04-16", b: "1990-03-15", choice: "b" as const }],
      second_applicants: [],
    },
  };
  it("shows B now, A, and the result for every row, keeping B's unless A's is picked", () => {
    const keep = detailRows(preview, {});
    expect(keep[0]).toMatchObject({ b: "(empty)", a: "a@example.com", after: "a@example.com", kind: "fill" });
    expect(keep[1]).toMatchObject({ b: "1990-03-15", a: "1990-04-16", after: "1990-03-15", kind: "keep" });
    expect(detailRows(preview, { "people.dob_iso": "a" })[1]).toMatchObject({ after: "1990-04-16", kind: "overwrite" });
  });
});


describe("the Merged and Removed lists", () => {
  it("tells a merge from a removal", () => {
    expect(isMergeRow(row({ state: "merged" }))).toBe(true);
    expect(isMergeRow(row({ state: "unmerged" }))).toBe(true);
    expect(isMergeRow(row({ state: "merge_failed" }))).toBe(true);
    expect(isMergeRow(row({ state: "removed" }))).toBe(false);
    expect(isMergeRow(row({ state: "restored" }))).toBe(false);
  });

  it("names the client a merge went into, falling back to the matter number", () => {
    expect(removedStateLabel(row({ state: "merged", merged_into: "2", merged_into_name: "Client A" }))).toBe("Merged into Client A");
    expect(removedStateLabel(row({ state: "merged", merged_into: "2" }))).toBe("Merged into matter 2");
  });

  it("says before the button is pressed what Undo does, for a merge and for a removal", () => {
    const merged = undoExplanation(row({ state: "merged", client_name: "Client A", merged_into: "2", merged_into_name: "Client B" }));
    expect(merged).toContain("reverses this merge");
    expect(merged).toContain("from Client A to Client B goes back to Client A");
    const removed = undoExplanation(row({ state: "removed", client_name: "Client A" }));
    expect(removed).toContain("shows Client A again");
    expect(removed).toContain("000 Removed");
  });
});
