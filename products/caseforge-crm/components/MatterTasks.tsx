"use client";

import { GRAPH_READ_CACHE_MS, useLazyFetch } from "@/lib/useLazyFetch";
import { formatArrived, isCompleted, subjectLine, taskPillLabel } from "@/lib/matterTasks";
import type { MatterTaskItem, MatterTasksResponse } from "@/lib/types";

export function useMatterTasks(matterId: string): MatterTasksResponse | null {

  const { data, failed } = useLazyFetch<MatterTasksResponse>(
    matterId ? `/api/clients/matter-tasks?matter_id=${encodeURIComponent(matterId)}` : null,
    { cacheMs: GRAPH_READ_CACHE_MS },
  );
  if (!matterId) return null;
  if (data) return data;
  return failed ? { matter_id: matterId, configured: false, open_complaints: 0, open_updates: 0, open_settlements: 0, items: [] } : null;
}

export function UpdateCounts({ tasks }: { tasks: MatterTasksResponse | null }) {
  if (!tasks || !tasks.configured) return null;
  return (
    <>
      {tasks.open_complaints > 0 && (
        <span className="matter-tasks-count matter-tasks-count--complaint">
          {tasks.open_complaints} open {tasks.open_complaints === 1 ? "complaint" : "complaints"}
        </span>
      )}
      {tasks.open_settlements > 0 && (
        <span className="matter-tasks-count matter-tasks-count--settlement">
          {tasks.open_settlements} open {tasks.open_settlements === 1 ? "settlement" : "settlements"}
        </span>
      )}
      {tasks.open_updates > 0 && (
        <span className="matter-tasks-count">
          {tasks.open_updates} open {tasks.open_updates === 1 ? "update" : "updates"}
        </span>
      )}
    </>
  );
}

export function UpdateRow({ item, now }: { item: MatterTaskItem; now: Date }) {
  const pill = taskPillLabel(item);
  const arrived = formatArrived(item.created, now);
  return (
    <li className="matter-task" data-kind={item.kind} data-completed={isCompleted(item)}>
      <div className="matter-task-head">
        {pill && <span className="matter-task-pill">{pill}</span>}
        {arrived && (
          <time className="matter-task-date" dateTime={item.created}>
            {arrived}
          </time>
        )}
        {isCompleted(item) && <span className="matter-task-date">Done</span>}
        {item.deadline && <span className="matter-task-deadline">Deadline: {item.deadline}</span>}
      </div>
      <p className="matter-task-summary">{item.summary || item.subject || "Email needs review"}</p>
      {item.summary && item.subject && <p className="matter-task-subject">{subjectLine(item.subject)}</p>}
      {item.web_link && (
        <a className="matter-task-link" href={item.web_link} target="_blank" rel="noreferrer">
          Open email
        </a>
      )}
    </li>
  );
}
