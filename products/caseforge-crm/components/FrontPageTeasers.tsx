"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { useDismiss } from "@/lib/dismiss";
import {
  availableTeasers,
  DEFAULT_CHOICE,
  parseChoice,
  serialiseChoice,
  STORAGE_KEY,
  toggleShown,
  visibleTeasers,
} from "@/lib/frontPageTeasers";
import type { TeaserChoice } from "@/lib/frontPageTeasers";
import { LAUNCHERS, visibleLaunchers } from "@/lib/frontPageLaunchers";
import { useHearingsUpcomingCount, useHearingTabs } from "@/lib/hearingsHost";
import { badgedName, tabsBadge } from "@/lib/launcherBadges";
import type { Badge } from "@/lib/launcherBadges";
import { useLauncherBadges } from "@/lib/useLauncherBadges";
import { CountBadge } from "./CountBadge";
import { CUSTOMISE_ITEMS, CUSTOMISE_LABELS } from "@/lib/headerCustomise";
import { useHeaderHidden } from "@/lib/useHeaderHidden";
import { toggleWindow, useWindowShowing } from "@/lib/cornerPrompts";
import { arrowTarget, pressTab, rememberedTab, rememberTab, shownTab, tabStop } from "@/lib/frontPageTabs";
import { usePresentNode } from "@/lib/presence";
import { onAutoSendOpened } from "@/lib/autoSendStore";
import type { AutoSendState } from "@/lib/autoSend";
import { StatusBoardBody } from "./StatusBoardBody";
import { AutoSentPanel } from "./AutoSentPanel";
import { CourtPrepBody } from "./CourtPrepBody";
import { IconAutomation, IconBell, IconCalendar, IconClock, IconFlag, IconPerson, IconSettings, IconStar, IconUserPlus } from "./icons";
import { IconTick } from "./TodoHeader";
import type { CustomiseId } from "@/lib/headerCustomise";

const HEADER_ICONS: Record<CustomiseId, (props: { "aria-hidden"?: boolean }) => React.ReactElement> = {
  clients: IconPerson,
  calendar: IconCalendar,
  flagged: IconFlag,
  starred: IconStar,
  bell: IconBell,
  todo: IconTick,
  robot: IconAutomation,
  newclient: IconUserPlus,
  clock: IconClock,
};

