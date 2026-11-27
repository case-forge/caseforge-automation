import type { SameNameFields } from "./sameName";

export interface ClientMatch extends SameNameFields {
  matter_id?: string | number | null;
  client_name?: string | null;
  matter_name?: string | null;
  client_role?: string | null;
  case_reference?: string | null;
  reference_summary?: string | null;
  email_primary?: string | null;
  phone_primary?: string | null;
  dob_iso?: string | null;
  address_summary?: string | null;
  party_summary?: string | null;
  matched_party_summary?: string | null;
  order_requested_text?: string | null;
  live_matter_folder?: string | null;
  legal_aid_tracker_status?: string | null;
  closed_at?: string | null;
  extra: Record<string, unknown>;
}

export interface PersonMattersResponse {
  matter_id: string;
  matters: ClientMatch[];
}

export interface ClientSearchResponse {
  query: string;
  resolved_query: string;
  source: string;
  count: number;
  results: ClientMatch[];
}

export interface ClientEdit {
  edit_id: string;
  matter_id: string;
  field_name: string;
  field_label: string;
  old_value: string | null;
  new_value: string;
  note: string;
  edited_by: string;
  created_at: string;
}

export interface MatterFlagsResponse {
  matter_id: string;
  flags: Record<string, boolean>;

  reasons?: Record<string, string>;

  shared?: Record<string, boolean>;

  personal?: Record<string, boolean>;
  personal_reasons?: Record<string, string>;
}

export interface FieldReviewFlag {
  review_id: string;
  matter_id: string;
  client_name: string;
  field_name: string;
  field_label: string;
  value_snapshot: string;
  note: string;
  flagged_by: string;
  flagged_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
}

export interface FieldReviewQueueResponse {
  results: ClientMatch[];
  flags_by_matter: Record<string, FieldReviewFlag[]>;
}

export interface MatterParty {
  party_id: string;
  matter_id: string;
  role: string;
  display_name: string;
  name_first: string;
  name_middle: string;
  name_last: string;
  aka_name: string;
  dob_iso: string;
  address_text: string;
  address_line1: string;
  address_line2: string;
  address_line3: string;
  address_line4: string;
  address_postcode: string;
  work_address_line1: string;
  work_address_line2: string;
  work_address_line3: string;
  work_address_line4: string;
  work_address_postcode: string;
  phone_primary: string;
  email_primary: string;
}

export interface MatterPartiesResponse {
  matter_id: string;
  parties: MatterParty[];
}

export interface RowField {
  name: string;
  label: string;
  kind?: "text" | "date" | "select";

  options?: string[];
  group: "identity" | "name" | "address" | "contact";
}

export const PARTY_FIELDS: RowField[] = [
  { name: "role", label: "Role", group: "identity" },
  { name: "name_first", label: "First name", group: "name" },
  { name: "name_middle", label: "Middle name", group: "name" },
  { name: "name_last", label: "Last name", group: "name" },
  { name: "aka_name", label: "Alias", group: "identity" },
  { name: "dob_iso", label: "Date of birth", kind: "date", group: "identity" },
  { name: "address_line1", label: "Address line 1", group: "address" },
  { name: "address_line2", label: "Address line 2", group: "address" },
  { name: "address_line3", label: "Address line 3", group: "address" },
  { name: "address_line4", label: "Address line 4", group: "address" },
  { name: "address_postcode", label: "Postcode", group: "address" },
  { name: "work_address_line1", label: "Work address line 1", group: "address" },
  { name: "work_address_line2", label: "Work address line 2", group: "address" },
  { name: "work_address_line3", label: "Work address line 3", group: "address" },
  { name: "work_address_line4", label: "Work address line 4", group: "address" },
  { name: "work_address_postcode", label: "Work postcode", group: "address" },
  { name: "phone_primary", label: "Telephone", group: "contact" },
  { name: "email_primary", label: "Email", group: "contact" },
];

export const PARTY_FIELD_NAMES: string[] = PARTY_FIELDS.map((f) => f.name);

export interface MatterChild {
  child_id: string;
  matter_id: string;
  child_name: string;
  name_first: string;
  name_middle: string;
  name_last: string;
  dob_iso: string;
  gender: string;
  parental_responsibility: string;
  lives_with: string;
  notes: string;
}

export interface MatterChildrenResponse {
  matter_id: string;
  children: MatterChild[];
}

