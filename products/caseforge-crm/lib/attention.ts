import type { AttentionItem, AttentionObligation, AttentionResponse } from "./types";
import { complaintDomainLabel } from "./matterTasks";
import { ageLabel } from "./robotNotices";
import { formatDraftTime } from "./anDrafts";
import { formatDateForDisplay } from "./types";

export interface BellContents {
  items: AttentionItem[];
  scopeCreep: AttentionItem[];
  obligations: AttentionObligation[];
  complaints: number;
  tasks: number;
  scopeCreepCount: number;
  obligationsCount: number;

  total: number;
}

export function bellContents(data: AttentionResponse): BellContents {
  const scopeCreep = data.scope_creep ?? [];
  const obligations = data.obligations ?? [];

  const newClients = (data.green ?? []).filter((row) => row.kind === "new_client");
  const scopeCreepCount = data.scope_creep_count ?? scopeCreep.length;
  const obligationsCount = data.obligations_count ?? obligations.length;
  return {
    items: orderBellItems([...data.red, ...data.yellow, ...newClients]),
    scopeCreep,
    obligations,
    complaints: data.red_count,
    tasks: data.yellow_count,
    scopeCreepCount,
    obligationsCount,
    total: data.red_count + data.yellow_count + newClients.length + scopeCreepCount + obligationsCount,
  };
}

export function obligationUrgencyLabel(urgency: string): string {
  if (urgency === "red") return "Red · overdue";
  if (urgency === "amber") return "Amber · ageing";
  return "Open";
}

export function obligationDetail(row: AttentionObligation): string {
  const parts: string[] = [];
  if (row.reason.trim()) parts.push(row.reason.trim());
  if (row.age_working_days != null) {
    parts.push(`${row.age_working_days} working ${row.age_working_days === 1 ? "day" : "days"} old`);
  }
  return parts.join(" · ");
}

export function canOpenObligation(row: AttentionObligation): boolean {
  return row.client.trim() !== "" && row.matter_id != null && String(row.matter_id).trim() !== "";
}

export function isCourtItem(item: { label?: string; kind?: string }): boolean {
  return (item.label ?? "").trim().toLowerCase() === "court" || item.kind === "court_order" || item.kind === "court_rejected";
}

export function counselItems(
  data: AttentionResponse | null,
  face: "accepted" | "rejected",
): { items: AttentionItem[]; count: number } {
  if (!data) return { items: [], count: 0 };
  const items = (face === "accepted" ? data.counsel_accepted : data.counsel_rejected) ?? [];
  const count = (face === "accepted" ? data.counsel_accepted_count : data.counsel_rejected_count) ?? items.length;
  return { items, count };
}

export function courtItems(data: AttentionResponse | null, face: "order" | "rejected"): { items: AttentionItem[]; count: number } {
  if (!data) return { items: [], count: 0 };
  const items = (face === "order" ? data.court_order : data.court_rejected) ?? [];
  const count = (face === "order" ? data.court_order_count : data.court_rejected_count) ?? items.length;
  return { items, count };
}

export function faceButtonLabel(face: "smile" | "frown", statements: number, counsel: number, court = 0): string {
  const title = face === "smile" ? "Approved and accepted" : "Wants changes or declined";
  if (statements + counsel + court === 0) return `${title}, none`;
  const parts: string[] = [];
  if (statements > 0) {
    parts.push(`${statements} statement${statements === 1 ? "" : "s"} ${face === "smile" ? "approved" : "needing changes"}`);
  }
  if (counsel > 0) parts.push(`${counsel} counsel ${face === "smile" ? "accepted" : "declined"}`);
  if (court > 0) parts.push(`${court} court ${face === "smile" ? (court === 1 ? "order" : "orders") : court === 1 ? "rejection" : "rejections"}`);
  return `${title}, ${parts.join(", ")}`;
}

export function canComplete(item: AttentionItem): boolean {
  return item.can_complete === true && item.task_id.trim() !== "";
}

