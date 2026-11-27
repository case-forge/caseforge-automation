
import { LEGAL_AID_RATE_PREFIX, type AppSetting, type AppSettingsView, type Person } from "./appSettings";

const LEGAL_AID_RATES: [string, string, string, string][] = [
  ["routine_letter_out", "Letter out", "each", "5.40"],
  ["routine_letter_in", "Routine letter in", "each", "2.70"],
  ["telephone", "Telephone", "each", "5.40"],
  ["attendance_preparation", "Attendance and preparation", "per hour", "59.40"],
  ["attendance_counsel_court", "Attendance on counsel or at court", "per hour", "32.40"],
  ["advocacy_court", "Advocacy at court", "per hour", "59.40"],
  ["travelling_waiting", "Travelling and waiting", "per hour", "28.80"],
];

const base = { restart_required: false, minimum: null, maximum: null, choices: [] as string[], writable: true, env_invalid: false, updated_by: "", updated_at: "", locked: false, source: "default" as const, max_length: 300 };
const text = (key: string, group: string, label: string, help: string, value: string, extra: Partial<AppSetting> = {}): AppSetting => ({
  ...base, key, group, type: "string", label, help, value, default: value, env: `CASEFORGE_SETTING_${key.toUpperCase()}`, ...extra,
});

const START: AppSetting[] = [
  text("firm_name", "firm", "Firm name", "The firm's full name, as court documents print it.", "Sample Firm Limited", { restart_required: true }),
  text("firm_trading_name", "firm", "Trading name", "The short name used in letters, email labels and the chat assistant.", "Example Law", { restart_required: true }),
  text("office_street", "firm", "Office street", "Building and street of the office on statements of service.", "1 Sample Street", { restart_required: true }),
  text("office_town", "firm", "Office town", "Town or city of the office.", "Sampletown", { restart_required: true }),
  text("office_postcode", "firm", "Office postcode", "Postcode of the office.", "AB1 2CD", { restart_required: true }),
  text("firm_phone", "firm", "Phone", "The firm's telephone number on court forms.", "020 7946 0000", { restart_required: true }),
  text("email_heading", "firm", "Email PDF heading", "The heading printed at the top of an email saved as a PDF.", "Example Law - Solicitors", { restart_required: true, locked: true, source: "env" }),
  { ...base, key: "solicitors", group: "solicitor", type: "people", label: "Instructing solicitors", help: "The firm's instructing solicitors: name, email and role label. Edit to add more.", value: [{ name: "A. Sample", email: "solicitor@example.test", role: "Solicitor" }], default: [{ name: "A. Sample", email: "solicitor@example.test", role: "Solicitor" }], env: "CASEFORGE_SETTING_SOLICITORS", restart_required: true, max_length: null },
  { ...base, key: "current_solicitor", group: "solicitor", type: "person_choice", label: "Current instructing solicitor", help: "Who signs statements of truth and appears on court forms. Chosen from the list above.", value: "A. Sample", default: "A. Sample", choices: ["A. Sample"], env: "CASEFORGE_SETTING_CURRENT_SOLICITOR", restart_required: true, max_length: null },
  text("scanned_docs_folder", "folders", "Scanned Docs folder", "The OneDrive folder scanned documents wait in. Blank restores the default.", "Company_Data/Scanned Docs", { type: "path" }),
  text("common_documents_folder", "folders", "Stock documents folder", "The OneDrive folder of stock documents the virtual scanner compares against. Blank restores the default.", "Library/Common Documents", { type: "path" }),
  { ...base, key: "backup_retention_days", group: "folders", type: "int", label: "Backup retention (days)", help: "How many days of nightly backups to keep in the backup folder. Older files are deleted weekly, always keeping the newest copy of every kind of backup. The least allowed is 3.", value: 14, default: 14, minimum: 3, maximum: 365, env: "CASEFORGE_SETTING_BACKUP_RETENTION_DAYS", max_length: null },
  text("unsorted_notes_folder", "folders", "Unsorted notes folder", "The OneDrive folder attendance notes go to when no client is found. Blank restores the default, Unsorted Attendance Notes. If the folder set here has been deleted, notes go to the default instead, and it is made again if it is missing.", "Library/Unsorted Attendance Notes", { type: "path" }),
  { ...base, key: "statement_draft_cleanup", group: "folders", type: "bool", label: "Tidy spare statement drafts", help: "When on, once a witness statement is signed, the spare draft Word files for it in Preliminary Docs are moved into 000 Removed in the client's folder (never deleted; move one back to undo). Off (the default) only reports.", value: false, default: false, env: "CASEFORGE_SETTING_STATEMENT_DRAFT_CLEANUP", max_length: null },
  { ...base, key: "referral_postcode_lookup", group: "folders", type: "bool", label: "Look up missing postcodes on a referral", help: "When on, a referral whose applicant or respondent address has no postcode gets one from a free address lookup (OpenStreetMap), only for the exact house, and the matter is marked for a person to check it. The address is sent to that service. Off (the default) sends nothing.", value: false, default: false, env: "CASEFORGE_SETTING_REFERRAL_POSTCODE_LOOKUP", max_length: null },
  { ...base, key: "minutes_per_page", group: "billing", type: "int", label: "Minutes per page", help: "Perusal and preparation notes bill this many minutes for each page, and bundle, court form and received document pages are charged at the attendance and preparation rate for this many minutes. Notes already made keep their time.", value: 2, default: 2, minimum: 1, maximum: 60, env: "CASEFORGE_SETTING_MINUTES_PER_PAGE", max_length: null },
  { ...base, key: "pipeline_auto_finish_court_pack", group: "billing", type: "bool", label: "Finish the court pack automatically", help: "When on, Case flow presses \"The forms are finished\" itself once every final form is on file, and bills the forms and draft orders by page count and the Notice of Acting as a letter out. Off (the default) leaves that press to a person.", value: false, default: false, env: "CASEFORGE_SETTING_PIPELINE_AUTO_FINISH_COURT_PACK", max_length: null },
  { ...base, key: "private_hourly_rate", group: "billing", type: "decimal", label: "Private hourly rate (£, before VAT)", help: "The hourly rate for work on a privately billed matter, before VAT (20% is added on top). New billing lines use it; a line keeps the rate it was made at.", value: "250.00", default: "250.00", env: "CASEFORGE_SETTING_PRIVATE_HOURLY_RATE", max_length: 300 },
  ...LEGAL_AID_RATES.map(([suffix, label, unit, standard]): AppSetting => ({
    ...base, key: `${LEGAL_AID_RATE_PREFIX}${suffix}`, group: "billing", type: "decimal", label: `Legal aid rate: ${label} (£ ${unit})`,
    help: "The legal aid rate for this work, before VAT. New billing lines use it; a line keeps the rate it was made at. Blank restores the standard rate.",
    value: standard, default: standard, env: `CASEFORGE_SETTING_LEGAL_AID_RATE_${suffix.toUpperCase()}`, max_length: 300,
  })),
];

