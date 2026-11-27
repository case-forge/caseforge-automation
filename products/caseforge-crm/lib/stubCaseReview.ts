
import formsFile from "./caseReviewForms.json";
import { BLANK_ANSWER, countsOf, isBlank, longDate, optionsOf, sameAnswer } from "./caseReviewTypes";
import type { CaseReview, CaseReviewAnswer, CaseReviewCounts, CaseReviewForm, CaseReviewRow } from "./caseReviewTypes";

export const STUB_CASE_REVIEW_FORMS = (formsFile as unknown as { forms: CaseReviewForm[] }).forms;
export const STUB_CASE_REVIEW_TODAY = "2026-10-12";

interface Facts {
  name: string;
  reference: string;
  order: string;
  opened: string;
  referralpartner?: boolean;
  opening?: string;
  closing?: string;
  hearings?: [string, string][];
}

const FACTS: Record<string, Facts> = {
  "9001": { name: "Stub Testperson", reference: "261001/01FL", order: "Non-Molestation Order", opened: "2026-10-01" },
  "9002": {
    name: "Second Stubperson",
    reference: "260914/02FL",
    order: "Prohibited Steps Order",
    opened: "2026-09-14",
    referralpartner: true,
    opening: "2026-09-22",
    hearings: [["2026-10-06", "First hearing, Anytown Family Court"]],
  },
  "9003": {
    name: "Third Stubperson",
    reference: "260601/03FL",
    order: "Non-Molestation Order",
    opened: "2026-06-01",
    referralpartner: true,
    opening: "2026-06-09",
    closing: "2026-09-30",
    hearings: [
      ["2026-06-20", "Return hearing, Anytown Family Court"],
      ["2026-09-15", "Final hearing, Anytown Family Court"],
    ],
  },
};

interface Stored {
  answers: Record<string, CaseReviewAnswer>;
  saved_by: string;
  saved_utc: string;
  first_saved_by: string;
  first_saved_utc: string;
}

const rows = (): CaseReviewRow[] => STUB_CASE_REVIEW_FORMS.flatMap((f) => f.sections.flatMap((s) => s.rows));
const summaryRows = (): CaseReviewRow[] => STUB_CASE_REVIEW_FORMS.filter((f) => f.key === "summary").flatMap((f) => f.sections.flatMap((s) => s.rows));
const factsFor = (matterId: string): Facts => FACTS[matterId] ?? { ...FACTS["9001"], name: "Stub Person", reference: "" };

function prefill(matterId: string): { answers: Record<string, CaseReviewAnswer>; notes: Record<string, string> } {
  const f = factsFor(matterId);
  const answers: Record<string, CaseReviewAnswer> = {};
  const fill = (key: string, source: string, fields: Partial<CaseReviewAnswer>) => {
    if (Object.values(fields).some((v) => v)) answers[key] = { ...BLANK_ANSWER, ...fields, source };
  };
  fill("r_client_name", "The client's name on the matter record.", { text: f.name });
  fill("s_client_name", "The client's name on the matter record.", { text: f.name });
  fill("r_file_reference", "The firm's reference on the matter record.", { text: f.reference });
  fill("s_matter_number", "The firm's reference on the matter record.", { text: f.reference });
  fill("r_matter_type", "The order sought on the matter record.", { text: f.order });
  fill("s_summary", "The order sought on the matter record. Add the rest of the summary by hand.", { text: `Order sought: ${f.order}` });
  fill("r_date_opened", "The date the matter record was created on the system. Check it against the file.", { text: f.opened });
  if (f.referralpartner) fill("s_source", "The referral source on the matter record.", { text: "referrer referral" });
  if (f.opening) {
    fill("s_ccl_sent", "Lexcel record: the date the opening client care letter was made, as a draft. The date it was sent is not recorded: check it, then initial.", {
      date: f.opening,
    });
  }
  const held = f.hearings ?? [];
  fill("s_key_dates", "The hearings on the hearing calendar.", { text: held.map(([day, what]) => `${longDate(day)}: ${what}`).join("\n") });
  fill("s_status", "Hearings on the hearing calendar whose date has passed. Check each one took place.", {
    text: held.filter(([day]) => day < STUB_CASE_REVIEW_TODAY).map(([day, what]) => `${what}: ${longDate(day)}`).join("\n"),
  });
  const letter = (day: string | undefined, name: string) =>
    day
      ? `Lexcel record: ${name} made on ${longDate(day)}, as a draft. The date it was sent is not recorded.`
      : `Lexcel record: no ${name} is recorded as made by the system (one made by hand is not recorded).`;
  return {
    answers,
    notes: {
      "Initial Client Care Letter & Terms of Business": letter(f.opening, "opening client care letter"),
      "End of Case Client Care Letter": letter(f.closing, "closing letter"),

      ...(f.hearings ? { "Key Dates": `Hearing calendar: ${held.length} hearing${held.length === 1 ? "" : "s"} recorded for this matter.` } : {}),
    },
  };
}

