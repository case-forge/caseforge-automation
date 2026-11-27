"use client";

import { useEffect, useState } from "react";
import { formatDateShort, formatTime12, requestLabel, vacatedSummary } from "@/lib/hearings";
import type { Hearing } from "@/lib/hearings";
import { REQUEST_CHOICES, VACATE_CHOICES, hearingState, moveStart, reasonsFor, validateMove } from "@/lib/hearingActions";
import type { RequestKind, RequestOptions } from "@/lib/hearingActions";
import { courtDecision, fetchRequestOptions, isAbort, requestFromCourt, setHearingStatus, vacateHearing } from "@/lib/hearingsClient";

type Run = (action: () => Promise<{ hearing: Hearing }>) => void;

interface Props {
  hearing: Hearing;
  busy: boolean;
  onEdit: () => void;

  run: Run;

  onError: (message: string | null) => void;
}

type Panel = null | "vacate" | "move" | RequestKind;

export function HearingStateActions(props: Props) {

  const [notice, setNotice] = useState<string | null>(null);
  const { hearing } = props;

  const bodyKey = `${hearing.status}|${hearing.request_state ?? ""}|${hearing.replaced_by?.hearing_id ?? ""}`;
  return <StateActionsBody key={bodyKey} {...props} notice={notice} setNotice={setNotice} />;
}

function StateActionsBody({ hearing, busy, onEdit, run, onError, notice, setNotice }: Props & { notice: string | null; setNotice: (summary: string | null) => void }) {
  const state = hearingState(hearing);
  const [panel, setPanel] = useState<Panel>(null);

  return (
    <>
      {notice && (
        <p className="hearing-link-notice" role="status">
          {notice}
        </p>
      )}
      {state === "vacation_requested" || state === "hybrid_requested" ? (
        <section className="hearing-request-box" aria-label="Request to the court">
          <p className="hearing-request-title">{requestLabel(hearing)}: waiting for the court</p>
          {hearing.request_reason && <p className="hearing-request-reason">{hearing.request_reason}</p>}
          <div className="hearing-actions">
            <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={() => run(() => courtDecision(hearing.hearing_id, true))}>
              Court agreed
            </button>
            <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} onClick={() => run(() => courtDecision(hearing.hearing_id, false))}>
              Court refused
            </button>
          </div>
        </section>
      ) : null}

      {state === "vacated" && (
        <p className="hearing-vacated-note" role="status">
          {vacatedSummary(hearing)}
        </p>
      )}
      {hearing.replaces_hearing_id != null && state !== "vacated" && <p className="hearing-muted">Replaces a hearing that was moved.</p>}

      <div className="hearing-actions">
        <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={onEdit}>
          Edit
        </button>
        {state !== "vacated" && (
          <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} aria-expanded={panel === "vacate" || panel === "move"} onClick={() => setPanel(panel === "vacate" ? null : "vacate")}>
            Vacate
          </button>
        )}
        {state === "scheduled" &&
          REQUEST_CHOICES.map((choice) => (
            <button key={choice.kind} type="button" className="cf-btn cf-btn--neutral" disabled={busy} aria-expanded={panel === choice.kind} onClick={() => setPanel(panel === choice.kind ? null : choice.kind)}>
              {choice.short}
            </button>
          ))}
        {state === "vacated" && !hearing.replaced_by && (
          <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} onClick={() => setPanel(panel === "move" ? null : "move")}>
            Moved to a new date/time
          </button>
        )}
        {state === "vacated" && (
          <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} onClick={() => run(() => setHearingStatus(hearing.hearing_id, "scheduled"))}>
            Reinstate
          </button>
        )}
      </div>

      {panel === "vacate" && (
        <section className="hearing-choice-box" aria-label="Vacate this hearing">
          <p className="hearing-choice-title">Why is it being vacated?</p>
          <div className="hearing-actions">
            {VACATE_CHOICES.map((choice) => (
              <button
                key={choice.kind}
                type="button"
                className="cf-btn cf-btn--neutral"
                disabled={busy}
                onClick={() => {
                  if (choice.kind === "moved") {
                    setPanel("move");
                    return;
                  }
                  if (!window.confirm("Vacate this hearing because you are no longer acting for the client? It stays on the calendar, struck through, and can be reinstated.")) return;
                  run(() => vacateHearing(hearing.hearing_id, choice.kind, "").then((out) => ({ hearing: out.hearing })));
                }}
              >
                {choice.label}
              </button>
            ))}
          </div>
          <p className="hearing-muted">If the court has not yet agreed to vacate it, use a request below instead: the court decides.</p>
        </section>
      )}

      {panel === "move" && <MovePanel hearing={hearing} busy={busy} run={run} onCancel={() => setPanel(null)} />}
      {(panel === "vacation" || panel === "hybrid") && <RequestPanel hearing={hearing} kind={panel} busy={busy} run={run} onError={onError} onDone={setNotice} onCancel={() => setPanel(null)} />}
    </>
  );
}

