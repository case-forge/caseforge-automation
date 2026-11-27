"use client";

import { useReportShowing } from "@/lib/cornerPrompts";
import { useEffect, useState } from "react";
import { usePresentNode } from "@/lib/presence";
import { filterHearings, formatDayHeading, formatTime12, groupByDay, hearingLabel, hearingParties, londonTodayIso, upcomingWindow } from "@/lib/hearings";
import type { Hearing } from "@/lib/hearings";
import { RAIL_WINDOW_ID, useHearingsRange } from "@/lib/useHearings";
import { windowPins } from "@/lib/windowPins";
import { countBadge } from "@/lib/hearingsHost";
import { CountBadge } from "./CountBadge";
import { useFloatingBox } from "@/lib/useFloatingBox";
import { RESIZE_EDGES } from "@/lib/demoWindows";
import { CardBar } from "./CardBar";
import { HearingBadges } from "./HearingBadges";
import { ClearableSearch } from "./ClearableSearch";

const WINDOW_DAYS = 14;

export function UpcomingRail({
  open,
  onOpenChange,
  refreshKey,
  onReviewCount,
  onUpcomingCount,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  refreshKey: number;
  onReviewCount: (count: number) => void;

  onUpcomingCount?: (count: number) => void;
  onSelect: (hearing: Hearing) => void;
}) {

  const [today, setToday] = useState<string | null>(null);
  useEffect(() => {
    setToday(londonTodayIso());
  }, [refreshKey]);

  const window14 = today ? upcomingWindow(today, WINDOW_DAYS) : null;
  const { hearings, toCheckCount, loading, error, loaded } = useHearingsRange(window14?.from ?? null, window14?.to ?? null, refreshKey);

  useEffect(() => {
    if (loaded) onReviewCount(toCheckCount);
  }, [loaded, toCheckCount, onReviewCount]);

  const [filterText, setFilterText] = useState("");
  const groups = groupByDay(filterHearings(hearings, filterText));
  const total = groups.reduce((sum, g) => sum + g.items.length, 0);
  const upcoming = hearings.length;
  useEffect(() => {
    if (loaded) onUpcomingCount?.(upcoming);
  }, [loaded, upcoming, onUpcomingCount]);

  const win = useFloatingBox(RAIL_WINDOW_ID, "Hearings Panel");
  const close = () => {
    if (win.pinned) windowPins.toggle(RAIL_WINDOW_ID);
    win.restore();
    onOpenChange(false);
  };
  useReportShowing("hearings", open && !win.minimised, close);

  return usePresentNode(open, (phase, onAnimationEnd) => (
    <aside
      ref={win.windowRef as React.RefObject<HTMLElement>}
      className={`hearings-panel fw ${win.windowClass} widget-${phase}`}
      {...win.windowAttrs}
      role="dialog"
      aria-label="Upcoming hearings"
      aria-hidden={win.minimised || phase === "closing" || undefined}
      style={win.style}
      onAnimationEnd={onAnimationEnd}
    >
      <div className="hearings-panel-frame">
        <CardBar id={RAIL_WINDOW_ID} title="Upcoming Hearings" windowName="Hearings Panel" extras={countBadge(upcoming) ? <CountBadge count={upcoming} label="upcoming hearings" /> : undefined} pinned={win.pinned} onClose={close} onMinimise={win.minimise} barProps={win.barProps} />

        <div className="hearings-rail-search">
          <ClearableSearch
            className="edit-input"
            value={filterText}
            onValueChange={setFilterText}
            clearLabel="Clear the filter"
            placeholder="Client, case number or court"
            aria-label="Filter upcoming hearings by client name, case number or court"
            autoComplete="off"
          />
        </div>

        <div className="hearings-rail-body">
          {error && (
            <p className="hearing-form-error" role="alert">
              {error}
            </p>
          )}
          {!error && loading && total === 0 && <p className="hearing-muted">Loading...</p>}
          {!error && !loading && total === 0 && <p className="hearing-muted">{filterText.trim() ? "No hearings match." : `No hearings in the next ${WINDOW_DAYS} days.`}</p>}
          {groups.map((group) => (
            <section key={group.date} className="hearings-rail-day">
              <h3 className="hearings-rail-day-title">{today ? formatDayHeading(group.date, today) : group.date}</h3>
              <ul className="hearings-rail-list">
                {group.items.map((hearing) => (
                  <li key={hearing.hearing_id}>
                    <button
                      type="button"
                      className={`hearings-rail-item${hearing.status !== "scheduled" ? " hearings-rail-item--muted" : ""}${hearing.review_state === "needs_review" ? " hearings-rail-item--review" : ""}`}
                      onClick={() => onSelect(hearing)}
                    >
                      <span className="hearings-rail-time">{formatTime12(hearing.hearing_time)}</span>
                      <span className="hearings-rail-what">
                        <span className="hearings-rail-label">{hearingLabel(hearing)}</span>
                        <span className="hearings-rail-who">{hearingParties(hearing)}</span>
                        {hearing.court && <span className="hearings-rail-court">{hearing.court}</span>}
                        <span className="hearings-rail-badges">
                          <HearingBadges hearing={hearing} markers />
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

      </div>
      {!win.maximised && !win.pinned && RESIZE_EDGES.map((edge) => <div key={edge} className={`fw-grip fw-grip-${edge}`} aria-hidden="true" {...win.gripProps(edge)} />)}
    </aside>
  ));
}