function seeded(row: CaseReviewRow): CaseReviewAnswer {
  if (row.kind === "date") return { ...BLANK_ANSWER, text: "2026-10-08" };
  if (row.kind === "text") return { ...BLANK_ANSWER, text: row.key.includes("reviewer") || row.key.includes("checked_by") || row.key.includes("fee_earner") ? "Stub Reviewer" : "Recorded on the file" };
  if (row.kind === "longtext") return { ...BLANK_ANSWER, text: row.key === "r_corrective_action" ? "None" : "Reviewed against the file." };
  if (row.kind === "signoff") return { ...BLANK_ANSWER, value: row.options?.[0]?.[0] ?? "", initials: "SR", date: "2026-10-08" };
  return { ...BLANK_ANSWER, value: optionsOf(row)[0][0] };
}

const reviews = new Map<string, Map<string, Stored>>();

function reviewsFor(matterId: string): Map<string, Stored> {
  let r = reviews.get(matterId);
  if (!r) {
    r = new Map();
    const filled = prefill(matterId).answers;
    const stored = (answers: Record<string, CaseReviewAnswer>, day: string): Stored => ({
      answers,
      saved_by: "Stub Reviewer",
      saved_utc: `${day}T10:00:00Z`,
      first_saved_by: "Stub Reviewer",
      first_saved_utc: `${day}T10:00:00Z`,
    });
    if (matterId === "9002") {
      const some = Object.fromEntries(rows().slice(8, 20).map((row) => [row.key, seeded(row)]));
      r.set("2026-10-05", stored({ ...filled, ...some }, "2026-10-05"));
    }
    if (matterId === "9003") {
      const early = Object.fromEntries(rows().slice(8, 30).map((row) => [row.key, { ...seeded(row), value: "no" }]));
      r.set("2026-07-01", stored({ ...filled, ...early }, "2026-07-01"));
      const all = Object.fromEntries(rows().filter((row) => !row.optional).map((row) => [row.key, filled[row.key] && row.kind !== "signoff" ? filled[row.key] : seeded(row)]));
      r.set("2026-10-08", stored(all, "2026-10-08"));
    }
    reviews.set(matterId, r);
  }
  return r;
}

function countsFor(answers: Record<string, CaseReviewAnswer>): Record<string, CaseReviewCounts> {
  return Object.fromEntries(STUB_CASE_REVIEW_FORMS.map((form) => [form.key, countsOf(form, answers)]));
}

const newestFirst = (r: Map<string, Stored>): string[] => [...r.keys()].sort().reverse();

function draft(matterId: string, except = ""): Record<string, CaseReviewAnswer> {
  const r = reviewsFor(matterId);
  const answers = { ...prefill(matterId).answers };
  const earlier = newestFirst(r).find((day) => day !== except);
  if (earlier) {
    for (const row of summaryRows()) {
      const before = r.get(earlier)!.answers[row.key];
      if (before && !isBlank(before) && !sameAnswer(before, answers[row.key])) answers[row.key] = { ...before, source: `Carried over from the review of ${longDate(earlier)}.` };
    }
  }
  return answers;
}

