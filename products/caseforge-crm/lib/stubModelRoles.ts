
import type { ModelRoleRow, ModelRolesView } from "./modelRoles";

export const STUB_MODELS_ADMIN_COOKIE = "caseforge_stub_models_admin";

const BIG = "qwen/qwen3-235b-a22b-2507";
const NOVA = "amazon/nova-lite-v1";
const DEEPSEEK = "deepseek/deepseek-v4-flash-0731";
const HAIKU = "anthropic/claude-haiku-5.5";
const SONNET = "anthropic/claude-sonnet-5.5";

type Seed = [string, string, "small" | "large", string, number, number, number | null, number, boolean?];
const SEEDS: Seed[] = [
  ["case_summary", "Writes the case summary on a bundle front page", "large", BIG, 41, 1, 38.2, 1.12],
  ["chronology", "Writes the chronology on a bundle front page", "large", BIG, 40, 0, 41.5, 1.07],
  ["ccl_draft", "Drafts the client care letter", "large", BIG, 18, 0, 22.4, 0.31],
  ["ccl_escalation", "Second look at a client care letter the first pass was unsure about", "large", HAIKU, 3, 0, 6.1, 0.02],
  ["ccl_field_check", "Checks the fields of a client care letter", "small", NOVA, 22, 0, 2.3, 0.01],
  ["client_letter", "Drafts letters to clients", "large", BIG, 9, 0, 19.8, 0.14],
  ["an_draft", "Proofreads attendance notes: spelling, punctuation and grammar only", "large", HAIKU, 212, 4, 3.4, 0.38],
  ["an_memo_classifier", "Sorts old memo text into attendance note types", "small", NOVA, 0, 0, null, 0],
  ["matter_facts", "Pulls the basic facts of a matter from its documents", "large", BIG, 64, 2, 17.0, 0.88],
  ["matter_incidents", "Lists incidents mentioned in a matter's documents", "small", DEEPSEEK, 58, 0, 9.6, 0.07],
  ["matter_timeline", "Builds the dated timeline of a matter", "small", DEEPSEEK, 58, 1, 11.2, 0.08],
  ["form_fill_strong", "Fills court forms (the careful pass)", "large", BIG, 12, 0, 27.9, 0.2],
  ["form_fill_cheap", "Fills court forms (the quick pass)", "small", NOVA, 31, 0, 4.0, 0.01],
  ["mail_triage", "Sorts incoming mail into categories", "small", NOVA, 1840, 12, 1.4, 0.43, true],
  ["mail_escalation", "Second look at mail the first pass could not sort", "large", BIG, 96, 3, 8.8, 0.35],
  ["email_pdf_label", "Names the PDF made from an email", "small", NOVA, 702, 2, 1.2, 0.12],
  ["scanned_docs_triage", "Works out what a scanned document is", "small", NOVA, 388, 5, 2.6, 0.09],
  ["vision", "Reads the text on a scanned page image", "small", NOVA, 1204, 21, 3.9, 0.74],
  ["vergil_chat", "Answers questions in Vergil, the chat assistant", "large", BIG, 133, 2, 12.7, 0.66],
  ["chat_title", "Gives each Vergil chat a short title", "small", "openai/gpt-oss-20b", 133, 0, 1.1, 0.01],
  ["safety_guard", "Checks messages for unsafe requests before they are answered", "small", "openai/gpt-oss-safeguard-20b", 133, 0, 0.9, 0.02],
  ["safety_guard_fallback", "Takes over the safety check when the main guard does not answer", "small", "nvidia/nemotron-3.5-content-safety", 0, 0, null, 0],
  ["amend_planner", "Case flow amend rounds: plans the changes", "large", SONNET, 7, 0, 21.0, 0.41],
  ["amend_editor", "Case flow amend rounds: edits the draft", "large", "anthropic/claude-opus-5.5", 7, 0, 33.4, 0.96],
];

const DEFAULTS = new Map(SEEDS.map((s) => [s[0], s[3]]));
const current = new Map(SEEDS.map((s) => [s[0], s[3]]));

