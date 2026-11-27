
import { FIRM_DEFAULTS } from "./firmDefaults";
import { DEMO_FIRM } from "./stubFirm";

export type FirmHostKey = "crm" | "chat" | "sign" | "demo";

export type FirmProfile = {

  short_name: string;

  workers: readonly string[];

  hostnames: Record<FirmHostKey, string>;
};

export type FirmEnv = Partial<Record<string, string | undefined>>;

const HOST_VARS: Record<FirmHostKey, string> = {
  crm: "NEXT_PUBLIC_FIRM_HOST_CRM",
  chat: "NEXT_PUBLIC_FIRM_HOST_CHAT",
  sign: "NEXT_PUBLIC_FIRM_HOST_SIGN",
  demo: "NEXT_PUBLIC_FIRM_HOST_DEMO",
};

function text(value: string | undefined, fallback: string): string {
  const v = (value ?? "").trim();
  return v || fallback;
}

function list(value: string | undefined, fallback: readonly string[]): readonly string[] {
  const names = (value ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  return names.length ? names : fallback;
}

export function resolveFirm(env: FirmEnv, demo: boolean, defaults: FirmProfile = FIRM_DEFAULTS): FirmProfile {
  const hostnames = { ...defaults.hostnames };
  for (const key of Object.keys(HOST_VARS) as FirmHostKey[]) hostnames[key] = text(env[HOST_VARS[key]], defaults.hostnames[key]);
  return {
    short_name: text(env.NEXT_PUBLIC_FIRM_SHORT_NAME, defaults.short_name),
    workers: demo ? DEMO_FIRM.workers : list(env.NEXT_PUBLIC_FIRM_WORKERS, defaults.workers),
    hostnames,
  };
}

export const FIRM: FirmProfile = resolveFirm(
  {
    NEXT_PUBLIC_FIRM_SHORT_NAME: process.env.NEXT_PUBLIC_FIRM_SHORT_NAME,
    NEXT_PUBLIC_FIRM_WORKERS: process.env.NEXT_PUBLIC_FIRM_WORKERS,
    NEXT_PUBLIC_FIRM_HOST_CRM: process.env.NEXT_PUBLIC_FIRM_HOST_CRM,
    NEXT_PUBLIC_FIRM_HOST_CHAT: process.env.NEXT_PUBLIC_FIRM_HOST_CHAT,
    NEXT_PUBLIC_FIRM_HOST_SIGN: process.env.NEXT_PUBLIC_FIRM_HOST_SIGN,
    NEXT_PUBLIC_FIRM_HOST_DEMO: process.env.NEXT_PUBLIC_FIRM_HOST_DEMO,
  },
  process.env.NEXT_PUBLIC_CASEFORGE_DEMO === "1",
);

export function firmUrl(key: FirmHostKey): string {
  return `https://${FIRM.hostnames[key]}`;
}
