"use client";

import { NeedsYou, StatusBoxes, StatusDetails } from "@/components/SystemStatusSections";
import { Fold } from "@/components/SystemStatusMore";
import { REFRESH_MS, tierAlerts } from "@/lib/healthTiers";
import { loadSystemStatus, type SystemStatusResponse } from "@/lib/systemStatus";
import { useCallback, useEffect, useRef, useState } from "react";
import { checkedLabel, durationLabel, loadOpsHealth, overallLabel, type OpsHealthAlert, type OpsHealthLoad } from "@/lib/opsHealth";

function AlertList({ alerts }: { alerts: OpsHealthAlert[] }) {
  return (
    <ul className="system-health-list">
      {alerts.map((alert, i) => (
        <li key={`${alert.title}-${i}`} className={`system-health-item system-health-item--${alert.severity}`}>
          <p className="system-health-item-title">{alert.title}</p>
          {alert.next_action && <p className="system-health-item-action">What to do: {alert.next_action}</p>}
          {alert.age_minutes !== null && alert.age_minutes > 0 && (
            <p className="system-health-item-age">Age {durationLabel(alert.age_minutes)}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

function clock(date: Date | null): string {
  return date ? date.toLocaleTimeString("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
}

export function SystemHealthPanel() {
  const [load, setLoad] = useState<OpsHealthLoad | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const alive = useRef(true);

  const read = useCallback(async () => {
    const [next, nextStatus] = await Promise.all([loadOpsHealth(), loadSystemStatus()]);
    if (!alive.current) return;
    setLoad(next);
    setStatus(nextStatus);
    setUpdatedAt(new Date());
  }, []);

  const refresh = useCallback(() => {
    setBusy(true);
    void read().finally(() => {
      if (alive.current) setBusy(false);
    });
  }, [read]);

  useEffect(() => {
    alive.current = true;
    void read();

    const tick = window.setInterval(() => {
      if (document.visibilityState === "visible") void read();
    }, REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void read();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive.current = false;
      window.clearInterval(tick);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [read]);

  if (load === null) return <div className="system-health" />;
  if (load.state === "hidden") {
    return (
      <div className="system-health">
        <p className="system-health-muted">There is nothing to show here.</p>
      </div>
    );
  }

  const data = load.state === "ok" ? load.data : null;
  const overall = data ? overallLabel(data) : null;
  const tiers = data ? tierAlerts(data.alerts) : null;
  const casework = tiers ? tiers.details.filter((a) => a.category === "housekeeping") : [];
  const otherAlerts = tiers ? tiers.details.filter((a) => a.category !== "housekeeping") : [];

  return (
    <div className="system-health">
      <div className="system-health-head">
        <p className="system-health-updated" role="status">
          {updatedAt ? `Updated ${clock(updatedAt)}. Refreshes every minute.` : ""}
        </p>
        <button type="button" className="cf-btn cf-btn--secondary system-health-refresh" disabled={busy} onClick={refresh}>
          {busy ? "Checking" : "Refresh now"}
        </button>
      </div>
      {load.state === "error" && (
        <p className="system-health-muted" role="status">
          The health report could not be loaded just now. It will try again in a minute.
        </p>
      )}
      {data && overall && (
        <section className={`system-health-summary system-health-summary--${overall.tone}`} aria-label="Overall">
          <p className="system-health-overall">{overall.label}</p>
          <p className="system-health-line">{overall.line}</p>
          {data.available && <p className="system-health-muted">{checkedLabel(data)}</p>}
        </section>
      )}
      {data && data.available && data.stale && (
        <p className="system-health-stale" role="status">
          This report is {durationLabel(data.snapshot_age_minutes) || "of unknown age"}
          {data.snapshot_age_minutes !== null ? " old" : ""}. The health check normally runs every 15 minutes, so it may have stopped.
          What is shown below may be out of date.
        </p>
      )}
      <NeedsYou status={status} alerts={tiers ? tiers.needsYou : []} />
      {status && <StatusBoxes status={status} />}
      {status && (
        <StatusDetails
          status={status}
          extra={
            otherAlerts.length > 0 ? (
              <Fold title="Also worth a look" summary={`${otherAlerts.length} that can wait, with what to do`}>
                <AlertList alerts={otherAlerts} />
              </Fold>
            ) : null
          }
        />
      )}
      {casework.length > 0 && (
        <Fold title="Casework to check" summary={`${casework.length} lines`}>
          <ul className="system-health-info-list">
            {casework.map((alert, i) => (
              <li key={`${alert.title}-${i}`}>{alert.title}</li>
            ))}
          </ul>
        </Fold>
      )}
    </div>
  );
}