export const CHILD_PARTY_OPTIONS = ["Client", "Opponent", "Both", "Neither"];

export function normalisePr(value: string): string {
  const v = value.trim();
  if (!v) return "";
  if (/^(yes|y|pr|has pr|r has pr|respondent|respondent has pr|opponent has pr)$/i.test(v)) return "Both";
  return v;
}

export const CHILD_FIELDS: RowField[] = [
  { name: "name_first", label: "First name", group: "name" },
  { name: "name_middle", label: "Middle name", group: "name" },
  { name: "name_last", label: "Last name", group: "name" },
  { name: "dob_iso", label: "Date of birth", kind: "date", group: "identity" },
  { name: "gender", label: "Sex", kind: "select", options: ["Male", "Female"], group: "identity" },
  { name: "lives_with", label: "Lives with", kind: "select", options: CHILD_PARTY_OPTIONS, group: "identity" },
  { name: "parental_responsibility", label: "Parental responsibility", kind: "select", options: CHILD_PARTY_OPTIONS, group: "identity" },
];

export const CHILD_FIELD_NAMES: string[] = CHILD_FIELDS.map((f) => f.name);

export function splitName(full: string): { name_first: string; name_middle: string; name_last: string } {
  const words = full.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return { name_first: "", name_middle: "", name_last: "" };
  if (words.length === 1) return { name_first: words[0], name_middle: "", name_last: "" };
  return { name_first: words[0], name_middle: words.slice(1, -1).join(" "), name_last: words[words.length - 1] };
}

const UK_POSTCODE = /^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$/;

export function splitAddress(full: string): {
  address_line1: string; address_line2: string; address_line3: string; address_line4: string; address_postcode: string;
} {
  const parts = full.split(/,|\n/).map((p) => p.trim()).filter(Boolean);
  let postcode = "";
  if (parts.length > 0 && UK_POSTCODE.test(parts[parts.length - 1])) postcode = parts.pop() as string;
  const lines = parts.slice(0, 3).concat(parts.length > 3 ? [parts.slice(3).join(", ")] : []);
  return {
    address_line1: lines[0] ?? "", address_line2: lines[1] ?? "", address_line3: lines[2] ?? "",
    address_line4: lines[3] ?? "", address_postcode: postcode,
  };
}

export function addressLinesOfText(full: string | null | undefined): string[] {
  return (full ?? "").split(/,|\n/).map((p) => p.trim()).filter(Boolean);
}

const flatten = (v: string) => v.replace(/\s*,\s*/g, ", ").replace(/\s+/g, " ").trim();

export function reconcileParty<T extends Record<string, string>>(row: T): T {
  const out: Record<string, string> = { ...row };
  const composedName = ["name_first", "name_middle", "name_last"].map((k) => row[k] ?? "").filter(Boolean).join(" ");

  const flatName = (row.display_name ?? row.child_name ?? "").split(/\s+aka\s+/i)[0];
  if (flatName && flatten(flatName) !== flatten(composedName)) Object.assign(out, splitName(flatName));
  const composedAddress = ["address_line1", "address_line2", "address_line3", "address_line4", "address_postcode"]
    .map((k) => row[k] ?? "")
    .filter(Boolean)
    .join(", ");
  if (row.address_text && flatten(row.address_text) !== flatten(composedAddress)) Object.assign(out, splitAddress(row.address_text));
  return out as T;
}

export interface SosStatusItem {
  name: string;
  modified_utc: string;
  web_url: string;
  is_draft: boolean;
}

export interface SosStatusResponse {
  matter_id: string;
  count: number;
  draft_count: number;
  items: SosStatusItem[];
  folder_found: boolean;
}

export interface BillOfCostsItem {
  item_date: string;
  description: string;
  net_amount: string;
  vat_amount: string;

  document_url?: string | null;

  party?: string | null;

  schedule?: 1 | 2 | null;

  attendance_draft_id?: string | null;

  possible_double_bill?: boolean;
}

export interface BillOfCostsCategory {
  category: string;
  label: string;
  items: BillOfCostsItem[];
  subtotal_net: string;
  subtotal_vat: string;
}

export interface BillOfCostsPartyLine {
  label: string;
  count: number;
  net: string;
  vat: string;
}

export interface BillOfCostsParty {
  party: string;
  label: string;
  lines: BillOfCostsPartyLine[];
}

export interface BillOfCostsRate {
  category: string;
  label: string;
  rate: string;
  unit: string;
}

