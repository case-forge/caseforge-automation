"use client";

import { useState } from "react";
import { downloadCaseReviewForm, fetchCaseReview, saveCaseReview, useCaseReview } from "@/lib/caseReview";
import { BLANK_ANSWER, countLine, countsOf, isAnswered, longDate, optionsOf, sameAnswer, savedLine } from "@/lib/caseReviewTypes";
import type { CaseReview, CaseReviewAnswer, CaseReviewForm, CaseReviewFormKey, CaseReviewRow, CaseReviewSection } from "@/lib/caseReviewTypes";
import { ConflictCheckPanel } from "./ConflictCheckPanel";

const FORM_NAMES: Record<CaseReviewFormKey, string> = { review: "File review", summary: "File summary sheet" };

function Choices({ row, answer, onChange }: { row: CaseReviewRow; answer: CaseReviewAnswer; onChange: (patch: Partial<CaseReviewAnswer>) => void }) {
  return (
    <span className="aud-choices" role="group" aria-label={row.label}>
      {optionsOf(row).map(([value, label]) => (

        <button key={value} type="button" className="cf-btn cf-btn--chip aud-choice" aria-pressed={answer.value === value} onClick={() => onChange({ value: answer.value === value ? "" : value })}>
          {label}
        </button>
      ))}
    </span>
  );
}

function Control({ row, answer, onChange }: { row: CaseReviewRow; answer: CaseReviewAnswer; onChange: (patch: Partial<CaseReviewAnswer>) => void }) {
  if (row.kind === "longtext") {
    return <textarea className="aud-text" rows={3} maxLength={4000} aria-label={row.label} value={answer.text} onChange={(e) => onChange({ text: e.target.value })} />;
  }
  if (row.kind === "text" || row.kind === "date") {
    return (
      <input
        className="aud-text"
        type={row.kind === "date" ? "date" : "text"}
        maxLength={300}
        aria-label={row.label}
        value={answer.text}
        onChange={(e) => onChange({ text: e.target.value })}
      />
    );
  }
  if (row.kind !== "signoff") return <Choices row={row} answer={answer} onChange={onChange} />;
  const notApplicable = answer.value === "na";
  return (
    <span className="aud-signoff">
      <Choices row={row} answer={answer} onChange={onChange} />
      <label>
        <span>{row.na === false ? "By" : "Initials"}</span>
        <input className="aud-initials" maxLength={60} disabled={notApplicable} value={answer.initials} onChange={(e) => onChange({ initials: e.target.value })} />
      </label>
      <label>
        <span>Date</span>
        <input type="date" disabled={notApplicable} value={answer.date} onChange={(e) => onChange({ date: e.target.value })} />
      </label>
    </span>
  );
}

function Row({ row, answer, onChange }: { row: CaseReviewRow; answer: CaseReviewAnswer | undefined; onChange: (patch: Partial<CaseReviewAnswer>) => void }) {
  const a = answer ?? BLANK_ANSWER;
  const done = isAnswered(row, a);
  const state = done ? "answered" : row.optional ? "optional" : "unanswered";
  return (
    <li className="aud-row" data-state={state}>
      <span className="aud-label">{row.label}</span>
      <Control row={row} answer={a} onChange={onChange} />
      <span className="aud-state">{done ? "Answered" : row.optional ? "Optional" : "To answer"}</span>
      {a.source && <small className="aud-source">Not typed here. {a.source}</small>}
    </li>
  );
}

