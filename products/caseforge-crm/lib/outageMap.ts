
import { dateTimeLabel, type SystemStatusResponse } from "@/lib/systemStatus";

export type Ring = 0 | 1 | 2;

export type Bot = "dev" | "ops" | "none";

export interface OutageService {
  id: string;
  name: string;
  sub?: string;
  ring: Ring;

  needs: string[];

  logo?: string;
  line?: string;
  bot: Bot;
}

export interface Capability {
  name: string;

  paths: string[][];
  alt?: string;

  down?: string;
}

export const LINE_ICONS: Record<string, string> = {
  crm: "M3 5h18v14H3z M7 10h5 M7 14h8 M16 10h1",
  sign: "M4 20l1-4L16 5l3 3L8 19z M14 7l3 3 M4 20h16",
  bug: "M9 10h6v6a3 3 0 0 1-6 0z M10 10a2 2 0 0 1 4 0 M5 12h4 M15 12h4 M6 18l3-1 M18 18l-3-1",
  server: "M4 4h16v6H4z M4 14h16v6H4z M8 7h.01 M8 17h.01",
  route: "M4 7h11 M12 4l3 3-3 3 M20 17H9 M12 14l-3 3 3 3",
};

export const SERVICES: OutageService[] = [
  { id: "prod", name: "Production", sub: "the firm's server", ring: 0, needs: [], line: "server", bot: "dev" },
  { id: "pg", name: "Client database", sub: "PostgreSQL", ring: 1, needs: ["prod"], logo: "postgresql", bot: "ops" },
  { id: "crm", name: "CRM", ring: 1, needs: ["prod"], line: "crm", bot: "ops" },
  { id: "sign", name: "Signing", sub: "Documenso", ring: 1, needs: ["prod"], line: "sign", bot: "ops" },
  { id: "tunnel", name: "Tunnel", sub: "to Cloudflare", ring: 1, needs: ["prod"], logo: "cloudflare", bot: "ops" },
  { id: "glitch", name: "Error log", sub: "GlitchTip", ring: 1, needs: ["prod"], line: "bug", bot: "ops" },
  { id: "cf", name: "Cloudflare", sub: "addresses, sign-in", ring: 2, needs: [], logo: "cloudflare", bot: "ops" },
  { id: "entra", name: "Microsoft sign-in", sub: "Entra", ring: 2, needs: [], logo: "microsoft", bot: "ops" },
  { id: "mail", name: "Firm mailbox", sub: "Outlook", ring: 2, needs: ["entra"], logo: "microsoftoutlook", bot: "ops" },
  { id: "files", name: "Client folders", sub: "OneDrive", ring: 2, needs: ["entra"], logo: "microsoftonedrive", bot: "ops" },
  { id: "kv", name: "Secrets vault", sub: "Azure Key Vault", ring: 2, needs: ["entra"], logo: "microsoftazure", bot: "ops" },
  { id: "func", name: "Mail relay", sub: "Azure function", ring: 2, needs: [], logo: "azurefunctions", bot: "ops" },
  { id: "gate", name: "Send gate", sub: "Azure function", ring: 2, needs: ["entra"], logo: "azurefunctions", bot: "ops" },
  { id: "or", name: "OpenRouter", sub: "unattended models", ring: 2, needs: [], line: "route", bot: "ops" },
  { id: "resend", name: "Resend", sub: "signing emails", ring: 2, needs: [], logo: "resend", bot: "ops" },
  { id: "tg", name: "Telegram", sub: "your alerts", ring: 2, needs: [], logo: "telegram", bot: "none" },
  { id: "oracle", name: "Watchers", sub: "two Oracle boxes", ring: 2, needs: [], logo: "oracle", bot: "none" },
  { id: "ts", name: "Tailscale", sub: "private network", ring: 2, needs: [], logo: "tailscale", bot: "ops" },
  { id: "gh", name: "GitHub", sub: "code, checks", ring: 2, needs: [], logo: "github", bot: "none" },
  { id: "port", name: "Dev desktop", sub: "CI, sessions", ring: 2, needs: [], logo: "ubuntu", bot: "dev" },
  { id: "an", name: "Anthropic", sub: "Claude", ring: 2, needs: [], logo: "anthropic", bot: "none" },
];