function MovePanel({ hearing, busy, run, onCancel }: { hearing: Hearing; busy: boolean; run: Run; onCancel: () => void }) {
  const start = moveStart(hearing);
  const [date, setDate] = useState(start.hearing_date);
  const [time, setTime] = useState(start.hearing_time);
  const [reason, setReason] = useState("");
  const problem = validateMove(hearing, { hearing_date: date, hearing_time: time });
  return (
    <section className="hearing-choice-box" aria-label="Move this hearing">
      <p className="hearing-choice-title">
        Moved from {formatDateShort(hearing.hearing_date)}, {formatTime12(hearing.hearing_time)}
      </p>
      <div className="hearing-move-fields">
        <label className="hearing-form-label" htmlFor="move-date">
          New date
          <input id="move-date" className="edit-input" type="date" value={date} onChange={(e) => setDate(e.target.value)} disabled={busy} />
        </label>
        <label className="hearing-form-label" htmlFor="move-time">
          New time
          <input id="move-time" className="edit-input" type="time" value={time} onChange={(e) => setTime(e.target.value)} disabled={busy} />
        </label>
      </div>
      <label className="hearing-form-label" htmlFor="move-reason">
        Reason for the move (optional)
        <input id="move-reason" className="edit-input" value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} placeholder="For example: relisted by the court" />
      </label>
      <p className="hearing-muted">The court, case number, type, counsel and the other details are carried to the new hearing. This one stays, struck through, linked to it.</p>
      {problem && <p className="hearing-form-error" role="alert">{problem}</p>}
      <div className="hearing-actions">
        <button
          type="button"
          className="cf-btn cf-btn--primary"
          disabled={busy || problem !== null}
          onClick={() => run(() => vacateHearing(hearing.hearing_id, "moved", reason, { hearing_date: date, hearing_time: time }).then((out) => ({ hearing: out.replacement ?? out.hearing })))}
        >
          Move hearing
        </button>
        <button type="button" className="cf-btn cf-btn--flush" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}

function RequestPanel({ hearing, kind, busy, run, onError, onDone, onCancel }: { hearing: Hearing; kind: RequestKind; busy: boolean; run: Run; onError: (m: string | null) => void; onDone: (summary: string) => void; onCancel: () => void }) {
  const [options, setOptions] = useState<RequestOptions | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState("");
  const [form, setForm] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchRequestOptions(hearing.hearing_id, controller.signal)
      .then((body) => {
        setOptions(body);
        setForm(body.form);
      })
      .catch((err: unknown) => {
        if (!isAbort(err)) onError(err instanceof Error ? err.message : "Could not load the stock reasons");
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hearing.hearing_id]);

  const reasons = [...Object.values(picked), extra].map((r) => r.trim()).filter(Boolean);
  const title = kind === "vacation" ? "Request vacation of this hearing" : "Request a remote or hybrid hearing";
  const missingForm = options !== null && form === "";

  return (
    <section className="hearing-choice-box" aria-label={title}>
      <p className="hearing-choice-title">{title}</p>
      <p className="hearing-muted">
        This drafts an application to the court, marked AI DRAFTED, and shows the hearing in red until the court answers. Nothing is sent: the court decides.
      </p>
      {options === null ? (
        <p className="hearing-muted">Loading the usual reasons...</p>
      ) : (
        <>
          <div className="hearing-request-form">
            <span className="hearing-form-label">Application</span>
            {options.forms.map((f) => (
              <label key={f} className="hearing-request-radio">
                <input type="radio" name="request-form" value={f} checked={form === f} onChange={() => setForm(f)} disabled={busy} /> {f === "FP2" ? "FP2 (family)" : "C2 (children)"}
              </label>
            ))}
            {missingForm && <span className="hearing-form-error" role="alert">The matter&apos;s orders do not say which: choose one.</span>}
          </div>
          <fieldset className="hearing-request-reasons">
            <legend className="hearing-form-label">Reasons (tick any, then edit the wording)</legend>
            {reasonsFor(options, kind).map((reason) => {
              const on = reason.id in picked;
              return (
                <div key={reason.id} className="hearing-request-reason-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={busy}
                      onChange={(e) =>
                        setPicked((current) => {
                          const next = { ...current };
                          if (e.target.checked) next[reason.id] = reason.text;
                          else delete next[reason.id];
                          return next;
                        })
                      }
                    />{" "}
                    {reason.label}
                  </label>
                  {on && (
                    <textarea
                      className="edit-input"
                      rows={3}
                      aria-label={`Wording: ${reason.label}`}
                      value={picked[reason.id]}
                      disabled={busy}
                      onChange={(e) => setPicked((current) => ({ ...current, [reason.id]: e.target.value }))}
                    />
                  )}
                </div>
              );
            })}
            <label className="hearing-form-label" htmlFor="request-extra">
              Anything else (this matter&apos;s own facts)
              <textarea id="request-extra" className="edit-input" rows={3} value={extra} disabled={busy} onChange={(e) => setExtra(e.target.value)} />
            </label>
          </fieldset>
          <div className="hearing-actions">
            <button
              type="button"
              className="cf-btn cf-btn--primary"
              disabled={busy || reasons.length === 0 || missingForm}
              onClick={() =>
                run(() =>
                  requestFromCourt(hearing.hearing_id, kind, reasons, form).then((out) => {
                    onDone(out.summary);
                    return { hearing: out.hearing };
                  }),
                )
              }
            >
              Draft the application
            </button>
            <button type="button" className="cf-btn cf-btn--flush" disabled={busy} onClick={onCancel}>
              Cancel
            </button>
          </div>
        </>
      )}
    </section>
  );
}
