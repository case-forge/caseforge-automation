"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSignedInName } from "@/lib/editorName";
import {
  AUTO_DISMISS_DAYS,
  BELL_DAYS,
  BOARD_TABS,
  boardRows,
  fetchNotificationBoard,
  fetchRobotBoard,
  NOTIFICATION_SORTS,
  opsFreshness,
  setNotificationState,
  tabCount,
} from "@/lib/notifications";
import type { BoardSide, BoardTab, NotificationBoardData, NotificationSort, NotificationState, RobotBoardData } from "@/lib/notifications";
import { ageLabel, tabForNotice, useRobotNotices } from "@/lib/robotNotices";
import type { OpenClientTarget } from "@/lib/robotNotices";

import { useAttentionDone } from "./AttentionDone";
import { IconRefresh } from "./icons";
import { NotificationRow } from "./NotificationRow";
import { ClearableSearch } from "./ClearableSearch";
import { useSpecialSenders } from "@/lib/specialSenders";

type OpenClient = (name: string, target?: OpenClientTarget) => void;

const SIDES: { key: BoardSide; label: string }[] = [
  { key: "human", label: "Human" },
  { key: "robot", label: "Automation" },
];

const EMPTY_WORDS: Record<BoardTab, string> = {
  active: `Nothing older than ${BELL_DAYS} days is waiting.`,
  dismissed: "Nothing has been dismissed.",
  hidden: "Nothing is hidden.",
};

const TAB_HINT: Record<BoardTab, string> = {
  active: `Notifications older than ${BELL_DAYS} days that nobody has dismissed. Each is dismissed automatically once it is ${AUTO_DISMISS_DAYS} days old.`,
  dismissed: `Dismissed by you, or automatically after ${AUTO_DISMISS_DAYS} days. Put back returns one to the board.`,
  hidden: "Hidden by you. Put back returns one to the board, or to your bell if it is recent.",
};

