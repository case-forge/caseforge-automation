
import { spendItem } from "./healthTiers";

export interface SystemSpend {
  available: boolean;
  note: string;
  generated_at: string;
  usage: number | null;
  usage_daily: number | null;
  limit: number | null;
  limit_remaining: number | null;
  remaining_fraction: number | null;
  tone: Tone;
}

export interface WorkerCheck {
  name: string;
  status: string;
  last_ping: string;

  last_kind?: string;
  period_seconds: number | null;
}

export interface WorkerRow {
  name: string;
  kind: string;
  description: string;
  schedule: string;
  last_run: string;
  last_result: string;
  next_run: string;
  period_seconds: number | null;
  overdue: boolean;
  check: WorkerCheck | null;
  no_check: boolean;
  tone: Tone;
}

export interface WorkerBox {
  box: string;
  label: string;
  available: boolean;
  generated_at: string;
  age_minutes: number | null;
  stale: boolean;
  rows: WorkerRow[];
}

export interface BackupRow {
  name: string;
  last_good: string;
  age_seconds: number | null;
  latest_size_bytes: number | null;
  sizes: number[];
  shrank: boolean;
  status: Tone;
}

export interface ExpiryRow {
  kind: string;
  name: string;
  expires_at: string;
  days_left: number | null;
  state: string;
  tone: Tone;
  note: string;
  renew_url: string;
}

export interface SystemBox {
  box: string;
  label: string;
  host: string;
  available: boolean;
  generated_at: string;
  age_minutes: number | null;
  stale: boolean;
  cpu: Record<string, number | null>;
  ram: Record<string, number | null>;
  storage: Record<string, number | null>;
  swap: Record<string, number | null>;
  zram: Array<Record<string, string | number | null>>;
}

export type ProviderState = "operational" | "degraded" | "outage" | "maintenance" | "unknown";

export interface SystemProvider {
  key: string;
  name: string;
  state: ProviderState | string;
  title: string;
  note: string;
  checked_at: string;
  flagged: boolean;
}

export interface SystemServiceState {
  key: string;
  state: "up" | "down" | "unknown" | string;
  reason: string;
  since: string;
}

export interface SystemServices {
  available: boolean;
  generated_at: string;
  age_minutes: number | null;
  stale: boolean;
  services: SystemServiceState[];
}

export interface SystemStatusResponse {
  boxes: SystemBox[];
  spend: SystemSpend;
  workers: {
    boxes: WorkerBox[];
    healthchecks: { available: boolean; note: string; checks: WorkerCheck[]; orphan_checks: WorkerCheck[] };
  };
  backups: { available: boolean; note: string; rows: BackupRow[] };
  expiries: { available: boolean; note: string; rows: ExpiryRow[] };
  functions: Array<{ key: string; name: string; last_event: string; state: string }>;
  providers: {
    available: boolean;
    generated_at: string;
    age_minutes: number | null;
    stale: boolean;
    providers: SystemProvider[];
  };

  services?: SystemServices;
}

export async function loadSystemStatus(fetcher: typeof fetch = fetch): Promise<SystemStatusResponse | null> {
  try {
    const res = await fetcher("/api/system-status", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as SystemStatusResponse;
  } catch {
    return null;
  }
}

export type Tone = "ok" | "amber" | "red" | "grey";

export function levelTone(percent: number | null | undefined): Tone {
  if (percent === null || percent === undefined || !Number.isFinite(percent)) return "grey";
  if (percent >= 90) return "red";
  if (percent >= 80) return "amber";
  return "ok";
}

export function cpuTone(percent: number | null | undefined): Tone {
  if (percent === null || percent === undefined || !Number.isFinite(percent)) return "grey";
  if (percent >= 95) return "red";
  if (percent >= 85) return "amber";
  return "ok";
}

export function bytesLabel(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "n/a";
  const gb = bytes / 1024 ** 3;
  if (gb >= 1) return `${gb >= 100 ? Math.round(gb) : gb.toFixed(1)} GB`;
  return `${Math.round(bytes / 1024 ** 2)} MB`;
}

export function percentLabel(percent: number | null | undefined): string {
  return percent === null || percent === undefined || !Number.isFinite(percent) ? "n/a" : `${Math.round(percent)}%`;
}

export function zramLabel(box: SystemBox): string {
  const devices = box.zram ?? [];
  if (devices.length === 0) return "none";
  const num = (d: Record<string, string | number | null>, k: string) => (typeof d[k] === "number" ? (d[k] as number) : 0);
  const size = devices.reduce((n, d) => n + num(d, "size_bytes"), 0);
  const data = devices.reduce((n, d) => n + num(d, "data_bytes"), 0);
  const compressed = devices.reduce((n, d) => n + num(d, "compressed_bytes"), 0);
  const ratio = compressed > 0 ? `${(data / compressed).toFixed(1)}:1` : "n/a";
  return `${bytesLabel(size)} device, ${bytesLabel(compressed)} compressed from ${bytesLabel(data)} (${ratio})`;
}

export function clockLabel(iso: string): string {
  const when = new Date(iso);
  if (!iso || Number.isNaN(when.getTime())) return "";
  return when.toLocaleTimeString("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit" });
}

export function providerStateLabel(p: SystemProvider): { label: string; tone: Tone } {
  switch (p.state) {
    case "operational":
      return { label: "Operational", tone: "ok" };
    case "degraded":
      return { label: "Degraded", tone: "amber" };
    case "outage":
      return { label: "Outage", tone: "red" };
    case "maintenance":
      return { label: "Maintenance", tone: "amber" };
    default:
      return { label: "Could not check", tone: "grey" };
  }
}

export function dollarsLabel(value: number | null | undefined): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "n/a" : `$${value.toFixed(2)}`;
}

