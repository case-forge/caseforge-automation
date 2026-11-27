"use client";

import { useMemo } from "react";
import type { MutableRefObject } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import listPlugin from "@fullcalendar/list";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg } from "@fullcalendar/interaction";
import type { CalendarApi, DatesSetArg, EventContentArg } from "@fullcalendar/core";
import enGbLocale from "@fullcalendar/core/locales/en-gb";
import { formatTime12, formatTimeCompact, hearingLabel, hearingParties, isCounselBooked, londonNowFloating, normaliseTime, toCalendarEvent } from "@/lib/hearings";
import type { Hearing } from "@/lib/hearings";
import { draftEvent, draftLabel } from "@/lib/hearingDrafts";
import type { HearingDraft } from "@/lib/hearingDrafts";
import { HearingBadges } from "./HearingBadges";

export type CalendarViewName = "dayGridMonth" | "timeGridWeek" | "listMonth";

export interface CalendarRange {
  from: string;

  toExclusive: string;
  title: string;
  view: CalendarViewName;

  anchor: string;
}

function EventBody({ arg }: { arg: EventContentArg }) {
  const draft = arg.event.extendedProps.draft as HearingDraft | undefined;
  if (draft) {
    return (
      <div className="hearing-ev-body">
        <span className="hearing-badge hearing-badge--draft">Draft</span>
        <span className="hearing-ev-label">{draftLabel(draft)}</span>
        {draft.values.court && <span className="hearing-ev-who">{draft.values.court}</span>}
      </div>
    );
  }
  const holiday = arg.event.extendedProps.holiday as string | undefined;
  if (holiday) return <div className="hearing-ev-body"><span className="hearing-ev-label">{holiday}</span></div>;
  const hearing = arg.event.extendedProps.hearing as Hearing;
  const label = hearingLabel(hearing);
  const who = hearingParties(hearing);
  const timed = normaliseTime(hearing.hearing_time) !== null;
  const inList = arg.view.type.startsWith("list");
  const week = arg.view.type === "timeGridWeek";
  return (
    <div className={`hearing-ev-body${week ? " hearing-ev-body--stacked" : ""}`}>
      {!inList && (
        <span className="hearing-ev-time">
          {arg.view.type === "dayGridMonth" ? formatTimeCompact(hearing.hearing_time) : timed ? formatTime12(hearing.hearing_time) : "Time TBC"}
        </span>
      )}
      <span className="hearing-ev-label">{label}</span>
      <span className="hearing-ev-who">{who}</span>
      {(week || inList) && hearing.court && <span className="hearing-ev-court">{hearing.court}</span>}
      <HearingBadges hearing={hearing} />
    </div>
  );
}

function describe(hearing: Hearing): string {
  const time = normaliseTime(hearing.hearing_time) ? formatTime12(hearing.hearing_time) : "time to be confirmed";
  return [
    `${hearingLabel(hearing)}, ${hearingParties(hearing)}`,
    time,
    hearing.court || "court not stated",
    hearing.status !== "scheduled" ? hearing.status : "",
    hearing.review_state === "needs_review" ? "needs review" : "",
    isCounselBooked(hearing) ? "counsel booked" : "",
    hearing.is_final ? "final hearing" : "",
  ]
    .filter(Boolean)
    .join(", ");
}

export default function CalendarGrid({
  hearings,
  drafts = [],
  bankHolidays,
  initialView,
  initialDate,
  apiRef,
  onRange,
  onSelect,
  onSelectDraft,
  onDateClick,
  selectedDate = null,
}: {
  hearings: Hearing[];

  drafts?: HearingDraft[];
  onSelectDraft?: (draft: HearingDraft) => void;

  bankHolidays: Record<string, string>;
  initialView: CalendarViewName;

  initialDate?: string;
  apiRef: MutableRefObject<CalendarApi | null>;
  onRange: (range: CalendarRange) => void;
  onSelect: (hearing: Hearing) => void;

  onDateClick: (date: string, time: string | null) => void;

  selectedDate?: string | null;
}) {
  const events = useMemo(
    () => [
      ...hearings.map(toCalendarEvent),
      ...drafts.map(draftEvent),

      ...Object.entries(bankHolidays).map(([date, name]) => ({
        id: `bankhol-${date}`,
        title: name,
        start: date,
        allDay: true,
        classNames: ["hearing-ev--holiday"],
        editable: false,
        extendedProps: { holiday: name },
      })),
    ],
    [hearings, drafts, bankHolidays],
  );

  return (
    <FullCalendar
      ref={(instance) => {
        apiRef.current = instance ? instance.getApi() : null;
      }}
      plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
      initialView={initialView}
      initialDate={initialDate}
      headerToolbar={false}
      locale={enGbLocale}
      firstDay={1}
      timeZone="UTC"
      now={() => londonNowFloating()}
      height="100%"
      events={events}
      eventInteractive

      dayCellClassNames={(arg) => (selectedDate && arg.date.toISOString().slice(0, 10) === selectedDate ? ["hearing-day--selected"] : [])}
      dayCellDidMount={(arg) => arg.el.removeAttribute("aria-labelledby")}
      dayHeaderDidMount={(arg) => arg.el.querySelector("a:not([href])")?.removeAttribute("aria-label")}
      dayMaxEvents={4}
      nowIndicator
      allDayText="Time TBC"
      allDaySlot
      slotMinTime="08:00:00"
      slotMaxTime="18:00:00"
      slotDuration="00:30:00"
      slotLabelFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
      scrollTime="09:00:00"
      expandRows
      noEventsText="No hearings in this period."
      views={{
        dayGridMonth: { displayEventTime: false },
        timeGridWeek: { displayEventTime: false },
        listMonth: { displayEventTime: true, displayEventEnd: false },
      }}
      eventTimeFormat={{ hour: "numeric", minute: "2-digit", hour12: true, meridiem: "short" }}
      eventContent={(arg) => <EventBody arg={arg} />}
      eventDidMount={(info) => {
        const draft = info.event.extendedProps.draft as HearingDraft | undefined;
        if (draft) {
          const text = `Draft hearing, ${draftLabel(draft)}, not yet added. Click to continue it`;
          info.el.setAttribute("aria-label", text);
          info.el.setAttribute("title", text);
          return;
        }
        const hearing = info.event.extendedProps.hearing as Hearing | undefined;
        if (hearing) {
          const text = describe(hearing);
          info.el.setAttribute("aria-label", text);
          info.el.setAttribute("title", text);
        }
      }}
      eventClick={(arg) => {
        arg.jsEvent.preventDefault();
        if (arg.event.extendedProps.holiday) return;
        const draft = arg.event.extendedProps.draft as HearingDraft | undefined;
        if (draft) {
          onSelectDraft?.(draft);
          return;
        }
        onSelect(arg.event.extendedProps.hearing as Hearing);
      }}
      dateClick={(arg: DateClickArg) => {
        const date = arg.dateStr.slice(0, 10);
        const time = arg.allDay ? null : arg.dateStr.slice(11, 16) || null;
        onDateClick(date, time);
      }}
      datesSet={(arg: DatesSetArg) => {
        onRange({
          from: arg.startStr.slice(0, 10),
          toExclusive: arg.endStr.slice(0, 10),
          title: arg.view.title,
          view: arg.view.type as CalendarViewName,
          anchor: arg.view.currentStart.toISOString().slice(0, 10),
        });
      }}
    />
  );
}
