
import { actorKindWord, type ActorKind } from "./actorKind";

export type AuditKind = "all" | ActorKind;

export interface AuditRow {
  id: string;
  at: string;

  kind: ActorKind | "";
  who: string;
  area: string;
  action: string;
  what: string;
  from: string;
  to: string;
  where: string;
  ip: string;
  seen_by: string[];
  likely_crm_user?: string;

  item_id?: string;
  matter_id?: string;
  mode?: string;
}

export interface AuditTrail {
  rows: AuditRow[];
  total: number;
  counts: Record<ActorKind, number>;
  since: string;
  until: string;
  kind: AuditKind;
}

export type AuditLoad = { state: "hidden" } | { state: "error" } | { state: "ok"; data: AuditTrail };

export interface AuditQuery {
  kind: AuditKind;
  days: number;
  q: string;
  offset: number;
  limit: number;
}

export const DAY_CHOICES = [1, 7, 30, 90] as const;
export const PAGE_SIZE = 100;

export function queryString(query: AuditQuery): string {
  const params = new URLSearchParams({ kind: query.kind, days: String(query.days), limit: String(query.limit), offset: String(query.offset) });
  if (query.q.trim()) params.set("q", query.q.trim());
  return params.toString();
}

export async function loadAuditTrail(query: AuditQuery, fetcher: typeof fetch = fetch): Promise<AuditLoad> {
  try {
    const res = await fetcher(`/api/audit-trail?${queryString(query)}`, { cache: "no-store" });
    if (res.status === 403) return { state: "hidden" };
    if (!res.ok) return { state: "error" };
    return { state: "ok", data: (await res.json()) as AuditTrail };
  } catch {
    return { state: "error" };
  }
}

export function whenLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("day")} ${get("month")}, ${get("hour")}:${get("minute")}`;
}

export function sourceLabel(seenBy: string[]): string {
  const ours = seenBy.includes("ours");
  const theirs = seenBy.includes("microsoft");
  return ours && theirs ? "Both logs" : theirs ? "Microsoft" : "Our log";
}

export function changeParts(row: AuditRow): { from: string; to: string } | { what: string } {
  return row.from && row.to ? { from: row.from, to: row.to } : { what: row.what || row.where || "" };
}

export function kindLabel(kind: ActorKind | ""): string {
  return actorKindWord(kind);
}