function Section({
  section,
  answers,
  notes,
  onlyUnanswered,
  onChange,
}: {
  section: CaseReviewSection;
  answers: Record<string, CaseReviewAnswer>;
  notes: Record<string, string>;
  onlyUnanswered: boolean;
  onChange: (key: string, patch: Partial<CaseReviewAnswer>) => void;
}) {
  const shown = section.rows.filter((row) => !onlyUnanswered || (!row.optional && !isAnswered(row, answers[row.key])));
  const groups: { name: string; rows: CaseReviewRow[] }[] = [];
  for (const row of shown) {
    const name = row.group ?? "";
    const last = groups[groups.length - 1];
    if (last && last.name === name) last.rows.push(row);
    else groups.push({ name, rows: [row] });
  }
  return (
    <section className="aud-section" aria-label={section.title}>
      <h4 className="aud-section-title">{section.title}</h4>
      {section.person_only && <p className="cf2-note">This section is the reviewer&apos;s alone. The system never fills or suggests an answer here.</p>}
      {shown.length === 0 && <p className="cf2-note">Nothing left to answer in this section.</p>}
      {groups.map((group) => (
        <div key={group.name || section.key} className="aud-group">
          {group.name && <h5 className="aud-group-title">{group.name}</h5>}
          {group.name && notes[group.name] && <p className="aud-fact">On record: {notes[group.name]}</p>}
          <ul className="aud-rows">
            {group.rows.map((row) => (
              <Row key={row.key} row={row} answer={answers[row.key]} onChange={(patch) => onChange(row.key, patch)} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

export function CaseReviewTab({ matterId }: { matterId: string }) {
  const { data, error, setData, setError } = useCaseReview(matterId);
  const [shownForm, setShownForm] = useState<CaseReviewFormKey>("review");
  const [onlyUnanswered, setOnlyUnanswered] = useState(false);
  const [message, setMessage] = useState("");

  if (error && !data) return <p className="cf2-error" role="alert">{error}</p>;
  if (!data) return <p className="cf2-empty">Loading the case review...</p>;

  return (
    <Review
      key={`${data.review_date}:${data.saved_utc}`}
      matterId={matterId}
      loaded={data}
      error={error}
      message={message}
      shownForm={shownForm}
      onlyUnanswered={onlyUnanswered}
      setData={setData}
      setError={setError}
      setMessage={setMessage}
      setShownForm={setShownForm}
      setOnlyUnanswered={setOnlyUnanswered}
    />
  );
}

interface ReviewProps {
  matterId: string;
  loaded: CaseReview;
  error: string;
  message: string;
  shownForm: CaseReviewFormKey;
  onlyUnanswered: boolean;
  setData: (a: CaseReview) => void;
  setError: (e: string) => void;
  setMessage: (m: string) => void;
  setShownForm: (f: CaseReviewFormKey) => void;
  setOnlyUnanswered: (only: boolean) => void;
}

function Review({ matterId, loaded, error, message, shownForm, onlyUnanswered, setData, setError, setMessage, setShownForm, setOnlyUnanswered }: ReviewProps) {
  const [answers, setAnswers] = useState<Record<string, CaseReviewAnswer>>(loaded.answers);
  const [dirty, setDirty] = useState(false);
  const [newDate, setNewDate] = useState(loaded.today);
  const [busy, setBusy] = useState("");

  function change(key: string, patch: Partial<CaseReviewAnswer>) {
    setAnswers((before) => {
      const next = { ...(before[key] ?? BLANK_ANSWER), ...patch };

      const original = loaded.answers[key];
      next.source = original && sameAnswer(original, next) ? original.source : "";
      return { ...before, [key]: next };
    });
    setDirty(true);
    setMessage("");
  }

  async function open(reviewDate: string) {
    if (busy) return;
    if (dirty && !window.confirm("This review has changes that are not saved. Leave it without saving?")) return;
    setBusy("open");
    setMessage("");
    try {
      setData(await fetchCaseReview(matterId, reviewDate));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the case review.");
    } finally {
      setBusy("");
    }
  }

  async function save() {
    if (busy) return;
    setBusy("save");
    setMessage("");
    try {
      setData(await saveCaseReview(matterId, loaded.review_date, answers));
      setError("");
      setMessage("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The review was not saved.");
    } finally {
      setBusy("");
    }
  }

  async function download(form: CaseReviewForm) {
    if (busy || dirty) return;
    setBusy(`download:${form.key}`);
    setMessage("");
    try {
      setMessage(`Downloaded ${await downloadCaseReviewForm(matterId, form.key, loaded.review_date)}.`);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The Word form could not be made.");
    } finally {
      setBusy("");
    }
  }

  const form = loaded.forms.find((f) => f.key === shownForm) ?? loaded.forms[0];
  const counts = countsOf(form, answers);
  const saveReason = busy === "save" ? "Saving." : "";
  const isSavedVersion = loaded.versions.some((v) => v.review_date === loaded.review_date);

  return (
    <div className="cf2 aud">
      <div className="cf2-bar">
        <h2 className="cf2-title">CaseReview</h2>
        <span className="cf2-note" role="status">
          {savedLine(loaded)}
          {dirty ? " Changes not saved." : ""}
        </span>
      </div>
      <p className="cf2-note">
        The firm&apos;s File Review Form and File Summary Sheet. The system fills only what it holds and says where each answer came from; change any of them. Everything else starts unanswered. Nothing is filed in the client&apos;s folder and no Case flow step is run.
      </p>

      <ConflictCheckPanel matterId={matterId} answers={answers} />

      <div className="aud-versions">
        <label>
          <span>Review</span>
          <select value={loaded.review_date} disabled={busy !== ""} onChange={(e) => void open(e.target.value)}>
            {!isSavedVersion && <option value={loaded.review_date}>{longDate(loaded.review_date)} (new, not saved)</option>}
            {loaded.versions.map((v) => (
              <option key={v.review_date} value={v.review_date}>
                {longDate(v.review_date)}, saved by {v.saved_by}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Review the file again, dated</span>
          <input type="date" value={newDate} max={loaded.today} onChange={(e) => setNewDate(e.target.value)} />
        </label>
        <button type="button" className="cf-btn cf-btn--neutral cf2-reset-step" disabled={busy !== "" || !newDate || newDate === loaded.review_date} onClick={() => void open(newDate)}>
          Start a new review
        </button>
        <small className="cf2-reason">{loaded.versions.length === 0 ? "No review saved yet." : `${loaded.versions.length} saved. An earlier review is kept as it was saved.`}</small>
      </div>

      <div className="aud-forms" role="group" aria-label="Form">
        {loaded.forms.map((f) => {
          const c = countsOf(f, answers);
          return (
            <button key={f.key} type="button" className="cf-btn cf-btn--chip aud-form-pick" aria-pressed={f.key === form.key} data-complete={c.unanswered === 0 ? "true" : "false"} onClick={() => setShownForm(f.key)}>
              {FORM_NAMES[f.key]} <span className="aud-form-count">{c.unanswered === 0 ? "complete" : `${c.unanswered} to answer`}</span>
            </button>
          );
        })}
      </div>

      <div className="aud-form-head">
        <h3 className="aud-form-title">{form.title}</h3>
        <span className="cf2-mark" role="status" data-complete={counts.unanswered === 0 ? "true" : "false"}>{countLine(counts)}</span>
        <label className="aud-only">
          <input type="checkbox" checked={onlyUnanswered} onChange={(e) => setOnlyUnanswered(e.target.checked)} /> Show only rows still to answer
        </label>
      </div>
      <p className="cf2-note">{form.note}</p>
      {form.key === "review" && <p className="aud-fact">Date file review conducted: {longDate(loaded.review_date)} (this review&apos;s date).</p>}

      {form.sections.map((section) => (
        <Section key={section.key} section={section} answers={answers} notes={loaded.notes} onlyUnanswered={onlyUnanswered} onChange={change} />
      ))}

      <div className="cf2-actions aud-actions">
        <span className="cf2-action">
          <button type="button" className="cf-btn cf-btn--primary cf2-run" disabled={saveReason !== "" || busy !== ""} title={saveReason || undefined} onClick={() => void save()}>
            {busy === "save" ? "Saving..." : "Save this review"}
          </button>
          {saveReason && busy === "" && <small className="cf2-reason">{saveReason}</small>}
        </span>
        {loaded.forms.map((f) => (
          <span key={f.key} className="cf2-action">
            <button type="button" className="cf-btn cf-btn--secondary cf2-mark-done" disabled={busy !== "" || dirty} onClick={() => void download(f)}>
              {busy === `download:${f.key}` ? "Making..." : `Download the ${f.title} as Word`}
            </button>
            {dirty && <small className="cf2-reason">Save first: the Word form is made from the saved review.</small>}
          </span>
        ))}
      </div>
      {error && <p className="cf2-error" role="alert">{error}</p>}
      {message && <p className="cf2-result" role="status">{message}</p>}
    </div>
  );
}
