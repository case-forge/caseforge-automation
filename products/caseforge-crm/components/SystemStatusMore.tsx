"use client";

import type { ReactNode } from "react";
import { groupExpiries } from "@/lib/healthTiers";
import {
  checkReason,
  dateTimeLabel,
  shrinkNote,
  dollarsLabel,
  bytesLabel,
  expiryLabel,
  spanLabel,
  trendLabel,
  workerResultLabel,
  type SystemStatusResponse,
  type Tone,
} from "@/lib/systemStatus";

export function Fold({ title, summary, open = false, children }: { title: string; summary: string; open?: boolean; children: ReactNode }) {
  return (
    <details className="system-health-fold" open={open}>
      <summary className="system-health-fold-summary">
        <span className="system-health-fold-title">{title}</span>
        <span className="system-health-fold-line">{summary}</span>
      </summary>
      {children}
    </details>
  );
}

function Bar({ label, fraction, tone }: { label: string; fraction: number | null; tone: Tone }) {
  const width = fraction === null ? 0 : Math.max(0, Math.min(100, fraction * 100));
  return (
    <div className={`system-meter-bar system-meter-bar--${tone}`} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(width)}>
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

export function SpendCard({ spend }: { spend: SystemStatusResponse["spend"] }) {
  if (!spend.available) {
    return (
      <section aria-label="OpenRouter spend">
        <h2 className="system-health-heading">OpenRouter spend</h2>
        <p className="system-health-muted">{spend.note || "No spend figures yet."}</p>
      </section>
    );
  }
  const used = spend.limit !== null && spend.limit_remaining !== null ? 1 - spend.limit_remaining / spend.limit : null;
  return (
    <section aria-label="OpenRouter spend">
      <h2 className="system-health-heading">OpenRouter spend</h2>
      <article className="system-box">
        <div className="system-meter-row">
          <span className="system-meter-label">Spent today</span>
          <span className="system-meter-detail">{dollarsLabel(spend.usage_daily)}</span>
        </div>
        <div className="system-meter-row">
          <span className="system-meter-label">Spent in total</span>
          <span className="system-meter-detail">{dollarsLabel(spend.usage)}</span>
        </div>
        {spend.limit !== null ? (
          <>
            <div className="system-meter-row">
              <span className="system-meter-label">Limit</span>
              <span className="system-meter-detail">
                {dollarsLabel(spend.limit)}, {dollarsLabel(spend.limit_remaining)} remaining
              </span>
            </div>
            <Bar label="Limit used" fraction={used} tone={spend.tone} />
          </>
        ) : (
          <p className="system-health-muted">No limit set on the key.</p>
        )}
      </article>
    </section>
  );
}

export function WorkersSection({ status }: { status: SystemStatusResponse }) {
  const { workers, functions } = status;
  const hc = workers.healthchecks;
  return (
    <section aria-label="Workers and schedules">
      <h2 className="system-health-heading">Workers and schedules</h2>
      <p className="system-health-muted">
        The scheduled jobs that keep the system tidy. Overdue means a job should have run by now. A Healthchecks check is an outside watcher that raises
        the alarm when a job stops checking in, and the reason is given under each one.
      </p>
      {workers.boxes.filter((box) => box.available || box.rows.length > 0).map((box) => (
        <details key={box.box} className="system-health-folded" open={box.rows.some((r) => r.tone !== "ok")}>
          <summary>
            {box.label} ({box.rows.length}){box.stale && box.available ? ", stale" : ""}
          </summary>
          {!box.available && <p className="system-health-muted">No schedules reported yet.</p>}
          <ul className="system-health-list">
            {box.rows.map((row) => (
              <li key={`${row.kind}-${row.name}`} className={`system-provider system-provider--${row.tone}`}>
                <div className="system-provider-row">
                  <span className="system-provider-name">{row.name}</span>
                  <span className={`system-provider-state system-provider-state--${row.tone}`}>
                    {row.overdue ? "Overdue" : workerResultLabel(row)}
                  </span>
                </div>
                {row.description && <p className="system-provider-detail">{row.description}</p>}
                <p className="system-provider-checked">
                  {row.schedule} · last {dateTimeLabel(row.last_run) || "n/a"} · next {dateTimeLabel(row.next_run) || "n/a"}
                </p>
                {row.check && (
                  <p className="system-provider-checked">
                    Healthchecks: {row.check.status}, last ping {dateTimeLabel(row.check.last_ping) || "none"}, every {spanLabel(row.check.period_seconds)}
                  </p>
                )}
                {row.check && checkReason(row.check) && <p className="system-provider-detail">{checkReason(row.check)}</p>}
                {row.no_check && <p className="system-provider-checked">No Healthchecks check</p>}
              </li>
            ))}
          </ul>
        </details>
      ))}
      {hc.available && hc.orphan_checks.length > 0 && (
        <details className="system-health-folded">
          <summary>Checks with no worker ({hc.orphan_checks.length})</summary>
          <ul className="system-health-list">
            {hc.orphan_checks.map((c) => (
              <li key={c.name} className="system-provider">
                <div className="system-provider-row">
                  <span className="system-provider-name">{c.name}</span>
                  <span className="system-provider-state">{c.status}</span>
                </div>
                <p className="system-provider-checked">last ping {dateTimeLabel(c.last_ping) || "none"}, every {spanLabel(c.period_seconds)}</p>
                {checkReason(c) && <p className="system-provider-detail">{checkReason(c)}</p>}
              </li>
            ))}
          </ul>
        </details>
      )}
      <h3 className="system-box-title">Azure Functions</h3>
      <ul className="system-health-list">
        {functions.map((f) => (
          <li key={f.key} className="system-provider">
            <div className="system-provider-row">
              <span className="system-provider-name">{f.name}</span>
              <span className="system-provider-state">{f.state === "ok" ? `last event ${dateTimeLabel(f.last_event)}` : "no data"}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function BackupsSection({ backups }: { backups: SystemStatusResponse["backups"] }) {
  return (
    <section aria-label="Backups">
      <h2 className="system-health-heading">Backups</h2>
      <p className="system-health-muted">
        The age is how long ago the last good backup finished. The bars are the last seven sizes against the biggest; a sudden drop usually means
        something was left out.
      </p>
      {!backups.available && <p className="system-health-muted">{backups.note}</p>}
      <ul className="system-health-list">
        {backups.rows.map((b) => (
          <li key={b.name} className={`system-provider system-provider--${b.status}`}>
            <div className="system-provider-row">
              <span className="system-provider-name">{b.name}</span>
              <span className={`system-provider-state system-provider-state--${b.status}`}>{b.age_seconds === null ? "no date" : `${spanLabel(b.age_seconds)} ago`}</span>
            </div>
            <p className="system-provider-checked">
              last good {dateTimeLabel(b.last_good) || "n/a"} · {bytesLabel(b.latest_size_bytes)} · <span aria-label="Last sizes">{trendLabel(b.sizes)}</span>
            </p>
            {b.shrank && <p className="system-provider-detail">{shrinkNote(b.sizes)}.</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ExpiriesSection({ expiries }: { expiries: SystemStatusResponse["expiries"] }) {
  const { dated, noExpiry } = groupExpiries(expiries.rows);
  return (
    <section aria-label="Certificates and expiring secrets">
      <h2 className="system-health-heading">Certificates and expiring secrets</h2>
      <p className="system-health-muted">Things that stop working on a date if nobody renews them. Amber from 30 days, red from 7.</p>
      {!expiries.available && <p className="system-health-muted">{expiries.note}</p>}
      {noExpiry > 0 && <p className="system-health-muted">{noExpiry} stored secrets have no expiry date, so there is nothing to renew by a date.</p>}
      <ul className="system-health-list">
        {dated.map((r) => (
          <li key={`${r.kind}-${r.name}`} className={`system-provider system-provider--${r.tone}`}>
            <div className="system-provider-row">
              <span className="system-provider-name">{r.name}</span>
              <span className={`system-provider-state system-provider-state--${r.tone}`}>{expiryLabel(r)}</span>
            </div>
            {r.expires_at && <p className="system-provider-checked">expires {dateTimeLabel(r.expires_at) || r.expires_at}</p>}
            {r.renew_url && (
              <p className="system-provider-checked">
                <a href={r.renew_url} target="_blank" rel="noopener noreferrer">Renew</a>
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
