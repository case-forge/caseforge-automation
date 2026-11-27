
export type ModelSource = "env" | "override" | "file" | "missing";

export interface ModelRoleStats {
  calls: number;
  failures: number;
  p50_seconds: number | null;
  cost_usd: number;
}

export interface ModelRoleRow {
  role: string;
  purpose: string;
  tier: "small" | "large";
  model: string;
  source: ModelSource;
  source_text: string;
  default_model: string;
  overridden: boolean;
  backend: "openrouter" | "anthropic-direct";
  anthropic_direct: boolean;
  retention: { status: "zdr" | "direct" | "unavailable"; text: string };
  spend_cap: { daily_usd: number | null; total_usd: number | null };
  stats: ModelRoleStats | null;
  swappable: boolean;
  locked: boolean;
  note: string;
  candidates: string[];
  applies: string;
}

export interface ModelRolesView {
  can_edit: boolean;
  stats_days: number;
  stats_available: boolean;
  anthropic_key_configured: boolean;
  models_in_use: string[];
  roles: ModelRoleRow[];
}

export const ROLE_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;

export function validRole(value: unknown): value is string {
  return typeof value === "string" && ROLE_PATTERN.test(value);
}

export function validModelId(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 120 && /^[A-Za-z0-9._:/-]+$/.test(value);
}

export function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "none yet";
  return value < 10 ? `${value.toFixed(1)} s` : `${Math.round(value)} s`;
}

export function formatCost(value: number): string {
  if (value === 0) return "$0";
  return value < 0.01 ? "under $0.01" : `$${value.toFixed(2)}`;
}

export function formatCap(cap: ModelRoleRow["spend_cap"]): string {
  const parts: string[] = [];
  if (cap.daily_usd !== null && cap.daily_usd > 0) parts.push(`$${cap.daily_usd.toFixed(2)} a day`);
  if (cap.total_usd !== null && cap.total_usd > 0) parts.push(`$${cap.total_usd.toFixed(2)} in all`);
  return parts.length ? parts.join(", ") : "none";
}

export function backendLabel(row: Pick<ModelRoleRow, "backend">): string {
  return row.backend === "anthropic-direct" ? "Anthropic direct" : "OpenRouter";
}

export function changeLine(row: Pick<ModelRoleRow, "purpose" | "model">, next: string): { purpose: string; from: string; to: string } {
  return { purpose: row.purpose, from: row.model, to: next };
}

export type LoadResult = { state: "ok"; view: ModelRolesView } | { state: "error" };

export async function loadModelRoles(fetcher: typeof fetch = fetch): Promise<LoadResult> {
  try {
    const res = await fetcher("/api/settings/models", { cache: "no-store" });
    if (!res.ok) return { state: "error" };
    const body = await res.json();
    return Array.isArray(body?.roles) ? { state: "ok", view: body as ModelRolesView } : { state: "error" };
  } catch {
    return { state: "error" };
  }
}

export type ChangeResult = { ok: true } | { ok: false; message: string };

async function sent(res: Response): Promise<ChangeResult> {
  if (res.ok) return { ok: true };
  let message = "The change could not be saved.";
  try {
    const body = await res.json();
    if (typeof body?.error === "string") message = body.error;
  } catch {

  }
  return { ok: false, message };
}

export async function saveRoleModel(role: string, model: string, expectedOld: string, fetcher: typeof fetch = fetch): Promise<ChangeResult> {
  try {
    return await sent(
      await fetcher("/api/settings/models", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, model, expected_old: expectedOld }),
      }),
    );
  } catch {
    return { ok: false, message: "The change could not be saved." };
  }
}

export async function resetRoleModel(role: string, fetcher: typeof fetch = fetch): Promise<ChangeResult> {
  try {
    return await sent(await fetcher(`/api/settings/models?role=${encodeURIComponent(role)}`, { method: "DELETE" }));
  } catch {
    return { ok: false, message: "The change could not be saved." };
  }
}
