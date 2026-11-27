
export const DEFAULT_SCANNED_FOLDER = "Company_Data/Scanned Docs";
export const MAX_SCANNED_FOLDER_CHARS = 200;

export function validScannedFolder(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const text = value.trim().replace(/^\/+|\/+$/g, "");
  if (text === "") return true;
  if (text.length > MAX_SCANNED_FOLDER_CHARS || /[\\\u0000-\u001f]/.test(text)) return false;
  return text.split("/").every((part) => part.trim() !== "" && part.trim() !== "." && part.trim() !== "..");
}

export type ScannedFolder = { path: string; default: string };

export async function loadScannedFolder(): Promise<ScannedFolder> {
  const fallback = { path: DEFAULT_SCANNED_FOLDER, default: DEFAULT_SCANNED_FOLDER };
  try {
    const res = await fetch("/api/settings/scanned-docs-folder", { cache: "no-store" });
    if (!res.ok) return fallback;
    const body = await res.json();
    return typeof body?.path === "string" && body.path ? { path: body.path, default: String(body.default || DEFAULT_SCANNED_FOLDER) } : fallback;
  } catch {
    return fallback;
  }
}

export async function saveScannedFolder(value: string): Promise<ScannedFolder | null> {
  if (!validScannedFolder(value)) return null;
  try {
    const res = await fetch("/api/settings/scanned-docs-folder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: value.trim() }),
    });
    if (!res.ok) return null;
    const body = await res.json();
    return typeof body?.path === "string" && body.path ? { path: body.path, default: String(body.default || DEFAULT_SCANNED_FOLDER) } : null;
  } catch {
    return null;
  }
}
