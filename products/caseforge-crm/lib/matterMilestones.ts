import { parseUtc } from "./matterTasks";

export type MilestoneKey = "contacted" | "papers_signed" | "filed" | "service_requested" | "served" | "legal_aid_done" | "invoice_paid" | "laa_interim_cert" | "laa_final_cert";

export const MILESTONES: { key: MilestoneKey; label: string; title: string }[] = [
  { key: "contacted", label: "Contacted", title: "When the first email with the client's statement was sent" },
  { key: "papers_signed", label: "Papers signed", title: "When the client's signed witness statement was filed (the letter of authority is usually signed first)" },
  { key: "filed", label: "Filed", title: "When the application reached the court: the court email sent, or marked filed through the portal" },
  { key: "service_requested", label: "Service requested", title: "When the papers were sent to referrer for personal service" },
  { key: "served", label: "Served", title: "When referrer sent the statement of service back" },
  { key: "legal_aid_done", label: "LAA signed", title: "When the client's signed legal aid declaration came back, or when someone recorded it" },
  { key: "invoice_paid", label: "Invoice paid", title: "When referrer paid the invoice (recorded by hand)" },
  { key: "laa_interim_cert", label: "LAA interim cert", title: "When an interim legal aid certificate was filed in the client's folder" },
  { key: "laa_final_cert", label: "LAA final cert", title: "When the full legal aid certificate was filed in the client's folder" },
];

export const MANUAL_MILESTONES: readonly MilestoneKey[] = ["legal_aid_done", "invoice_paid"];

export interface MilestoneValue {
  at: string;
  source: string;
  set_by: string;

  manual: boolean;

  can_set: boolean;

  link?: string;
}

export interface MatterMilestonesResponse {
  matter_id: string;
  milestones: Record<MilestoneKey, MilestoneValue>;
}

export interface StatusBoardItem {
  matter_id: string;
  client_name: string;

  date_joined: string;
  loa: string;
  initial_ws: string;

  order_codes: string[];

  book: string;
  milestones: Record<MilestoneKey, string>;

  links?: Partial<Record<"referred" | "contacted" | "initial_ws" | "filed" | "service_requested" | "laa_final_cert", string>>;

  wetransfer_pending?: boolean;

  portal_court?: boolean;

  nudge?: {
    client_docs?: { rule_id: string; since_date: string; working_days: number };
    witness_statement?: { rule_id: string; since_date: string; working_days: number };
  };
}

export interface StatusBoardResponse {
  columns: { key: MilestoneKey; label: string }[];
  items: StatusBoardItem[];
}

const LONDON_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const LONDON_DATE = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "numeric", month: "short", year: "numeric" });

export function milestoneTime(iso: string): string {
  const ms = parseUtc(iso);
  return Number.isNaN(ms) ? "" : LONDON_TIME.format(new Date(ms));
}

export function boardDate(iso: string): string {
  const ms = parseUtc(iso);
  return Number.isNaN(ms) ? "" : LONDON_DATE.format(new Date(ms));
}

const LONDON_DAY_MONTH = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "numeric", month: "short" });
const LONDON_YEAR = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", year: "numeric" });
const LONDON_MONTH = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", month: "2-digit" });

export function boardDayMonth(iso: string): string {
  const ms = parseUtc(iso);
  return Number.isNaN(ms) ? "" : LONDON_DAY_MONTH.format(new Date(ms));
}

export function boardYear(iso: string): string {
  const ms = parseUtc(iso);
  return Number.isNaN(ms) ? "" : LONDON_YEAR.format(new Date(ms));
}

export function boardMonth(iso: string): string {
  const ms = parseUtc(iso);
  return Number.isNaN(ms) ? "" : LONDON_MONTH.format(new Date(ms));
}

export function milestoneSourceNote(value: MilestoneValue | undefined): string {
  if (!value || !value.at) return "";
  if (value.manual) return value.set_by ? `Recorded by ${value.set_by}` : "Recorded by hand";
  return value.source ? `From: ${value.source}` : "";
}

export function toLocalInputValue(date: Date): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/London",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function fromLocalInputValue(value: string): string {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value.trim()) ? value.trim() : "";
}

export function isManualMilestone(key: string): key is MilestoneKey {
  return (MANUAL_MILESTONES as readonly string[]).includes(key);
}

export function emptyMilestones(): Record<MilestoneKey, MilestoneValue> {
  return Object.fromEntries(
    MILESTONES.map(({ key }) => [key, { at: "", source: "", set_by: "", manual: false, can_set: isManualMilestone(key) }]),
  ) as Record<MilestoneKey, MilestoneValue>;
}
