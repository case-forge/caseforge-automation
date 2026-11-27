import { describe, expect, it } from "vitest";
import type { ClientEdit } from "@/lib/types";
import { notesHistoryOf } from "./NotesHistory";

function edit(over: Partial<ClientEdit>): ClientEdit {
  return {
    edit_id: "e",
    matter_id: "5",
    field_name: "tracker_notes",
    field_label: "Notes",
    old_value: null,
    new_value: "",
    note: "",
    edited_by: "Sam",
    created_at: "2026-10-01T10:00:00Z",
    ...over,
  };
}

describe("notesHistoryOf", () => {
  it("lists newest first, keeps the note that was there before history, and ignores other fields", () => {
    const rows = [
      edit({ edit_id: "1", old_value: "Intake note", new_value: "First", created_at: "2026-10-01T10:00:00Z" }),
      edit({ edit_id: "2", old_value: "First", new_value: "Second", created_at: "2026-10-02T10:00:00Z" }),
      edit({ edit_id: "3", field_name: "phone_primary", new_value: "0123" }),
    ];
    expect(notesHistoryOf(rows, "5").map((e) => e.text)).toEqual(["Second", "First", "Intake note"]);
  });

  it("is empty for another matter", () => {
    expect(notesHistoryOf([edit({ new_value: "x" })], "6")).toEqual([]);
  });
});