export const CAPABILITIES: Capability[] = [
  {
    name: "Staff already signed in use the CRM",
    paths: [["crm", "pg", "tunnel", "cf"], ["crm", "pg", "ts"]],
    alt: "Only at the private-network address, on a device that is on Tailscale.",
  },
  {
    name: "Someone signs in to the CRM afresh",
    paths: [["crm", "pg", "tunnel", "cf", "mail"], ["crm", "pg", "ts"]],
    alt: "The sign-in code is emailed to the firm mailbox. Without it, only the private-network address works.",
  },
  { name: "New referrals and court emails reach the system", paths: [["mail", "func", "pg"]] },
  { name: "Client folders are read and filed to", paths: [["files", "prod"]] },
  { name: "Emails are drafted into the mailbox", paths: [["mail", "or", "pg"]] },
  { name: "Safelisted emails send by themselves", paths: [["gate", "mail", "pg"]] },
  {
    name: "Clients sign documents",
    paths: [["sign", "tunnel", "cf", "resend"], ["sign", "tunnel", "cf"]],
    alt: "Signing pages open, but invitation and completion emails do not go out.",
  },
  {
    name: "A restarted service gets its secrets",
    paths: [["kv", "prod"]],
    down: "Running services keep the secrets they loaded. Do not restart or reboot anything until this is back.",
  },
  {
    name: "Outage alerts reach your Telegram",
    paths: [["tg", "prod"], ["tg", "oracle"]],
    alt: "caseforge_counsel_bot is silent while production is down; caseforge_dev_bot still pages you from the two watcher boxes.",
  },
  { name: "Errors are recorded", paths: [["glitch"]] },
  { name: "Code is checked and deployed", paths: [["gh", "port", "prod"]] },
  { name: "Development sessions run", paths: [["an", "port"]] },
];

export const PRESETS: Array<[string, string[]]> = [
  ["Microsoft outage", ["entra"]],
  ["Mailbox only", ["mail"]],
  ["Cloudflare", ["cf"]],
  ["Production box", ["prod"]],
  ["OpenRouter", ["or"]],
];

const BY_ID: Record<string, OutageService> = Object.fromEntries(SERVICES.map((s) => [s.id, s]));

export function serviceById(id: string): OutageService {
  return BY_ID[id];
}

export function isDown(id: string, off: ReadonlySet<string>, seen: ReadonlySet<string> = new Set()): boolean {
  if (off.has(id)) return true;
  if (seen.has(id)) return false;
  const next = new Set(seen).add(id);
  return BY_ID[id].needs.some((n) => isDown(n, off, next));
}

export type CapState = "ok" | "warn" | "bad";

export interface CapResult {
  cap: Capability;
  state: CapState;
  label: string;
  why: string;
}

export function capabilityState(cap: Capability, off: ReadonlySet<string>): CapResult {
  const up = cap.paths.map((p) => p.every((id) => !isDown(id, off)));
  if (up[0]) return { cap, state: "ok", label: "Works", why: "" };
  const missing = [...new Set(cap.paths[0].filter((id) => isDown(id, off)).map((id) => BY_ID[id].name))].join(", ");
  if (up.slice(1).some(Boolean)) return { cap, state: "warn", label: "Limited", why: `${cap.alt ?? ""} Missing: ${missing}.`.trim() };
  return { cap, state: "bad", label: "Stops", why: `${cap.down ? `${cap.down} ` : ""}Missing: ${missing}.` };
}

const ORDER: Record<CapState, number> = { bad: 0, warn: 1, ok: 2 };

export function capabilityResults(off: ReadonlySet<string>): CapResult[] {
  return CAPABILITIES.map((c) => capabilityState(c, off)).sort((a, b) => ORDER[a.state] - ORDER[b.state]);
}

export interface Placed extends OutageService {
  x: number;
  y: number;
}

export function layout(): Placed[] {
  const placed: Placed[] = [];
  for (const ring of [0, 1, 2] as const) {
    const group = SERVICES.filter((s) => s.ring === ring);
    const r = ring === 1 ? 135 : 305;
    group.forEach((s, i) => {
      if (ring === 0) return placed.push({ ...s, x: 0, y: 0 });
      const a = -Math.PI / 2 + (i + (ring === 1 ? 0.5 : 0)) * ((2 * Math.PI) / group.length);
      placed.push({ ...s, x: r * Math.cos(a), y: r * Math.sin(a) });
    });
  }
  return placed;
}

export function wiring(): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  for (const s of SERVICES) {
    const to = s.needs.length ? s.needs : s.ring === 2 ? ["prod"] : [];
    for (const t of to) out.push([s.id, t]);
  }
  return out;
}

export type RouteKind = "page" | "digest" | "none";

export interface TelegramCard {
  bot: string;
  route: RouteKind;
  routeText: string;
  text: string;
}

