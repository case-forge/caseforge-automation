
import type { ActorKind } from "./actorKind";
import type { AuditFolders, FolderClient, FolderEvent, FolderFlag, FolderItem, FolderTree } from "./auditFolders";

const sorter = (at: string, action = "Uploaded", extra: Partial<FolderEvent> = {}): FolderEvent => ({ at, kind: "automation", who: "mail-sorter", action, seen_by: ["ours", "microsoft"], ...extra });
const person = (at: string, who: string, action: string, extra: Partial<FolderEvent> = {}): FolderEvent => ({ at, kind: "person", who, action, seen_by: ["microsoft"], ...extra });
const agent = (at: string, action: string, extra: Partial<FolderEvent> = {}): FolderEvent => ({ at, kind: "agent", who: "Owner (CLI session)", action, seen_by: ["ours"], ...extra });

function file(path: string, made: FolderEvent | null, moved: FolderEvent | null = null, extra: Partial<FolderItem> = {}): FolderItem {
  return { path, name: path.split("/").pop() ?? path, type: "file", modified: "2026-11-10T09:00:00Z", size: 48213, indexed: true, removed: false, created: made, placed: moved, edits: 0, last_edit: null, flags: {}, ...extra };
}

function folder(path: string): FolderItem {
  return { path, name: path.split("/").pop() ?? path, type: "folder", modified: "2026-10-01T09:00:00Z", size: null, indexed: true, removed: false, created: null, placed: null, edits: 0, last_edit: null, flags: {} };
}

const SAMPLE_ITEMS: FolderItem[] = [
  folder("Correspondence"),
  folder("Court Documents"),
  folder("Orders"),
  folder("Statements"),
  file("Correspondence/26.11.04 Email from court - listing.pdf", sorter("2026-11-04T09:12:00Z")),
  file("Correspondence/26.11.09 Email from other side.pdf", sorter("2026-11-09T14:30:00Z")),
  file("Correspondence/26.11.12 Email to client.pdf", person("2026-11-12T10:05:00Z", "person-a@example.test", "Uploaded")),

  file("Orders/26.11.05 Order.pdf", sorter("2026-11-05T08:02:00Z"), person("2026-11-06T16:40:00Z", "person-a@example.test", "Moved", { from: "Correspondence/26.11.05 Order.pdf", to: "Orders/26.11.05 Order.pdf" })),

  file("Court Documents/26.11.13 Email from another client.pdf", sorter("2026-11-13T11:15:00Z")),
  file("Statements/26.11.13 Scanned post.pdf", sorter("2026-11-13T11:16:00Z")),
  file("Orders/26.11.16 Email from landlord.pdf", sorter("2026-11-16T07:45:00Z")),

  file("Statements/26.11.10 Witness statement (draft).docx", agent("2026-11-10T13:20:00Z", "Uploaded"), null, { edits: 2, last_edit: person("2026-11-11T09:00:00Z", "person-b@example.test", "Edited") }),
  file("Court Documents/Application.pdf", person("2026-11-02T15:00:00Z", "person-b@example.test", "Uploaded")),
  file("Court Documents/Old bundle index.pdf", null),
  file("Statements/Signed statement.pdf", null),
  file("Notes.docx", null),
  {
    ...file("Court Documents/26.11.05 Email from other side.pdf", sorter("2026-11-05T08:03:00Z")),
    indexed: false,
    removed: true,
    created: null,
    removed_by: person("2026-11-07T09:30:00Z", "person-a@example.test", "Moved", { from: "Court Documents/26.11.05 Email from other side.pdf", to: "Another Client/26.11.05 Email from other side.pdf", to_outside: true }),
    moved_to: "Another Client/26.11.05 Email from other side.pdf",
    to_outside: true,
  },
];

const CLIENTS: FolderClient[] = [
  { name: "Sample Client", person: 3, agent: 1, automation: 5, unrecorded: 0, last_at: "2026-11-16T07:45:00Z", flagged: 0 },
  { name: "Example Person", person: 1, agent: 0, automation: 2, unrecorded: 0, last_at: "2026-11-12T10:05:00Z", flagged: 0 },
  { name: "Another Person", person: 0, agent: 0, automation: 0, unrecorded: 0, last_at: "", flagged: 0 },
];

const FLAGS = new Map<string, FolderFlag>();

const OTHER_FLAGS: Record<string, Partial<Record<ActorKind, FolderFlag>>> = {
  "sample client/court documents/26.11.13 email from another client.pdf": {
    agent: { by: "AI session", at: "2026-11-17T10:00:00Z", note: "An email about a different client: wrong client folder?" },
    automation: { by: "audit-sweep", at: "2026-11-17T04:00:00Z", note: "Named like an email. Court-served papers only here." },
  },
  "sample client/statements/26.11.13 scanned post.pdf": {
    agent: { by: "AI session", at: "2026-11-17T10:00:00Z", note: "Scanned post, not a statement." },
  },
  "sample client/orders/26.11.16 email from landlord.pdf": {
    automation: { by: "audit-sweep", at: "2026-11-17T04:00:00Z", note: "Named like an email. Court-served papers only here." },
  },
};

export function stubSetFlag(client: string, path: string, flagged: boolean, by = "admin@example.test"): { flagged: boolean } {
  const key = `${client}/${path}`.toLowerCase();
  if (flagged) FLAGS.set(key, { by, at: new Date().toISOString(), note: "" });
  else FLAGS.delete(key);
  return { flagged };
}

function flagsFor(client: string, path: string): Partial<Record<ActorKind, FolderFlag>> {
  const key = `${client}/${path}`.toLowerCase();
  const person = FLAGS.get(key);
  return { ...(OTHER_FLAGS[key] ?? {}), ...(person ? { person } : {}) };
}

function treeFor(name: string): FolderTree | null {
  if (name !== "Sample Client") return null;
  const flagged = SAMPLE_ITEMS.map((i) => ({ ...i, flags: flagsFor(name, i.path) }));
  const live = flagged.filter((i) => !i.removed && i.type === "file");
  const count = (kind: string) => live.filter((i) => ((i.placed ?? i.created)?.kind ?? "unrecorded") === kind).length;
  return {
    name,
    items: flagged,
    truncated: false,
    summary: { person: count("person"), agent: count("agent"), automation: count("automation"), unrecorded: count("unrecorded"), removed: flagged.filter((i) => i.removed).length, flagged: flagged.filter((i) => Object.keys(i.flags).length > 0).length, flags_by_kind: { person: flagged.filter((i) => i.flags.person).length, agent: flagged.filter((i) => i.flags.agent).length, automation: flagged.filter((i) => i.flags.automation).length } },
  };
}

export function stubAuditFolders(folderName: string, days: number): AuditFolders {
  const known = CLIENTS.find((c) => c.name.toLowerCase() === folderName.trim().toLowerCase());
  return {
    book: "Sample book",
    days,
    since: "2026-08-19T00:00:00Z",
    until: "2026-11-17T12:00:00Z",
    clients: CLIENTS.map((c) => ({ ...c, flagged: [...new Set([...FLAGS.keys(), ...Object.keys(OTHER_FLAGS)])].filter((k) => k.startsWith(`${c.name.toLowerCase()}/`)).length })),
    microsoft_through: "2026-11-16T23:50:00Z",
    index_through: "2026-11-17T11:50:00Z",
    folder: known ? (treeFor(known.name) ?? { name: known.name, items: [], truncated: false, summary: { person: 0, agent: 0, automation: 0, unrecorded: 0, removed: 0, flagged: 0, flags_by_kind: { person: 0, agent: 0, automation: 0 } } }) : null,
  };
}