export interface BillOfCostsResponse {
  matter_id: string;
  client_name: string;
  categories: BillOfCostsCategory[];
  parties: BillOfCostsParty[];

  billing_basis?: "legal_aid" | "private";
  rates: BillOfCostsRate[];

  rate_tbc?: { item_id: string; item_date: string; description: string }[];
  total_net: string;
  total_vat: string;
  total_gross: string;
  item_count: number;

  removed?: BillOfCostsRemovedItem[];
}

export interface BillOfCostsRemovedItem {
  item_id: string;
  item_date: string;
  description: string;
  category_label: string;
  net_amount: string;
  vat_amount: string;
  removed_utc: string;
  removed_by: string;
}

export interface RestoreBillingItemResponse {
  item_id: string;
  on_bill: boolean;
  restored_utc: string;
  restored_by: string;
}

export interface ConcludedMattersResponse {
  results: ClientMatch[];
  total: number;
  next_offset: number | null;
}

export interface FlaggedMattersResponse {
  results: ClientMatch[];
  flags_by_matter: Record<string, string[]>;

  flag_reasons_by_matter?: Record<string, string>;
}

export interface EditableField {
  name: string;
  label: string;
  group: "Name" | "Identity" | "Contact & address" | "Case details" | "Notes";
  kind?: "text" | "boolean" | "textarea" | "ordertypes" | "date" | "select" | "courtrefs";

  options?: string[];
  extraKey?: string;
}

export const COURT_REFERENCE_BOXES = 5;

export const EDITABLE_FIELDS: EditableField[] = [
  { name: "name_first", label: "First name", group: "Name", extraKey: "name_first" },
  { name: "name_middle", label: "Middle name", group: "Name", extraKey: "name_middle" },
  { name: "name_last", label: "Last name", group: "Name", extraKey: "name_last" },
  { name: "dob_iso", label: "Date of birth", group: "Identity", kind: "date" },
  { name: "nino_canonical", label: "NI number", group: "Identity", extraKey: "nino_canonical" },
  { name: "phone_primary", label: "Telephone", group: "Contact & address" },
  { name: "email_primary", label: "Email", group: "Contact & address" },
  { name: "address_line1", label: "Address line 1", group: "Contact & address", extraKey: "client_address_line1" },
  { name: "address_line2", label: "Address line 2", group: "Contact & address", extraKey: "client_address_line2" },
  { name: "address_line3", label: "Address line 3", group: "Contact & address", extraKey: "client_address_line3" },
  { name: "address_line4", label: "Address line 4", group: "Contact & address", extraKey: "client_address_line4" },
  { name: "address_postcode", label: "Postcode", group: "Contact & address", extraKey: "client_address_postcode" },
  { name: "client_role", label: "Client role", group: "Case details", kind: "select", options: ["Applicant", "Respondent"] },
  { name: "company_reference", label: "Company reference", group: "Case details", extraKey: "company_reference" },

  { name: "order_type_tags", label: "Matter", group: "Case details", kind: "ordertypes", extraKey: "order_type_tags" },

  { name: "court_references", label: "Court reference(s)", group: "Case details", kind: "courtrefs" },
  { name: "concluded", label: "Concluded", group: "Case details", kind: "boolean" },

  { name: "tracker_notes", label: "Notes", group: "Notes", kind: "textarea", extraKey: "tracker_notes" },
];

export function editableFieldValue(match: ClientMatch, fieldName: string): string {
  if (fieldName === "phone_primary") return match.phone_primary ?? "";
  if (fieldName === "email_primary") return match.email_primary ?? "";
  if (fieldName === "dob_iso") return match.dob_iso ?? "";
  if (fieldName === "client_role") return match.client_role ?? "";
  if (fieldName === "court_references") return referenceGroupsOf(match).court.join("\n");
  if (fieldName === "order_requested_text") return match.order_requested_text ?? "";
  if (fieldName === "has_c8") return hasC8(match) ? "1" : "0";
  if (fieldName === "concluded") return match.closed_at ? "1" : "0";
  const entry = EDITABLE_FIELDS.find((f) => f.name === fieldName);
  if (entry?.extraKey) {
    const value = match.extra?.[entry.extraKey];
    return typeof value === "string" ? value : "";
  }
  return "";
}

