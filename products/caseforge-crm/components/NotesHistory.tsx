import type { ClientEdit } from "@/lib/types";

export function notesHistoryOf(rows: ClientEdit[], matterId: string): { text: string; by: string; at: string }[] {
  const mine = rows
    .filter((r) => r.field_name === "tracker_notes" && String(r.matter_id) === matterId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const out = mine.map((r) => ({ text: r.new_value, by: r.edited_by, at: r.created_at }));
  const oldest = mine[mine.length - 1];
  if (oldest && (oldest.old_value ?? "").trim()) {
    out.push({ text: oldest.old_value as string, by: "", at: "" });
  }
  return out;
}

export function NotesHistory({ rows, matterId }: { rows: ClientEdit[]; matterId: string }) {
  const entries = notesHistoryOf(rows, matterId);
  if (entries.length < 2) return null;
  return (
    <details className="proposal-history">
      <summary>Notes history ({entries.length})</summary>
      <ul className="proposal-list proposal-list--resolved">
        {entries.map((e, i) => (
          <li className="proposal-item proposal-item--resolved" key={`${e.at}-${i}`}>
            <p className="proposal-item-note">{e.text || "(blank)"}</p>
            <p className="proposal-item-meta">
              {i === 0 ? "Current. " : ""}
              {e.at ? `${e.at.slice(0, 10)}${e.by ? ` by ${e.by}` : ""}` : "Earlier note, before history was kept"}
            </p>
          </li>
        ))}
      </ul>
    </details>
  );
}
