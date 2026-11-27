
import { sameNameHint, sameNameSuffix, sameNameTitle } from "@/lib/sameName";
import type { SameNameFields } from "@/lib/sameName";

type Row = SameNameFields & { dob_iso?: string | null; company_reference?: string | null };

export function SameNameSuffix({ row }: { row: Row | null | undefined }) {
  const suffix = sameNameSuffix(row);
  if (!suffix) return null;
  return (
    <span className="same-name-index" title={sameNameTitle(row)}>
      {suffix}
    </span>
  );
}

export function SameNameHint({ row, as: Tag = "p", className = "" }: { row: Row | null | undefined; as?: "p" | "span"; className?: string }) {
  const hint = sameNameHint(row);
  if (!hint) return null;
  return <Tag className={`same-name-hint ${className}`.trim()}>{hint}</Tag>;
}