const isDate = (text: string): boolean => /^\d{4}-\d{2}-\d{2}$/.test(text) && !Number.isNaN(Date.parse(text));

export function stubCaseReview(matterId: string, reviewDate = ""): CaseReview | { error: string } {
  const r = reviewsFor(matterId);
  const dates = newestFirst(r);
  if (reviewDate && !isDate(reviewDate)) return { error: "the review date must be a date" };
  if (reviewDate > STUB_CASE_REVIEW_TODAY) return { error: "the review date cannot be in the future" };
  const wanted = reviewDate || dates[0] || STUB_CASE_REVIEW_TODAY;
  const saved = r.get(wanted);
  const answers = saved ? saved.answers : draft(matterId);
  return {
    matter_id: matterId,
    review_date: wanted,
    today: STUB_CASE_REVIEW_TODAY,
    saved: saved !== undefined,
    saved_by: saved?.saved_by ?? "",
    saved_utc: saved?.saved_utc ?? "",
    first_saved_by: saved?.first_saved_by ?? "",
    first_saved_utc: saved?.first_saved_utc ?? "",
    forms: STUB_CASE_REVIEW_FORMS,
    answers,
    notes: prefill(matterId).notes,
    counts: countsFor(answers),
    versions: dates.map((day) => ({ review_date: day, saved_by: r.get(day)!.saved_by, saved_utc: r.get(day)!.saved_utc, counts: countsFor(r.get(day)!.answers) })),
  };
}

export function stubSaveCaseReview(matterId: string, reviewDate: string, submitted: unknown, by: string): CaseReview | { error: string } {
  if (!by.trim()) return { error: "type your name first" };
  if (!isDate(reviewDate)) return { error: "the review date must be a date" };
  if (reviewDate > STUB_CASE_REVIEW_TODAY) return { error: "the review date cannot be in the future" };
  const given = (submitted && typeof submitted === "object" ? submitted : {}) as Record<string, Partial<CaseReviewAnswer> | undefined>;
  const r = reviewsFor(matterId);
  const before = r.get(reviewDate);
  const supplied = draft(matterId, reviewDate);
  const clean: Record<string, CaseReviewAnswer> = {};
  for (const row of rows()) {
    const raw = given[row.key];
    if (!raw) continue;
    const answer: CaseReviewAnswer = { ...BLANK_ANSWER };
    if (row.kind === "text" || row.kind === "longtext" || row.kind === "date") {
      answer.text = String(raw.text ?? "").trim();
      if (row.kind === "date" && answer.text && !isDate(answer.text)) return { error: `${row.label}: that is not a date` };
    } else {
      answer.value = String(raw.value ?? "").trim();
      if (answer.value && !optionsOf(row).some(([v]) => v === answer.value)) return { error: `${row.label}: that is not one of its answers` };
      if (row.kind === "signoff") {
        answer.initials = String(raw.initials ?? "").trim();
        answer.date = String(raw.date ?? "").trim();
        if (answer.date && !isDate(answer.date)) return { error: `${row.label}: that is not a date` };
      }
    }
    if (isBlank(answer)) continue;
    const origin = [supplied[row.key], before?.answers[row.key]].find((o) => o?.source && sameAnswer(o, answer));
    clean[row.key] = { ...answer, source: origin?.source ?? "" };
  }
  const now = new Date().toISOString();
  r.set(reviewDate, {
    answers: clean,
    saved_by: by.trim(),
    saved_utc: now,
    first_saved_by: before?.first_saved_by ?? by.trim(),
    first_saved_utc: before?.first_saved_utc ?? now,
  });
  return stubCaseReview(matterId, reviewDate);
}
