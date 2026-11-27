
import { DEFAULT_MINUTES_PER_PAGE } from "./types";

export const MIN_MINUTES_PER_PAGE = 1;
export const MAX_MINUTES_PER_PAGE = 60;

export function validMinutesPerPage(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= MIN_MINUTES_PER_PAGE && value <= MAX_MINUTES_PER_PAGE;
}

export async function loadMinutesPerPage(): Promise<number> {
  try {
    const res = await fetch("/api/settings/minutes-per-page", { cache: "no-store" });
    if (!res.ok) return DEFAULT_MINUTES_PER_PAGE;
    const body = await res.json();
    return validMinutesPerPage(body?.minutes_per_page) ? body.minutes_per_page : DEFAULT_MINUTES_PER_PAGE;
  } catch {
    return DEFAULT_MINUTES_PER_PAGE;
  }
}

export async function saveMinutesPerPage(value: number): Promise<number | null> {
  if (!validMinutesPerPage(value)) return null;
  try {
    const res = await fetch("/api/settings/minutes-per-page", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ minutes_per_page: value }),
    });
    if (!res.ok) return null;
    const body = await res.json();
    return validMinutesPerPage(body?.minutes_per_page) ? body.minutes_per_page : null;
  } catch {
    return null;
  }
}
