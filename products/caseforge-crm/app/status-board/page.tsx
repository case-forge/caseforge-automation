"use client";

import { BackToHome } from "@/components/BackToHome";
import { useEffect, useMemo, useState } from "react";
import { daysWaiting, formatBoardDay } from "@/lib/boardCompact";
import { WaitingTag } from "@/components/StatusBoardCompact";
import { boardDate, type StatusBoardResponse } from "@/lib/matterMilestones";
import { BoardDateLink } from "@/components/BoardDateLink";
import { boardLinkFor } from "@/lib/boardLinks";
import { ClearableSearch } from "@/components/ClearableSearch";
import { NudgeCell } from "@/components/NudgeCell";
import { clientHref } from "@/lib/clientLink";
import { nudgeDocFor } from "@/lib/nudge";
import { PortalCell } from "@/components/PortalCell";
import { showsPortal } from "@/lib/portalCell";
import {
  BOARD_COLUMNS,
  nextSort,
  sortItems,
  type Sort,
  type SortBy,
} from "@/lib/statusBoardColumns";
import {
  MONTHS,
  ORDER_FILTERS,
  ORDER_FILTER_LABELS,
  STORAGE_KEY,
  applyFilter,
  carriedForward,
  describe,
  pageDefaultFilter,
  parseStored,
  serialise,
  toggleCode,
  undatedCount,
  yearsIn,
  type BoardFilter,
} from "@/lib/statusBoardFilter";

function Cell({ iso, href, columnKey }: { iso: string; href: string; columnKey: string }) {
  const short = iso ? formatBoardDay(iso) : "";
  const full = iso ? boardDate(iso) : "";
  return short ? (
    <td className="status-board-done" title={full} aria-label={full}>
      <BoardDateLink href={href} columnKey={columnKey}>
        {short}
      </BoardDateLink>
    </td>
  ) : (
    <td className="status-board-empty" aria-label="Not yet">
      –
    </td>
  );
}

const ariaSort = (sort: Sort, by: SortBy) => (sort?.by === by ? (sort.dir === "asc" ? "ascending" : "descending") : "none");
const arrow = (sort: Sort, by: SortBy) => (sort?.by === by ? (sort.dir === "asc" ? " ▲" : " ▼") : "");