export function telegramCards(off: ReadonlySet<string>): TelegramCard[] {
  if (off.size === 0) return [{ bot: "No message", route: "none", routeText: "Everything running", text: "" }];
  if (off.has("tg")) {
    return [
      {
        bot: "Nothing arrives",
        route: "none",
        routeText: "Telegram is down",
        text: "No bot can reach you while Telegram is down. Messages sent in the meantime are logged on the box but not delivered.",
      },
    ];
  }
  const results = capabilityResults(off);
  const stops = results.filter((r) => r.state === "bad");
  const limited = results.filter((r) => r.state === "warn");
  const summary = (names: string[]): string => {
    const lines = [`DOWN: ${names.join(", ")}`];
    if (stops.length) lines.push("", "Stops:", ...stops.map((r) => `  - ${r.cap.name}`));
    if (limited.length) lines.push("", "Limited:", ...limited.map((r) => `  - ${r.cap.name}`));
    lines.push("", `${results.length - stops.length - limited.length} of ${results.length} things are unaffected.`);
    const act = results.find((r) => r.cap.down && r.state === "bad");
    lines.push(
      act
        ? `Do: ${act.cap.down}`
        : limited.some((r) => r.cap.paths[0].includes("cf"))
          ? "Do: use the private-network address for the CRM."
          : "Do: nothing. You will be told when it is back.",
    );
    return lines.join("\n");
  };
  const ids = [...off];
  const names = (list: string[]) => list.map((id) => BY_ID[id].name);
  const dev = ids.filter((id) => BY_ID[id].bot === "dev");

  const ops = ids.filter((id) => BY_ID[id].bot === "ops" && !(off.has("prod") && BY_ID[id].ring === 1));
  const none = ids.filter((id) => BY_ID[id].bot === "none" && id !== "oracle");
  const cards: TelegramCard[] = [];
  let first = true;
  if (dev.length) {
    if (off.has("oracle")) {
      cards.push({
        bot: "caseforge_dev_bot",
        route: "none",
        routeText: "Silent",
        text: `The watcher boxes are down, so nothing reports ${names(dev).join(" or ")} being unreachable.`,
      });
    } else {
      cards.push({ bot: "caseforge_dev_bot", route: "page", routeText: "Page now", text: summary(names(dev)) });
      first = false;
    }
  } else if (off.has("oracle")) {
    cards.push({
      bot: "caseforge_dev_bot",
      route: "none",
      routeText: "Silent",
      text: "Nothing reports the watchers themselves while both are down. Production and the desktop are unwatched until they return.",
    });
  }
  if (ops.length) {
    if (off.has("prod")) {
      cards.push({
        bot: "caseforge_counsel_bot",
        route: "none",
        routeText: "Held",
        text: `The supervisor runs on the production box, so ${names(ops).join(", ")} is reported only once production is back.`,
      });
    } else {
      cards.push({
        bot: "caseforge_counsel_bot",
        route: "digest",
        routeText: "Morning digest, page after 2 h",
        text: first ? summary(names(ops)) : `DOWN: ${names(ops).join(", ")}`,
      });
      first = false;
    }
  }
  if (none.length) {
    cards.push({ bot: "No bot", route: "none", routeText: "Not watched", text: `${names(none).join(", ")}: no alert is set up for this.` });
  }
  return cards;
}

const PROVIDER_SERVICES: Record<string, string[]> = {
  cloudflare: ["cf"],
  github: ["gh"],
  anthropic: ["an"],
  openrouter: ["or"],
  azure: ["kv", "func", "gate"],
  telegram: ["tg"],
};

export interface LiveDown {
  ids: string[];
  reasons: Record<string, string>;
}

export function liveDownFromStatus(status: SystemStatusResponse | null): LiveDown {
  const reasons: Record<string, string> = {};
  if (!status) return { ids: [], reasons };
  if (status.providers.available) {
    for (const p of status.providers.providers) {
      if (p.state !== "outage") continue;
      for (const id of PROVIDER_SERVICES[p.key] ?? []) reasons[id] = `${p.name} declares an outage${p.title ? `: ${p.title}` : ""}.`;
    }
  }
  const probes = status.services;
  if (probes && probes.available && !probes.stale) {
    for (const row of probes.services) {
      if (row.state === "down" && BY_ID[row.key]) {
        const since = dateTimeLabel(row.since);
        reasons[row.key] = `${row.reason || "Its health check is failing."}${since ? ` Since ${since}.` : ""}`;
      }
    }
  }
  return { ids: Object.keys(reasons), reasons };
}
