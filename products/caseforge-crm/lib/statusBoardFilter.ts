
import { awaitingSignature } from "./boardCompact";
import { boardMonth, boardYear, type StatusBoardItem } from "./matterMilestones";

export const ORDER_FILTERS = ["NMO", "CAO", "OO", "PSO", "SIO", "OTHER"] as const;
export type OrderFilter = (typeof ORDER_FILTERS)[number];

export const ORDER_FILTER_LABELS: Record<OrderFilter, string> = { NMO: "NMO", CAO: "CAO", OO: "OO", PSO: "PSO", SIO: "SIO", OTHER: "Other" };

export const STORAGE_KEY = "status-board-filter-v1";

type Facts = Pick<StatusBoardItem, "order_codes" | "book"> & Partial<Pick<StatusBoardItem, "date_joined" | "initial_ws">> & { milestones?: { contacted?: string } };

export interface BoardFilter {
  codes: OrderFilter[];

  book: string;

  year?: string;

  month?: string;
}

export const MONTHS: readonly { value: string; label: string }[] = [
  "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
].map((label, i) => ({ value: String(i + 1).padStart(2, "0"), label }));

export function periodWords(year: string | undefined, month: string | undefined): string {
  const m = MONTHS.find((x) => x.value === month)?.label ?? "";
  if (year && m) return `${m} ${year}`;
  if (year) return year;
  return m ? `${m} in any year` : "";
}

export function groupsOf(item: Pick<StatusBoardItem, "order_codes">): OrderFilter[] {
  const codes = (item.order_codes ?? []).map((c) => c.toUpperCase());
  const known = ORDER_FILTERS.filter((c) => c !== "OTHER" && codes.includes(c));
  return known.length > 0 ? known : ["OTHER"];
}

export function carriedForward(item: Facts, filter: BoardFilter): boolean {
  if (!awaitingSignature(item)) return false;
  const year = boardYear(item.date_joined ?? "");
  if (!year) return false;
  if (!filter.year) return Boolean(filter.month);
  if (year !== filter.year) return year < filter.year;
  return Boolean(filter.month) && boardMonth(item.date_joined ?? "") < (filter.month ?? "");
}

export function matchesFilter(item: Facts, filter: BoardFilter): boolean {
  if (filter.book && (item.book ?? "") !== filter.book) return false;
  if (carriedForward(item, filter)) return groupsOf(item).some((g) => filter.codes.includes(g));
  const year = boardYear(item.date_joined ?? "");
  if (filter.year && year && year !== filter.year) return false;

  const month = boardMonth(item.date_joined ?? "");
  if (filter.month && month && month !== filter.month) return false;
  return groupsOf(item).some((g) => filter.codes.includes(g));
}

export function applyFilter<T extends Facts>(items: T[], filter: BoardFilter): T[] {
  return items.filter((i) => matchesFilter(i, filter));
}

export function booksIn(items: Pick<StatusBoardItem, "book">[]): string[] {
  return [...new Set(items.map((i) => (i.book ?? "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, "en-GB", { numeric: true }));
}

export function yearsIn(items: Partial<Pick<StatusBoardItem, "date_joined">>[]): string[] {
  return [...new Set(items.map((i) => boardYear(i.date_joined ?? "")).filter(Boolean))].sort((a, b) => b.localeCompare(a));
}

export function undatedCount(items: Partial<Pick<StatusBoardItem, "date_joined">>[]): number {
  return items.filter((i) => !boardYear(i.date_joined ?? "")).length;
}

export function defaultYear(items: Partial<Pick<StatusBoardItem, "date_joined">>[], now: Date = new Date()): string {
  const years = yearsIn(items);
  const current = boardYear(now.toISOString());
  return years.includes(current) ? current : (years[0] ?? "");
}

export function pageDefaultFilter(items: Partial<Pick<StatusBoardItem, "date_joined">>[], now: Date = new Date()): BoardFilter {
  return { codes: ["NMO", "CAO"], book: "", year: defaultYear(items, now), month: "" };
}

export function nmoCaoBook(books: string[]): string {
  return books.find((b) => /nmo[\s-]*cao/i.test(b)) ?? "";
}

export function defaultFilter(items: (Pick<StatusBoardItem, "book"> & Partial<Pick<StatusBoardItem, "date_joined">>)[], now: Date = new Date()): { filter: BoardFilter; fallback: boolean } {
  const book = nmoCaoBook(booksIn(items));
  return book
    ? { filter: { codes: ["NMO", "CAO"], book, year: defaultYear(items, now) }, fallback: false }
    : { filter: { codes: [...ORDER_FILTERS], book: "", year: defaultYear(items, now) }, fallback: true };
}

export function parseStored(raw: string | null, items: (Pick<StatusBoardItem, "book"> & Partial<Pick<StatusBoardItem, "date_joined">>)[], now: Date = new Date()): BoardFilter | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as { codes?: unknown; year?: unknown; month?: unknown };
    if (!Array.isArray(data.codes)) return null;
    const codes = ORDER_FILTERS.filter((c) => (data.codes as unknown[]).includes(c));
    const year = typeof data.year === "string" && (data.year === "" || yearsIn(items).includes(data.year)) ? data.year : defaultYear(items, now);
    const month = typeof data.month === "string" && MONTHS.some((m) => m.value === data.month) ? data.month : "";
    return { codes, book: "", year, month };
  } catch {
    return null;
  }
}

export function serialise(filter: BoardFilter): string {
  return JSON.stringify({ codes: filter.codes, year: filter.year ?? "", month: filter.month ?? "" });
}

export function toggleCode(filter: BoardFilter, code: OrderFilter): BoardFilter {
  const on = filter.codes.includes(code);
  return { ...filter, codes: ORDER_FILTERS.filter((c) => (c === code ? !on : filter.codes.includes(c))) };
}

export function describe(shown: number, total: number, filter: BoardFilter, fallbackNote = false, undated = 0, carried = 0): string {
  const matters = `${total} open matter${total === 1 ? "" : "s"}`;
  const everyType = ORDER_FILTERS.every((c) => filter.codes.includes(c));
  const types = filter.codes.length === 0 ? "no order types ticked" : everyType ? "all order types" : filter.codes.map((c) => ORDER_FILTER_LABELS[c]).join(", ");
  const folder = filter.book ? `; folder ${filter.book}` : "";
  const period = periodWords(filter.year, filter.month);
  const when = period ? `; referred in ${period}` : "";
  const noDate = undated > 0 ? ` ${undated} with no Referred date ${undated === 1 ? "is" : "are"} shown in every year and month.` : "";
  const hidden = shown < total ? ` ${total - shown} hidden by these filters.` : "";
  const note = fallbackNote ? " There is no NMO-CAO folder in the data, so everything is shown." : "";
  const forward = carried > 0 ? ` ${carried} referred earlier ${carried === 1 ? "is" : "are"} carried forward until they sign.` : "";
  return `Showing ${shown} of ${matters}: ${types}${folder}${when}.${hidden}${noDate}${forward}${note}`;
}