const STUB_OPERATIONS = [
  { key: "auto_draft_hold", label: "Automatic drafting", help: "While held, Case flow auto mode skips every drafting step.", held: true, reason: "held from the Settings page" },
  { key: "email_filing_hold", label: "Automatic filing of court replies", help: "While held, court replies are not filed automatically.", held: true, reason: "held" },
];
const operations = new Map<string, boolean>();

export function stubSetOperation(key: string, held: boolean, canEdit: boolean): Done {
  if (!canEdit) return { ok: false, status: 403, message: "Only an administrator can change settings" };
  if (!STUB_OPERATIONS.some((o) => o.key === key)) return { ok: false, status: 404, message: "There is no such switch" };
  operations.set(key, held);
  return { ok: true };
}

type Value = string | number | boolean | Person[];
const state = new Map<string, Value>();

function namesOf(value: unknown): string[] {
  return (value as Person[]).map((p) => p.name);
}

export function stubAppSettings(canEdit: boolean): AppSettingsView {
  return {
    can_edit: canEdit,
    secrets_note: "Passwords, tokens and connection strings are managed in Key Vault and never shown or stored on this page.",
    groups: [
      { key: "firm", label: "Firm", description: "How the firm names and addresses itself on court documents and emails." },
      { key: "solicitor", label: "Instructing solicitor", description: "The solicitor who instructs the firm's work and signs it off." },
      { key: "folders", label: "Folders", description: "Where the system looks for scanned documents, stock documents and unsorted notes." },
      { key: "billing", label: "Billing", description: "Time and page rules for notes." },
      { key: "operations", label: "Operations", description: "Switches that stop automatic work. An administrator can hold or release each." },
    ],
    settings: START.map((s) => {
      const stored = state.get(s.key);
      if (stored === undefined || s.locked) return s;
      return { ...s, value: stored, source: "database" as const, updated_by: "demo.admin@example.test", updated_at: "2026-10-25T12:00:00Z" };
    }).map((s) => (s.key === "current_solicitor" ? { ...s, choices: namesOf(state.get("solicitors") ?? START.find((x) => x.key === "solicitors")!.value) } : s)),
    status: STUB_OPERATIONS.map((o) => ({ ...o, held: operations.get(o.key) ?? o.held })),
  };
}

