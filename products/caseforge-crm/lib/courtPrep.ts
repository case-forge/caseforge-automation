
import { formatBoardDay } from "./boardCompact";

export const COURT_PREP_KEYS = ["court_informed", "client_informed", "papers_sent", "opponent_served", "counsel_booked", "bundle_sent", "brief_sent"] as const;
export type CourtPrepKey = (typeof COURT_PREP_KEYS)[number];

export interface CourtPrepItem {
  matter_id: string;
  client_name: string;
  hearing_id: number;

  hearing_date: string;
  hearing_time: string;
  hearing_type: string;

  notice?: string;
  court: string;
  is_final: boolean;

  milestones: Record<CourtPrepKey, string>;
}

export interface CourtPrepResponse {
  items: CourtPrepItem[];

  in_review?: number;
}

export const COURT_PREP_COLUMNS: readonly { key: CourtPrepKey; label: string; title: string }[] = [
  { key: "court_informed", label: "Court Informed", title: "When an email to the court about this client was sent" },
  { key: "client_informed", label: "Client Informed", title: "When the court's papers and the hearing date were sent to the client" },
  { key: "papers_sent", label: "Process Server Informed", title: "When our email with the papers to serve went to referrer" },
  { key: "opponent_served", label: "Papers Served", title: "When referrer's statement of service came back" },
  { key: "counsel_booked", label: "Counsel Booked", title: "When counsel was recorded on the hearing" },
  { key: "bundle_sent", label: "Bundle Sent", title: "When the hearing bundle was sent" },
  { key: "brief_sent", label: "Brief Sent", title: "When the brief to counsel was sent" },
];

export function courtPrepCell(value: string): string {
  if (!value) return "";
  return value === "yes" ? "Yes" : formatBoardDay(value);
}

export function hearingLine(item: Pick<CourtPrepItem, "hearing_date" | "hearing_time" | "hearing_type">): string {
  const day = formatBoardDay(item.hearing_date);
  return [day + (item.hearing_time ? ` ${item.hearing_time.slice(0, 5)}` : ""), item.hearing_type].filter(Boolean).join(" · ");
}

export function courtPrepRows(items: readonly CourtPrepItem[]): CourtPrepItem[] {
  return [...items].sort((a, b) => (a.hearing_date + (a.hearing_time || "99:99")).localeCompare(b.hearing_date + (b.hearing_time || "99:99")) || a.client_name.localeCompare(b.client_name, "en-GB", { numeric: true }) || a.hearing_id - b.hearing_id);
}