export default function StatusBoardPage() {
  const [board, setBoard] = useState<StatusBoardResponse | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [view, setView] = useState<BoardFilter | null>(null);
  const [sort, setSort] = useState<Sort>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/status-board", { cache: "no-store" })
      .then(async (res) => ({ ok: res.ok, body: await res.json().catch(() => ({})) }))
      .then(({ ok, body }) => {
        if (cancelled) return;
        if (!ok) setError(String(body.error ?? body.detail ?? "The status board could not be loaded."));
        else {
          const data = body as StatusBoardResponse;
          let stored: string | null = null;
          try {
            stored = window.localStorage.getItem(STORAGE_KEY);
          } catch {
            stored = null;
          }
          setView(parseStored(stored, data.items) ?? pageDefaultFilter(data.items));
          setBoard(data);
        }
      })
      .catch(() => !cancelled && setError("The status board could not be loaded."));
    return () => {
      cancelled = true;
    };
  }, []);

  const years = useMemo(() => yearsIn(board?.items ?? []), [board]);
  const inView = useMemo(() => (board && view ? applyFilter(board.items, view) : []), [board, view]);

  function change(next: BoardFilter) {
    setView(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, serialise(next));
    } catch {

    }
  }

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return sortItems(inView.filter((r) => !needle || r.client_name.toLowerCase().includes(needle) || r.matter_id.includes(needle)), sort);
  }, [inView, filter, sort]);
  const columns = BOARD_COLUMNS;
  const undated = undatedCount(inView);
  const carried = view ? inView.filter((r) => carriedForward(r, view)).length : 0;

  return (
    <main className="status-board">
      <p>
        <BackToHome />
      </p>
      <h1>Status Board</h1>
      <p className="status-board-note">
        Every open matter and the date it reached each stage. A dash means nothing is recorded yet. Results could be delayed by up to one hour. Click a heading to sort by it
        (the full time decides the order): once for up, again for down, a third time for the usual order.
      </p>
      <div className="status-board-controls">
        <label className="status-board-filter">
          <span className="status-board-label">Find a client</span>
          <ClearableSearch value={filter} onValueChange={setFilter} clearLabel="Clear the filter" placeholder="Name or no." />
        </label>
        {board && view && (
          <>
            <div className="status-board-toggles" role="group" aria-labelledby="sb-order-types">
              <span id="sb-order-types" className="status-board-label">
                Order types
              </span>
              {ORDER_FILTERS.map((c) => (
                <label key={c} className="status-board-toggle" data-on={view.codes.includes(c) ? "true" : undefined}>
                  <input type="checkbox" checked={view.codes.includes(c)} onChange={() => change(toggleCode(view, c))} />
                  <span>{ORDER_FILTER_LABELS[c]}</span>
                </label>
              ))}
            </div>
            <label className="status-board-filter status-board-year">
              <span className="status-board-label">Year</span>
              <select value={view.year ?? ""} onChange={(e) => change({ ...view, year: e.target.value })}>
                <option value="">All years</option>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
            <label className="status-board-filter status-board-month">
              <span className="status-board-label">Month</span>
              <select value={view.month ?? ""} onChange={(e) => change({ ...view, month: e.target.value })}>
                <option value="">All months</option>
                {MONTHS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>
      {board && view && (
        <div className="status-board-count-row">
          <p className="status-board-count" role="status">
            {describe(inView.length, board.items.length, view, false, undated, carried)}
          </p>
        </div>
      )}
      {error && <p className="status-board-error" role="alert">{error}</p>}
      {!board && !error && <p role="status">Loading…</p>}
      {board && (
        <div className="status-board-scroll">
          <table className="status-board-table">
            <colgroup>
              <col className="status-board-col-client" />
              <col className="status-board-col-no" />
              {columns.map((c) => (
                <col key={c.id} className="status-board-col-date" />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th scope="col" aria-sort={ariaSort(sort, "client")}>
                  <button type="button" className="status-board-sort" onClick={() => setSort(nextSort(sort, "client"))}>
                    Client{arrow(sort, "client")}
                  </button>
                </th>
                <th scope="col" aria-sort={ariaSort(sort, "no")}>
                  <button type="button" className="status-board-sort" onClick={() => setSort(nextSort(sort, "no"))}>
                    No.{arrow(sort, "no")}
                  </button>
                </th>
                {columns.map((c) => (
                  <th key={c.id} scope="col" title={c.title} aria-sort={ariaSort(sort, c.id)}>
                    <button type="button" className="status-board-sort" onClick={() => setSort(nextSort(sort, c.id))}>
                      {c.label}
                      {arrow(sort, c.id)}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.matter_id}>
                  <th scope="row" title={r.client_name}>
                    <a className="sb-client-link" href={clientHref(r.client_name, { matterId: r.matter_id })} target="_blank" rel="noopener noreferrer">{r.client_name}</a>
                    <WaitingTag days={daysWaiting(r)} />
                  </th>
                  <td className="status-board-no">{r.matter_id}</td>
                  {columns.map((c) => {
                    const iso = c.value(r);
                    if (showsPortal(r, c.id, iso)) return <PortalCell key={c.id} className="status-board-empty" />;
                    const doc = nudgeDocFor(r, c.id, iso);
                    return doc ? <NudgeCell key={c.id} matterId={r.matter_id} clientName={r.client_name} doc={doc} className="status-board-empty" /> : <Cell key={c.id} iso={iso} href={boardLinkFor(r, c.id)} columnKey={c.id} />;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          { }
          {rows.length === 0 && (
            <p className="status-board-empty-state" role="status">
              {filter ? "No open matter matches." : "No open matter matches the filters above."}
            </p>
          )}
        </div>
      )}
    </main>
  );
}
