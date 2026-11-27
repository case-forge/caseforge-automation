
export interface SameNameFields {
  same_name_index?: number | null;
  same_name_count?: number | null;

  same_name_birth_year?: number | null;

  same_name_ref?: string | null;
}

const ROMAN: [number, string][] = [
  [1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"],
  [50, "l"], [40, "xl"], [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"],
];

export function romanNumeral(n: number): string {
  if (!Number.isInteger(n) || n < 1 || n > 3999) return "";
  let left = n;
  let out = "";
  for (const [value, letters] of ROMAN) {
    while (left >= value) {
      out += letters;
      left -= value;
    }
  }
  return out;
}

export function hasNamesake(row: SameNameFields | null | undefined): boolean {
  const count = Number(row?.same_name_count ?? 0);
  const index = Number(row?.same_name_index ?? 0);
  return count >= 2 && index >= 1 && index <= count;
}

export function sameNameSuffix(row: SameNameFields | null | undefined): string {
  return hasNamesake(row) ? `(${romanNumeral(Number(row?.same_name_index))})` : "";
}

export function nameWithSuffix(name: string, row: SameNameFields | null | undefined): string {
  const suffix = sameNameSuffix(row);
  return suffix ? `${name} ${suffix}` : name;
}

function birthYearOf(row: SameNameFields & { dob_iso?: string | null }): number | null {
  if (row.same_name_birth_year) return row.same_name_birth_year;
  const dob = String(row.dob_iso ?? "").trim();
  return /^\d{4}/.test(dob) ? Number(dob.slice(0, 4)) : null;
}

export function sameNameHint(
  row: (SameNameFields & { dob_iso?: string | null; company_reference?: string | null }) | null | undefined,
): string {
  if (!row || !hasNamesake(row)) return "";
  const year = birthYearOf(row);
  const ref = String(row.same_name_ref ?? row.company_reference ?? "").trim();
  const parts = [year ? `Born ${year}` : "", ref ? `Ref ${ref}` : ""].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No birth year or reference on record";
}

export function sameNameTitle(row: SameNameFields | null | undefined): string {
  if (!hasNamesake(row)) return "";
  return `${Number(row?.same_name_count)} different clients have this name. (i) is the one whose first case was opened first. A label only: it never decides who a client is.`;
}

export function companyReferenceOf(extra: Record<string, unknown> | undefined): string | null {
  const value = extra?.["company_reference"];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
