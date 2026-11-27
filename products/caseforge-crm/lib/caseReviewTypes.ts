
export type CaseReviewKind = "ynna" | "yn" | "choice" | "text" | "longtext" | "date" | "signoff";
export type CaseReviewFormKey = "review" | "summary";

export interface CaseReviewRow {
  key: string;
  label: string;
  kind: CaseReviewKind;

  group?: string;
  options?: [string, string][];

  na?: boolean;

  optional?: boolean;
}

export interface CaseReviewSection {
  key: string;
  title: string;

  person_only?: boolean;
  rows: CaseReviewRow[];
}

export interface CaseReviewForm {
  key: CaseReviewFormKey;
  title: string;
  note: string;
  sections: CaseReviewSection[];
}

export interface CaseReviewAnswer {

  value: string;

  text: string;

  initials: string;
  date: string;

  source: string;
}

export interface CaseReviewCounts {
  total: number;
  answered: number;
  unanswered: number;
}

export interface CaseReviewVersion {
  review_date: string;
  saved_by: string;
  saved_utc: string;
  counts: Record<string, CaseReviewCounts>;
}

export interface CaseReview {
  matter_id: string;

  review_date: string;
  today: string;
  saved: boolean;
  saved_by: string;
  saved_utc: string;
  first_saved_by: string;
  first_saved_utc: string;
  forms: CaseReviewForm[];
  answers: Record<string, CaseReviewAnswer>;

  notes: Record<string, string>;
  counts: Record<string, CaseReviewCounts>;

  versions: CaseReviewVersion[];
}

export const BLANK_ANSWER: CaseReviewAnswer = { value: "", text: "", initials: "", date: "", source: "" };

const PRESETS: Partial<Record<CaseReviewKind, [string, string][]>> = {
  ynna: [["yes", "Yes"], ["no", "No"], ["na", "N/A"]],
  yn: [["yes", "Yes"], ["no", "No"]],
};

export function optionsOf(row: CaseReviewRow): [string, string][] {
  const preset = PRESETS[row.kind];
  if (preset) return preset;
  const own = row.options ?? [];
  return row.kind === "signoff" && row.na !== false ? [...own, ["na", "N/A"]] : own;
}

export function isAnswered(row: CaseReviewRow, answer: CaseReviewAnswer | undefined): boolean {
  const a = answer ?? BLANK_ANSWER;
  if (row.kind === "text" || row.kind === "longtext" || row.kind === "date") return a.text.trim() !== "";
  if (row.kind === "signoff") {
    if (a.value === "na" && row.na !== false) return true;
    const chosen = a.value !== "" || (row.options ?? []).length === 0;
    return chosen && a.initials.trim() !== "" && a.date !== "";
  }
  return a.value !== "";
}

export function countsOf(form: CaseReviewForm, answers: Record<string, CaseReviewAnswer>): CaseReviewCounts {
  const counts: CaseReviewCounts = { total: 0, answered: 0, unanswered: 0 };
  for (const section of form.sections) {
    for (const row of section.rows) {
      if (row.optional) continue;
      counts.total += 1;
      if (isAnswered(row, answers[row.key])) counts.answered += 1;
      else counts.unanswered += 1;
    }
  }
  return counts;
}

export function countLine(counts: CaseReviewCounts): string {
  if (counts.unanswered === 0) return `All ${counts.total} rows answered.`;
  return `${counts.answered} of ${counts.total} answered, ${counts.unanswered} still to answer.`;
}

export function sameAnswer(a: CaseReviewAnswer | undefined, b: CaseReviewAnswer | undefined): boolean {
  const x = a ?? BLANK_ANSWER;
  const y = b ?? BLANK_ANSWER;
  return x.value === y.value && x.text === y.text && x.initials === y.initials && x.date === y.date;
}

export function isBlank(a: CaseReviewAnswer | undefined): boolean {
  return sameAnswer(a, BLANK_ANSWER);
}

export function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

export function savedLine(caseReview: Pick<CaseReview, "review_date" | "saved" | "saved_by" | "saved_utc">): string {
  const which = `Review of ${longDate(caseReview.review_date)}`;
  if (!caseReview.saved) return `${which}: not saved yet.`;
  return `${which}: saved by ${caseReview.saved_by} on ${longDate(caseReview.saved_utc)}.`;
}
