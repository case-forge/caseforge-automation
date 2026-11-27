"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { CalendarApi } from "@fullcalendar/core";
import { calendarShown, countUnlinked, formatDateShort, icsHref, inclusiveRange, leadNotes, londonTodayIso, truncateText } from "@/lib/hearings";
import type { Hearing, HearingFormValues, HearingLead } from "@/lib/hearings";
import { resolveLead } from "@/lib/hearingsClient";
import { useHearingsRange } from "@/lib/useHearings";
import type { CalendarRange, CalendarViewName } from "./CalendarGrid";
import { hearingsHost } from "@/lib/hearingsHost";
import { datedDraftsBetween, useHearingDrafts } from "@/lib/hearingDrafts";
import { LeadsSection } from "./LeadsSection";
import { ReviewQueue } from "./ReviewQueue";
import { IconAlert, IconChevronLeft, IconChevronRight, IconDownload, IconPlus, IconSearch } from "./icons";
import { SearchClearButton } from "./ClearableSearch";

const CalendarGrid = dynamic(() => import("./CalendarGrid"), {
  ssr: false,
  loading: () => <p className="hearing-muted calendar-loading">Loading the calendar...</p>,
});

const VIEW_STORAGE_KEY = "caseforge-client-viewer:calendar-view";
const SHOW_PAST_STORAGE_KEY = "caseforge-client-viewer:calendar-show-past";
const VIEWS: { value: CalendarViewName; label: string }[] = [
  { value: "dayGridMonth", label: "Month" },
  { value: "timeGridWeek", label: "Week" },
  { value: "listMonth", label: "Agenda" },
];

function initialView(): CalendarViewName {
  try {
    const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
    if (stored === "dayGridMonth" || stored === "timeGridWeek" || stored === "listMonth") return stored;
  } catch {

  }
  return window.innerWidth < 700 ? "listMonth" : "dayGridMonth";
}

