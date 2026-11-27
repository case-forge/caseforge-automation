"use client";

import { CLIENT_LISTS, listHref } from "@/lib/clientLists";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { useDismiss } from "@/lib/dismiss";
import { PANEL_ITEMS } from "@/lib/headerOverflow";
import type { HeaderItemId } from "@/lib/headerOverflow";
import Link from "next/link";
import { IconScan, IconTray, IconCheck, IconApps, IconCall, IconFlag, IconHome, IconGraduationCap, IconMessage, IconSettings, IconPen, IconLocation, IconBundle, IconEnvelope, IconStar, IconPhoneRinging, IconChevronRight, IconClose, IconAlert, IconFolder, IconClock, IconRegenerate, IconShield, IconBell, IconListChecks, IconPound, IconList, IconFunnel, IconShieldOff, IconAuditLog } from "./icons";
import { HelpMenuEntry } from "./HelpTour";
import { FIRM, firmUrl } from "@/lib/firm";
import { ThemeToggle } from "./ThemeToggle";
import { useC8Guard } from "@/lib/c8Guard";
import { IS_DEMO } from "./HeaderClock";
import { countBadge } from "@/lib/hearingsHost";

const LIST_ICONS: Record<string, typeof IconCall> = {
  "to-check": IconAlert,
  concluded: IconCheck,
  flagged: IconFlag,
  starred: IconStar,
  "frequent-callers": IconPhoneRinging,
  transferred: IconChevronRight,
  "dropped-out": IconClose,
  billed: IconChevronRight,
};

function C8GuardTile() {
  const [on, setOn] = useC8Guard();
  return (
    <button
      type="button"
      className="cf-btn cf-btn--flush app-drawer-quick-list-item"
      aria-pressed={on}
      title="With the guard on, a client with any C8 protection has every contact detail treated as C8, not only the ones ticked. The ticks themselves are not changed."
      onClick={() => setOn(!on)}
    >
      {on ? <IconShield aria-hidden="true" /> : <IconShieldOff aria-hidden="true" />}
      <span>{on ? "C8 Guard: On" : "C8 Guard: Off"}</span>
    </button>
  );
}

function useScansWaiting(menuOpen: boolean): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let live = true;
    fetch("/api/scans/count", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((body: { known?: boolean; count?: number } | null) => {
        if (live) setCount(body?.known && Number.isInteger(body.count) ? Number(body.count) : 0);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [menuOpen]);
  return count;
}

function titleCase(label: string): string {
  return label.replace(/\b[a-z]/g, (c) => c.toUpperCase());
}

export function AppDrawer({
  compactItems,
  collapsed = [],
  overflowSlotRef,
  flagCounts,
  clientReviewCount = 0,
}: {

  compactItems?: React.ReactNode;

  collapsed?: readonly HeaderItemId[];

  overflowSlotRef?: (slot: HTMLElement | null) => void;
  flagCounts?: { flagged: number; starred: number };
  clientReviewCount?: number;
}) {
  const [open, setOpen] = useState(false);
  const scansWaiting = useScansWaiting(open);
  const rootRef = useRef<HTMLDetailsElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useDismiss(
    open,
    (reason) => {
      setOpen(false);
      if (reason === "escape") rootRef.current?.querySelector("summary")?.focus();
    },
    rootRef,
  );

  useEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    const onClick = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest("[data-menu-close]")) setOpen(false);
    };
    menu.addEventListener("click", onClick);
    return () => menu.removeEventListener("click", onClick);
  }, []);

  const showInMenu = (id: HeaderItemId) => collapsed.includes(id);
  const hasOverflowEntries = showInMenu("clock") || showInMenu("view") || PANEL_ITEMS.some(showInMenu);

  return (
    <details
      className="app-drawer"
      ref={rootRef}
      data-header-fixed=""
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cf-btn cf-btn--icon app-drawer-trigger" aria-label={`Quick lists and other ${FIRM.short_name} apps`} title={`Quick lists and other ${FIRM.short_name} apps`}>
        <IconApps />
      </summary>
      <div className="app-drawer-menu" ref={menuRef}>
        <div className="app-drawer-overflow" hidden={!hasOverflowEntries}>
          {compactItems}
          <div className="app-drawer-overflow-slot" ref={overflowSlotRef} />
          <div className="app-drawer-divider" />
        </div>
        <>
            <div className="app-drawer-quick-lists">
              { }
              <Link href="/scans" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconScan aria-hidden="true" />
                <span title={scansWaiting > 0 ? `${scansWaiting} scanned documents waiting to be filed` : undefined}>
                  Scans{scansWaiting > 0 ? ` (${countBadge(scansWaiting)})` : ""}
                </span>
              </Link>
              <Link href="/notification-board" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconBell aria-hidden="true" />
                <span>Notification Board</span>
              </Link>
              { }
              <Link href="/review-mail" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconFunnel aria-hidden="true" />
                <span>Improve Classifier</span>
              </Link>
              { }
              <Link href="/status-board" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconListChecks aria-hidden="true" />
                <span>Status Board</span>
              </Link>
              { }
              <Link href="/billing-chart" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconPound aria-hidden="true" />
                <span>Billing by Day</span>
              </Link>
              { }
              <Link href="/audit" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconAuditLog aria-hidden="true" />
                <span>Audit trail</span>
              </Link>
              { }
              <Link href="/client-lists" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconList aria-hidden="true" />
                <span>Client Lists{clientReviewCount > 0 ? ` (${clientReviewCount})` : ""}</span>
              </Link>
              { }
              {CLIENT_LISTS.filter(({ id }) => (id === "flagged" || id === "starred") && showInMenu(id)).map(({ id, label }) => {
                const EntryIcon = LIST_ICONS[id] ?? IconClock;
                const count = id === "flagged" ? flagCounts?.flagged : flagCounts?.starred;
                return (
                  <Link key={id} href={listHref(id)} target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                    <EntryIcon aria-hidden="true" />
                    <span>
                      {titleCase(label)}
                      {count && count > 0 ? ` (${count})` : ""}
                    </span>
                  </Link>
                );
              })}
              { }
              <a href={IS_DEMO ? firmUrl("crm") : firmUrl("demo")} target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                {IS_DEMO ? <IconHome aria-hidden="true" /> : <IconGraduationCap aria-hidden="true" />}
                <span>{IS_DEMO ? "Home" : "Demo"}</span>
              </a>
              { }
              <a href={firmUrl("chat")} target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconMessage aria-hidden="true" />
                <span>Vergil</span>
              </a>
              { }
              <a href={firmUrl("sign")} target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconPen aria-hidden="true" />
                <span>E-Signatures</span>
              </a>
              <a href="https://caseforge.uk/bundletool" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconBundle aria-hidden="true" />
                <span>BundleTool</span>
              </a>
              <a href="https://caseforge.uk/chambers-finder" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconLocation aria-hidden="true" />
                <span>Chambers Finder</span>
              </a>
              <a href="https://caseforge.uk/envelope-guide" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconEnvelope aria-hidden="true" />
                <span>Envelope Guide</span>
              </a>
              { }
              <HelpMenuEntry />
              { }
              <div className="app-drawer-theme" role="group" aria-label="Theme">
                <ThemeToggle />
              </div>
              { }
              <C8GuardTile />
              { }
              <Link href="/settings" target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="">
                <IconSettings aria-hidden="true" />
                <span>Settings</span>
              </Link>
            </div>
        </>
      </div>
    </details>
  );
}
