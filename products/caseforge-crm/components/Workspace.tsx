"use client";

import { RecentlyViewedMenu } from "@/components/RecentlyViewedMenu";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { CSSProperties } from "react";
import { AppFooter, AppHeader } from "@/components/Shell";
import type { AppView } from "@/components/Shell";
import { legacyViewPage, parseClientLink } from "@/lib/clientLink";
import { SearchBar } from "@/components/SearchBar";
import { ResultsList } from "@/components/ResultsList";
import { DetailPanel, resetTabMemory } from "@/components/DetailPanel";
import type { OpenTab } from "@/components/DetailPanel";
import type { OpenClientTarget } from "@/lib/robotNotices";
import { UpdateBanner } from "@/components/UpdateBanner";
import { WetransferBanner } from "@/components/WetransferBanner";
import { flagsReady } from "@/lib/matterFlagsFetch";
import { ScrollChrome } from "@/components/ScrollChrome";
import { TodayBoard } from "@/components/TodayBoard";
import { FrontPageTeasers } from "@/components/FrontPageTeasers";
import { showTodayBoard } from "@/lib/todayBoard";
import { CalendarView } from "@/components/CalendarView";
import { hearingsHost, useHearingsReviewCount, useHearingsVersion } from "@/lib/hearingsHost";
import { ResizeHandle, useResultsPaneWidth } from "@/components/ResizeHandle";
import { IconChevronLeft, IconChevronRight } from "@/components/icons";
import type { Hearing } from "@/lib/hearings";
import { useFieldReviewQueue } from "@/lib/fieldReviewQueue";
import type { ClientMatch } from "@/lib/types";
import { fetchClientSearch, isAbortError, looksLikeStaleSession } from "@/lib/clientSearch";
import { applyFieldUpdate, fullNameOf, matchKey } from "@/lib/types";
import { recentSelection, recordRecentlyViewed } from "@/lib/recentlyViewed";
import { markSessionStale } from "@/lib/sessionStale";
import { measureScrollbarWidth } from "@/lib/scrollbarWidth";
import { NARROW_LAYOUT_MAX_PX, narrowPane } from "@/lib/narrowPane";
import { confirmLeaveUnsaved, unsavedLabels } from "@/lib/unsavedEdits";
import type { UnsavedSource } from "@/lib/unsavedEdits";
import { pruneExpiredDrafts } from "@/lib/formDrafts";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { DETAIL_TAB_IDS } from "@/lib/detailTabs";
import type { DetailTabId } from "@/lib/detailTabs";
import { MODE_TO_VIEW, calendarPath, clientPath, parseWorkspacePath, searchPath, viewToMode } from "@/lib/workspaceUrl";
import { useSwitcherShortcut } from "@/lib/quickSwitcher";

const QuickSwitcher = dynamic(() => import("@/components/QuickSwitcher"), { ssr: false });

const NUMBER_ORDER_LABEL = "By matter number";

const DEBOUNCE_MS = 300;