export function FrontPageTeasers() {
  const [choice, setChoice] = useState<TeaserChoice>(DEFAULT_CHOICE);
  const [menuOpen, setMenuOpen] = useState(false);
  const launchers = visibleLaunchers(choice.hidden);
  const upcoming = useHearingsUpcomingCount();
  const menuRef = useRef<HTMLDivElement>(null);
  const header = useHeaderHidden();
  const badges = { ...useLauncherBadges(), "add-hearing": tabsBadge(useHearingTabs().tabs.length) } as Record<string, Badge | null>;
  const [openTab, setOpenTab] = useState(rememberedTab);

  const [autoTab, setAutoTab] = useState<AutoSendState>("leaving_soon");
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    try {
      setChoice(parseChoice(window.localStorage.getItem(STORAGE_KEY)));
    } catch {

    }
  }, []);
  useDismiss(menuOpen, () => setMenuOpen(false), menuRef);

  function update(next: TeaserChoice) {
    setChoice(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, serialiseChoice(next));
    } catch {

    }
  }

  const shown = visibleTeasers(choice);
  const ids = shown.map((t) => t.id);
  const open = shownTab(openTab, ids);
  const stop = tabStop(open, ids);

  function press(id: string) {
    const next = pressTab(open, id);
    setOpenTab(next);
    rememberTab(next);
    if (next === "auto-sent") onAutoSendOpened();
  }

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>, id: string) {
    const target = arrowTarget(ids, id, e.key);
    if (!target) return;
    e.preventDefault();
    tabRefs.current[target]?.focus();
  }

  if (shown.length === 0 && launchers.length === 0 && !menuOpen) return <HiddenRow onShow={() => setMenuOpen(true)} />;

  return (
    <section className="teasers" aria-label="Front page overviews">
      <div className="teasers-row" ref={menuRef}>
        <div className="teasers-tabs" role="tablist" aria-label="Overviews">
          {shown.map((t) => {
            const badge = badges[t.id] ?? null;
            const active = open === t.id;
            return (
              <button
                key={t.id}
                ref={(el) => {
                  tabRefs.current[t.id] = el;
                }}
                type="button"
                role="tab"
                id={`front-tab-${t.id}`}
                className="cf-btn cf-btn--flush view-tab teaser-tab front-tab"
                aria-selected={active}
                aria-expanded={active}
                aria-controls={active ? "front-tabpanel" : undefined}
                tabIndex={t.id === stop ? 0 : -1}
                aria-label={badgedName(t.label, badge)}
                onClick={() => press(t.id)}
                onKeyDown={(e) => onTabKey(e, t.id)}
              >
                <t.icon className="view-tab-icon" aria-hidden="true" />
                {t.label}
                {badge && <CountBadge count={badge.count} tone={badge.tone} label={badge.meaning} decorative />}
              </button>
            );
          })}
        </div>
        <div className="teasers-launchers" role="group" aria-label="Panels">
          {launchers.map((l) => (
            <LauncherButton key={l.id} launcher={l} badge={badges[l.id] ?? null}>
              {l.id === "hearings" && <CountBadge count={upcoming} label="upcoming hearings" />}
            </LauncherButton>
          ))}
        </div>
        <div className="teasers-customise">
          <button
            type="button"
            className="cf-btn cf-btn--icon teasers-cog"
            aria-expanded={menuOpen}
            aria-label="Customise"
            title="Customise"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <IconSettings aria-hidden="true" />
          </button>
          {menuOpen && (
            <div className="teasers-menu">
              <div role="group" aria-label="Show overviews">
                <p className="teasers-menu-heading">Overviews</p>
                {availableTeasers().map((t) => (
                  <label key={t.id} className="teasers-menu-item">
                    <input type="checkbox" checked={!choice.hidden.includes(t.id)} onChange={() => update(toggleShown(choice, t.id))} />
                    <t.icon aria-hidden="true" />
                    {t.label}
                  </label>
                ))}
                {LAUNCHERS.map((l) => (
                  <label key={l.id} className="teasers-menu-item">
                    <input type="checkbox" checked={!choice.hidden.includes(l.id)} onChange={() => update(toggleShown(choice, l.id))} />
                    <l.icon aria-hidden="true" />
                    {l.label}
                  </label>
                ))}
              </div>
              <div role="group" aria-label="Show header items">
                <p className="teasers-menu-heading">Header</p>
                {CUSTOMISE_ITEMS.map((id) => {
                  const Icon = HEADER_ICONS[id];
                  return (
                    <label key={id} className="teasers-menu-item">
                      <input type="checkbox" role="switch" checked={!header.hidden.includes(id)} onChange={() => header.toggle(id)} />
                      <Icon aria-hidden />
                      {CUSTOMISE_LABELS[id]}
                    </label>
                  );
                })}
                <div className="teasers-menu-actions">
                  <button type="button" className="cf-btn cf-btn--secondary" onClick={() => header.showAll()}>
                    Show all
                  </button>
                  <button type="button" className="cf-btn cf-btn--secondary" onClick={() => header.hideAll()}>
                    Hide all
                  </button>
                </div>
                <p className="teasers-menu-note">Applies to you, in this browser only.</p>
              </div>
            </div>
          )}
        </div>
      </div>
      <TabFold open={open}>
        {(id) =>
          id === "status-board" ? <StatusBoardBody /> : id === "auto-sent" ? <AutoSentPanel tab={autoTab} onTab={setAutoTab} /> : id === "court-prep" ? <CourtPrepBody /> : null
        }
      </TabFold>
    </section>
  );
}

function TabFold({ open, children }: { open: string; children: (id: string) => ReactNode }) {

  return usePresentNode(Boolean(open), (phase, onAnimationEnd) => (
    <div className={`tabfold tabfold-${phase}`} onAnimationEnd={onAnimationEnd}>
      <div className="tabfold-clip">
        <div className="tabfold-panel" role="tabpanel" id="front-tabpanel" aria-labelledby={`front-tab-${open}`}>
          {children(open)}
        </div>
      </div>
    </div>
  ));
}

function LauncherButton({ launcher: l, badge, children }: { launcher: (typeof LAUNCHERS)[number]; badge: import("@/lib/launcherBadges").Badge | null; children?: React.ReactNode }) {
  const showing = useWindowShowing(l.window);
  return (
    <button type="button" className="cf-btn cf-btn--flush view-tab teaser-tab teaser-launcher" title={l.hint} aria-expanded={showing} aria-label={badge ? badgedName(l.label, badge) : undefined} onClick={() => toggleWindow(l.window)}>
      <l.icon className="view-tab-icon" aria-hidden="true" />
      {l.label}
      {badge && <CountBadge count={badge.count} tone={badge.tone} label={badge.meaning} decorative />}
      {children}
    </button>
  );
}

function HiddenRow({ onShow }: { onShow: () => void }) {
  return (
    <section className="teasers teasers--empty" aria-label="Front page overviews">
      <button type="button" className="cf-btn cf-btn--icon teasers-cog" aria-label="Customise" title="Customise" onClick={onShow}>
        <IconSettings aria-hidden="true" />
      </button>
    </section>
  );
}
