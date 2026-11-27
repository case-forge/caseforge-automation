"use client";

import { actorKindWord } from "@/lib/actorKind";
import { useActivityLog } from "@/lib/pipeline";
import { eventStatusWord, eventTime, oldestFirst, safeLinks, seenByLine } from "@/lib/pipelineDisplay";
import { sortRows, useSort } from "@/lib/sortRows";
import { ActorKindLabel } from "./ActorKindLabel";
import { SortHeader } from "./SortHeader";

type LogColumn = "time" | "step" | "status" | "summary" | "by";

export function ActivityLogTab({ matterId }: { matterId: string }) {
  const { events: rows, viewers, error } = useActivityLog(matterId);
  const { sort, toggle } = useSort<LogColumn>(null);

  if (error && !rows) return <p className="cf2-error" role="alert">{error}</p>;
  if (!rows) return <p className="cf2-empty">Loading the activity log...</p>;

  const events = sortRows(oldestFirst(rows), sort, (e, key) =>
    key === "time" ? e.created_utc : key === "status" ? eventStatusWord(e.status) : key === "by" ? `${actorKindWord(e.actor_kind)} ${e.by}, ${e.mode}` : e[key],
  );
  return (
    <div className="cf2">
      <div className="cf2-bar">
        <h2 className="cf2-title">Activity log</h2>
      </div>
      <p className="cf2-note">Oldest first, newest at the bottom, unless you sort by a heading. Nothing here can be changed.</p>
      {seenByLine(viewers) && <p className="cf2-note cf2-seen-by">{seenByLine(viewers)}</p>}
      {error && <p className="cf2-error" role="alert">{error}</p>}
      {events.length === 0 ? (
        <p className="cf2-empty">Nothing has run yet.</p>
      ) : (
        <>
        <div className="cf2-log-head">
          <SortHeader label="When" sortKey="time" sort={sort} onSort={toggle} />
          <SortHeader label="Step" sortKey="step" sort={sort} onSort={toggle} />
          <SortHeader label="Result" sortKey="status" sort={sort} onSort={toggle} />
          <SortHeader label="What happened" sortKey="summary" sort={sort} onSort={toggle} />
          <SortHeader label="By" sortKey="by" sort={sort} onSort={toggle} />
        </div>
        <ol className="cf2-log" aria-label="Activity log">
          {events.map((e) => {
            const links = safeLinks(e.links);
            return (
              <li key={e.event_id} data-status={e.status}>
                <span className="cf2-log-time">{eventTime(e.created_utc)}</span>
                <span className="cf2-log-step">{e.step}</span>
                <span className="cf2-log-status">{eventStatusWord(e.status)}</span>
                <span className="cf2-log-summary">{e.summary}</span>
                <span className="cf2-log-by">
                  <ActorKindLabel kind={e.actor_kind} /> {e.by}, {e.mode}
                </span>
                {links.length > 0 && (
                  <ul className="cf2-links cf2-log-links" aria-label="Open">
                    {links.map((l) => (
                      <li key={l.url}>
                        <a href={l.url} target="_blank" rel="noreferrer">{l.label}</a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
        </>
      )}
    </div>
  );
}