function tierOf(model: string): Set<string> {
  return new Set(SEEDS.filter((s) => current.get(s[0]) === model).map((s) => s[2]));
}

function rowFor(seed: Seed): ModelRoleRow {
  const [role, purpose, tier, , calls, failures, p50, cost, locked] = seed;
  const model = current.get(role) ?? seed[3];
  const direct = model.startsWith("anthropic/");
  const overridden = !locked && model !== DEFAULTS.get(role);
  const used = new Set(current.values());
  const guard = role.startsWith("safety_guard");
  const candidates = locked || role === "vision" ? [] : [...used].filter((m) => {
    if (m === model || !tierOf(m).has(tier)) return false;
    const serves = SEEDS.filter((s) => current.get(s[0]) === m).map((s) => s[0]);
    if (guard) return serves.some((r) => r.startsWith("safety_guard"));
    return !serves.every((r) => r.startsWith("safety_guard"));
  }).sort();
  return {
    role,
    purpose,
    tier,
    model,
    source: locked ? "env" : overridden ? "override" : "file",
    source_text: locked ? "Pinned by an environment variable" : overridden ? "Changed in Settings" : "Model roles file (default)",
    default_model: DEFAULTS.get(role) ?? model,
    overridden,
    backend: direct ? "anthropic-direct" : "openrouter",
    anthropic_direct: direct,
    retention: direct
      ? { status: "direct", text: "Anthropic's own API, by the owner's decision. It has no per-request zero retention setting." }
      : { status: "zdr", text: "Zero data retention asserted on every request; a model with no such provider is refused." },
    spend_cap: direct ? { daily_usd: 10, total_usd: 90 } : { daily_usd: 4, total_usd: null },
    stats: { calls, failures, p50_seconds: p50, cost_usd: cost },
    swappable: candidates.length > 0,
    locked: Boolean(locked),
    note: locked
      ? "Pinned by an environment variable on the server, so it cannot be changed here."
      : candidates.length === 0
        ? "No other model in use can do this job."
        : "",
    candidates,
    applies: "next call",
  };
}

export function stubModelRoles(canEdit: boolean): ModelRolesView {
  return {
    can_edit: canEdit,
    stats_days: 14,
    stats_available: true,
    anthropic_key_configured: true,
    models_in_use: [...new Set(current.values())].sort(),
    roles: SEEDS.map(rowFor),
  };
}

type Done = { ok: true; change: { role: string; old: string; new: string } } | { ok: false; status: number; message: string };

export function stubSwapRole(role: string, model: string, expectedOld: string, canEdit: boolean): Done {
  const seed = SEEDS.find((s) => s[0] === role);
  if (!canEdit) return { ok: false, status: 403, message: "Only an administrator can change a model" };
  if (!seed) return { ok: false, status: 404, message: "There is no such role." };
  const row = rowFor(seed);
  if (row.locked) return { ok: false, status: 409, message: row.note };
  if (expectedOld && expectedOld !== row.model) return { ok: false, status: 409, message: "This role was changed by someone else since you opened the page. Reload and try again." };
  if (!row.candidates.includes(model)) return { ok: false, status: 422, message: "That model is not serving any role at the moment, and only models already in use can be chosen." };
  current.set(role, model);
  return { ok: true, change: { role, old: row.model, new: model } };
}

export function stubResetRole(role: string, canEdit: boolean): Done {
  const seed = SEEDS.find((s) => s[0] === role);
  if (!canEdit) return { ok: false, status: 403, message: "Only an administrator can change a model" };
  if (!seed) return { ok: false, status: 404, message: "There is no such role." };
  const old = current.get(role) ?? seed[3];
  if (old === seed[3]) return { ok: false, status: 422, message: "This role is not changed from its default." };
  current.set(role, seed[3]);
  return { ok: true, change: { role, old, new: seed[3] } };
}

export function resetStubModelRoles(): void {
  for (const s of SEEDS) current.set(s[0], s[3]);
}
