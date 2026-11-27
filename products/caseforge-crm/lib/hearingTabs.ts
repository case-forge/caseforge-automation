
export const MAX_HEARING_TABS = 5;
export const TABS_FULL_HINT = "Close a tab to start another";

export interface HearingTab<T = unknown> {
  key: string;
  spec: T;
}
export interface TabsState<T = unknown> {
  tabs: HearingTab<T>[];

  active: string;
}

export const emptyTabs = <T>(): TabsState<T> => ({ tabs: [], active: "" });

export const tabsFull = (state: TabsState<unknown>): boolean => state.tabs.length >= MAX_HEARING_TABS;

export function addTab<T>(state: TabsState<T>, tab: HearingTab<T>): { state: TabsState<T>; added: boolean; full: boolean } {
  if (state.tabs.some((t) => t.key === tab.key)) return { state: { ...state, active: tab.key }, added: false, full: false };
  if (tabsFull(state)) return { state, added: false, full: true };
  return { state: { tabs: [...state.tabs, tab], active: tab.key }, added: true, full: false };
}

export function closeTab<T>(state: TabsState<T>, key: string): TabsState<T> {
  const at = state.tabs.findIndex((t) => t.key === key);
  if (at < 0) return state;
  const tabs = state.tabs.filter((t) => t.key !== key);
  const active = state.active !== key ? state.active : (tabs[at - 1] ?? tabs[at])?.key ?? "";
  return { tabs, active };
}

export function activateTab<T>(state: TabsState<T>, key: string): TabsState<T> {
  return state.tabs.some((t) => t.key === key) ? { ...state, active: key } : state;
}

export function tabTitle(spec: { clientName?: string }): string {
  return spec.clientName?.trim() || "New hearing";
}

export function serialiseTabs<T extends object>(state: TabsState<T>): string {
  return JSON.stringify({
    active: state.active,
    tabs: state.tabs.map((t) => ({ key: t.key, spec: Object.fromEntries(Object.entries(t.spec).filter(([, v]) => typeof v !== "function")) })),
  });
}

export function parseTabs<T>(raw: string | null): TabsState<T> {
  if (!raw) return emptyTabs();
  try {
    const data = JSON.parse(raw) as { active?: unknown; tabs?: unknown };
    const tabs = Array.isArray(data.tabs)
      ? (data.tabs as { key?: unknown; spec?: unknown }[]).filter((t) => t && typeof t.key === "string" && t.spec && typeof t.spec === "object").slice(0, MAX_HEARING_TABS).map((t) => ({ key: t.key as string, spec: t.spec as T }))
      : [];
    const active = typeof data.active === "string" && tabs.some((t) => t.key === data.active) ? data.active : (tabs[0]?.key ?? "");
    return { tabs, active };
  } catch {
    return emptyTabs();
  }
}