type Done = { ok: true } | { ok: false; status: number; message: string };

export function stubSave(values: Record<string, unknown>, canEdit: boolean): Done {
  if (!canEdit) return { ok: false, status: 403, message: "Only an administrator can change settings" };
  const next = new Map<string, Value>();
  for (const [key, raw] of Object.entries(values)) {
    const s = START.find((x) => x.key === key);
    if (!s) return { ok: false, status: 404, message: "There is no such setting" };
    if (s.locked) return { ok: false, status: 409, message: `${s.label} is set by the environment (${s.env}) and cannot be changed here` };
    if (!s.writable) return { ok: false, status: 422, message: `${s.label} is changed on its own, not with the other settings` };
    if (s.type === "people") {
      const list = raw as Person[];
      const okShape = Array.isArray(list) && list.length >= 1 && list.length <= 20 && list.every((p) => p && typeof p.name === "string" && p.name.trim() !== "" && /^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$/.test(String(p.email).trim()));
      if (!okShape) return { ok: false, status: 422, message: `${s.label} needs a name and a valid email address for every entry` };
      next.set(key, list.map((p) => ({ name: p.name.trim(), email: p.email.trim(), role: String(p.role ?? "").trim() })));
      continue;
    }
    if (s.type === "person_choice") {
      next.set(key, String(raw));
      continue;
    }
    if (s.type === "int") {
      if (raw === "" || raw === null) { next.set(key, ""); continue; }
      if (typeof raw !== "number" || !Number.isInteger(raw) || raw < (s.minimum ?? 0) || raw > (s.maximum ?? 1e9)) return { ok: false, status: 422, message: `${s.label} must be a whole number from ${s.minimum} to ${s.maximum}` };
    } else if (s.type === "bool") {
      if (typeof raw !== "boolean") return { ok: false, status: 422, message: `${s.label} must be on or off` };
    } else if (s.type === "enum") {
      if (typeof raw !== "string" || !s.choices.includes(raw)) return { ok: false, status: 422, message: `${s.label} must be one of: ${s.choices.join(", ")}` };
    } else if (typeof raw !== "string" || raw.length > 300) {
      return { ok: false, status: 422, message: `${s.label} must be text` };
    } else if (s.type === "email" && raw.trim() !== "" && !/^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$/.test(raw.trim())) {
      return { ok: false, status: 422, message: `${s.label} must be an email address` };
    }
    next.set(key, typeof raw === "string" ? raw.trim() : (raw as number | boolean));
  }
  const people = (next.get("solicitors") ?? state.get("solicitors") ?? START.find((x) => x.key === "solicitors")!.value) as Person[];
  const current = next.get("current_solicitor") ?? state.get("current_solicitor");
  if (typeof current === "string" && current !== "" && !people.some((p) => p.name === current)) {
    return { ok: false, status: 422, message: "Current instructing solicitor must be one of the instructing solicitors listed" };
  }
  for (const [key, value] of next) {
    if (value === "") state.delete(key);
    else state.set(key, value);
  }
  return { ok: true };
}

export function resetStubAppSettings(): void {
  state.clear();
  operations.clear();
}
