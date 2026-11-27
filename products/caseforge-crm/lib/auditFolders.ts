
import { ACTOR_KINDS, isActorKind, type ActorKind } from "./actorKind";

export interface FolderEvent {
  at: string;

  kind: ActorKind | "";
  who: string;
  action: string;
  seen_by: string[];

  from?: string;
  to?: string;
  from_outside?: boolean;
  to_outside?: boolean;
  program?: string;
  unit?: string;
}

export interface FolderFlag {
  by: string;
  at: string;
  note: string;
}

export interface FolderItem {

  path: string;
  name: string;
  type: "file" | "folder";
  modified: string;
  size: number | null;

  indexed: boolean;
  removed: boolean;

  created: FolderEvent | null;

  placed: FolderEvent | null;
  edits: number;
  last_edit: FolderEvent | null;
  removed_by?: FolderEvent | null;
  moved_to?: string;
  to_outside?: boolean;
  flags: Partial<Record<ActorKind, FolderFlag>>;

  flag_gone?: boolean;

  unseen?: boolean;

  stale?: boolean;
}

export interface FolderRollup {
  person: number;
  agent: number;
  automation: number;
  unrecorded: number;
}

export interface FolderClient extends FolderRollup {
  name: string;
  last_at: string;
  flagged: number;
}

export interface FolderTree {
  name: string;
  items: FolderItem[];
  truncated: boolean;
  summary: FolderRollup & { removed: number; flagged: number; flags_by_kind: Record<ActorKind, number> };
}

export interface AuditFolders {
  book: string;
  days: number;
  since: string;
  until: string;
  clients: FolderClient[];
  folder: FolderTree | null;

  microsoft_through: string;

  index_through: string;
}

export type FoldersLoad = { state: "hidden" } | { state: "error" } | { state: "ok"; data: AuditFolders };

export const FOLDER_DAYS = 90;

export async function loadAuditFolders(folder: string, days: number = FOLDER_DAYS, fetcher: typeof fetch = fetch): Promise<FoldersLoad> {
  try {
    const params = new URLSearchParams({ days: String(days) });
    if (folder) params.set("folder", folder);
    const res = await fetcher(`/api/audit-folders?${params.toString()}`, { cache: "no-store" });
    if (res.status === 403) return { state: "hidden" };
    if (!res.ok) return { state: "error" };
    return { state: "ok", data: (await res.json()) as AuditFolders };
  } catch {
    return { state: "error" };
  }
}

