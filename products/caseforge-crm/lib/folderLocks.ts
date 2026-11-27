
export interface FolderLock {
  path: string;
  locked_by: string;
  locked_utc: string;
}

export interface FolderLocks {

  fixed: string[];
  locked: FolderLock[];

  books: string[];

  children: Record<string, string[]>;
}

export function exclusionPath(book: string, sub = "", typed = ""): string {
  const parts = [book, sub, typed]
    .flatMap((p) => p.split(/[\\/]/))
    .map((p) => p.trim())
    .filter(Boolean);
  if (!book.trim() || parts.some((p) => p.startsWith("."))) return "";
  return parts.join("/");
}

export function exclusionLabel(path: string): string {
  const [book, ...rest] = path.split("/");
  return [folderBookLabel(book ?? ""), ...rest].join(" / ");
}

export function alreadyExcluded(locks: FolderLocks, path: string): boolean {
  const target = `/${path.toLowerCase()}/`;
  return locks.locked.some((l) => target.includes(`/${l.path.toLowerCase()}/`));
}

export type PendingChange = { kind: "add" | "remove"; path: string };

export function confirmQuestion(change: PendingChange): string {
  const name = exclusionLabel(change.path);
  return change.kind === "add" ? `Stop automation changing anything in ${name}?` : `Let automation work in ${name} again?`;
}

export function folderBookLabel(book: string): string {
  const stripped = book.replace(/^\d+[A-Z]*-Z\s*-?\s*/i, "").trim();
  return stripped || book;
}

function norm(value: string): string {
  return value.trim().toLowerCase();
}

export function isFixed(locks: FolderLocks, book: string): boolean {
  return locks.fixed.some((f) => norm(f) === norm(book));
}

export function isReadOnly(locks: FolderLocks, book: string): boolean {
  if (!book.trim()) return false;
  return isFixed(locks, book) || locks.locked.some((l) => norm(l.path) === norm(book));
}

async function failure(res: Response, fallback: string): Promise<Error> {
  const body = await res.json().catch(() => ({}));
  return new Error(typeof body?.error === "string" && body.error ? body.error : typeof body?.detail === "string" && body.detail ? body.detail : fallback);
}

export async function fetchFolderLocks(): Promise<FolderLocks> {
  const res = await fetch("/api/folder-locks");
  if (!res.ok) throw await failure(res, "Could not read the read-only folders.");
  const body = (await res.json()) as Partial<FolderLocks>;
  return { fixed: body.fixed ?? [], locked: body.locked ?? [], books: body.books ?? [], children: body.children ?? {} };
}

export async function changeFolderLock(folder: string, locked: boolean): Promise<FolderLocks> {
  const res = await fetch("/api/folder-locks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder, locked }),
  });
  if (!res.ok) throw await failure(res, "Could not change the read-only setting.");
  const body = (await res.json()) as Partial<FolderLocks>;
  return { fixed: body.fixed ?? [], locked: body.locked ?? [], books: body.books ?? [], children: body.children ?? {} };
}
