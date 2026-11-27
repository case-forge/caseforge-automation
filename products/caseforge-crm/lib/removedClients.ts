
export type RemovedClient = {
  matter_id: string;
  client_name: string;
  reason: string;
  removed_by: string;
  removed_utc: string;
  state: "removed" | "restored" | "purged" | "merged" | "unmerged" | "merge_failed";
  merged_into: string;

  merged_into_name: string;
  folder_moved: boolean;
  restored_by: string;
  restored_utc: string;
  purged_utc: string;
  purge_note: string;
  can_undo: boolean;
};

function key(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(" ").toLocaleLowerCase("en-GB");
}

export function removeConfirmed(typed: string, clientName: string): boolean {
  return key(clientName) !== "" && key(typed) === key(clientName);
}

export function undoActionFor(row: RemovedClient): "undo" | "undo-merge" {
  return row.state === "merged" ? "undo-merge" : "undo";
}

export type MergePreview = {
  from: { matter_id: string; client_name?: string; folder?: string };
  into: { matter_id: string; client_name?: string; folder?: string };
  refusals: string[];
  moves: { label: string; table: string; move: number; stay: number; fill?: number; fill_columns?: string[]; conflicts?: string[]; added?: number; added_tables?: string[] }[];
  folder: { action?: string; note?: string };
  choices?: { conflicts: MergeConflict[]; fills?: MergeFill[]; second_applicants: SecondApplicant[] };
};

export type MergeConflict = { id: string; column: string; a: string; b: string; choice: "a" | "b" };

export type MergeFill = { id: string; column: string; party: boolean; new: string };

export type SecondApplicant = {
  id: string;
  party_id: number;
  b_party_id: number;
  name: string;
  dob: string;
  b_name: string;
  b_dob: string;
  choice: "keep" | "discard";
};

export type MergePicks = Record<string, string>;

const COLUMN_LABELS: Record<string, string> = {
  dob_iso: "Date of birth",
  email_primary: "Email",
  phone_primary: "Phone",
  nino_canonical: "NI number",
  address_text: "Address",
};

export function conflictLabel(column: string): string {
  const [table, name = ""] = column.split(".");
  const what = COLUMN_LABELS[name] ?? name;
  return table === "people" ? `${what} (client)` : `${what} (party)`;
}

export function pickAll(preview: MergePreview, side: "a" | "b", picks: MergePicks): MergePicks {
  const out = { ...picks };
  for (const c of preview.choices?.conflicts ?? []) out[c.id] = side;
  return out;
}

export function picksBody(preview: MergePreview | null, picks: MergePicks): MergePicks {
  const out: MergePicks = {};
  for (const c of preview?.choices?.conflicts ?? []) if (picks[c.id] === "a") out[c.id] = "a";
  for (const s of preview?.choices?.second_applicants ?? []) out[s.id] = picks[s.id] === "keep" ? "keep" : "discard";
  return out;
}

export function mergeMoveLines(preview: MergePreview): string[] {
  const away = `matter ${preview.from.matter_id}`;
  const kept = `matter ${preview.into.matter_id}`;
  return preview.moves.map((m) => {
    if (m.added !== undefined) return `${m.label}: ${m.added} added to ${kept} from ${away}`;
    if (m.fill !== undefined) {
      const conflicts = m.conflicts?.length ? `; differs, ${kept}'s kept unless you choose ${away}'s: ${m.conflicts.join(", ")}` : "";
      return `${m.label}: ${m.fill} empty on ${kept} filled from ${away}${m.fill_columns?.length ? ` (${m.fill_columns.join(", ")})` : ""}${conflicts}`;
    }
    const stays = m.stay ? `, ${m.stay} stay on ${away} (${kept} already has its own)` : "";
    return `${m.label}: ${m.move} move${stays}`;
  });
}

export function mergeConfirmed(preview: MergePreview | null, typedFrom: string, typedInto: string): boolean {
  if (!preview || preview.refusals.length > 0) return false;
  return removeConfirmed(typedFrom, preview.from.client_name ?? "") && removeConfirmed(typedInto, preview.into.client_name ?? "");
}

const MERGE_STATES: RemovedClient["state"][] = ["merged", "unmerged", "merge_failed"];

export function isMergeRow(row: RemovedClient): boolean {
  return MERGE_STATES.includes(row.state);
}

export function undoExplanation(row: RemovedClient): string {
  const name = row.client_name || `matter ${row.matter_id}`;
  if (row.state === "merged") {
    const into = row.merged_into_name || `matter ${row.merged_into}`;
    return `Undo reverses this merge: everything it moved from ${name} to ${into} goes back to ${name}, the folder ${name} lent to ${into} is released, and ${name} shows again. It cannot be undone after 30 days.`;
  }
  return `Undo shows ${name} again and moves the folder back out of 000 Removed. It cannot be undone after 30 days.`;
}

export function removedStateLabel(row: RemovedClient): string {
  if (row.state === "merged") return `Merged into ${row.merged_into_name || `matter ${row.merged_into}`}`;
  if (row.state === "unmerged") return `Merge undone by ${row.restored_by || "someone"}`;
  if (row.state === "merge_failed") return "Merge failed; nothing was moved";
  if (row.state === "purged") return "Purged";
  if (row.state === "restored") return `Restored by ${row.restored_by || "someone"}`;
  return row.can_undo ? "Removed" : "Removed, kept as a tombstone (never purged)";
}

export type DetailRow = { id: string; label: string; b: string; a: string; after: string; kind: "fill" | "keep" | "overwrite" };

export function detailRows(preview: MergePreview | null, picks: MergePicks): DetailRow[] {
  const rows: DetailRow[] = [];
  for (const f of preview?.choices?.fills ?? []) {
    rows.push({ id: f.id, label: conflictLabel(f.column), b: "(empty)", a: f.new, after: f.new, kind: "fill" });
  }
  for (const c of preview?.choices?.conflicts ?? []) {
    const useA = picks[c.id] === "a";
    rows.push({ id: c.id, label: conflictLabel(c.column), b: c.b, a: c.a, after: useA ? c.a : c.b, kind: useA ? "overwrite" : "keep" });
  }
  return rows;
}

export type ChangeRow = { id: string; label: string; before: string; after: string; overwrites: boolean };

export function changeRows(preview: MergePreview | null, picks: MergePicks): ChangeRow[] {
  const rows: ChangeRow[] = [];
  for (const f of preview?.choices?.fills ?? []) {
    rows.push({ id: f.id, label: conflictLabel(f.column), before: "(empty)", after: f.new, overwrites: false });
  }
  for (const c of preview?.choices?.conflicts ?? []) {
    if (picks[c.id] === "a") rows.push({ id: c.id, label: conflictLabel(c.column), before: c.b, after: c.a, overwrites: true });
  }
  return rows;
}