export async function setFolderFlag(client: string, item: Pick<FolderItem, "path" | "type">, flagged: boolean, fetcher: typeof fetch = fetch): Promise<boolean> {
  try {
    const res = await fetcher("/api/audit-folders/flag", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client, path: item.path, type: item.type, flagged }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export function carryPinned(previous: FolderItem[], next: FolderItem[], pinned: ReadonlySet<string>): FolderItem[] {
  const present = new Set(next.map((i) => i.path.toLowerCase()));
  const carried = previous.filter((i) => pinned.has(i.path) && !present.has(i.path.toLowerCase())).map((i) => ({ ...i, stale: true }));
  return carried.length ? [...next, ...carried] : next;
}

export function flagKindsOf(item: Pick<FolderItem, "flags">): ActorKind[] {
  return ACTOR_KINDS.filter((kind) => item.flags[kind] !== undefined);
}

export function placerOf(item: FolderItem): FolderEvent | null {
  return item.placed ?? item.created;
}

export type Group = ActorKind | "unrecorded";

export function groupOf(item: FolderItem): Group {
  const kind = placerOf(item)?.kind;
  return isActorKind(kind) ? kind : "unrecorded";
}

export const GROUPS: readonly Group[] = [...ACTOR_KINDS, "unrecorded"];

export function emptyRollup(): FolderRollup {
  return { person: 0, agent: 0, automation: 0, unrecorded: 0 };
}

export interface TreeNode {
  name: string;

  path: string;
  type: "file" | "folder";
  item: FolderItem | null;
  children: TreeNode[];

  rollup: FolderRollup;
  removedBelow: number;
}

export type GroupFilter = "all" | Group;

export interface TreeOptions {
  group: GroupFilter;

  onlyChanged: boolean;

  text: string;

  flagKinds: ReadonlySet<ActorKind>;

  keep: ReadonlySet<string>;
}

export function hasRecord(item: FolderItem): boolean {
  return item.removed || item.created !== null || item.placed !== null || item.edits > 0;
}

function filterGroup(item: FolderItem): Group {
  if (!item.removed) return groupOf(item);
  const kind = item.removed_by?.kind;
  return isActorKind(kind) ? kind : "unrecorded";
}

function keeps(item: FolderItem, options: TreeOptions): boolean {
  const text = options.text.trim().toLowerCase();
  if (text && !item.path.toLowerCase().includes(text)) return false;

  if (flagKindsOf(item).length > 0 || options.keep.has(item.path)) {
    return options.flagKinds.size === 0 || flagKindsOf(item).some((k) => options.flagKinds.has(k)) || options.keep.has(item.path);
  }
  if (options.flagKinds.size > 0) return false;
  if (options.onlyChanged && !hasRecord(item)) return false;
  return options.group === "all" || filterGroup(item) === options.group;
}

export function buildTree(items: FolderItem[], options: TreeOptions): TreeNode {
  const root: TreeNode = { name: "", path: "", type: "folder", item: null, children: [], rollup: emptyRollup(), removedBelow: 0 };
  const folders = new Map<string, TreeNode>([["", root]]);

  const folderAt = (path: string): TreeNode => {
    const found = folders.get(path);
    if (found) return found;
    const cut = path.lastIndexOf("/");
    const parent = folderAt(cut < 0 ? "" : path.slice(0, cut));
    const node: TreeNode = { name: path.slice(cut + 1), path, type: "folder", item: null, children: [], rollup: emptyRollup(), removedBelow: 0 };
    parent.children.push(node);
    folders.set(path, node);
    return node;
  };

  const sorted = [...items].sort((a, b) => a.path.localeCompare(b.path, "en-GB", { sensitivity: "base", numeric: true }));
  for (const item of sorted) {
    if (!keeps(item, options)) continue;
    const cut = item.path.lastIndexOf("/");
    const parent = folderAt(cut < 0 ? "" : item.path.slice(0, cut));
    if (item.type === "folder" && !item.removed) {
      const existing = folders.get(item.path);
      if (existing) {
        existing.item = item;
        continue;
      }
      const node: TreeNode = { name: item.name, path: item.path, type: "folder", item, children: [], rollup: emptyRollup(), removedBelow: 0 };
      parent.children.push(node);
      folders.set(item.path, node);
      continue;
    }
    parent.children.push({ name: item.name, path: item.path, type: item.type, item, children: [], rollup: emptyRollup(), removedBelow: 0 });
  }

  const roll = (node: TreeNode): void => {
    node.children.sort((a, b) => (a.type === b.type ? 0 : a.type === "folder" ? -1 : 1) || a.name.localeCompare(b.name, "en-GB", { sensitivity: "base", numeric: true }));
    for (const child of node.children) {
      roll(child);
      for (const group of GROUPS) node.rollup[group] += child.rollup[group];
      node.removedBelow += child.removedBelow;
    }
    if (node.type === "file" && node.item) {
      if (node.item.removed) node.removedBelow += 1;
      else node.rollup[groupOf(node.item)] += 1;
    }
  };
  roll(root);
  return root;
}

export function rollupTotal(rollup: FolderRollup): number {
  return rollup.person + rollup.agent + rollup.automation + rollup.unrecorded;
}

export function folderPaths(node: TreeNode): string[] {
  return node.children.flatMap((child) => (child.type === "folder" ? [child.path, ...folderPaths(child)] : []));
}

const GROUP_WORDS: Record<Group, string> = { person: "People", agent: "Agents", automation: "Automation", unrecorded: "No record" };

export function groupWord(group: Group): string {
  return GROUP_WORDS[group];
}

export function rollupSentence(rollup: FolderRollup): string {
  const parts: string[] = [];
  if (rollup.person) parts.push(`${rollup.person} put there by people`);
  if (rollup.agent) parts.push(`${rollup.agent} by agents`);
  if (rollup.automation) parts.push(`${rollup.automation} by automation`);
  if (rollup.unrecorded) parts.push(`${rollup.unrecorded} with no record`);
  return parts.join(", ") || "Nothing here";
}

export function dayLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "numeric", month: "short" }).format(date);
}
