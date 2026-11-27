"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clientGuessLabel, dateSourceLabel, fetchScans, pagesLabel, readAtLabel, sameContentsNote, scanDateLabel, scansSummary } from "@/lib/scans";
import type { ScanRow, ScansTable } from "@/lib/scans";
import { fetchCandidates } from "@/lib/scanResolver";
import type { ScanCandidates } from "@/lib/scanResolver";
import { IconRefresh } from "./icons";
import { ScanConfirm } from "./ScanConfirm";

type Estimate = { state: "waiting" } | { state: "done"; scan: ScanCandidates } | { state: "failed"; message: string };

function Row({ row, estimate }: { row: ScanRow; estimate: Estimate | undefined }) {
  const duplicate = sameContentsNote(row.same_contents_as);
  return (
    <tr data-date-source={row.date_source}>
      <td className="scans-date">
        <span className="scans-date-day">{scanDateLabel(row.scan_date)}</span>
        <span className="scans-note" data-marked={row.date_source === "filename" ? undefined : "true"}>
          {dateSourceLabel(row.date_source)}
        </span>
      </td>
      <td className="scans-name">
        {row.web_url ? (
          <a href={row.web_url} target="_blank" rel="noopener noreferrer">
            {row.name}
          </a>
        ) : (
          <span>{row.name}</span>
        )}
        {duplicate && <span className="scans-flag">{duplicate}</span>}
      </td>
      <td className="scans-pages">{pagesLabel(row.pages)}</td>
      <td className="scans-client">
        {!estimate || estimate.state === "waiting" ? (
          <span className="scans-note" role="status">Estimating the client...</span>
        ) : estimate.state === "failed" ? (
          <>
            <span>{clientGuessLabel(row.possible_client)}</span>
            <span className="scans-note">{estimate.message}</span>
          </>
        ) : (
          <ScanConfirm scan={estimate.scan} />
        )}
      </td>
      <td className="scans-where">{row.folder}</td>
    </tr>
  );
}

export function ScansView() {
  const [table, setTable] = useState<ScansTable | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [estimates, setEstimates] = useState<Record<string, Estimate>>({});

  const latest = useRef(0);

  const load = useCallback(async () => {
    const mine = ++latest.current;
    setLoading(true);
    try {
      const next = await fetchScans();
      if (mine !== latest.current) return;
      setTable(next);
      setError("");
    } catch (err) {
      if (mine !== latest.current) return;
      setError(err instanceof Error ? err.message : "Could not load the scans. Press Refresh to try again.");
    } finally {
      if (mine === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      latest.current += 1;
    };
  }, [load]);

  useEffect(() => {
    if (!table || !table.readable) return;
    let cancelled = false;
    const queue = table.rows.filter((r) => r.id);
    setEstimates(Object.fromEntries(queue.map((r) => [r.id, { state: "waiting" } as Estimate])));
    async function worker() {
      for (let row = queue.shift(); row && !cancelled; row = queue.shift()) {
        const id = row.id;
        try {
          const scan = await fetchCandidates(id);
          if (!cancelled) setEstimates((e) => ({ ...e, [id]: { state: "done", scan } }));
        } catch (err) {
          const message = err instanceof Error ? err.message : "Could not estimate the client.";
          if (!cancelled) setEstimates((e) => ({ ...e, [id]: { state: "failed", message } }));
        }
      }
    }
    void Promise.all([worker(), worker()]);
    return () => {
      cancelled = true;
    };
  }, [table]);

  const readAt = table ? readAtLabel(table.read_utc) : "";
  const unreadable = !!table && !table.readable;
  const empty = !!table && table.readable && table.rows.length === 0;
  const rows = table && table.readable ? table.rows : [];

  return (
    <section className="scans-view" aria-label="Scans" aria-busy={loading}>
      <header className="scans-bar">
        <h2 className="scans-title">Scans</h2>
        {table && <span className="scans-summary">{scansSummary(table)}</span>}
        {readAt && <span className="scans-read-at">Read at {readAt}</span>}
        <button type="button" className="cf-btn cf-btn--neutral scans-refresh" onClick={() => void load()} disabled={loading}>
          <IconRefresh aria-hidden="true" />
          {loading ? "Reading…" : "Refresh"}
        </button>
      </header>
      <p className="scans-hint">
        What is waiting in Scanned Docs, with an estimate of whose each scan is, worked out from the file name and the document&apos;s text. Check it, set the number
        of copies and press Confirm: only then is the scan moved into that client&apos;s folder, and it is not billed. The folder is read when you open this page and
        when you press Refresh.
      </p>

      {error && (
        <p className="scans-notice scans-notice--error" role="alert">
          {error}
          {table && table.readable && readAt ? ` The list below is as it was at ${readAt}.` : ""}
        </p>
      )}
      {unreadable && !error && (
        <p className="scans-notice scans-notice--error" role="alert">
          Could not read the Scanned Docs folder ({table.folder}). This does not mean it is empty: scans may be waiting. Press Refresh to try again, or look in the
          folder itself.
        </p>
      )}

      {!table && loading && (
        <p className="scans-empty" role="status">
          Reading the Scanned Docs folder…
        </p>
      )}
      {empty && (
        <p className="scans-empty" role="status">
          No scans are waiting in {table.folder}.
        </p>
      )}

      {rows.length > 0 && (
        <div className="scans-scroll">
          <table className="scans-table">
            <thead>
              <tr>
                <th scope="col">Scan date</th>
                <th scope="col">File name</th>
                <th scope="col">Pages</th>
                <th scope="col">Likely client (an estimate)</th>
                <th scope="col">Where it is</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <Row key={`${row.id || row.name}:${index}`} row={row} estimate={estimates[row.id]} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
