
export interface FolderMapEntry {
  name: string;
  per_order: boolean;
}

export interface FolderMapPreview {
  surname: string;
  orders: string[];
  folders: string[];
  without_orders: string[];
  warnings: string[];
}

export interface FolderMapView {
  can_edit: boolean;
  entries: FolderMapEntry[];
  default: FolderMapEntry[];
  is_default: boolean;
  changed_by: string;
  changed_at: string;
  max_entries: number;
  max_name: number;
  order_codes: string[];
  preview: FolderMapPreview;
  note: string;
}

const FORBIDDEN = /[\\/:*?"<>|{}\u0000-\u001f\u007f]/;

export function nameKey(name: string): string {
  return name.replace(/[\s\-_'’]+/g, "").toLowerCase();
}

export function localProblems(entries: FolderMapEntry[], maxName = 60, maxEntries = 60): Record<number, string> {
  const problems: Record<number, string> = {};
  const seen = new Map<string, number>();
  entries.forEach((entry, index) => {
    const name = entry.name.split(/\s+/).filter(Boolean).join(" ");
    if (!name) problems[index] = "Give this folder a name.";
    else if (name.length > maxName) problems[index] = `Keep the name to ${maxName} characters.`;
    else if (FORBIDDEN.test(name)) problems[index] = "A folder name cannot contain \\ / : * ? \" < > | { }.";
    else if (name.includes("..") || name.startsWith(".") || name.endsWith(".")) problems[index] = "A name cannot start or end with a dot, or have two dots in a row.";
    else if (seen.has(nameKey(name))) problems[index] = `Same folder as row ${(seen.get(nameKey(name)) ?? 0) + 1}.`;
    if (name && !seen.has(nameKey(name))) seen.set(nameKey(name), index);
  });
  if (entries.length === 0) problems[-1] = "The map needs at least one folder.";
  if (entries.length > maxEntries) problems[-1] = `The map can have at most ${maxEntries} folders.`;
  return problems;
}

export type LoadResult = { state: "ok"; view: FolderMapView } | { state: "error" };
export type CallResult<T> = { ok: true; value: T } | { ok: false; message: string };

const URL_PATH = "/api/settings/folder-map";

async function failure(res: Response): Promise<{ ok: false; message: string }> {
  let message = "That could not be done.";
  try {
    const body = await res.json();
    if (typeof body?.error === "string") message = body.error;
  } catch {

  }
  return { ok: false, message };
}

export async function loadFolderMap(fetcher: typeof fetch = fetch): Promise<LoadResult> {
  try {
    const res = await fetcher(URL_PATH, { cache: "no-store" });
    if (!res.ok) return { state: "error" };
    const body = await res.json();
    return Array.isArray(body?.entries) && body?.preview ? { state: "ok", view: body as FolderMapView } : { state: "error" };
  } catch {
    return { state: "error" };
  }
}

export async function previewFolderMap(entries: FolderMapEntry[], fetcher: typeof fetch = fetch): Promise<CallResult<FolderMapPreview>> {
  try {
    const res = await fetcher(`${URL_PATH}?preview=1`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ entries }) });
    return res.ok ? { ok: true, value: (await res.json()) as FolderMapPreview } : await failure(res);
  } catch {
    return { ok: false, message: "The preview could not be made." };
  }
}

export async function saveFolderMap(entries: FolderMapEntry[], fetcher: typeof fetch = fetch): Promise<CallResult<FolderMapView>> {
  try {
    const res = await fetcher(URL_PATH, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ entries }) });
    return res.ok ? { ok: true, value: (await res.json()) as FolderMapView } : await failure(res);
  } catch {
    return { ok: false, message: "The folder map could not be saved." };
  }
}

export async function resetFolderMap(fetcher: typeof fetch = fetch): Promise<CallResult<FolderMapView>> {
  try {
    const res = await fetcher(URL_PATH, { method: "DELETE" });
    return res.ok ? { ok: true, value: (await res.json()) as FolderMapView } : await failure(res);
  } catch {
    return { ok: false, message: "The folder map could not be reset." };
  }
}
