
export type LandingTabId = "attendance" | "caseflow" | "hearings" | "updates";

export const DETAIL_TAB_IDS = ["client", "details", "caseflow", "activity", "case-review", "hearings", "updates", "attendance", "billing", "scanner", "todo", "vergil"] as const;
export type DetailTabId = (typeof DETAIL_TAB_IDS)[number];

export function landingTab<T extends string>(tab: T): T {
  return tab;
}

export function tabCount(label: string, count: number, noun: string, nounPlural: string): { count: number; ariaLabel?: string } {
  const n = Math.max(0, count);
  if (n === 0) return { count: 0 };
  return { count: n, ariaLabel: `${label}, ${n} ${n === 1 ? noun : nounPlural}` };
}

export function carriedTab<T extends string>(remembered: T | null | undefined, available: readonly T[]): T {
  return remembered != null && available.includes(remembered) ? remembered : available[0];
}

export function drawerSwitchTab<T extends string>({
  onExtraPage,
  lastMain,
  lastExtra,
  mainTabs,
  extraTabs,
}: {
  onExtraPage: boolean;
  lastMain: T | null | undefined;
  lastExtra: T | null | undefined;
  mainTabs: readonly T[];
  extraTabs: readonly T[];
}): T {
  return onExtraPage ? carriedTab(lastMain, mainTabs) : carriedTab(lastExtra, extraTabs);
}
