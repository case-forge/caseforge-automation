
import type { ReplyState, StatementReplies, StatementReply } from "./statementRepliesTypes";
import { DEMO_PRINCIPAL, DEMO_SECOND } from "./stubFirm";

const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const NAMES: Record<string, string> = { "9001": "Stub Testperson", "9002": "Second Stubperson", "9003": "Third Stubperson" };

const replies: StatementReply[] = [
  { matter_id: "9003", client_name: NAMES["9003"], state: "approved", note: "", by: DEMO_SECOND, recorded_utc: iso(Date.now() - 3 * 3_600_000) },
  { matter_id: "9001", client_name: NAMES["9001"], state: "approved", note: "", by: "auto", recorded_utc: iso(Date.now() - 26 * 3_600_000) },
  { matter_id: "9002", client_name: NAMES["9002"], state: "amend", note: "Paragraph 4 has the wrong month, and please add the second incident.", by: DEMO_PRINCIPAL, recorded_utc: iso(Date.now() - 50 * 60_000) },
];

export function stubStatementReplies(): StatementReplies {
  const sorted = [...replies].sort((a, b) => b.recorded_utc.localeCompare(a.recorded_utc));
  return {
    approved_count: sorted.filter((r) => r.state === "approved").length,
    amend_count: sorted.filter((r) => r.state === "amend").length,
    items: sorted.map((r) => ({ ...r })),
  };
}

export function stubHideReply(matterId: string, by: string): { matter_id: string; state: string } | { error: string } {
  if (!by.trim()) return { error: "type your name first" };
  const at = replies.findIndex((r) => r.matter_id === matterId);
  if (at < 0) return { error: "there is no statement reply for this matter" };
  const [gone] = replies.splice(at, 1);
  return { matter_id: matterId, state: gone.state };
}

export function stubSetReply(matterId: string, state: string, note: string, by: string): { matter_id: string; state: string } | { error: string } {
  if (!/^\d+$/.test(matterId)) return { error: "matter_id must be a matter number" };
  if (!by.trim()) return { error: "type your name first" };
  if (state && state !== "approved" && state !== "amend") return { error: "state must be approved, amend or empty" };
  const text = note.split(/\s+/).filter(Boolean).join(" ").slice(0, 500);
  if (state === "amend" && !text) return { error: "say what the client wants changed" };
  const at = replies.findIndex((r) => r.matter_id === matterId);
  if (at >= 0) replies.splice(at, 1);
  if (state) {
    replies.push({
      matter_id: matterId,
      client_name: NAMES[matterId] ?? `Matter ${matterId}`,
      state: state as ReplyState,
      note: text,
      by: by.trim(),
      recorded_utc: iso(Date.now()),
    });
  }
  return { matter_id: matterId, state };
}