export function CalendarView({
  refreshKey,
  onChanged,
  onReviewCount,
  onOpenClient,
  startDate,
  startView,
  onNavigate,
}: {

  startDate?: string;
  startView?: CalendarViewName;

  onNavigate?: (anchor: string, view: CalendarViewName) => void;
  refreshKey: number;

  onChanged: () => void;
  onReviewCount: (count: number) => void;
  onOpenClient: (hearing: Hearing) => void;
}) {
  const apiRef = useRef<CalendarApi | null>(null);
  const [view, setView] = useState<CalendarViewName>(() => startView ?? initialView());
  const [tab, setTab] = useState<"calendar" | "review">("calendar");
  const [range, setRange] = useState<CalendarRange | null>(null);

  const [selected, setSelected] = useState<{ date: string; time: string | null } | null>(null);
  const [onlyUnlinked, setOnlyUnlinked] = useState(false);
  const [filterText, setFilterText] = useState("");

  const [showPast, setShowPast] = useState(false);
  useEffect(() => {
    try {
      setShowPast(window.localStorage.getItem(SHOW_PAST_STORAGE_KEY) === "1");
    } catch {

    }
  }, []);
  function toggleShowPast() {
    const next = !showPast;
    setShowPast(next);
    try {
      window.localStorage.setItem(SHOW_PAST_STORAGE_KEY, next ? "1" : "0");
    } catch {

    }
  }

  const inclusive = range ? inclusiveRange(range.from, range.toExclusive) : null;
  const { hearings, bankHolidays, toCheckCount, loading, error, loaded } = useHearingsRange(inclusive?.from ?? null, inclusive?.to ?? null, refreshKey);

  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (loaded) onReviewCount(toCheckCount);
  }, [loaded, toCheckCount, onReviewCount]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 12000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  function changeView(next: CalendarViewName) {
    setView(next);
    apiRef.current?.changeView(next);
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, next);
    } catch {

    }
  }

  function openCreate(defaults: Partial<HearingFormValues>, lead?: HearingLead) {
    hearingsHost.openCreate({
      matterId: defaults.matter_id ?? "",
      suffix: lead ? `lead-${lead.lead_id}` : "manual",
      defaults,
      known: hearings,
      intro: lead ? `Adding a hearing from the email "${truncateText(lead.source_subject || "(no subject)", 100)}". When you save it, that email is marked done.` : undefined,
      openAfter: !lead,
      onCreated: (h) => {
        if (lead) {

          const added = `Hearing added for ${formatDateShort(h.hearing_date)}.`;
          resolveLead(lead.lead_id, "done")
            .then(() => setNotice(`${added} The email was marked done.`))
            .catch((err: unknown) => setNotice(`${added} It could not be marked done (${err instanceof Error ? err.message : "error"}); mark it done yourself so it leaves the list.`))
            .finally(onChanged);
          return;
        }
        setTab("calendar");
        apiRef.current?.gotoDate(h.hearing_date);
        onChanged();
      },
    });
  }

  const active = hearings.filter((h) => h.review_state !== "dismissed");

  const unlinkedCount = countUnlinked(active);
  const savedDrafts = useHearingDrafts();
  const datedDrafts = datedDraftsBetween(savedDrafts, "0000-01-01");
  const shown = calendarShown(hearings, { todayIso: londonTodayIso(), showPast, onlyUnlinked, filterText });
  const visibleCount = shown.length;

  return (
    <section className="calendar-view" aria-label="Hearings calendar">
      <div className="search-bar-row">
        <div className="search-card calendar-filter-card">
          <div className="search-row">
            <div className="search-input-wrap">
              <IconSearch />
              <input
                type="search"
                className="search-input"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Client, case no. or court"
                aria-label={tab === "calendar" ? "Filter hearings by client name, case number or court" : "Filter the To check list"}
                autoComplete="off"
              />
              {filterText !== "" && <SearchClearButton label="Clear the filter" onClear={() => setFilterText("")} />}
            </div>
          </div>
        </div>
        <div className="view-tabs" role="group" aria-label="Calendar sections">
          <button type="button" className="cf-btn cf-btn--neutral view-tab" aria-pressed={tab === "calendar"} onClick={() => setTab("calendar")}>
            Calendar
          </button>
          <button
            type="button"
            className="cf-btn cf-btn--flush view-tab view-tab--icon"
            aria-pressed={tab === "review"}
            aria-label={toCheckCount > 0 ? `To check, ${toCheckCount} ${toCheckCount === 1 ? "item" : "items"}` : "To check"}
            title="To check"
            onClick={() => setTab("review")}
          >
            <IconAlert className="view-tab-icon" aria-hidden="true" />
            <span className="view-tab-count">{toCheckCount}</span>
          </button>
        </div>
      </div>

      {tab === "calendar" ? (
        <>
          <div className="calendar-toolbar">
            <div className="calendar-nav">
              <button type="button" className="cf-btn cf-btn--neutral" onClick={() => apiRef.current?.today()}>
                Today
              </button>
              <button type="button" className="cf-btn cf-btn--icon hearing-icon-button" aria-label="Previous" onClick={() => apiRef.current?.prev()}>
                <IconChevronLeft />
              </button>
              <button type="button" className="cf-btn cf-btn--icon hearing-icon-button" aria-label="Next" onClick={() => apiRef.current?.next()}>
                <IconChevronRight />
              </button>
              <h2 className="calendar-title" aria-live="polite">
                {range?.title ?? ""}
              </h2>
            </div>
            <div className="calendar-view-switch" role="group" aria-label="Calendar view">
              {VIEWS.map((v) => (
                <button key={v.value} type="button" className="cf-btn cf-btn--segment calendar-view-button" aria-pressed={view === v.value} onClick={() => changeView(v.value)}>
                  {v.label}
                </button>
              ))}
            </div>
            <div className="calendar-actions">
              <button
                type="button"
                className="cf-btn cf-btn--chip calendar-action calendar-filter"
                aria-pressed={onlyUnlinked}
                onClick={() => setOnlyUnlinked((v) => !v)}
                title="Show only hearings with no client recorded, in the period on screen"
              >
                Unlinked
                <span className="calendar-filter-count">{unlinkedCount}</span>
              </button>
              <button
                type="button"
                className="cf-btn cf-btn--chip calendar-action calendar-filter"
                aria-pressed={showPast}
                onClick={toggleShowPast}
                title="Past hearings are kept; this shows or hides the ones before today"
              >
                Show past
              </button>
              <button
                type="button"
                className="cf-btn cf-btn--primary calendar-action"
                title={selected ? `Add a Hearing on ${formatDateShort(selected.date)}` : "Add a Hearing"}
                onClick={() => openCreate(selected ? { hearing_date: selected.date, hearing_time: selected.time ?? "" } : {})}
              >
                <IconPlus aria-hidden="true" />
                Add hearing
              </button>
              {inclusive ? (
                <a className="cf-btn cf-btn--neutral calendar-action" href={icsHref(inclusive.from, inclusive.to)} download>
                  <IconDownload aria-hidden="true" />
                  Export .ics
                </a>
              ) : (
                <span className="cf-btn cf-btn--neutral calendar-action" aria-disabled="true">
                  <IconDownload aria-hidden="true" />
                  Export .ics
                </span>
              )}
            </div>
          </div>

          <div className="calendar-status" role="status" aria-live="polite">
            {error ? (
              <span className="hearing-form-error" role="alert">{error}</span>
            ) : loading ? (
              <span className="hearing-muted">Loading hearings...</span>
            ) : range && visibleCount === 0 ? (
              <span className="hearing-muted">{onlyUnlinked || filterText.trim() ? "No hearings match in this period." : showPast ? "No hearings in this period." : "No upcoming hearings in this period."}</span>
            ) : null}
          </div>

          <div className="hearing-calendar" data-view={view}>
            <CalendarGrid
              hearings={shown}
              drafts={datedDrafts}
              onSelectDraft={(d) => hearingsHost.openDraft(d, hearings)}
              bankHolidays={bankHolidays}
              initialView={view}
              initialDate={range?.anchor ?? (startDate && startDate.length === 7 ? `${startDate}-01` : startDate)}
              apiRef={apiRef}
              onRange={(next) => {
                setRange(next);
                onNavigate?.(next.anchor, next.view);
              }}
              onSelect={(h) => hearingsHost.openEdit(h)}
              selectedDate={selected?.date ?? null}
              onDateClick={(date, time) => setSelected({ date, time })}
            />
          </div>
        </>
      ) : (
        <div className="to-check">
          {notice && (
            <p className="hearing-link-notice" role="status">
              {notice}
            </p>
          )}
          <LeadsSection
            filter={filterText}
            refreshKey={refreshKey}
            onChanged={onChanged}
            onAddHearing={(lead) => openCreate({ notes: leadNotes(lead) }, lead)}
          />
          <ReviewQueue
            filter={filterText}
            refreshKey={refreshKey}
            onChanged={onChanged}
            onOpen={(h) => hearingsHost.openEdit(h)}
          />
        </div>
      )}

    </section>
  );
}
