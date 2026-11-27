
export const LEGAL_AID_RATE_PREFIX = "legal_aid_rate_";

export type SettingType = "string" | "email" | "path" | "int" | "bool" | "enum" | "people" | "person_choice" | "decimal";

export interface Person {
  name: string;
  email: string;
  role: string;
}

export interface AppSetting {
  key: string;
  group: string;
  type: SettingType;
  label: string;
  help: string;
  restart_required: boolean;
  minimum: number | null;
  maximum: number | null;
  choices: string[];
  writable: boolean;
  env: string;
  max_length: number | null;
  value: string | number | boolean | Person[];
  default: string | number | boolean | Person[];
  source: "env" | "database" | "default";
  locked: boolean;
  env_invalid: boolean;
  updated_by: string;
  updated_at: string;
}

export interface SettingsGroup {
  key: string;
  label: string;
  description: string;
}

export interface OperationStatus {
  key: string;
  label: string;
  help: string;
  held: boolean;
  reason: string;
}

export interface AppSettingsView {
  can_edit: boolean;
  secrets_note: string;
  groups: SettingsGroup[];
  settings: AppSetting[];
  status: OperationStatus[];
}

export const GROUP_TABS = ["firm", "solicitor", "folders", "billing", "operations"] as const;

export function asText(value: AppSetting["value"]): string {
  if (Array.isArray(value)) return value.map((p) => p.name).join(", ");
  return typeof value === "boolean" ? (value ? "on" : "off") : String(value ?? "");
}

export type Draft = string | boolean | Person[];
export type Sendable = string | number | boolean | Person[];

const EMAIL = /^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$/;

export function readPeople(setting: AppSetting, draft: Person[]): { ok: true; value: Person[] } | { ok: false; error: string } {
  const out: Person[] = [];
  for (const p of draft) {
    const name = p.name.trim().replace(/\s+/g, " ");
    const email = p.email.trim();
    const role = p.role.trim().replace(/\s+/g, " ");
    if (!name) return { ok: false, error: `${setting.label}: every entry needs a name.` };
    if (!EMAIL.test(email)) return { ok: false, error: `${setting.label}: ${name} needs a valid email address.` };
    if (role.length > 80) return { ok: false, error: `${setting.label}: ${name} has a role label that is too long.` };
    if (out.some((o) => o.name.toLowerCase() === name.toLowerCase())) return { ok: false, error: `${setting.label} lists ${name} more than once.` };
    out.push({ name, email, role });
  }
  if (out.length === 0 || out.length > 20) return { ok: false, error: `${setting.label} needs between 1 and 20 entries.` };
  return { ok: true, value: out };
}

export function sameDraft(a: Draft, b: Draft): boolean {
  return Array.isArray(a) || Array.isArray(b) ? JSON.stringify(a) === JSON.stringify(b) : a === b;
}

export function readDraft(setting: AppSetting, draft: Draft): { ok: true; value: Sendable } | { ok: false; error: string } {
  if (setting.type === "people") return Array.isArray(draft) ? readPeople(setting, draft) : { ok: false, error: `${setting.label} is not a list.` };
  if (Array.isArray(draft)) return { ok: false, error: `${setting.label} is not a list.` };
  if (setting.type === "bool") return { ok: true, value: Boolean(draft) };
  const text = String(draft).trim();
  if (setting.type === "int") {
    if (text === "") return { ok: true, value: "" };
    if (!/^\d+$/.test(text)) return { ok: false, error: `${setting.label} must be a whole number.` };
    const n = Number(text);
    if (setting.minimum !== null && n < setting.minimum) return { ok: false, error: `${setting.label} must be at least ${setting.minimum}.` };
    if (setting.maximum !== null && n > setting.maximum) return { ok: false, error: `${setting.label} must be at most ${setting.maximum}.` };
    return { ok: true, value: n };
  }
  if (setting.type === "decimal" && text !== "") {
    const amount = text.replace(/^£/, "");
    if (!/^\d{1,4}(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0 || Number(amount) >= 2000) {
      return { ok: false, error: `${setting.label} must be an amount in pounds above 0 and below 2,000, such as 250.00.` };
    }
    return { ok: true, value: Number(amount).toFixed(2) };
  }
  if (setting.max_length !== null && text.length > setting.max_length) return { ok: false, error: `${setting.label} is too long.` };
  if (setting.type === "email" && text !== "" && !/^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$/.test(text)) {
    return { ok: false, error: `${setting.label} must be an email address.` };
  }
  if (setting.type === "path" && text !== "") {
    const parts = text.replace(/^\/+|\/+$/g, "").split("/");
    if (/[\\\u0000-\u001f]/.test(text) || parts.some((p) => p.trim() === "" || p.trim() === "." || p.trim() === "..")) {
      return { ok: false, error: `${setting.label} must use forward slashes and no empty or relative parts.` };
    }
  }
  return { ok: true, value: text };
}

export function fieldForError(message: string, settings: AppSetting[]): string | null {
  return settings.find((s) => message.startsWith(s.label))?.key ?? null;
}

export type SettingsLoad = { state: "ok"; view: AppSettingsView } | { state: "error" };

export async function loadAppSettings(fetcher: typeof fetch = fetch): Promise<SettingsLoad> {
  try {
    const res = await fetcher("/api/settings", { cache: "no-store" });
    if (!res.ok) return { state: "error" };
    const body = await res.json();
    return Array.isArray(body?.settings) && Array.isArray(body?.groups) ? { state: "ok", view: body as AppSettingsView } : { state: "error" };
  } catch {
    return { state: "error" };
  }
}

export type SaveResult = { ok: true; view: AppSettingsView } | { ok: false; message: string };

async function answer(res: Response): Promise<SaveResult> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {

  }
  if (res.ok && body && typeof body === "object" && Array.isArray((body as AppSettingsView).settings)) return { ok: true, view: body as AppSettingsView };
  const message = body && typeof body === "object" && typeof (body as { error?: unknown }).error === "string" ? (body as { error: string }).error : "The settings could not be saved.";
  return { ok: false, message };
}

export async function saveSettings(values: Record<string, Sendable>, fetcher: typeof fetch = fetch): Promise<SaveResult> {
  try {
    return await answer(await fetcher("/api/settings", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ values }) }));
  } catch {
    return { ok: false, message: "The settings could not be saved." };
  }
}

export async function setOperation(key: string, held: boolean, fetcher: typeof fetch = fetch): Promise<SaveResult> {
  try {
    return await answer(await fetcher(`/api/settings/operations/${encodeURIComponent(key)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ held }) }));
  } catch {
    return { ok: false, message: "The switch could not be changed." };
  }
}
