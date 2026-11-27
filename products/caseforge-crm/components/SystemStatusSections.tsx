"use client";

import {
  attentionItems,
  dollarsLabel,
  bytesLabel,
  clockLabel,
  cpuTone,
  loadNote,
  levelTone,
  percentLabel,
  providerStateLabel,
  zramLabel,
  type SystemBox,
  type SystemProvider,
  type SystemStatusResponse,
  type Tone,
} from "@/lib/systemStatus";
import { liveDownFromStatus } from "@/lib/outageMap";
import { OutageMap } from "./OutageMap";
import { plainAction, schedulesSummary } from "@/lib/healthTiers";
import type { OpsHealthAlert } from "@/lib/opsHealth";
import { BackupsSection, ExpiriesSection, Fold, SpendCard, WorkersSection } from "./SystemStatusMore";

function Meter({ label, percent, tone, detail }: { label: string; percent: number | null | undefined; tone: Tone; detail: string }) {
  const width = percent === null || percent === undefined ? 0 : Math.max(0, Math.min(100, percent));
  return (
    <div className="system-meter">
      <div className="system-meter-row">
        <span className="system-meter-label">{label}</span>
        <span className="system-meter-detail">{detail}</span>
      </div>
      <div
        className={`system-meter-bar system-meter-bar--${tone}`}
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(width)}
      >
        <span style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function BoxCard({ box }: { box: SystemBox }) {
  if (!box.available) {
    return (
      <article className="system-box">
        <h3 className="system-box-title">{box.label}</h3>
        <p className="system-health-muted">{box.host}: no numbers reported yet.</p>
      </article>
    );
  }
  const cpu = box.cpu;
  const busy = cpu.busy_percent ?? null;
  const load = typeof cpu.load_1 === "number" ? cpu.load_1.toFixed(2) : "n/a";
  const reported = clockLabel(box.generated_at);
  return (
    <article className={`system-box${box.stale ? " system-box--stale" : ""}`}>
      <div className="system-box-head">
        <h3 className="system-box-title">{box.label}</h3>
        <span className="system-box-host">{box.host}</span>
      </div>
      <p className={box.stale ? "system-box-stale" : "system-health-muted"}>
        {box.stale ? "Stale: last reported" : "Last reported"} {reported || "at an unknown time"}
      </p>
      <Meter
        label="CPU"
        percent={busy}
        tone={box.stale ? "grey" : cpuTone(busy)}
        detail={`${percentLabel(busy)} busy, load ${load} on ${cpu.cores ?? "?"} cores (${loadNote(cpu.load_1, cpu.cores) || "load unknown"})`}
      />
      <Meter
        label="RAM"
        percent={box.ram.used_percent}
        tone={box.stale ? "grey" : levelTone(box.ram.used_percent)}
        detail={`${bytesLabel(box.ram.used_bytes)} of ${bytesLabel(box.ram.total_bytes)}, ${bytesLabel(box.ram.available_bytes)} available`}
      />
      <Meter
        label="Storage"
        percent={box.storage.used_percent}
        tone={box.stale ? "grey" : levelTone(box.storage.used_percent)}
        detail={`${percentLabel(box.storage.used_percent)} used, ${bytesLabel(box.storage.free_bytes)} free`}
      />
      <Meter
        label="Swap"
        percent={box.swap.used_percent}
        tone={box.stale ? "grey" : levelTone(box.swap.used_percent)}
        detail={(box.swap.total_bytes ?? 0) > 0 ? `${bytesLabel(box.swap.used_bytes)} of ${bytesLabel(box.swap.total_bytes)}` : "none"}
      />
      <p className="system-box-zram">
        <span className="system-meter-label">zram</span> {zramLabel(box)}
      </p>
    </article>
  );
}

function ProviderRow({ provider }: { provider: SystemProvider }) {
  const { label, tone } = providerStateLabel(provider);
  const checked = clockLabel(provider.checked_at);
  const detail = provider.title || provider.note;

  const showChecked = checked !== "" && (provider.state !== "unknown" || provider.note.startsWith("Could not check"));
  return (
    <li className={`system-provider system-provider--${tone}`}>
      <div className="system-provider-row">
        <span className="system-provider-name">{provider.name}</span>
        <span className={`system-provider-state system-provider-state--${tone}`}>{label}</span>
      </div>
      {detail && <p className="system-provider-detail">{detail}</p>}
      {showChecked && <p className="system-provider-checked">checked {checked}</p>}
    </li>
  );
}

export function NeedsYou({ status, alerts }: { status: SystemStatusResponse | null; alerts: OpsHealthAlert[] }) {
  const items = [
    ...(status ? attentionItems(status).map((i) => ({ tone: i.tone, title: i.title, why: i.why })) : []),
    ...alerts.map((a) => ({ tone: a.severity === "red" ? ("red" as const) : ("amber" as const), title: a.title, why: plainAction(a.next_action) })),
  ];
  return (
    <section aria-label="Needs you">
      <h2 className="system-health-heading">Needs you</h2>
      {items.length === 0 ? (
        <p className="system-health-muted">Nothing needs you. The details below are folded away.</p>
      ) : (
        <ul className="system-health-list">
          {items.map((item, i) => (
            <li key={`${item.title}-${i}`} className={`system-provider system-provider--${item.tone}`}>
              <div className="system-provider-row">
                <span className="system-provider-name">{item.title}</span>
                <span className={`system-provider-state system-provider-state--${item.tone}`}>{item.tone === "red" ? "Act now" : "Soon"}</span>
              </div>
              {item.why && <p className="system-provider-detail">{item.why}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function StatusBoxes({ status }: { status: SystemStatusResponse }) {
  return (
    <section aria-label="Boxes">
      <h2 className="system-health-heading">Boxes</h2>
      <div className="system-boxes">
        {status.boxes.map((box) => (
          <BoxCard key={box.box} box={box} />
        ))}
      </div>
    </section>
  );
}

function providersSummary(status: SystemStatusResponse): string {
  const list = status.providers.providers;
  const bad = list.filter((p) => p.state === "outage" || p.state === "degraded" || p.state === "maintenance").length;
  const unknown = list.filter((p) => p.state === "unknown").length;
  return `${list.length - bad - unknown} fine${bad ? `, ${bad} with a problem on their side` : ""}${unknown ? `, ${unknown} could not be checked` : ""}`;
}

export function StatusDetails({ status, extra }: { status: SystemStatusResponse; extra?: React.ReactNode }) {
  const liveDown = liveDownFromStatus(status);
  const spend = status.spend;
  const spendLine = spend.available ? `${dollarsLabel(spend.usage_daily)} today${spend.limit_remaining !== null ? `, ${dollarsLabel(spend.limit_remaining)} left on the key` : ""}` : "no figures yet";
  const failing = status.workers.boxes.some((b) => b.rows.some((r) => r.last_result === "failed" || r.overdue));
  const badBackup = status.backups.rows.some((b) => b.status !== "ok");
  const expiring = status.expiries.rows.some((r) => r.tone === "red" || r.tone === "amber");
  return (
    <>
      {extra}
      <Fold title="Outside services" summary={providersSummary(status)} open={status.providers.providers.some((p) => p.state === "outage")}>
        <p className="system-health-muted">What each provider&rsquo;s own status page says. Grey means it could not be checked.</p>
        <ul className="system-health-list">
          {status.providers.providers.map((p) => (
            <ProviderRow key={p.key} provider={p} />
          ))}
        </ul>
      </Fold>
      <Fold title="OpenRouter spend" summary={spendLine} open={spend.tone === "amber" || spend.tone === "red"}>
        <SpendCard spend={spend} />
      </Fold>
      <Fold title="Scheduled jobs" summary={schedulesSummary(status)} open={failing}>
        <WorkersSection status={status} />
      </Fold>
      <Fold title="Backups" summary={`${status.backups.rows.length} kinds, ${badBackup ? "one needs a look" : "all recent"}`} open={badBackup}>
        <BackupsSection backups={status.backups} />
      </Fold>
      <Fold title="Certificates and expiring secrets" summary={expiring ? "one is close to expiring" : "none close to expiring"} open={expiring}>
        <ExpiriesSection expiries={status.expiries} />
      </Fold>
      <Fold title="What stops when a service goes down" summary="click a service to see what the firm would lose">
        <OutageMap key={liveDown.ids.join(",")} live={liveDown} />
      </Fold>
    </>
  );
}
