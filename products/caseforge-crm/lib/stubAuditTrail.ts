
import { ACTOR_KINDS, type ActorKind } from "./actorKind";
import type { AuditKind, AuditRow, AuditTrail } from "./auditTrail";

const ROWS: AuditRow[] = [
  { id: "view:3", at: "2026-11-06T16:30:00Z", kind: "person", who: "person-b@example.test", area: "view", action: "Opened the Activity log", what: "", from: "", to: "", where: "Matter 640", ip: "", seen_by: ["ours"], matter_id: "640" },
  { id: "sent:640:amend:1", at: "2026-11-06T16:18:48Z", kind: "automation", who: "our draft, sent as made", area: "mail", action: "Sent the amend email (round 1)", what: "<sent-1@example.test>", from: "", to: "", where: "Matter 640", ip: "", seen_by: ["ours"], matter_id: "640" },
  { id: "sent:640:email:0", at: "2026-11-06T15:51:17Z", kind: "person", who: "written by hand", area: "mail", action: "Sent the court email", what: "<sent-2@example.test>", from: "", to: "", where: "Matter 640", ip: "", seen_by: ["ours"], matter_id: "640" },
  { id: "prov:4", at: "2026-11-06T12:39:59Z", kind: "automation", who: "documenso_webhook_worker", area: "file", action: "Saved ws from documenso", what: "Book A/Sample Client/Statements/WS.SAMPLE.pdf", from: "Documenso envelope envelope_sample (document 211)", to: "item 015XSAMPLE sha256 9f2c41aa07d3b6e1", where: "Matter 640", ip: "", seen_by: ["ours"], matter_id: "640", item_id: "015XSAMPLE" },
  { id: "ms:1", at: "2026-11-06T16:02:11Z", kind: "person", who: "person-a@example.test", area: "file", action: "Moved", what: "", from: "Book A/Sample Client/Docs-A/Intro.pdf", to: "Book A/Sample Client/Docs-B/Intro.pdf", where: "Book A/Sample Client/Docs-A", ip: "203.0.113.5", seen_by: ["microsoft"], likely_crm_user: "person-a@example.test" },
  { id: "flow:a", at: "2026-11-06T15:55:20Z", kind: "agent", who: "Owner (CLI session)", area: "case flow", action: "Case flow mode", what: "This client is on Auto, set by Owner (CLI session).", from: "", to: "", where: "Matter 640", ip: "", seen_by: ["ours"], matter_id: "640", mode: "auto" },
  { id: "ms:2", at: "2026-11-06T15:48:40Z", kind: "person", who: "person-b@example.test", area: "folder", action: "Renamed folder", what: "", from: "Book B/old folder", to: "Book B/old folder (renamed)", where: "Book B", ip: "203.0.113.9", seen_by: ["microsoft"] },
  { id: "flow:b", at: "2026-11-06T15:40:00Z", kind: "automation", who: "Case flow", area: "case flow", action: "Case flow email", what: "Armed with the send gate: sends at 16:10 unless a person stops it.", from: "", to: "", where: "Matter 640", ip: "", seen_by: ["ours"], matter_id: "640", mode: "auto" },
  { id: "tel:3", at: "2026-11-06T15:30:02Z", kind: "automation", who: "matter-folder-closure", area: "file", action: "Moved", what: "", from: "Book A/Example Person", to: "Concluded/Example Person", where: "Book A", ip: "198.51.100.7", seen_by: ["ours", "microsoft"] },
  { id: "tel:4", at: "2026-11-06T14:12:55Z", kind: "automation", who: "casework-scans", area: "file", action: "Uploaded", what: "Book A/Another Person/Notes/26.11.06-note.docx", from: "", to: "", where: "Book A/Another Person/Notes", ip: "", seen_by: ["ours"] },
  { id: "flow:c", at: "2026-11-06T13:50:00Z", kind: "person", who: "Person B", area: "case flow", action: "Case flow statement", what: "Draft statement saved.", from: "", to: "", where: "Matter 640", ip: "", seen_by: ["ours"], matter_id: "640", mode: "manual" },
  { id: "edit:5", at: "2026-11-06T13:40:00Z", kind: "person", who: "Person B", area: "record", action: "Edited phone", what: "", from: "07700 900001", to: "07700 900002", where: "Matter 640", ip: "", seen_by: ["ours"] },
  { id: "ms:6", at: "2026-11-06T12:21:09Z", kind: "automation", who: "app 70518a75", area: "mail", action: "Created email", what: "Reminder: Letter of Authority & Statement for Signature", from: "", to: "", where: "\\Drafts", ip: "198.51.100.7", seen_by: ["microsoft"] },
  { id: "ms:7", at: "2026-11-06T11:05:33Z", kind: "person", who: "admin@example.test", area: "admin", action: "Consent to application", what: "audit log reader", from: "", to: "", where: "", ip: "203.0.113.9", seen_by: ["microsoft"] },
];

export function stubAuditTrail(kind: AuditKind, q: string): AuditTrail {
  const needle = q.trim().toLowerCase();
  let rows = ROWS;
  if (kind !== "all") rows = rows.filter((r) => r.kind === kind);
  if (needle) rows = rows.filter((r) => [r.who, r.action, r.what, r.from, r.to, r.where, r.ip].join(" ").toLowerCase().includes(needle));
  const counts = Object.fromEntries(ACTOR_KINDS.map((k) => [k, ROWS.filter((r) => r.kind === k).length])) as Record<ActorKind, number>;
  return {
    rows,
    total: rows.length,
    counts,
    since: "2026-10-30T00:00:00Z",
    until: "2026-11-06T17:00:00Z",
    kind,
  };
}