function RobotSide({ onOpenClient, reloadToken, onLoading }: { onOpenClient?: OpenClient; reloadToken: number; onLoading: (loading: boolean) => void }) {
  const [data, setData] = useState<RobotBoardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const { dismiss } = useRobotNotices();
  const latest = useRef(0);

  const load = useCallback(async () => {
    const mine = ++latest.current;
    setLoading(true);
    onLoading(true);
    setError("");
    try {
      const next = await fetchRobotBoard();
      if (mine === latest.current) setData(next);
    } catch (err) {
      if (mine === latest.current) setError(err instanceof Error ? err.message : "Could not read the Automation notices.");
    } finally {
      if (mine === latest.current) {
        setLoading(false);
        onLoading(false);
      }
    }
  }, [onLoading]);
  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  return (
    <>
      <p className="assign-hint">
        What the automatic jobs could not finish by themselves, and the system health alerts. An Automation notice clears itself when the problem is
        fixed, or when you dismiss it.
      </p>
      {error && (
        <p className="assign-notice assign-notice--error" role="alert">
          {error}
        </p>
      )}
      {!data && loading && (
        <p className="assign-empty" role="status">
          Reading the Automation notices…
        </p>
      )}
      {data && (
        <>
          <h3 className="attention-group-title">Needs a person ({data.open.length})</h3>
          {data.open.length === 0 ? (
            <p className="assign-empty">Nothing needs a person.</p>
          ) : (
            <ul className="attention-list notification-list">
              {data.open.map((notice) => (
                <li key={notice.notice_id} className="attention-item" data-kind="robot">
                  <div className="attention-item-head">
                    <span className="attention-item-who">{notice.title}</span>
                    {notice.client_name && <span className="attention-item-pill">{notice.client_name}</span>}
                    <span className="attention-item-date">{ageLabel(notice.created_utc)}</span>
                  </div>
                  {notice.detail && <p className="attention-item-summary">{notice.detail}</p>}
                  <div className="attention-item-actions">
                    {onOpenClient && notice.client_name && (
                      <button
                        type="button"
                        className="cf-btn cf-btn--link attention-item-link"
                        onClick={() => onOpenClient(notice.client_name, { matterId: notice.matter_id, tab: tabForNotice(notice.kind) })}
                      >
                        Open client
                      </button>
                    )}
                    <button
                      type="button"
                      className="cf-btn cf-btn--link attention-item-link"
                      onClick={() => void dismiss(notice.notice_id).then(() => load())}
                    >
                      Dismiss
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <h3 className="attention-group-title">System health</h3>
          <p className="assign-hint">{opsFreshness(data.ops)}</p>
          {data.ops.admin && data.ops.alerts.length > 0 && (
            <ul className="attention-list notification-list">
              {data.ops.alerts.map((alert, i) => (
                <li key={`${alert.title}:${i}`} className="attention-item" data-kind="ops" data-tone={alert.severity === "red" ? "red" : alert.severity === "amber" ? "amber" : "grey"}>
                  <div className="attention-item-head">
                    <span className="attention-item-who">{alert.title}</span>
                    <span className="attention-item-pill">{alert.severity === "red" ? "Red" : alert.severity === "amber" ? "Amber" : "Info"}</span>
                    <span className="attention-item-pill">{alert.category === "housekeeping" ? "Housekeeping" : "Health"}</span>
                  </div>
                  {alert.next_action && <p className="attention-item-summary">{alert.next_action}</p>}
                </li>
              ))}
            </ul>
          )}
          {data.ops.admin && data.ops.available && data.ops.alerts.length === 0 && <p className="assign-empty">No alerts.</p>}
          <h3 className="attention-group-title">Closed ({data.resolved.length})</h3>
          {data.resolved.length === 0 ? (
            <p className="assign-empty">Nothing has been closed yet.</p>
          ) : (
            <ul className="attention-list notification-list">
              {data.resolved.map((notice) => (
                <li key={notice.notice_id} className="attention-item" data-kind="robot-closed" data-tone="grey">
                  <div className="attention-item-head">
                    <span className="attention-item-who">{notice.title}</span>
                    {notice.client_name && <span className="attention-item-pill">{notice.client_name}</span>}
                    <span className="attention-item-date">{notice.resolved_utc ? ageLabel(notice.resolved_utc) : ""}</span>
                  </div>
                  <p className="attention-note notification-status">Closed{notice.resolved_by ? ` by ${notice.resolved_by}` : ""}</p>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}

export function NotificationBoardView({ onOpenClient }: { onOpenClient?: OpenClient }) {
  const done = useAttentionDone();
  const [side, setSide] = useState<BoardSide>("human");
  const [tab, setTab] = useState<BoardTab>("active");
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<NotificationSort>("newest");
  const [robotToken, setRobotToken] = useState(0);
  const [robotLoading, setRobotLoading] = useState(false);
  const [data, setData] = useState<NotificationBoardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyNid, setBusyNid] = useState("");
  const latest = useRef(0);

  const load = useCallback(async () => {
    const mine = ++latest.current;
    setLoading(true);
    setError("");
    try {
      const next = await fetchNotificationBoard();
      if (mine === latest.current) setData(next);
    } catch (err) {
      if (mine === latest.current) setError(err instanceof Error ? err.message : "Could not read the Notification board.");
    } finally {
      if (mine === latest.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function change(nid: string, state: NotificationState) {
    setBusyNid(nid);
    setError("");
    try {
      await setNotificationState(nid, state);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that.");
    } finally {
      setBusyNid("");
    }
  }

  const specialSenders = useSpecialSenders();
  const rows = boardRows(data, tab, filter, sort, specialSenders);
  const refreshing = side === "human" ? loading : robotLoading;
  const bellRows = data ? data.counts.bell : 0;

  return (
    <section className="assign-view notification-board" aria-label="Notification board" aria-busy={loading}>
      <header className="assign-bar">
        <h2 className="assign-title">Notification Board</h2>
        {side === "human" && data && (
          <span className="assign-summary">
            {bellRows} on the bell · {data.counts.board} more · {data.counts.dismissed} dismissed · {data.counts.hidden} hidden
          </span>
        )}
        <button
          type="button"
          className="cf-btn cf-btn--neutral assign-refresh notification-refresh"
          onClick={() => (side === "human" ? void load() : setRobotToken((n) => n + 1))}
          disabled={refreshing}
        >
          <IconRefresh aria-hidden="true" />
          {refreshing ? "Reading…" : "Refresh"}
        </button>
      </header>
      <div className="assign-controls">
        <div className="assign-modes" role="group" aria-label="Whose notifications">
          {SIDES.map((s) => (
            <button key={s.key} type="button" className="cf-btn cf-btn--chip assign-mode" aria-pressed={side === s.key} onClick={() => setSide(s.key)}>
              {s.label}
            </button>
          ))}
        </div>
        {side === "human" && (
          <>
            <div className="assign-modes" role="group" aria-label="List">
              {BOARD_TABS.map((t) => (
                <button key={t.key} type="button" className="cf-btn cf-btn--chip assign-mode" aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
                  {t.label}
                  {data && <span className="assign-mode-count">{tabCount(data, t.key)}</span>}
                </button>
              ))}
            </div>
            <ClearableSearch
              wrapClassName="assign-filter-wrap"
              className="assign-filter"
              placeholder="Filter by client name or number"
              aria-label="Filter by client name or number"
              clearLabel="Clear the filter"
              value={filter}
              onValueChange={setFilter}
            />
            <label className="attention-field">
              <span>Sort by</span>
              <select value={sort} onChange={(event) => setSort(event.target.value as NotificationSort)} aria-label="Sort notifications by">
                {NOTIFICATION_SORTS.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>
      {side === "robot" ? (
        <RobotSide onOpenClient={onOpenClient} reloadToken={robotToken} onLoading={setRobotLoading} />
      ) : (
        <>
          <p className="assign-hint">
            {TAB_HINT[tab]} The bell holds the last {BELL_DAYS} days. Dismiss and Hide affect only you, and nothing is deleted.
          </p>
          {error && (
            <p className="assign-notice assign-notice--error" role="alert">
              {error}
              {data ? " The list below is from the last successful read." : ""}
            </p>
          )}
          {!data && loading && (
            <p className="assign-empty" role="status">
              Reading the Notification board…
            </p>
          )}
          {data && rows.length === 0 && (
            <p className="assign-empty" role="status">
              {filter.trim() ? "No notification here matches." : EMPTY_WORDS[tab]}
            </p>
          )}
          {data && rows.length > 0 && (
            <ul className="attention-list notification-list">
              {rows.map((n) => (
                <NotificationRow
                  key={n.nid}
                  n={n}
                  done={done}
                  onOpenClient={onOpenClient}
                  onState={(nid, state) => void change(nid, state)}
                  busyNid={busyNid}
                  showStatus
                />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