export function applyFieldUpdate(match: ClientMatch, fieldName: string, newValue: string): ClientMatch {
  if (fieldName === "phone_primary") return { ...match, phone_primary: newValue };
  if (fieldName === "email_primary") return { ...match, email_primary: newValue };
  if (fieldName === "dob_iso") return { ...match, dob_iso: newValue };
  if (fieldName === "court_references") {
    const kept = (match.reference_summary ?? "")
      .split(" | ")
      .filter((segment) => segment.trim() && !COURT_REF_TYPES.has(segment.split(":")[0].trim()));
    const courtRefs = newValue.split("\n").map((v) => v.trim()).filter(Boolean).map((v) => `court_family:${v}`);
    return { ...match, reference_summary: [...kept, ...courtRefs].join(" | ") || null };
  }
  if (fieldName === "client_role") return { ...match, client_role: newValue };
  if (fieldName === "order_requested_text") return { ...match, order_requested_text: newValue };
  if (fieldName === "has_c8") {
    const on = newValue === "1";

    return { ...match, extra: { ...match.extra, has_c8: on, c8_phone: on, c8_email: on, c8_address: on } };
  }
  if ((C8_FIELDS as string[]).includes(fieldName)) {
    const extra = { ...match.extra, [fieldName]: newValue === "1" };

    extra.has_c8 = C8_FIELDS.some((f) => f === fieldName ? newValue === "1" : c8Of({ ...match, extra: match.extra }, f));
    return { ...match, extra };
  }
  if (fieldName === "concluded") {

    const on = newValue === "1";
    return {
      ...match,
      closed_at: on ? new Date().toISOString() : null,
      extra: { ...match.extra, closed_notes: on ? "" : "Reopened" },
    };
  }
  if (fieldName === "name_derived" || fieldName === "client_address_derived") {
    return { ...match, extra: { ...match.extra, [fieldName]: newValue } };
  }
  const entry = EDITABLE_FIELDS.find((f) => f.name === fieldName);
  if (entry?.extraKey) {
    return { ...match, extra: { ...match.extra, [entry.extraKey]: newValue } };
  }
  return match;
}

export const FLAG_FIELDS: { name: string; label: string }[] = [

  { name: "flagged", label: "Flagged" },
  { name: "starred", label: "Starred" },
  { name: "persistent_caller", label: "Frequent caller" },

  { name: "persistent_caller_respondent", label: "Frequent caller (Opponent)" },

  { name: "transferred", label: "Transferred" },
  { name: "dropped_out", label: "Dropped out" },

  { name: "private_billing", label: "Privately billed" },

  { name: "billed", label: "Billed" },
];

export const CATEGORY_PILL_FLAGS: { name: string; label: string }[] = [
  { name: "cat_nmo_cao", label: "NMO-CAO" },
  { name: "cat_care_proceedings", label: "CARE" },
  { name: "cat_immigration", label: "Immigration" },
  { name: "cat_divorce_financial", label: "Divorce" },
  { name: "cat_ila", label: "ILA" },
  { name: "cat_litigation", label: "Litigation" },
  { name: "cat_crime", label: "Crime" },
  { name: "cat_housing", label: "Housing" },
  { name: "cat_probate", label: "Probate" },
  { name: "cat_employment", label: "Employment" },

  { name: "ncf_nmo", label: "NMO" },
  { name: "ncf_occupation", label: "OO" },
  { name: "ncf_cao", label: "CAO" },
  { name: "ncf_pso_sio", label: "PSO / SIO" },
  { name: "ncf_divorce", label: "Divorce" },
  { name: "ncf_employment", label: "Employment" },
  { name: "ncf_pi_cn", label: "PI / CN" },

  { name: "src_private", label: "Private" },
];

export const ALWAYS_SHOWN_CATEGORY_PILLS: ReadonlySet<string> = new Set(["cat_care_proceedings"]);

export function pillFlagsToShow(flags: Record<string, boolean> | undefined, hasOrderTags: boolean): PillFlag[] {
  const category = new Set(CATEGORY_PILL_FLAGS.map((f) => f.name).filter((name) => !ALWAYS_SHOWN_CATEGORY_PILLS.has(name)));
  return PILL_FLAGS.filter((flag) => flags?.[flag.name] && !(hasOrderTags && category.has(flag.name)));
}

export const PORTAL_URL =
  "https://hmcts-access.service.gov.uk/login?client_id=xuiwebapp&redirect_uri=https://manage-case.platform.hmcts.net/oauth2/callback";

export const PORTAL_FLAG = "portal";

