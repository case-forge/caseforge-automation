
export interface DayTotal {
  date: string;
  items: number;
  net_pence: number;
  vat_pence: number;
  gross_pence: number;
}

export interface DailyTotals {
  from: string;
  to: string;
  days: DayTotal[];
  total_items: number;
  total_net_pence: number;
  total_vat_pence: number;
  total_gross_pence: number;
  undated_items: number;
}

export const MAX_RANGE_DAYS = 366;

export const PRESETS = [
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
  { label: "Last year", days: 366 },
] as const;

export function londonToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function addDays(iso: string, delta: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

export function dayCount(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T12:00:00Z`) - Date.parse(`${from}T12:00:00Z`)) / 86_400_000) + 1;
}

export interface Range {
  from: string;
  to: string;
}

export function presetRange(days: number, today: string = londonToday()): Range {
  return { from: addDays(today, 1 - days), to: today };
}

export function rangeProblem(r: Range): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(r.from) || !/^\d{4}-\d{2}-\d{2}$/.test(r.to)) return "Choose both dates.";
  if (r.to < r.from) return "The start date must not be after the end date.";
  if (dayCount(r.from, r.to) > MAX_RANGE_DAYS) return `Choose at most ${MAX_RANGE_DAYS} days.`;
  return null;
}

export function formatPounds(pence: number): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(pence / 100);
}

export function axisPounds(pence: number): string {
  return `£${(pence / 100).toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
}

export function formatDay(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function shortDay(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export function niceStep(max: number, maxTicks = 5): number {
  if (!(max > 0)) return 100;
  const rough = max / maxTicks;
  const power = 10 ** Math.floor(Math.log10(rough));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * power >= rough) return m * power;
  return 10 * power;
}

export interface YScale {
  top: number;
  step: number;
  ticks: number[];
}

export function yScale(values: readonly number[], maxTicks = 5): YScale {
  const biggest = Math.max(0, ...values);
  const step = Math.max(1, Math.round(niceStep(biggest, maxTicks)));
  const top = Math.max(step, Math.ceil(biggest / step) * step);
  const ticks: number[] = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  return { top, step, ticks };
}

export function barHeight(value: number, top: number, height: number): number {
  if (value <= 0) return 0;
  return Math.max(2, (value / top) * height);
}
