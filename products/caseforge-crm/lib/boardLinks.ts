import type { StatusBoardItem } from "./matterMilestones";

export type BoardLinkKey = "referred" | "contacted" | "initial_ws" | "filed" | "service_requested" | "laa_final_cert";

const COLUMN_LINK: Record<string, BoardLinkKey> = {
  referred: "referred",
  joined: "referred",
  contacted: "contacted",
  ws: "initial_ws",
  filed: "filed",
  service_requested: "service_requested",
  laa_final: "laa_final_cert",
};

const HOST_SUFFIXES = [".office.com", ".office365.com", ".sharepoint.com", ".live.com"] as const;

export function safeBoardLink(value: unknown): string {
  if (typeof value !== "string") return "";
  const text = value.trim();
  if (!text || text.length > 2000 || /\s/.test(text)) return "";
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return "";
  }
  if (url.protocol !== "https:" || url.username || url.password) return "";
  return HOST_SUFFIXES.some((s) => url.hostname.toLowerCase().endsWith(s)) ? text : "";
}

export function boardLinkFor(item: StatusBoardItem, columnKey: string): string {
  const key = COLUMN_LINK[columnKey];
  return key ? safeBoardLink(item.links?.[key]) : "";
}

export function boardLinkTarget(columnKey: string): string {
  const key = COLUMN_LINK[columnKey];
  return key === "initial_ws" || key === "laa_final_cert" ? "the file" : "the email";
}
