"use client";

import { useCallback, useEffect, useState } from "react";
import { bytesLabel, levelTone, percentLabel } from "@/lib/systemStatus";
import {
  REFRESH_MS,
  backupFraction,
  loadStorageStatus,
  pieSlices,
  sizeLabel,
  storageGroups,
  updatedLabel,
  type StorageRow,
  type StorageStatusResponse,
} from "@/lib/storageStatus";
import { StoragePie } from "./StoragePie";

function Bar({ label, fraction, tone }: { label: string; fraction: number; tone: string }) {
  const width = Math.max(0, Math.min(100, fraction * 100));
  return (
    <div className={`system-meter-bar system-meter-bar--${tone}`} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(width)}>
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

function RowItem({ row }: { row: StorageRow }) {
  return (
    <li className="storage-row">
      <span className="storage-row-name">{row.name}</span>
      <span className={`storage-row-size${row.bytes === null ? " storage-row-size--unknown" : ""}`}>{sizeLabel(row)}</span>
      {row.note && row.bytes === null && <span className="storage-row-note">{row.note}</span>}
    </li>
  );
}

export function StoragePanel() {
  const [data, setData] = useState<StorageStatusResponse | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    setBusy(true);
    void loadStorageStatus().then((next) => {
      setData(next);
      setBusy(false);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void loadStorageStatus().then((next) => {
      if (!cancelled) setData(next);
    });
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      void loadStorageStatus().then((next) => {
        if (!cancelled && next) setData(next);
      });
    }, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (data === undefined) return <div className="storage" />;
  if (data === null || !data.available) {
    return (
      <div className="storage">
        <p className="system-health-muted">{data?.note || "There is nothing to show here yet."}</p>
      </div>
    );
  }

  const slices = pieSlices(data.rows);
  const backup = data.rows.find((r) => r.key === "backup_folder");
  const fraction = backupFraction(data.rows);
  const root = data.rows.find((r) => r.key === "server_root");
  const rootPercent = root && root.bytes !== null && root.total_bytes ? (root.bytes / root.total_bytes) * 100 : null;
  const groups = storageGroups(data.rows).map((g) => (g.id === "server" ? { ...g, rows: g.rows.filter((r) => r.key !== "server_root") } : g)).filter((g) => g.rows.length > 0);

  return (
    <div className="storage">
      <div className="system-health-head">
        <p className={data.stale ? "system-health-stale" : "system-health-muted"} role="status">
          {updatedLabel(data.generated_at)}
          {data.stale ? ". This is older than expected, so the figures may be out of date." : "."}
        </p>
        <button type="button" className="cf-btn cf-btn--secondary system-health-refresh" disabled={busy} onClick={refresh}>
          {busy ? "Checking" : "Refresh"}
        </button>
      </div>

      <section aria-label="Cloud storage">
        <h2 className="system-health-heading">Cloud storage</h2>
        <StoragePie slices={slices} />
        <p className="system-health-muted">
          The recycle bin is where deleted files wait, for up to 93 days, before they are gone for good. They still count towards the space used.
        </p>
      </section>

      {backup && (
        <section aria-label="Backups against the target">
          <h2 className="system-health-heading">Backup folder</h2>
          <article className="system-box">
            <div className="system-meter-row">
              <span className="system-meter-label">In the folder now</span>
              <span className="system-meter-detail">
                {sizeLabel(backup)} of a {bytesLabel(data.target_backup_bytes)} target{backup.note ? `, ${backup.note}` : ""}
              </span>
            </div>
            {fraction !== null && <Bar label="Backup folder against its target" fraction={fraction} tone={fraction > 1 ? "red" : fraction > 0.85 ? "amber" : "ok"} />}
          </article>
        </section>
      )}

      {root && (
        <section aria-label="Production box disk">
          <h2 className="system-health-heading">Production box</h2>
          <article className="system-box">
            <div className="system-meter-row">
              <span className="system-meter-label">Whole disk</span>
              <span className="system-meter-detail">
                {sizeLabel(root)} used{root.total_bytes ? ` of ${bytesLabel(root.total_bytes)} (${percentLabel(rootPercent)})` : ""}
              </span>
            </div>
            {rootPercent !== null && <Bar label="Production box disk" fraction={rootPercent / 100} tone={levelTone(rootPercent)} />}
          </article>
        </section>
      )}

      {groups.map((g) => (
        <section key={g.id} aria-label={g.title}>
          <h2 className="system-health-heading">{g.title}</h2>
          {g.blurb && <p className="system-health-muted">{g.blurb}</p>}
          <ul className="storage-list">
            {g.rows.map((row) => (
              <RowItem key={row.key} row={row} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
