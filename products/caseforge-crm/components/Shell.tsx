"use client";

import { useRef, useState } from "react";
import type { ClientMatch } from "@/lib/types";
import { AppDrawer } from "./AppDrawer";
import { AttentionBell } from "./AttentionBell";
import { RobotNotices } from "./RobotNotices";
import type { OpenClientTarget } from "@/lib/robotNotices";
import { TodoHeader } from "./TodoHeader";
import { loadFlagList } from "@/lib/flagLists";
import { useFlagCounts } from "@/lib/useFlagCounts";
import { IconCalendar, IconFlag, IconPerson, IconSearch, IconStar } from "./icons";
import { HeaderItem, HeaderOverflowProvider, useHeaderOverflow } from "./HeaderOverflow";
import { calendarLabel, clientsLabel, showsCount } from "@/lib/headerOverflow";
import { hiddenHeaderItems } from "@/lib/headerCustomise";
import { useHeaderHidden } from "@/lib/useHeaderHidden";
import { HeaderClock, IS_DEMO } from "./HeaderClock";
import { DemoWindows } from "./DemoWindows";
import { NewClientButton } from "./NewClientButton";

export type AppView = "search" | "calendar";

export const APP_NAME = "Client Relationship Manager";

export function AppHeader({
  onQuickListResults,
  view = "search",
  onViewChange,
  reviewCount = 0,
  clientReviewCount = 0,
  onOpenClientByName,
  onOpenSwitcher,
  onGoHome,
  activeList = null,
}: {

  activeList?: string | null;
  onQuickListResults?: (results: ClientMatch[], label: string) => void;
  view?: AppView;
  onViewChange?: (view: AppView) => void;

  reviewCount?: number;

  clientReviewCount?: number;

  onOpenClientByName?: (name: string, target?: OpenClientTarget) => void;

  onGoHome?: () => void;

  onOpenSwitcher?: () => void;
}) {
  async function showFlagList(flag: "flagged" | "starred", label: string) {
    onQuickListResults?.(await loadFlagList(flag), label);
  }

  const { hidden } = useHeaderHidden();
  const clientsName = clientsLabel(clientReviewCount);
  const calendarName = calendarLabel(reviewCount);
  const viewButton = onViewChange ? (
    <span className="header-view-switch" data-header-measure="" role="group" aria-label="Clients and calendar">
      {!hidden.includes("clients") && (
      <button
        type="button"
        className="cf-btn cf-btn--flush header-view-button"
        data-active={view === "search" && !activeList}
        aria-current={view === "search" && !activeList ? "page" : undefined}
        aria-label={clientsName}
        title="Clients"
        onClick={() => onViewChange("search")}
      >
        <IconPerson aria-hidden="true" />
        {clientReviewCount > 0 && (
          <span className="header-view-badge" aria-hidden="true">
            {clientReviewCount}
          </span>
        )}
      </button>
      )}
      {!hidden.includes("calendar") && (
      <button
        type="button"
        className="cf-btn cf-btn--flush header-view-button"
        data-active={view === "calendar"}
        aria-current={view === "calendar" ? "page" : undefined}
        aria-label={calendarName}
        title="Calendar"
        onClick={() => onViewChange("calendar")}
      >
        <IconCalendar aria-hidden="true" />
        {reviewCount > 0 && (
          <span className="header-view-badge" aria-hidden="true">
            {reviewCount}
          </span>
        )}
      </button>
      )}
    </span>
  ) : null;

  const flagCounts = useFlagCounts();

  const actionsRef = useRef<HTMLDivElement>(null);

  const hiddenItems = hiddenHeaderItems(hidden);
  const collapsed = useHeaderOverflow(actionsRef, hiddenItems);
  const shows = (id: (typeof hiddenItems)[number]) => !hiddenItems.includes(id);

  const [overflowSlot, setOverflowSlot] = useState<HTMLElement | null>(null);

  const flaggedButton = onQuickListResults ? (
      <button
        type="button"
        className="cf-btn cf-btn--flush header-view-button"
        data-header-measure=""
        aria-label={flagCounts.flagged > 0 ? `Flagged, ${flagCounts.flagged}` : "Flagged"}
        title="Flagged clients"
        data-active={activeList === "Flagged"}
        aria-pressed={activeList === "Flagged"}
        onClick={() => void showFlagList("flagged", "Flagged")}
      >
        <IconFlag aria-hidden="true" />
        {flagCounts.flagged > 0 && <span className="header-view-badge" aria-hidden="true">{flagCounts.flagged}</span>}
      </button>
  ) : null;
  const starredButton = onQuickListResults ? (
      <button
        type="button"
        className="cf-btn cf-btn--flush header-view-button"
        data-header-measure=""
        aria-label={flagCounts.starred > 0 ? `Starred, ${flagCounts.starred}` : "Starred"}
        title="Starred clients"
        data-active={activeList === "Starred"}
        aria-pressed={activeList === "Starred"}
        onClick={() => void showFlagList("starred", "Starred")}
      >
        <IconStar aria-hidden="true" />
        {flagCounts.starred > 0 && <span className="header-view-badge" aria-hidden="true">{flagCounts.starred}</span>}
      </button>
  ) : null;

  const compactItems = (
    <>
      {collapsed.includes("clock") && shows("clock") && <HeaderClock inMenu />}
      {onViewChange && (collapsed.includes("view") && !hidden.includes("clients")) && (
          <button type="button" className="cf-btn cf-btn--flush cf-btn--row app-drawer-item" data-menu-close="" aria-label={clientsName} aria-current={view === "search" ? "page" : undefined} onClick={() => onViewChange("search")}>
            <IconPerson aria-hidden="true" />
            <span className="header-overflow-label">Clients</span>
            {showsCount(clientReviewCount) && <span className="header-view-badge" aria-hidden="true">{clientReviewCount}</span>}
          </button>
      )}
      {onViewChange && (collapsed.includes("view") && !hidden.includes("calendar")) && (
          <button type="button" className="cf-btn cf-btn--flush cf-btn--row app-drawer-item" data-menu-close="" aria-label={calendarName} aria-current={view === "calendar" ? "page" : undefined} onClick={() => onViewChange("calendar")}>
            <IconCalendar aria-hidden="true" />
            <span className="header-overflow-label">Calendar</span>
            {showsCount(reviewCount) && <span className="header-view-badge" aria-hidden="true">{reviewCount}</span>}
          </button>
      )}
    </>
  );

  return (
    <header className="app-header" aria-label={APP_NAME}>
      { }
      <button type="button" className="cf-btn cf-btn--icon app-header-brand" aria-label={`${APP_NAME}: back to today`} title={`${APP_NAME} - back to today`} onClick={onGoHome}>
        <img
          className="app-header-logo app-header-mark-dark"
          src="/caseforge-mark-dark.svg"
          alt=""
          aria-hidden="true"
          width={32}
          height={32}
        />
        <img
          className="app-header-logo app-header-mark-light"
          src="/caseforge-mark-light.svg"
          alt=""
          aria-hidden="true"
          width={32}
          height={32}
        />
      </button>
      {onOpenSwitcher && (

        <button
          type="button"
          className="cf-btn cf-btn--flush header-view-button switcher-phone-button"
          aria-label="Find a client"
          title="Find a client"
          onClick={onOpenSwitcher}
        >
          <IconSearch aria-hidden="true" />
        </button>
      )}
      <div className="app-header-actions" ref={actionsRef}>
        <HeaderOverflowProvider value={{ collapsed, slot: overflowSlot }}>
          {shows("clock") && (<HeaderItem id="clock">
            <HeaderClock />
          </HeaderItem>)}
          {shows("view") && (<HeaderItem id="view">{viewButton}</HeaderItem>)}
          {shows("flagged") && (<HeaderItem id="flagged">{flaggedButton}</HeaderItem>)}
          {shows("starred") && (<HeaderItem id="starred">{starredButton}</HeaderItem>)}
          {shows("bell") && (<HeaderItem id="bell">
            <AttentionBell onOpenClient={onOpenClientByName} />
          </HeaderItem>)}
          {shows("todo") && (<HeaderItem id="todo">
            <TodoHeader onOpenClient={onOpenClientByName} />
          </HeaderItem>)}
          {shows("robot") && (<HeaderItem id="robot">
            <RobotNotices onOpenClient={onOpenClientByName} />
          </HeaderItem>)}
          {shows("newclient") && (<HeaderItem id="newclient">
            <NewClientButton />
          </HeaderItem>)}
        </HeaderOverflowProvider>
        <AppDrawer
          compactItems={compactItems}
          collapsed={collapsed}
          overflowSlotRef={setOverflowSlot}
          flagCounts={flagCounts}
          clientReviewCount={clientReviewCount}
        />
      </div>
    </header>
  );
}

export function AppFooter() {
  return (
    <footer className="app-footer">
      {IS_DEMO && <DemoWindows />}
      <span className="app-footer-line app-footer-credit">
        <img
          className="app-footer-mark app-footer-mark-dark"
          src="/caseforge-mark-dark.svg"
          alt=""
          aria-hidden="true"
        />
        <img
          className="app-footer-mark app-footer-mark-light"
          src="/caseforge-mark-light.svg"
          alt=""
          aria-hidden="true"
        />
        <span>
          Built by{" "}
          <a href="https://caseforge.uk" target="_blank" rel="noopener noreferrer">
            CaseForge
          </a>
        </span>
      </span>
    </footer>
  );
}
