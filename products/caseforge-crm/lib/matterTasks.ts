import type { MatterTaskItem, MatterTasksResponse } from "./types";

const COMPLAINT_DOMAIN_LABELS: Record<string, string> = {
  ccl_terms: "CCL terms",
  documenso_process: "Documenso",
  other: "Other",
};

const SETTLEMENT_STAGE_LABELS: Record<string, string> = {
  requested: "Requested",
  sent: "Sent out",
  signed: "Signed and returned",
};

export function settlementStageLabel(stage: string): string {
  return SETTLEMENT_STAGE_LABELS[stage] ?? "";
}

export function complaintDomainLabel(domain: string): string {
  return COMPLAINT_DOMAIN_LABELS[domain] ?? "Other";
}

export function taskPillLabel(item: MatterTaskItem): string | null {
  if (item.kind === "complaint") return `Complaint · ${complaintDomainLabel(item.complaint_domain)}`;
  if (item.kind === "switchboard") return "Switchboard";
  if (item.kind === "scope_creep") return "Scope creep";
  if (item.kind === "settlement") {
    if (item.settlement_stage === "care") return "Care proceedings";
    const stage = settlementStageLabel(item.settlement_stage);
    return stage ? `Settlement · ${stage}` : "Settlement";
  }
  return null;
}

export function isCompleted(item: MatterTaskItem): boolean {
  return item.status === "completed";
}

export function subjectLine(subject: string): string {
  const trimmed = subject.trim();
  if (!trimmed) return "";
  return /^re:\s*/i.test(trimmed) ? trimmed : `Re: ${trimmed}`;
}

export function parseUtc(iso: string): number {
  const trimmed = (iso || "").trim();
  if (!trimmed) return Number.NaN;
  const normalised = trimmed.replace(/(\.\d{3})\d+/, "$1");
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalised) ? normalised : `${normalised}Z`;
  return Date.parse(zoned);
}

const LONDON_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function formatArrived(iso: string, now: Date = new Date()): string {
  const ms = parseUtc(iso);
  if (Number.isNaN(ms)) return "";
  const parts = (d: Date) => Object.fromEntries(LONDON_PARTS.formatToParts(d).map((p) => [p.type, p.value]));
  const at = parts(new Date(ms));
  const year = at.year === parts(now).year ? "" : ` ${at.year}`;
  return `${at.day} ${at.month}${year} ${at.hour}:${at.minute}`;
}

export function newestFirst(items: MatterTaskItem[]): MatterTaskItem[] {
  const key = (item: MatterTaskItem) => {
    const ms = parseUtc(item.created);
    return Number.isNaN(ms) ? Number.NEGATIVE_INFINITY : ms;
  };
  return [...items].sort((a, b) => key(b) - key(a));
}

export function openItemCount(tasks: MatterTasksResponse | null): number {
  if (!tasks || !tasks.configured) return 0;
  return tasks.items.filter((item) => !isCompleted(item)).length;
}
