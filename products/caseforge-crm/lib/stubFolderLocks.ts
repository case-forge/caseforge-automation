
import type { FolderLocks } from "./folderLocks";

const locked = new Map<string, string>();
const CHILDREN: Record<string, string[]> = {
  "2A-Z - Alex": ["Client A", "Client B", "Client C"],
  "2B-Z - Sam": ["Client D", "Client E"],
  "2C-Z - Jordan": ["Client F"],
  "2AA-Z - Shared": [],
};
const BOOKS = ["2A-Z - Alex", "2B-Z - Sam", "2C-Z - Jordan", "2AA-Z - Shared"];

export function stubFolderLocks(): FolderLocks {
  return { fixed: [], locked: [...locked].map(([path, by]) => ({ path, locked_by: by, locked_utc: "" })), books: BOOKS, children: CHILDREN };
}

export function stubSetFolderLock(folder: string, on: boolean, by: string): FolderLocks | { error: string } {
  if (!folder.trim()) return { error: "folder is required" };
  if (on) locked.set(folder, by);
  else locked.delete(folder);
  return stubFolderLocks();
}
