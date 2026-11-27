"use client";

import { useEffect, useRef, useState } from "react";
import {
  AMEND_ANSWERS_MAX,
  AMEND_CLIENT_QUESTION_MAX,
  AMEND_EDIT_MAX,
  AMEND_EMAIL_MAX,
  amendFlagLabel,
  amendRoundSummary,
  approveLabel,
  decideBlockedReason,
  editProblem,
  flaggedLine,
  paragraphHeading,
  prepareBlockedReason,
  questionTypeLabel,
  repeatLine,
  wordDiff,
} from "@/lib/amendRound";
import { approveAmendRound, discardAmendRound, prepareAmendRound } from "@/lib/pipeline";
import { eventTime, safeLinks } from "@/lib/pipelineDisplay";
import type { AmendOpenRound, AmendParagraph, Pipeline, PipelineLink, PipelineStep } from "@/lib/pipelineTypes";

interface Result {
  ok: boolean;
  message: string;
  links?: PipelineLink[];
}

interface Props {
  matterId: string;
  step: PipelineStep;

  locked: string;

  running: string;
  setRunning: (id: string) => void;
  setData: (p: Pipeline) => void;
  refresh: () => void;
}

export function CaseFlowAmendPanel({ matterId, step, locked, running, setRunning, setData, refresh }: Props) {
  const info = step.amend;
  const hint = info?.email_hint ?? "";
  const [emailText, setEmailText] = useState(() => hint.slice(0, AMEND_EMAIL_MAX));
  const [result, setResult] = useState<Result | null>(null);

  const [formShown, setFormShown] = useState(() => hint !== "");
  const prefilled = useRef(hint !== "");

  useEffect(() => {
    if (prefilled.current || !hint) return;
    prefilled.current = true;
    setEmailText((typed) => typed || hint.slice(0, AMEND_EMAIL_MAX));
    setFormShown(true);
  }, [hint]);

  if (!info) return null;
  const open = info.open;

  async function act(id: string, call: () => Promise<Result & { pipeline?: Pipeline }>) {
    setRunning(id);
    setResult(null);
    try {
      const out = await call();
      if (out.pipeline) setData(out.pipeline);
      setResult({ ok: out.ok, message: out.message, links: out.links });
    } catch (err) {
      setResult({ ok: false, message: err instanceof Error && err.message ? err.message : "That did not work." });
    } finally {
      setRunning("");
      refresh();
    }
  }

  function prepare() {
    void act("amend:prepare", async () => {
      const pipeline = await prepareAmendRound(matterId, emailText.trim());
      setFormShown(false);
      return { ok: true, message: "The amended statement is prepared below. Nothing is saved or sent until you approve it.", pipeline };
    });

  }

  function approve(round: number, answers: string, keepOriginal: string[], clientQuestions?: string[], edits: Record<string, string> = {}) {
    void act("amend:approve", async () => {
      const out = await approveAmendRound(matterId, round, answers.trim(), keepOriginal, clientQuestions, edits);
      if (out.ok) setEmailText("");
      return out;
    });
  }

  function discard(round: number) {
    void act("amend:discard", async () => {
      const pipeline = await discardAmendRound(matterId, round);
      return { ok: true, message: `Round ${round} discarded. Nothing was saved or sent.`, pipeline };
    });
  }

  const flag = flaggedLine(info);
  const prepareReason = prepareBlockedReason({
    canStart: info.can_start,
    startBlocked: info.start_blocked,
    locked,
    busy: running !== "",
    hasEmail: emailText.trim() !== "",
  });
  const preparing = running === "amend:prepare";
  const boxId = `cf2-amend-email-${matterId}`;
  const links = safeLinks(result?.links);

  return (
    <div className="cf2-amend" aria-busy={running.startsWith("amend:") ? true : undefined}>
      {flag && (
        <p className="cf2-amend-rounds">
          <strong className="cf2-amend-flagged">{flag}</strong>
        </p>
      )}

      {!open && info.can_start && !formShown && (
        <div className="cf2-form-buttons">
          <button type="button" className="cf-btn cf-btn--secondary cf2-mark-done" disabled={locked !== ""} title={locked || undefined} onClick={() => setFormShown(true)} aria-expanded={false}>
            Paste the client&apos;s email asking for changes
          </button>
          {locked && <small className="cf2-reason">{locked}</small>}
        </div>
      )}

      {!open && info.can_start && formShown && (
        <div className="cf2-form cf2-amend-start">
          <div className="cf2-field">
            <label htmlFor={boxId}>The client&apos;s email asking for changes</label>
            <textarea
              id={boxId}
              className="cf2-amend-text"
              rows={8}
              maxLength={AMEND_EMAIL_MAX}
              value={emailText}
              disabled={preparing}
              onChange={(e) => setEmailText(e.target.value)}
            />
            <small className="cf2-field-hint">
              Paste the client&apos;s email as it is. Preparing takes a minute or two. Nothing is saved or sent until you approve the round.
            </small>
          </div>
          <div className="cf2-form-buttons">
            <button type="button" className="cf-btn cf-btn--primary cf2-run" disabled={prepareReason !== ""} title={prepareReason || undefined} onClick={prepare}>
              {preparing ? "Preparing… (a minute or two)" : "Prepare the amended statement"}
            </button>
            {prepareReason && !preparing && <small className="cf2-reason">{prepareReason}</small>}
          </div>
        </div>
      )}

      {open && (
        <AmendRoundView
          key={open.round}
          open={open}
          blocked={decideBlockedReason({ locked, busy: running !== "" })}
          running={running}
          onApprove={approve}
          onDiscard={discard}
        />
      )}

      {result && (
        <div className={result.ok ? "cf2-result" : "cf2-error"} role={result.ok ? "status" : "alert"}>
          {result.ok ? "Done: " : "Not done: "}
          {asSentence(result.message)}
          {links.length > 0 && (
            <ul className="cf2-links" aria-label="Open">
              {links.map((l) => (
                <li key={l.url}>
                  <a href={l.url} target="_blank" rel="noreferrer">{l.label}</a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function asSentence(text: string): string {
  const t = text.trim();
  return t && !/[.!?]$/.test(t) ? `${t}.` : t;
}

function DiffText({ parts, show }: { parts: ReturnType<typeof wordDiff>; show: "before" | "after" }) {
  return (
    <>
      {parts.map((part, n) => {
        if (part.kind === "same") return <span key={n}>{part.text}</span>;
        if (show === "before" && part.kind === "del") return <del key={n}>{part.text}</del>;
        if (show === "after" && part.kind === "ins") return <ins key={n}>{part.text}</ins>;
        return null;
      })}
    </>
  );
}

function ParagraphCard({
  p,
  keep,
  onKeep,
  edit,
  onEdit,
  disabled,
}: {
  p: AmendParagraph;
  keep: boolean;
  onKeep: (keep: boolean) => void;

  edit: string | undefined;
  onEdit: (text: string | undefined) => void;
  disabled: boolean;
}) {
  const editing = edit !== undefined && !keep;
  const shown = editing && edit.trim() ? edit : p.after;
  const parts = wordDiff(p.before, shown);
  const problem = editing ? editProblem(edit) : "";
  const editId = `cf2-amend-edit-${p.id}`;
  return (
    <li
      className="cf2-amend-para"
      data-flagged={p.flags.length > 0 ? "true" : undefined}
      data-kept={keep ? "true" : undefined}
      data-edited={p.edited || (editing && edit !== p.after) ? "true" : undefined}
    >
      <div className="cf2-amend-para-head">
        <strong>{paragraphHeading(p)}</strong>
        {(p.edited || (editing && edit !== p.after)) && (
          <span className="cf2-amend-badge" data-kind="edited" title="The text is yours, not the model's.">
            Edited by you
          </span>
        )}
        {p.flags.map((f, n) => {
          const label = amendFlagLabel(f.kind);
          return (
            <span key={n} className="cf2-amend-badge" data-kind={f.kind} title={label.meaning}>
              {label.badge}
            </span>
          );
        })}
      </div>
      <div className="cf2-amend-texts">
        {p.para !== null && (
          <div className="cf2-amend-before">
            <span className="cf2-amend-tag">Before</span>
            <p>
              <DiffText parts={parts} show="before" />
            </p>
          </div>
        )}
        <div className="cf2-amend-after">
          <span className="cf2-amend-tag">{p.para === null ? "New text" : "After"}</span>
          {editing ? (
            <>
              <label htmlFor={editId} className="cf2-amend-tag">Your text for this paragraph</label>
              <textarea
                id={editId}
                className="cf2-amend-text"
                rows={5}
                maxLength={AMEND_EDIT_MAX}
                value={edit}
                disabled={disabled}
                aria-invalid={problem !== "" ? true : undefined}
                onChange={(e) => onEdit(e.target.value)}
              />
              <small className={problem ? "cf2-reason" : "cf2-field-hint"} role={problem ? "alert" : undefined}>
                {problem || "Approve saves exactly this text. The paragraph number stays as it is."}
              </small>
            </>
          ) : (
            <p>
              <DiffText parts={parts} show="after" />
            </p>
          )}
          {p.edited && p.model_after && <small className="cf2-field-hint">Written by you; the proposal was: {p.model_after}</small>}
        </div>
      </div>
      {p.why && <p className="cf2-amend-why">{p.why}</p>}
      {p.client_words && (
        <blockquote className="cf2-amend-quote">
          <span className="cf2-amend-tag">The client wrote</span> {p.client_words}
        </blockquote>
      )}
      {p.flags.length > 0 && (
        <ul className="cf2-detail">
          {p.flags.map((f, n) => (
            <li key={n}>
              <strong>{amendFlagLabel(f.kind).badge}:</strong> {f.text || amendFlagLabel(f.kind).meaning}
            </li>
          ))}
        </ul>
      )}
      {p.after !== "" && (
        <div className="cf2-form-buttons">
          {editing ? (
            <button type="button" className="cf-btn cf-btn--neutral cf2-reset-step" disabled={disabled} onClick={() => onEdit(undefined)}>
              Use the proposed text
            </button>
          ) : (
            <button
              type="button"
              className="cf-btn cf-btn--secondary cf2-mark-done"
              disabled={disabled || keep || p.edited}
              title={keep ? "Clear the tick box below to edit this." : undefined}
              onClick={() => onEdit(p.after)}
            >
              Edit
            </button>
          )}
        </div>
      )}
      <label className="cf2-amend-keep">
        <input type="checkbox" checked={keep} disabled={disabled} onChange={(e) => onKeep(e.target.checked)} />{" "}
        {p.para === null ? "Keep the original (do not add this paragraph)" : "Keep the original (reject this change)"}
      </label>
    </li>
  );
}

function AmendRoundView({
  open,
  blocked,
  running,
  onApprove,
  onDiscard,
}: {
  open: AmendOpenRound;
  blocked: string;
  running: string;
  onApprove: (round: number, answers: string, keepOriginal: string[], clientQuestions?: string[], edits?: Record<string, string>) => void;
  onDiscard: (round: number) => void;
}) {
  const [keep, setKeep] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});

  const sent: Record<string, string> = {};
  let editBlock = "";
  for (const p of open.paragraphs) {
    const text = edits[p.id];
    if (text === undefined || keep.includes(p.id)) continue;
    const problem = editProblem(text);
    if (problem && !editBlock) editBlock = `${paragraphHeading(p)}: ${problem}`;
    if (!problem && text.trim() !== p.after.trim()) sent[p.id] = text;
  }
  const [answers, setAnswers] = useState("");

  const [asked, setAsked] = useState<string[]>(() => (open.ai_questions ?? []).map((q) => q.question));
  const busy = running.startsWith("amend:");
  const answersId = `cf2-amend-answers-${open.round}`;
  const when = eventTime(open.prepared_utc);

  return (
    <div className="cf2-amend-round">
      <p className="cf2-amend-summary">
        <strong>Round {open.round}</strong>
        {open.status === "saved" ? " (statement saved, email not drafted yet)" : ""}: {amendRoundSummary(open)}.
        {open.prepared_by && (
          <small className="cf2-reason">
            {" "}Prepared by {open.prepared_by}
            {when ? `, ${when}` : ""}.
          </small>
        )}
      </p>

      {open.paragraphs.length > 0 && (
        <ol className="cf2-amend-paras">
          {open.paragraphs.map((p) => (
            <ParagraphCard
              key={p.id}
              p={p}
              keep={keep.includes(p.id)}
              disabled={busy || open.status === "saved"}
              edit={open.status === "prepared" ? edits[p.id] : undefined}
              onEdit={(text) =>
                setEdits((all) => {
                  const next = { ...all };
                  if (text === undefined) delete next[p.id];
                  else next[p.id] = text;
                  return next;
                })
              }
              onKeep={(on) => setKeep((ids) => (on ? [...ids.filter((id) => id !== p.id), p.id] : ids.filter((id) => id !== p.id)))}
            />
          ))}
        </ol>
      )}

      {open.questions.length > 0 && (
        <section className="cf2-amend-section">
          <h4>The client&apos;s questions and requests for advice</h4>
          <ul className="cf2-amend-list">
            {open.questions.map((q, n) => (
              <li key={n}>
                <strong>{questionTypeLabel(q.type)}</strong>
                {q.para !== null ? ` (paragraph ${q.para})` : ""}: {q.client_words}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(open.ai_questions ?? []).length > 0 && (
        <section className="cf2-amend-section">
          <h4>Questions for the client (go into the email; edit or delete any)</h4>
          <ol className="cf2-amend-list">
            {asked.map((q, n) => (
              <li key={n}>
                <textarea
                  className="cf2-amend-text"
                  rows={2}
                  aria-label={`Question ${n + 1} for the client`}
                  maxLength={AMEND_CLIENT_QUESTION_MAX}
                  value={q}
                  disabled={busy}
                  onChange={(e) => setAsked((list) => list.map((x, i) => (i === n ? e.target.value : x)))}
                />
                <button type="button" className="cf-btn cf-btn--flush cf-btn--danger cf-btn--small" disabled={busy} onClick={() => setAsked((list) => list.filter((_, i) => i !== n))}>
                  Delete
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="cf2-field">
        <label htmlFor={answersId}>Your answers to the client&apos;s questions (go into the email)</label>
        <textarea
          id={answersId}
          className="cf2-amend-text"
          rows={4}
          maxLength={AMEND_ANSWERS_MAX}
          value={answers}
          disabled={busy}
          onChange={(e) => setAnswers(e.target.value)}
        />
      </div>

      {open.unplaced.length > 0 && (
        <section className="cf2-amend-section">
          <h4>Requests not placed on a paragraph</h4>
          <ul className="cf2-amend-list">
            {open.unplaced.map((u, n) => (
              <li key={n}>
                {u.client_words}
                {u.why && <small className="cf2-reason"> ({u.why})</small>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {open.repeats.length > 0 && (
        <section className="cf2-amend-section">
          <h4>Asked for before</h4>
          <ul className="cf2-amend-list">
            {open.repeats.map((r, n) => (
              <li key={n} data-missing={r.in_text_now ? undefined : "true"}>
                {r.para !== null ? `Paragraph ${r.para}: ` : ""}
                {r.client_words} <strong>{repeatLine(r)}</strong>
              </li>
            ))}
          </ul>
        </section>
      )}

      {open.db_updates.length > 0 && (
        <section className="cf2-amend-section">
          <h4>Proposed database updates</h4>
          <p className="cf2-note">Not applied. Change them on the Client tab if they are right; the signed statement wins.</p>
          <div className="cf2-amend-table-wrap">
            <table className="cf2-amend-table">
              <thead>
                <tr>
                  <th scope="col">Record</th>
                  <th scope="col">The statement said</th>
                  <th scope="col">Now says</th>
                  <th scope="col">From</th>
                </tr>
              </thead>
              <tbody>
                {open.db_updates.map((u, n) => (
                  <tr key={n}>
                    <td>{u.field}</td>
                    <td>{u.current || "(empty)"}</td>
                    <td>{u.proposed}</td>
                    <td>
                      {u.para !== null ? `Paragraph ${u.para}` : ""}
                      {u.quote ? `${u.para !== null ? ": " : ""}"${u.quote}"` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {open.notes.length > 0 && (
        <section className="cf2-amend-section">
          <h4>Notes</h4>
          <ul className="cf2-detail">
            {open.notes.map((note, n) => (
              <li key={n}>{note}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="cf2-form-buttons">
        <button
          type="button"
          className="cf-btn cf-btn--primary cf2-run cf2-amend-approve"
          disabled={blocked !== "" || (open.status === "prepared" && editBlock !== "")}
          title={blocked || editBlock || "Saves the amended statement and drafts the email as AI DRAFTED. Nothing is sent."}
          onClick={() => onApprove(open.round, answers, keep, (open.ai_questions ?? []).length ? asked : undefined, open.status === "prepared" ? sent : {})}
        >
          {running === "amend:approve" ? "Saving…" : approveLabel(open.status)}
        </button>
        { }
        {open.status === "prepared" && (
          <button
            type="button"
            className="cf-btn cf-btn--neutral cf2-reset-step"
            disabled={blocked !== ""}
            title={blocked || "Forget this round. Nothing is sent."}
            onClick={() => onDiscard(open.round)}
          >
            {running === "amend:discard" ? "Discarding…" : "Discard this round"}
          </button>
        )}
        {blocked && !busy && <small className="cf2-reason">{blocked}</small>}
        {!blocked && editBlock && !busy && open.status === "prepared" && <small className="cf2-reason">{editBlock}</small>}
      </div>
      {Object.keys(sent).length > 0 && open.status === "prepared" && (
        <p className="cf2-note">
          {Object.keys(sent).length === 1 ? "1 paragraph uses" : `${Object.keys(sent).length} paragraphs use`} your own text.
        </p>
      )}
      {keep.length > 0 && open.status === "prepared" && (
        <p className="cf2-note">
          {keep.length === 1 ? "1 paragraph keeps" : `${keep.length} paragraphs keep`} the original text.
        </p>
      )}
    </div>
  );
}