export function withoutItem(data: AttentionResponse, taskId: string): AttentionResponse {
  const has = (rows: AttentionItem[] | undefined): boolean => !!rows && rows.some((row) => row.task_id === taskId);
  const drop = (rows: AttentionItem[] | undefined): AttentionItem[] | undefined =>
    rows ? rows.filter((row) => row.task_id !== taskId) : rows;
  const lower = (rows: AttentionItem[] | undefined, count: number | undefined): number | undefined =>
    count !== undefined && has(rows) ? Math.max(0, count - 1) : count;
  return {
    ...data,
    red_count: lower(data.red, data.red_count) ?? data.red_count,
    yellow_count: lower(data.yellow, data.yellow_count) ?? data.yellow_count,
    red: drop(data.red) ?? [],
    yellow: drop(data.yellow) ?? [],
    scope_creep_count: lower(data.scope_creep, data.scope_creep_count),
    scope_creep: drop(data.scope_creep),
    counsel_accepted_count: lower(data.counsel_accepted, data.counsel_accepted_count),
    counsel_accepted: drop(data.counsel_accepted),
    counsel_rejected_count: lower(data.counsel_rejected, data.counsel_rejected_count),
    counsel_rejected: drop(data.counsel_rejected),
    court_order_count: lower(data.court_order, data.court_order_count),
    court_order: drop(data.court_order),
    court_rejected_count: lower(data.court_rejected, data.court_rejected_count),
    court_rejected: drop(data.court_rejected),
  };
}

export function bellButtonLabel(complaints: number, tasks: number): string {
  const total = complaints + tasks;
  if (total === 0) return "Notifications, none open";
  const parts = [`${total} open`];
  if (complaints > 0) parts.push(`${complaints} ${complaints === 1 ? "complaint" : "complaints"}`);
  return `Notifications, ${parts.join(", ")}`;
}

export function complaintPill(domain: string): string {
  const label = complaintDomainLabel(domain);
  return label === "Other" ? "Complaint" : `Complaint · ${label}`;
}

export function attentionItemTitle(item: AttentionItem): string {
  return item.who.trim() || item.subject.trim() || "Unknown sender";
}

export function canOpenClient(item: AttentionItem): boolean {
  return item.matter_id.trim() !== "" && item.who.trim() !== "";
}

export type BellTone = "red" | "amber" | "green" | "blue" | "grey";

export function isSoftComplaint(item: AttentionItem): boolean {
  return item.kind === "switchboard" || (item.kind === "complaint" && item.severity === "soft");
}

export function orderBellItems(items: AttentionItem[]): AttentionItem[] {
  return [...items.filter((i) => !isSoftComplaint(i)), ...items.filter(isSoftComplaint)];
}

export function bellItemTone(item: AttentionItem): BellTone {
  if (isSoftComplaint(item)) return "amber";
  switch (item.kind) {
    case "complaint":
    case "counsel_rejected":
    case "court_rejected":
      return "red";
    case "settlement":
    case "new_client":
    case "counsel_accepted":
    case "court_order":
      return "green";
    case "scope_creep":
      return "grey";
  }
  const label = (item.label ?? "").trim().toUpperCase();
  if (item.importance === "high" || (item.deadline ?? "").trim() !== "") return "amber";
  if (label === "NEW REFERRAL") return "green";
  if (label === "FYI" || label === "PROSPECT" || item.importance === "low") return "grey";
  return "blue";
}

export function obligationTone(urgency: string): BellTone {
  if (urgency === "red") return "red";
  if (urgency === "amber") return "amber";
  return "blue";
}

export function bellItemWhen(created: string, now: Date = new Date()): { label: string; exact: string } | null {
  const raw = (created ?? "").trim();
  if (!raw) return null;
  const label = ageLabel(raw, now);
  if (!label) return { label: formatDateForDisplay(raw), exact: raw };
  return { label, exact: formatDraftTime(raw) };
}
