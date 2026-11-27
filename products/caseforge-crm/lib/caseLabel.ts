
import type { ClientMatch } from "./types";
import { ORDER_TYPE_LABELS, orderTypeTagsOf, referenceGroupsOf } from "./types";
import { normaliseOrderText } from "./orderText";
import { companyReferenceOf } from "./sameName";

function extraText(match: ClientMatch, key: string): string {
  const value = match.extra?.[key];
  return value == null ? "" : String(value).trim();
}

export function personKeyOf(match: ClientMatch): string {
  const personId = extraText(match, "primary_person_id");
  if (personId) return `id:${personId}`;
  const name = String(match.client_name ?? "").trim().toLowerCase().replace(/\s+/g, " ");
  if (!name) return "";
  return `name:${name}|${match.same_name_index ?? ""}|${String(match.dob_iso ?? "").trim()}`;
}

export function openedDateText(value: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!m) return "";
  const date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  if (Number.isNaN(date.getTime()) || date.getUTCDate() !== Number(m[3])) return "";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function orderTypeText(match: ClientMatch): string {
  const text = normaliseOrderText(match.order_requested_text).trim();
  if (text) return text;
  const tags = orderTypeTagsOf(match);
  return tags.map((code) => ORDER_TYPE_LABELS[code]).join(" and ");
}

export function caseDescriptor(match: ClientMatch): string {
  const order = orderTypeText(match);
  const opened = openedDateText(extraText(match, "created_utc"));
  const parts = [order, opened ? `Opened ${opened}` : ""].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  const refs = referenceGroupsOf(match);
  const ref = refs.court[0] || refs.company[0] || companyReferenceOf(match.extra) || "";
  if (ref) return `Ref ${ref}`;
  return match.matter_id != null && String(match.matter_id).trim() ? `Matter ${match.matter_id}` : "";
}

function matterNumber(match: ClientMatch): number {
  const n = Number(match.matter_id);
  return Number.isFinite(n) ? n : Number.MAX_SAFE_INTEGER;
}

export function caseLabelsFor(results: ClientMatch[]): Map<string, string> {
  const groups = new Map<string, ClientMatch[]>();
  const seen = new Set<string>();
  for (const match of results) {
    const id = match.matter_id != null ? String(match.matter_id).trim() : "";
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const key = personKeyOf(match);
    if (!key) continue;
    const group = groups.get(key) ?? [];
    group.push(match);
    groups.set(key, group);
  }
  const labels = new Map<string, string>();
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const ordered = [...group].sort((a, b) => {
      const da = extraText(a, "created_utc");
      const db = extraText(b, "created_utc");

      if (da !== db) return !da ? 1 : !db ? -1 : da < db ? -1 : 1;
      return matterNumber(a) - matterNumber(b) || String(a.matter_id).localeCompare(String(b.matter_id));
    });
    ordered.forEach((match, i) => {
      const descriptor = caseDescriptor(match);
      const head = `Case ${i + 1} of ${ordered.length}`;
      labels.set(String(match.matter_id).trim(), descriptor ? `${head} · ${descriptor}` : head);
    });
  }
  return labels;
}
