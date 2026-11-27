import { parseUtc } from "./matterTasks";
import type { StatusBoardItem } from "./matterMilestones";

export type ColumnId = "joined" | "contacted" | "loa" | "ws" | "filed" | "service_requested" | "served" | "laa_signed" | "laa_interim" | "laa_final";

export interface BoardColumn {
  id: ColumnId;

  label: string;
  title: string;

  value: (item: StatusBoardItem) => string;
}

export const BOARD_COLUMNS: readonly BoardColumn[] = [
  { id: "joined", label: "Referred", title: "The date the referral was sent", value: (i) => i.date_joined },
  { id: "contacted", label: "Contacted", title: "When the first email with the client's statement was sent", value: (i) => i.milestones.contacted ?? "" },
  { id: "loa", label: "LoA Signed", title: "When the signed letter of authority was filed", value: (i) => i.loa },
  { id: "ws", label: "WS Signed", title: "When the signed witness statement was filed", value: (i) => i.initial_ws },
  { id: "filed", label: "Filed to Court", title: "When the application reached the court", value: (i) => i.milestones.filed ?? "" },
  { id: "service_requested", label: "Service Requested", title: "When the papers were sent to referrer for personal service", value: (i) => i.milestones.service_requested ?? "" },
  { id: "served", label: "Served", title: "When referrer sent the statement of service back", value: (i) => i.milestones.served ?? "" },
  { id: "laa_signed", label: "LAA Signed", title: "When the signed legal aid declaration came back", value: (i) => i.milestones.legal_aid_done ?? "" },
  { id: "laa_interim", label: "LAA Interim Cert", title: "When an interim certificate was filed in the client's folder", value: (i) => i.milestones.laa_interim_cert ?? "" },
  { id: "laa_final", label: "LAA Final Cert", title: "When the full certificate was filed in the client's folder", value: (i) => i.milestones.laa_final_cert ?? "" },
];

export type SortBy = "client" | "no" | ColumnId;
export type Sort = { by: SortBy; dir: "asc" | "desc" } | null;

export function nextSort(sort: Sort, by: SortBy): Sort {
  if (!sort || sort.by !== by) return { by, dir: "asc" };
  return sort.dir === "asc" ? { by, dir: "desc" } : null;
}

const column = (id: ColumnId) => BOARD_COLUMNS.find((c) => c.id === id)!;

export function sortItems(items: readonly StatusBoardItem[], sort: Sort): StatusBoardItem[] {
  if (!sort) return [...items];
  const sign = sort.dir === "asc" ? 1 : -1;
  const text = (a: string, b: string) => a.localeCompare(b, "en-GB", { numeric: true, sensitivity: "base" });
  return [...items].sort((a, b) => {
    if (sort.by === "client") return sign * text(a.client_name, b.client_name);
    if (sort.by === "no") return sign * text(a.matter_id, b.matter_id);
    const get = column(sort.by).value;
    const x = parseUtc(get(a));
    const y = parseUtc(get(b));
    const hasX = !Number.isNaN(x);
    const hasY = !Number.isNaN(y);
    if (hasX !== hasY) return hasX ? -1 : 1;
    return hasX ? sign * (x - y) : 0;
  });
}
