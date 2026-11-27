
import { ADMIN_LINK_DEFAULTS, EXPORT_BOARD_DEFAULT } from "./firmDefaults";

export type FirmLink = {
  label: string;
  href: string;
  description: string;

  logo?: string;
  mono?: boolean;
};

const ALL_BASE_LINKS: FirmLink[] = [
  { label: "Cloudflare", href: "https://dash.cloudflare.com", description: "DNS, tunnels, Access", logo: "cloudflare.svg", mono: true },
  { label: "GitHub", href: "https://github.com/case-forge/caseforge-automation", description: "Source, issues, Actions", logo: "github.svg", mono: true },
  { label: "OpenRouter", href: "https://openrouter.ai/workspaces/default/activity", description: "Model routing, usage and spend", logo: "openrouter.svg", mono: true },
  { label: "Tailscale", href: "https://login.tailscale.com/admin", description: "Tailnet devices, ACLs and auth keys", logo: "tailscale.svg", mono: true },
  { label: "GlitchTip", href: (process.env.NEXT_PUBLIC_FIRM_LINK_GLITCHTIP ?? "").trim() || ADMIN_LINK_DEFAULTS.glitchtip, description: "Error tracking for the CRM, Vergil and the hub API", logo: "glitchtip.svg", mono: false },
  { label: "Healthchecks", href: (process.env.NEXT_PUBLIC_FIRM_LINK_HEALTHCHECKS ?? "").trim(), description: "Dead-man-switch pings for cron and systemd jobs", logo: "healthchecks.svg", mono: false },
  { label: "Healthchecks.io", href: "https://healthchecks.io/", description: "The hosted checks account", logo: "healthchecks.svg", mono: false },
  { label: "Claude", href: "https://claude.ai/new#settings/usage", description: "Subscription usage", logo: "claude.svg", mono: true },
  { label: "Claude API", href: "https://platform.claude.com/settings/keys", description: "API keys and spend", logo: "anthropic.svg", mono: true },
  { label: "Entra", href: "https://entra.microsoft.com/", description: "Users, sign-ins and devices", logo: "shield.svg", mono: true },
  { label: "App registrations", href: "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade", description: "The Graph apps, their permissions and secrets", logo: "grid.svg", mono: true },
  { label: "Azure", href: "https://portal.azure.com/#home", description: "Secrets, function apps and billing", logo: "cloud.svg", mono: true },
];

const BASE_LINKS: FirmLink[] = ALL_BASE_LINKS.filter((link) => link.href !== "");

function webAddress(value: string | undefined): string {
  const v = (value ?? "").trim();
  try {
    return /^https?:$/.test(new URL(v).protocol) ? v : "";
  } catch {
    return "";
  }
}

export const EXPORT_BOARD_URL: string = webAddress(process.env.NEXT_PUBLIC_FIRM_LINK_EXPORT_BOARD) || EXPORT_BOARD_DEFAULT;

export function buildFirmLinks(umamiUrl: string | undefined): FirmLink[] {
  const umami = webAddress(umamiUrl);
  return umami ? [...BASE_LINKS, { label: "Umami", href: umami, description: "Website and app analytics", logo: "umami.svg", mono: true }] : BASE_LINKS;
}

export const FIRM_LINKS: FirmLink[] = buildFirmLinks(process.env.NEXT_PUBLIC_UMAMI_URL);

export function logoSrc(link: FirmLink): string {
  return `/link-logos/${link.logo}`;
}

export function isTailnetOnly(href: string): boolean {
  let host: string;
  try {
    host = new URL(href).hostname;
  } catch {
    return false;
  }
  return /^100\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host) || host === "ts.net" || host.endsWith(".ts.net");
}