export type PillFlag = { name: string; label: string;   href?: string };

export const PILL_FLAGS: PillFlag[] = [
  { name: "transferred", label: "Transferred" },
  { name: "dropped_out", label: "Dropped out" },
  { name: "private_billing", label: "Privately billed" },
  { name: "billed", label: "Billed" },
  { name: PORTAL_FLAG, label: "PORTAL", href: PORTAL_URL },
  ...CATEGORY_PILL_FLAGS,
];

function extraString(match: ClientMatch, key: string): string | null {
  const value = match.extra?.[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export function nameFirstOf(match: ClientMatch): string | null {
  return extraString(match, "name_first");
}

export function nameMiddleOf(match: ClientMatch): string | null {
  return extraString(match, "name_middle");
}

export function nameLastOf(match: ClientMatch): string | null {
  return extraString(match, "name_last");
}

export function sentenceCaseName(name: string): string {
  return name
    .split(" ")
    .map((word) => {
      if (!word) return word;
      const hasOwnCapitalisation = word !== word.toUpperCase() && word !== word.toLowerCase();
      if (hasOwnCapitalisation) return word;
      return word.replace(/[^-'\s]+/g, (piece) => piece.charAt(0).toUpperCase() + piece.slice(1).toLowerCase());
    })
    .join(" ");
}

export function shortNameOf(match: ClientMatch): string {
  const first = nameFirstOf(match);
  const last = nameLastOf(match);
  if (first && last) return sentenceCaseName(`${first} ${last}`);
  return match.client_name ? sentenceCaseName(match.client_name) : "(no name on record)";
}

export function fullNameOf(match: ClientMatch): string {
  return shortNameOf(match);
}

export function clientAddressLinesOf(match: ClientMatch): string[] {
  const keys = ["client_address_line1", "client_address_line2", "client_address_line3", "client_address_line4"];
  const lines = keys.map((key) => extraString(match, key)).filter((line): line is string => Boolean(line));
  const postcode = extraString(match, "client_address_postcode");
  if (postcode) lines.push(postcode);
  return lines;
}

export function ninoOf(match: ClientMatch): string | null {
  const value = match.extra?.["nino_canonical"];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export function dateJoinedOf(match: ClientMatch): string | null {
  const referral = extraString(match, "referral_sent_at");
  if (referral) return formatDateForDisplay(referral);
  const sourceEmail = extraString(match, "source_email_sent_at");
  return sourceEmail ? formatDateForDisplay(sourceEmail) : null;
}

export function childrenOf(match: ClientMatch, today: Date = new Date()): string | null {
  const value = match.extra?.["children_summary"];
  return typeof value === "string" && value.trim().length > 0 ? withLiveAges(value, today) : null;
}

export function ageOn(dobIso: string, today: Date = new Date()): number | null {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dobIso);
  if (!parts) return null;
  const [year, month, day] = [Number(parts[1]), Number(parts[2]), Number(parts[3])];
  const born = new Date(Date.UTC(year, month - 1, day));
  if (born.getUTCFullYear() !== year || born.getUTCMonth() !== month - 1 || born.getUTCDate() !== day) return null;
  const nowY = today.getFullYear();
  const nowM = today.getMonth() + 1;
  const nowD = today.getDate();
  if (year > nowY || (year === nowY && (month > nowM || (month === nowM && day > nowD)))) return null;
  return nowY - year - (nowM < month || (nowM === month && nowD < day) ? 1 : 0);
}

export function withLiveAges(summary: string, today: Date = new Date()): string {
  return summary.replace(/\((\d{4}-\d{2}-\d{2})(?:,\s*age\s+\d+)?\)/g, (_all, dob: string) => {
    const age = ageOn(dob, today);
    return age === null ? `(${dob})` : `(${dob}, age ${age})`;
  });
}

export function propertyOf(match: ClientMatch): string | null {
  const value = match.extra?.["property_summary"];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export function benefitsOf(match: ClientMatch): string | null {
  const value = match.extra?.["benefits_canonical"];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export function hasC8(match: ClientMatch): boolean {
  const value = match.extra?.["has_c8"];
  return value === true || value === 1 || value === "1";
}

export type C8Field = "c8_phone" | "c8_email" | "c8_address";
export const C8_FIELDS: C8Field[] = ["c8_phone", "c8_email", "c8_address"];

export function c8Of(match: ClientMatch, field: C8Field): boolean {
  const value = match.extra?.[field];
  if (value === null || value === undefined) return hasC8(match);
  return value === true || value === 1 || value === "1";
}

export const ORDER_TYPE_LABELS: Record<string, string> = {
  NMO: "Non-Molestation Order",
  OO: "Occupation Order",
  CAO: "Child Arrangements Order",
  PSO: "Prohibited Steps Order",
  SIO: "Specific Issue Order",
};
const ORDER_TYPE_CODES = Object.keys(ORDER_TYPE_LABELS);

export function orderTypeTagsOf(match: ClientMatch): string[] {
  const raw = extraString(match, "order_type_tags");
  if (!raw) return [];
  const found = new Set(raw.split(",").map((v) => v.trim()).filter((v) => ORDER_TYPE_CODES.includes(v)));
  return ORDER_TYPE_CODES.filter((code) => found.has(code));
}

export function orderTypesText(codes: string[]): string {
  const names = ORDER_TYPE_CODES.filter((c) => codes.includes(c)).map((c) => ORDER_TYPE_LABELS[c]);
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function notesOf(match: ClientMatch): string | null {
  return extraString(match, "tracker_notes");
}

export function nextHearingOf(match: ClientMatch): string | null {
  return extraString(match, "next_hearing_text");
}

export function isConcludedFolder(match: ClientMatch): boolean {
  const folder = match.live_matter_folder || "";
  return /concluded/i.test(folder);
}

export function isDeleteLaterFolder(match: ClientMatch): boolean {
  return /delete[\s_-]*later/i.test(match.live_matter_folder || "");
}

export function formatDateForDisplay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function concludedStatus(
  match: ClientMatch
): { label: string; source: "closed_at" | "folder" } | null {
  const closedAt = (match.closed_at || "").trim();
  if (closedAt) return { label: formatDateForDisplay(closedAt), source: "closed_at" };

  if (wasReopened(match)) return null;
  if (isConcludedFolder(match)) return { label: "Concluded", source: "folder" };
  return null;
}

export function wasReopened(match: ClientMatch): boolean {
  if ((match.closed_at || "").trim()) return false;
  const notes = match.extra?.closed_notes;
  return typeof notes === "string" && notes.trim() !== "";
}

export interface AddressBlock {
  heading: string;
  lines: string[];
}

function dropTrailingUkLine(lines: string[]): string[] {
  if (lines.length > 0 && lines[lines.length - 1] === "UK") {
    return lines.slice(0, -1);
  }
  return lines;
}

export function addressBlocks(match: ClientMatch): AddressBlock[] {
  const raw = match.address_summary;
  if (!raw) return [];
  return raw
    .split(" | ")
    .map((segment) => {
      const trimmed = segment.trim();
      const colonAt = trimmed.indexOf(": ");
      const rawHeading = colonAt >= 0 ? trimmed.slice(0, colonAt) : "";

      const heading = rawHeading
        ? rawHeading.charAt(0).toUpperCase() + rawHeading.slice(1)
        : "";
      const rest = colonAt >= 0 ? trimmed.slice(colonAt + 2) : trimmed;
      const lines = dropTrailingUkLine(
        rest
          .split(",")
          .map((line) => line.trim())
          .filter(Boolean)
      );
      return { heading, lines };
    })
    .filter((block) => block.lines.length > 0);
}

export function partyDobBlocks(match: ClientMatch): PartyBlock[] {
  const raw = extraString(match, "party_dob_summary");
  if (!raw) return [];
  return raw
    .split(" | ")
    .map((segment) => {
      const trimmed = segment.trim();
      const colonAt = trimmed.indexOf(": ");
      const rawRole = colonAt >= 0 ? trimmed.slice(0, colonAt) : "";
      const role = rawRole ? rawRole.charAt(0).toUpperCase() + rawRole.slice(1) : "Party";
      const name = (colonAt >= 0 ? trimmed.slice(colonAt + 2) : trimmed).trim();
      return { role, name };
    })
    .filter((block) => block.name.length > 0);
}

export interface ReferenceGroups {
  court: string[];
  company: string[];
  legalAid: string[];
  other: string[];
}

const COURT_REF_TYPES = new Set(["court_family", "court_children", "court_ref"]);
const COMPANY_REF_TYPES = new Set(["company_ref", "company"]);
const LEGAL_AID_REF_TYPES = new Set(["ccms_ref", "laa_case_ref"]);

const COURT_NAME_REF_TYPE = "court";
const COURT_EMAIL_REF_TYPE = "court_email";

export interface CourtDetails {
  name: string | null;
  email: string | null;
}

export function courtDetailsOf(match: ClientMatch): CourtDetails {
  const details: CourtDetails = { name: null, email: null };
  for (const segment of (match.reference_summary ?? "").split(" | ")) {
    const trimmed = segment.trim();
    const colonAt = trimmed.indexOf(":");
    if (colonAt < 0) continue;
    const refType = trimmed.slice(0, colonAt).trim();
    const value = trimmed.slice(colonAt + 1).trim();
    if (!value) continue;
    if (refType === COURT_NAME_REF_TYPE && details.name === null) details.name = value;
    else if (refType === COURT_EMAIL_REF_TYPE && details.email === null) details.email = value;
  }
  return details;
}

export function referenceGroupsOf(match: ClientMatch): ReferenceGroups {
  const groups: ReferenceGroups = { court: [], company: [], legalAid: [], other: [] };
  const raw = match.reference_summary;
  if (!raw) {
    if (match.case_reference) groups.other.push(match.case_reference);
  } else {
    for (const segment of raw.split(" | ")) {
      const trimmed = segment.trim();
      const colonAt = trimmed.indexOf(":");
      const refType = colonAt >= 0 ? trimmed.slice(0, colonAt).trim() : "";
      const value = (colonAt >= 0 ? trimmed.slice(colonAt + 1) : trimmed).trim();
      if (!value) continue;
      if (COURT_REF_TYPES.has(refType)) groups.court.push(value);
      else if (COMPANY_REF_TYPES.has(refType)) groups.company.push(value);
      else if (LEGAL_AID_REF_TYPES.has(refType)) groups.legalAid.push(value);
      else if (refType === COURT_NAME_REF_TYPE || refType === COURT_EMAIL_REF_TYPE) continue;
      else groups.other.push(value);
    }
  }

  const columnCompanyRef = extraString(match, "company_reference");
  if (columnCompanyRef) groups.company = [columnCompanyRef];
  return groups;
}

export interface PartyBlock {
  role: string;
  name: string;
}

export function partyBlocks(match: ClientMatch): PartyBlock[] {
  const raw = match.party_summary;
  if (!raw) return [];
  return raw
    .split(" | ")
    .map((segment) => {
      const trimmed = segment.trim();
      const colonAt = trimmed.indexOf(": ");
      const rawRole = colonAt >= 0 ? trimmed.slice(0, colonAt) : "";
      const role = rawRole ? rawRole.charAt(0).toUpperCase() + rawRole.slice(1) : "Party";
      const name = (colonAt >= 0 ? trimmed.slice(colonAt + 2) : trimmed).trim();
      return { role, name };
    })
    .filter((block) => block.name.length > 0);
}

export function matchedViaOf(match: ClientMatch): string | null {
  const value = (match.matched_party_summary || "").trim();
  if (!value) return null;
  return value === (match.client_name || "").trim() ? null : value;
}

export function matchKey(match: ClientMatch, index: number): string {
  return match.matter_id != null ? String(match.matter_id) : `row-${index}`;
}

export interface MatterTaskItem {
  task_id: string;
  kind: string;
  complaint_domain: string;
  settlement_stage: string;
  subject: string;
  summary: string;
  deadline: string;
  importance: string;
  status: string;
  created: string;
  web_link: string;
}

export interface MatterTasksResponse {
  matter_id: string;
  configured: boolean;
  open_complaints: number;
  open_updates: number;
  open_settlements: number;
  items: MatterTaskItem[];
}

export type MatterMarkerStatus = "received" | "missing" | "pending" | "unsearchable" | "unknown";

export interface MatterMarker {
  status: MatterMarkerStatus;

  reason?: string;
  date: string;

  url?: string;
}

export interface MatterMarkersResponse {
  matter_id: string;
  loa: MatterMarker;
  initial_ws: MatterMarker;

  intro?: MatterMarker;
}

export interface AttentionItem extends SameNameFields {
  task_id: string;
  matter_id: string;
  who: string;
  kind: string;
  label: string;
  complaint_domain: string;

  severity?: string;
  settlement_stage: string;
  subject: string;
  summary: string;
  deadline: string;
  importance: string;
  created: string;
  web_link: string;

  sender_domain?: string;

  can_complete?: boolean;
}

export interface AttentionObligation extends SameNameFields {
  matter_id: string | number | null;
  client: string;
  label: string;
  urgency: string;
  reason: string;
  hearing_date: string;
  age_working_days: number | null;
}

export interface AttentionResponse {
  configured: boolean;
  red_count: number;
  yellow_count: number;
  green_count: number;
  red: AttentionItem[];
  yellow: AttentionItem[];
  green: AttentionItem[];

  scope_creep_count?: number;
  scope_creep?: AttentionItem[];
  counsel_accepted_count?: number;
  counsel_accepted?: AttentionItem[];
  counsel_rejected_count?: number;
  counsel_rejected?: AttentionItem[];

  court_order_count?: number;
  court_order?: AttentionItem[];
  court_rejected_count?: number;
  court_rejected?: AttentionItem[];
  obligations_count?: number;
  obligations?: AttentionObligation[];
  obligations_error?: string;
}

export const ATTENDANCE_CALLERS = ["client", "counsel", "court", "respondent", "other"] as const;
export type AttendanceCaller = (typeof ATTENDANCE_CALLERS)[number];

export const ATTENDANCE_CALLER_LABELS: Record<AttendanceCaller, string> = {
  court: "Court",
  counsel: "Counsel",
  client: "Client",
  respondent: "Opponent",
  other: "Other",
};

export const ATTENDANCE_KINDS = ["call", "perusal", "preparation", "letter_out", "letter_in", "bundle"] as const;
export type AttendanceNoteKind = (typeof ATTENDANCE_KINDS)[number];

export const ATTENDANCE_KIND_LABELS: Record<AttendanceNoteKind, string> = {
  call: "Attendance",
  perusal: "Perusal",
  preparation: "Preparation",
  letter_out: "Letter out (earlier note)",
  letter_in: "Letter in (earlier note)",
  bundle: "Bundle (earlier note)",
};

export const ATTENDANCE_CREATE_KINDS = ["call", "perusal", "preparation"] as const;

export function isAttendanceCreateKind(value: unknown): value is (typeof ATTENDANCE_CREATE_KINDS)[number] {
  return typeof value === "string" && (ATTENDANCE_CREATE_KINDS as readonly string[]).includes(value);
}

export function takesPages(kind: AttendanceNoteKind): boolean {
  return kind === "perusal" || kind === "preparation";
}

export const DEFAULT_MINUTES_PER_PAGE = 2;

export const MAX_TIME_MINUTES = 5999;

export const ATTENDANCE_WHO_LEGEND = "Party";

export const ATTENDANCE_NOTE_PLACEHOLDER: Record<AttendanceNoteKind, string> = {
  call: "What was said, advice given, what was agreed",
  perusal: "What was perused",
  preparation: "What was prepared",
  letter_out: "What the letter was about",
  letter_in: "What the letter was about",
  bundle: "What was prepared, and for which hearing",
};

export function currentKind(kind: AttendanceNoteKind): AttendanceNoteKind {
  return kind === "letter_in" ? "perusal" : kind === "letter_out" ? "preparation" : kind;
}

export function isAttendanceKind(value: unknown): value is AttendanceNoteKind {
  return typeof value === "string" && (ATTENDANCE_KINDS as readonly string[]).includes(value);
}

export function filedLabel(item: Pick<AttendanceNoteStatus, "billing_removed" | "billing_note" | "bundle_pages">): string {
  if (item.billing_removed) return "Filed. Taken off the bill.";
  if (item.billing_note) return "Filed, not billed.";
  if (typeof item.bundle_pages === "number") {
    return `Filed and billed: ${item.bundle_pages} page${item.bundle_pages === 1 ? "" : "s"}.`;
  }
  return "Filed and billed.";
}

export interface AttendanceNoteCreateResponse {
  draft_id: string;
  matter_id: string;
  status: string;
}

export type AttendanceNoteState = "filing" | "filed" | "failed";

export interface AttendanceNoteStatus {
  draft_id: string;
  matter_id: string;
  state: AttendanceNoteState;
  an_url: string | null;

  unsorted?: boolean;

  filed_folder?: string;
  billing_item_id: string | null;

  billing_removed: boolean;

  error: string | null;
  created_utc: string;

  kind?: AttendanceNoteKind;

  bundle_pages?: number | null;

  billing_note?: string;
}

export interface FrequentCallersResponse {
  results: ClientMatch[];
  an_counts: Record<string, number>;
  pinned_matters: string[];
}