export function spanLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return "n/a";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} days`;
}

export function dateTimeLabel(iso: string): string {
  const when = new Date(iso);
  if (!iso || Number.isNaN(when.getTime())) return "";
  return when.toLocaleString("en-GB", { timeZone: "Europe/London", weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function trendLabel(sizes: number[]): string {
  const max = Math.max(...sizes, 0);
  if (max <= 0) return "";
  const bars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588";
  return sizes.map((n) => bars[Math.min(7, Math.floor((n / max) * 7.999))]).join("");
}

export function expiryLabel(row: ExpiryRow): string {
  if (row.state === "needs_permission") return row.note;
  if (row.state === "no_expiry") return "no expiry set";
  if (row.days_left === null) return row.note || "could not check";
  if (row.days_left < 0) return `expired ${-row.days_left} days ago`;
  return `${row.days_left} days left`;
}

export function workerResultLabel(row: WorkerRow): string {
  if (row.last_result === "failed") return "failed";
  if (row.last_result === "success") return "success";
  if (row.last_run) return "ran";
  return row.kind === "cron" ? "reports nothing back" : "not run yet";
}

export function checkReason(check: WorkerCheck, now: Date = new Date()): string {
  const every = spanLabel(check.period_seconds);
  const silent = Number.isNaN(new Date(check.last_ping).getTime()) || !check.last_ping ? "" : spanLabel((now.getTime() - new Date(check.last_ping).getTime()) / 1000);
  if (check.status === "down") {
    if (check.last_kind === "fail") return `The job reported a failure${silent ? ` ${silent} ago` : ""}. Look at its own log.`;
    if (!check.last_ping) return `It has never checked in. It should every ${every}.`;
    return `No check-in for ${silent}; it should every ${every}. The job did not run, or could not reach Healthchecks.`;
  }
  if (check.status === "grace") return `Late (due every ${every}) but still inside its grace time.`;
  if (check.status === "paused") return "Paused on purpose in Healthchecks, so it is not watching anything.";
  if (check.status === "new") return "Created but never pinged yet.";
  return "";
}

export interface AttentionItem {
  tone: "red" | "amber";
  title: string;
  why: string;
}

export function attentionItems(status: SystemStatusResponse, now: Date = new Date()): AttentionItem[] {
  const out: AttentionItem[] = [];
  for (const p of status.providers.providers) {

    if (p.state === "outage") out.push({ tone: "red", title: `${p.name} says it is down`, why: p.title || "Its own status page declares an outage." });
  }
  const cap = spendItem(status.spend);
  if (cap) out.push({ tone: status.spend.tone === "red" ? "red" : "amber", title: cap.title, why: cap.why });
  for (const b of status.boxes) {
    if (b.available && b.stale) out.push({ tone: "amber", title: `${b.label} has not reported for a while`, why: `Last report ${clockLabel(b.generated_at) || "unknown"}. The box may be fine and only its reporter stuck; the box's own alert pages you if it is unreachable.` });
    for (const [label, m] of [["RAM", b.ram], ["Storage", b.storage], ["Swap", b.swap]] as const) {
      const tone = levelTone(m.used_percent);
      if (b.available && !b.stale && (tone === "amber" || tone === "red")) out.push({ tone, title: `${b.label}: ${label} ${percentLabel(m.used_percent)} used`, why: "From 80% is worth watching, from 90% it needs freeing." });
    }
  }
  const seen = new Set<string>();
  const checkItem = (c: WorkerCheck, worker?: string) => {
    if (seen.has(c.name) || (c.status !== "down" && c.status !== "grace")) return;
    seen.add(c.name);
    out.push({ tone: c.status === "down" ? "red" : "amber", title: `${worker ?? c.name}: Healthchecks says ${c.status}`, why: checkReason(c, now) });
  };
  for (const box of status.workers.boxes) {
    for (const row of box.rows) {
      if (row.check) checkItem(row.check, row.name);
      if (row.last_result === "failed") out.push({ tone: "red", title: `${row.name} failed on ${box.label}`, why: "Its last run ended in an error." });
      else if (row.overdue) out.push({ tone: "amber", title: `${row.name} is overdue on ${box.label}`, why: `It should have run by now; its schedule is ${row.schedule}.` });
    }
  }
  status.workers.healthchecks.orphan_checks.forEach((c) => checkItem(c));
  for (const b of status.backups.rows) {
    if (b.status === "ok") continue;
    const reasons = [b.age_seconds === null ? "no good backup on record" : `last good ${spanLabel(b.age_seconds)} ago`];
    if (b.shrank) reasons.push(shrinkNote(b.sizes));
    out.push({ tone: b.status === "red" ? "red" : "amber", title: `Backup ${b.name}`, why: reasons.join("; ") });
  }
  for (const r of status.expiries.rows) {
    if (r.tone === "red" || r.tone === "amber") out.push({ tone: r.tone, title: r.name, why: `${expiryLabel(r)}. Renew it before then.` });
  }
  return out.sort((a, b) => (a.tone === b.tone ? 0 : a.tone === "red" ? -1 : 1));
}

export function shrinkNote(sizes: number[]): string {
  const [prev, last] = sizes.slice(-2);
  if (!prev || last === undefined) return "the newest backup is much smaller than the one before: it may be incomplete";
  return `the newest backup is ${bytesLabel(last)}, ${Math.round((last / prev) * 100)}% of the one before (${bytesLabel(prev)}): it may be incomplete`;
}

export function loadNote(load1: number | null | undefined, cores: number | null | undefined): string {
  if (typeof load1 !== "number" || typeof cores !== "number" || cores <= 0) return "";
  if (load1 >= cores) return "busy: more work waiting than cores to do it";
  return "not overloaded: fewer tasks waiting than cores";
}
