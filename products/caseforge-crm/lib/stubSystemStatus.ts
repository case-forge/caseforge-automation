
import type { SystemStatusResponse } from "./systemStatus";

function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}
const GB = 1024 ** 3;

export function stubSystemStatus(): SystemStatusResponse {
  return {
    boxes: [
      {
        box: "dev",
        label: "Development box",
        host: "dev-host",
        available: true,
        generated_at: minutesAgo(1),
        age_minutes: 1,
        stale: false,
        cpu: { load_1: 3.2, load_5: 2.8, load_15: 2.1, cores: 8, busy_percent: 38.5 },
        ram: { total_bytes: 31 * GB, available_bytes: 6 * GB, used_bytes: 25 * GB, used_percent: 80.6 },
        storage: { total_bytes: 200 * GB, used_bytes: 120 * GB, free_bytes: 80 * GB, used_percent: 60 },
        swap: { total_bytes: 8 * GB, used_bytes: 1 * GB, used_percent: 12.5 },
        zram: [
          { name: "zram0", size_bytes: 16 * GB, data_bytes: 6 * GB, compressed_bytes: 2 * GB, memory_bytes: 2.1 * GB, ratio: 3 },
        ],
      },
      {
        box: "prod",
        label: "Production box",
        host: "prod-host",
        available: true,
        generated_at: minutesAgo(9),
        age_minutes: 9,
        stale: true,
        cpu: { load_1: 0.4, load_5: 0.5, load_15: 0.6, cores: 4, busy_percent: 9.1 },
        ram: { total_bytes: 16 * GB, available_bytes: 9 * GB, used_bytes: 7 * GB, used_percent: 43.8 },
        storage: { total_bytes: 160 * GB, used_bytes: 70 * GB, free_bytes: 90 * GB, used_percent: 43.8 },
        swap: { total_bytes: 2 * GB, used_bytes: 0, used_percent: 0 },
        zram: [],
      },
    ],
    spend: {
      available: true,
      note: "",
      generated_at: minutesAgo(3),
      usage: 41.2,
      usage_daily: 1.37,
      limit: 50,
      limit_remaining: 8.8,
      remaining_fraction: 0.176,
      tone: "amber",
    },
    workers: {
      boxes: [
        {
          box: "dev",
          label: "Development box",
          available: true,
          generated_at: minutesAgo(2),
          age_minutes: 2,
          stale: false,
          rows: [
            {
              name: "host-watch",
              kind: "timer",
              description: "Text the owner when this box shows swap, disk or update trouble",
              schedule: "OnCalendar=*-*-* *:*:00",
              last_run: minutesAgo(1),
              last_result: "success",
              next_run: minutesAgo(-1),
              period_seconds: 60,
              overdue: false,
              check: { name: "host-watch", status: "up", last_ping: minutesAgo(1), period_seconds: 120 },
              no_check: false,
              tone: "ok",
            },
          ],
        },
        {
          box: "prod",
          label: "Production box",
          available: true,
          generated_at: minutesAgo(2),
          age_minutes: 2,
          stale: false,
          rows: [
            {
              name: "nightly-field-audit",
              kind: "timer",
              description: "Nightly field audit: model reads, code checks, never overwrites",
              schedule: "OnCalendar=*-*-* 02:00:00",
              last_run: minutesAgo(60 * 80),
              last_result: "success",
              next_run: minutesAgo(-60 * 4),
              period_seconds: 86400,
              overdue: true,
              check: null,
              no_check: true,
              tone: "amber",
            },
            {
              name: "client-index-refresh",
              kind: "cron",
              description: "python3 tools/index_refresh.py",
              schedule: "*/15 * * * *",
              last_run: "",
              last_result: "",
              next_run: "",
              period_seconds: 900,
              overdue: false,
              check: { name: "client-index-refresh", status: "down", last_ping: minutesAgo(600), period_seconds: 900 },
              no_check: false,
              tone: "ok",
            },
          ],
        },
      ],
      healthchecks: {
        available: true,
        note: "",
        checks: [],
        orphan_checks: [{ name: "old-import-job", status: "paused", last_ping: "", period_seconds: 86400 }],
      },
    },
    backups: {
      available: true,
      note: "",
      rows: [
        { name: "clientdb-<date>.dump.age", last_good: minutesAgo(60 * 7), age_seconds: 60 * 60 * 7, latest_size_bytes: 210 * 1024 ** 2, sizes: [200, 203, 205, 207, 208, 209, 210].map((n) => n * 1024 ** 2), shrank: false, status: "ok" },
        { name: "qdrant-<date>-<id>.snapshot.age", last_good: minutesAgo(60 * 60), age_seconds: 60 * 60 * 60, latest_size_bytes: 60 * 1024 ** 2, sizes: [120, 121, 119, 120, 122, 121, 60].map((n) => n * 1024 ** 2), shrank: true, status: "red" },
      ],
    },
    expiries: {
      available: true,
      note: "",
      rows: [
        { kind: "served", name: "crm.example.test", expires_at: minutesAgo(-60 * 24 * 62), days_left: 62, state: "ok", tone: "ok", note: "", renew_url: "https://dash.cloudflare.com" },
        { kind: "secret", name: "graph-client-secret", expires_at: minutesAgo(-60 * 24 * 12), days_left: 12, state: "ok", tone: "amber", note: "", renew_url: "https://portal.azure.com" },
        { kind: "secret", name: "signing-key", expires_at: "", days_left: null, state: "no_expiry", tone: "grey", note: "", renew_url: "https://portal.azure.com" },
        { kind: "permission", name: "Azure app registration client secrets", expires_at: "", days_left: null, state: "needs_permission", tone: "grey", note: "needs a permission: Application.Read.All", renew_url: "" },
      ],
    },
    functions: [
      { key: "relay", name: "Mail webhook relay", last_event: minutesAgo(4), state: "ok" },
      { key: "send_gate", name: "Send gate", last_event: "", state: "no_data" },
    ],

    services: {
      available: true,
      generated_at: minutesAgo(2),
      age_minutes: 2,
      stale: false,
      services: [
        { key: "pg", state: "up", reason: "", since: minutesAgo(60 * 30) },
        { key: "crm", state: "up", reason: "", since: minutesAgo(60 * 30) },
        { key: "sign", state: "up", reason: "", since: minutesAgo(60 * 30) },
        { key: "tunnel", state: "up", reason: "", since: minutesAgo(60 * 30) },
        { key: "glitch", state: "down", reason: "The error log's health page is not running at all (no answer (URLError)).", since: minutesAgo(35) },
      ],
    },
    providers: {
      available: true,
      generated_at: minutesAgo(2),
      age_minutes: 2,
      stale: false,
      providers: [
        { key: "cloudflare", name: "Cloudflare", state: "operational", title: "", note: "", checked_at: minutesAgo(2), flagged: false },
        { key: "github", name: "GitHub", state: "operational", title: "", note: "", checked_at: minutesAgo(2), flagged: false },
        {
          key: "anthropic",
          name: "Anthropic",
          state: "degraded",
          title: "Elevated errors on the API",
          note: "",
          checked_at: minutesAgo(2),
          flagged: true,
        },
        {
          key: "openrouter",
          name: "OpenRouter",
          state: "unknown",
          title: "",
          note: "Could not check (HTTPError)",
          checked_at: minutesAgo(2),
          flagged: false,
        },
        { key: "azure", name: "Microsoft Azure", state: "operational", title: "", note: "", checked_at: minutesAgo(2), flagged: false },
        { key: "telegram", name: "Telegram", state: "unknown", title: "", note: "Telegram publishes no official status feed.", checked_at: minutesAgo(2), flagged: false },
      ],
    },
  };
}
