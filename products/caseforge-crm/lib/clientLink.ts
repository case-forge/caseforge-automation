
import type { OpenClientTarget } from "./robotNotices";
import type { LandingTabId } from "./detailTabs";

const LANDING_TABS: readonly LandingTabId[] = ["attendance", "caseflow", "hearings", "updates"];

export function clientHref(name: string, target?: OpenClientTarget): string {
  const params = new URLSearchParams();
  params.set("q", name.trim());
  const matterId = String(target?.matterId ?? "").trim();
  if (!/^\d+$/.test(matterId)) return `/clients?${params.toString()}`;
  if (target?.hearingId != null) params.set("hearing", String(target.hearingId));
  return `/clients/${matterId}${target?.tab ? `/${target.tab}` : ""}?${params.toString()}`;
}

export function openClientInNewTab(name: string, target?: OpenClientTarget): void {
  if (!name.trim() || typeof window === "undefined") return;
  window.open(clientHref(name, target), "_blank", "noopener,noreferrer");
}

export function parseClientLink(search: string): { query: string; target: OpenClientTarget | null } {
  const params = new URLSearchParams(search);
  const query = (params.get("q") ?? "").trim();
  const matterId = (params.get("matter") ?? "").trim();
  if (!query || !/^\d+$/.test(matterId)) return { query, target: null };
  const tab = params.get("tab") as LandingTabId | null;
  const hearing = Number(params.get("hearing"));
  return {
    query,
    target: {
      matterId,
      tab: tab && LANDING_TABS.includes(tab) ? tab : undefined,
      hearingId: Number.isInteger(hearing) && hearing > 0 ? hearing : undefined,
    },
  };
}

const LEGACY_VIEW_PAGES: Record<string, string> = {
  scans: "/scans",
  notifications: "/notification-board",
};

export function legacyViewPage(view: string | null): string | null {
  return view ? (LEGACY_VIEW_PAGES[view] ?? null) : null;
}