export function Workspace() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ClientMatch[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedMatch, setSelectedMatch] = useState<ClientMatch | null>(null);

  const [listSource, setListSource] = useState<string | null>(null);
  const [resultsPaneWidth, setResultsPaneWidth] = useResultsPaneWidth();

  const [resultsCollapsed, setResultsCollapsed] = useState(false);

  const shellRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLElement>(null);

  const resultsTop = useRef(0);
  useEffect(() => {
    resultsTop.current = 0;
    if (query.trim() || listSource) setResultsCollapsed(false);
  }, [query, listSource]);
  useEffect(() => {
    if (resultsCollapsed) return;
    const pane = pageRef.current?.querySelector<HTMLElement>(".results-pane");
    if (pane && resultsTop.current) pane.scrollTop = resultsTop.current;
  }, [resultsCollapsed]);

  const [narrowShowsClient, setNarrowShowsClient] = useState(false);

  const narrowResultsTop = useRef<number | null>(null);
  useEffect(() => {
    const page = pageRef.current;
    const saved = narrowResultsTop.current;
    if (!page || saved === null) return;
    if (narrowShowsClient) {
      page.scrollTop = 0;
      return;
    }
    narrowResultsTop.current = null;
    page.scrollTop = saved;
  }, [narrowShowsClient]);

  const pathname = usePathname();
  const route = useMemo(() => parseWorkspacePath(pathname), [pathname]);

  const inBrowser = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const view: AppView = route.kind === "calendar" ? "calendar" : "search";

  const lastCalendar = useRef("/calendar");
  const lastClients = useRef("/");

  const hearingsRefresh = useHearingsVersion();
  const [reviewCount, setReviewCount] = useState(0);
  const panelReviewCount = useHearingsReviewCount();
  useEffect(() => setReviewCount(panelReviewCount), [panelReviewCount]);

  const clientReview = useFieldReviewQueue(0);

  const abortRef = useRef<AbortController | null>(null);

  const [switcherOpen, setSwitcherOpen] = useState(false);
  useSwitcherShortcut(switcherOpen, setSwitcherOpen);

  const [searchNonce, setSearchNonce] = useState(0);
  const [searchesDone, setSearchesDone] = useState(0);
  const [pendingOpen, setPendingOpen] = useState<{ matterId: string; tab?: OpenTab["tab"]; hearingId?: number; searchesAtStart: number } | null>(null);
  const [openTab, setOpenTab] = useState<OpenTab | null>(null);

  const go = useCallback((url: string, how: "push" | "replace") => {
    if (typeof window === "undefined") return;
    if (`${window.location.pathname}${window.location.search}` === url) return;
    if (how === "push") window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
  }, []);

  const setView = useCallback(
    (next: AppView) => {
      if (next === view) return;
      go(next === "calendar" ? lastCalendar.current : lastClients.current, "push");
    },
    [view, go],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const requested = new URLSearchParams(window.location.search).get("view");
    const moved = legacyViewPage(requested);
    if (moved) window.location.replace(moved);
    else if (requested === "calendar") go("/calendar", "replace");
  }, [go]);

  const refreshHearings = useCallback(() => hearingsHost.bump(), []);

  function openClientFromHearing(hearing: Hearing) {
    const key = hearing.case_ref.trim() || (hearing.client_name ?? "").trim();
    if (key && hearing.matter_id != null) {
      openClientByName(key, { matterId: String(hearing.matter_id), tab: "hearings", hearingId: hearing.hearing_id });
      return;
    }
    if (key) {
      setListSource(null);
      setQuery(key);
    }
    setView("search");
  }

  useEffect(() => hearingsHost.register(openClientFromHearing));

  function openClientByName(name: string, target?: OpenClientTarget) {
    const key = name.trim();
    if (!key) return;
    setListSource(null);
    setQuery(key);
    setView("search");
    const matterId = String(target?.matterId ?? "").trim();
    if (matterId) {
      setPendingOpen({ matterId, tab: target?.tab, hearingId: target?.hearingId, searchesAtStart: searchesDone });
      setSearchNonce((n) => n + 1);
    }
  }

  useEffect(() => {
    if (!pendingOpen) return;
    const open = (match: ClientMatch, index: number) => {
      selectResult(match, matchKey(match, index));
      if (pendingOpen.tab) setOpenTab({ matterId: String(match.matter_id), tab: pendingOpen.tab, hearingId: pendingOpen.hearingId, nonce: Date.now() });
      setPendingOpen(null);
    };
    const hit = results.findIndex((m) => String(m.matter_id) === pendingOpen.matterId);
    if (hit >= 0) return open(results[hit], hit);
    if (loading || searchesDone <= pendingOpen.searchesAtStart) return;

    if (results.length === 1) open(results[0], 0);
    else setPendingOpen(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingOpen, results, loading, searchesDone]);

  useEffect(() => {

    const pane = document.querySelector<HTMLElement>(".detail-pane");
    const own = pane ? pane.offsetWidth - pane.clientWidth : -1;
    const width = own >= 0 && own < 40 ? own : measureScrollbarWidth(document);
    document.documentElement.style.setProperty("--scrollbar-w", `${width}px`);
  }, []);

  const shownMatter = selectedMatch?.matter_id != null ? String(selectedMatch.matter_id) : "";
  useEffect(() => {
    if (typeof window === "undefined") return;
    const search = window.location.search;
    if (route.kind === "client") {
      if (route.matterId === shownMatter || pendingOpen?.matterId === route.matterId) return;
      const params = new URLSearchParams(search);
      const name = (params.get("q") ?? "").trim() || route.matterId;
      const hearing = Number(params.get("hearing"));
      openClientByName(name, { matterId: route.matterId, hearingId: Number.isInteger(hearing) && hearing > 0 ? hearing : undefined, tab: (DETAIL_TAB_IDS as readonly string[]).includes(route.tab ?? "") ? (route.tab as DetailTabId) : undefined });
      return;
    }
    if (route.kind === "clients" || route.kind === "home") {
      const { query: initial, target } = parseClientLink(window.location.search);
      if (initial && initial !== query) setQuery(initial);
      if (initial && target && !shownMatter) setPendingOpen({ matterId: target.matterId ?? "", tab: target.tab, hearingId: target.hearingId, searchesAtStart: 0 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const [shownTab, setShownTab] = useState<{ matterId: string; tab: string } | null>(null);
  const hydrated = useRef(false);
  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      return;
    }
    if (view !== "search") return;
    if (selectedMatch && shownMatter) {
      const tab = shownTab && shownTab.matterId === shownMatter ? shownTab.tab : null;
      const url = clientPath(shownMatter, tab, fullNameOf(selectedMatch));
      lastClients.current = url;
      go(url, route.kind === "client" && route.matterId === shownMatter ? "replace" : "push");
    } else if (!listSource && !pendingOpen) {
      const url = searchPath(query);
      lastClients.current = url;
      go(url, "replace");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownMatter, shownTab, query, view]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      abortRef.current?.abort();
      if (!listSource) {
        setResults([]);
        setCount(0);
      }
      setError(null);
      setLoading(false);
      return;
    }
    setListSource(null);

    const timer = setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      setError(null);

      fetchClientSearch(trimmed, 20, controller.signal)
        .then(async (body) => {

          await flagsReady(body.results.map((r) => (r.matter_id != null ? String(r.matter_id) : "")).filter(Boolean));
          if (controller.signal.aborted) return;
          setResults(body.results);
          setCount(body.count);
        })
        .catch((err: unknown) => {
          if (isAbortError(err)) return;

          if (looksLikeStaleSession(err)) markSessionStale();
          setError(err instanceof Error ? err.message : "Search failed");
          setResults([]);
          setCount(0);
        })
        .finally(() => {
          if (abortRef.current === controller) setLoading(false);
          if (!controller.signal.aborted) setSearchesDone((n) => n + 1);
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [query, searchNonce]);

  function selectResult(match: ClientMatch, key: string) {

    if (key !== selectedKey && !confirmLeaveUnsaved()) return;

    const page = pageRef.current;
    if (!narrowShowsClient && page && window.matchMedia(`(max-width: ${NARROW_LAYOUT_MAX_PX}px)`).matches) {
      narrowResultsTop.current = page.scrollTop;
    }
    setSelectedKey(key);
    setSelectedMatch(match);
    setNarrowShowsClient(true);
    recordRecentlyViewed(match);
  }

  function openRecent(match: ClientMatch, all: ClientMatch[]) {

    const { matches, index } = recentSelection(all, match);
    handleQuickListResults(matches, "Recently viewed");
    selectResult(matches[index], matchKey(matches[index], index));
  }

  function openByNumber(match: ClientMatch) {
    if (!confirmLeaveUnsaved()) return;
    const index = results.findIndex((m) => String(m.matter_id) === String(match.matter_id));
    if (index < 0) {
      setListSource(NUMBER_ORDER_LABEL);
      setResults([match]);
      setCount(1);
    }
    setSelectedKey(matchKey(match, Math.max(index, 0)));
    setSelectedMatch(match);
    setView("search");
    recordRecentlyViewed(match);
  }

  function openFromSwitcher(match: ClientMatch, switcherQuery: string) {
    const matterId = match.matter_id != null ? String(match.matter_id) : "";
    openClientByName(switcherQuery || fullNameOf(match), matterId ? { matterId } : undefined);
  }

  useEffect(() => pruneExpiredDrafts(), []);

  function showUnsaved(source: UnsavedSource) {
    const el = document.querySelector<HTMLElement>(`[data-unsaved-source="${CSS.escape(source.id)}"]`);
    if (!el) {
      if (source.matterId && source.clientName) openClientByName(source.clientName, { matterId: source.matterId });
      return;
    }
    if (el.closest(".search-view")) {
      setView("search");
      setNarrowShowsClient(true);
    }
    window.requestAnimationFrame(() => {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      el.querySelector<HTMLElement>("input:not([type=checkbox]), textarea, select")?.focus({ preventScroll: true });
      el.classList.add("unsaved-flash");
      window.setTimeout(() => el.classList.remove("unsaved-flash"), 1600);
    });
  }

  function goHome() {
    if (!confirmLeaveUnsaved()) return;
    resetTabMemory();
    setQuery("");
    setListSource(null);
    setResults([]);
    setCount(0);
    setSelectedKey(null);
    setSelectedMatch(null);
    setResultsCollapsed(false);
    setView("search");
  }

  function handleViewChange(next: AppView) {
    if (next === "search" && view === "search") {
      if (listSource) {
        goHome();
        return;
      }
      document.querySelector<HTMLInputElement>(".search-input")?.focus();
      return;
    }
    setView(next);
  }

  function handleQuickListResults(quickResults: ClientMatch[], label: string) {
    if (!confirmLeaveUnsaved()) return;
    setListSource(label);
    setResults(quickResults);
    setCount(quickResults.length);
    setSelectedKey(null);
    setSelectedMatch(null);
    setView("search");
  }

  function handleFieldUpdated(fieldName: string, newValue: string) {
    setSelectedMatch((current) => (current ? applyFieldUpdate(current, fieldName, newValue) : current));
    setResults((current) =>
      current.map((m) => (m.matter_id === selectedMatch?.matter_id ? applyFieldUpdate(m, fieldName, newValue) : m)),
    );
  }

  useEffect(() => {
    if (!selectedKey) return;
    const stillPresent = results.some((m, i) => matchKey(m, i) === selectedKey);

    if (!stillPresent && unsavedLabels().length === 0) {
      setSelectedKey(null);
      setSelectedMatch(null);
    }
  }, [results, selectedKey]);

  return (

    <div
      ref={shellRef}
      className="app-shell"
      suppressHydrationWarning
    >
      <a className="skip-link" href="#main-content">
        Skip to the main content
      </a>
      <AppHeader
        onQuickListResults={handleQuickListResults}
        activeList={view === "search" ? listSource : null}
        view={view}
        onViewChange={handleViewChange}
        reviewCount={reviewCount}
        clientReviewCount={clientReview.count}
        onOpenClientByName={openClientByName}
        onOpenSwitcher={() => setSwitcherOpen(true)}
        onGoHome={goHome}
      />
      <UpdateBanner onShowUnsaved={showUnsaved} />
      <WetransferBanner />
      <main className="page" id="main-content" tabIndex={-1} ref={pageRef}>
        <h1 className="sr-only">{view === "calendar" ? "Calendar" : "Clients"}</h1>
        <div className="search-view" hidden={view !== "search"}>
          { }
          <div className="search-bar-row">
            {(query.trim() !== "" || listSource !== null) && (
              <button
                type="button"
                className="cf-btn cf-btn--flush view-tab view-tab--icon results-toggle"
                aria-pressed={resultsCollapsed}
                aria-label={resultsCollapsed ? "Show search results" : "Hide search results"}
                title={resultsCollapsed ? "Show search results" : "Hide search results"}
                onClick={() => {
                  if (!resultsCollapsed) resultsTop.current = pageRef.current?.querySelector(".results-pane")?.scrollTop ?? 0;
                  setResultsCollapsed((v) => !v);
                }}
              >
                {resultsCollapsed ? <IconChevronRight className="view-tab-icon" aria-hidden="true" /> : <IconChevronLeft className="view-tab-icon" aria-hidden="true" />}
              </button>
            )}
            <SearchBar value={query} onChange={setQuery} />
            <div className="view-tabs" role="group" aria-label="Client sections">
              <RecentlyViewedMenu onOpen={openRecent} onShowList={handleQuickListResults} />
            </div>
          </div>
          { }
          {showTodayBoard(query, listSource, selectedMatch !== null) ? (
            <>
            <FrontPageTeasers />
            <TodayBoard onOpenClient={(name, matterId, tab, hearingId) => openClientByName(name, matterId ? { matterId, tab, hearingId } : undefined)} />
            </>
          ) : (
          <div
            className="viewer-layout"
            data-narrow-pane={narrowPane({ clientOpen: selectedMatch !== null, showClient: narrowShowsClient, resultsCollapsed })}
            style={{ "--results-pane-width": `${resultsPaneWidth}px` } as CSSProperties}
          >
            {!resultsCollapsed && (
            <>
            <ResultsList
              results={results}
              count={count}
              loading={loading}
              error={error}
              query={query}
              listSource={listSource}
              selectedKey={selectedKey}
              onSelect={selectResult}
            />
            <ResizeHandle width={resultsPaneWidth} onResize={setResultsPaneWidth} />
            </>
            )}
            { }
            <button
              type="button"
              className="cf-btn cf-btn--neutral view-tab viewer-back"
              onClick={() => {
                setNarrowShowsClient(false);
                setResultsCollapsed(false);
              }}
            >
              <IconChevronLeft className="view-tab-icon" aria-hidden="true" />
              Back to results
            </button>
            <DetailPanel
              match={selectedMatch}
              onFieldUpdated={handleFieldUpdated}
              openTab={openTab}
              onOpenMatter={openByNumber}
              onShown={(matterId, tab) => setShownTab((cur) => (cur && cur.matterId === matterId && cur.tab === tab ? cur : { matterId, tab }))}
            />
          </div>
          )}
        </div>
        {view === "calendar" && inBrowser && (
          <CalendarView
            startDate={route.kind === "calendar" ? (route.date ?? undefined) : undefined}
            startView={route.kind === "calendar" && route.mode ? MODE_TO_VIEW[route.mode] : undefined}
            onNavigate={(anchor, calView) => {
              const url = calendarPath(anchor, viewToMode(calView));
              lastCalendar.current = url;
              go(url, "replace");
            }}
            refreshKey={hearingsRefresh}
            onChanged={refreshHearings}
            onReviewCount={setReviewCount}
            onOpenClient={openClientFromHearing}
          />
        )}
      </main>
      {switcherOpen && (
        <QuickSwitcher open onOpenChange={setSwitcherOpen} onOpenMatch={openFromSwitcher} onOpenRecent={openRecent} />
      )}
      <ScrollChrome shellRef={shellRef} pageRef={pageRef} resetKey={`${view}|${selectedKey ?? ""}`} />
      <AppFooter />
    </div>
  );
}
