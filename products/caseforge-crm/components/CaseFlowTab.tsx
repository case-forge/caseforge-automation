"use client";

import { StatusShape, SyncGlyph } from "./Glyphs";
import { IconCircle, IconCircleDot } from "./icons";
import { useEffect, useRef, useState } from "react";
import { STALE_TEXT, syncMark } from "@/lib/syncMark";
import { autoStalledReason, effectiveMode, firmModeSetBy, matterChoiceLabel, matterModeBlockedReason, matterModeSentence, matterModeSetBy, matterSetting } from "@/lib/matterMode";
import { fetchPipeline, runPipelineStep, sendGameDraft, sendStepForm, setMatterMode, setPipelineMode, usePipeline } from "@/lib/pipeline";
import { canConfirmCourt, canMarkDone, canResetStep, lastReadLabel, lockedReason, attemptBadge, pipelineLoadingText, runBlockedReason, safeLinks, statusMark } from "@/lib/pipelineDisplay";
import { closeStepForm, shownStepForm, stepFormBlockedReason, stepFormDoneMessage, stepFormFailedMessage, toggleStepForm } from "@/lib/pipelineForms";
import type { StepFormKind, StepFormRequest } from "@/lib/pipelineForms";
import { CaseFlowAmendPanel } from "./CaseFlowAmendPanel";
import { CaseFlowStepForm, stepFormId } from "./CaseFlowStepForm";
import { IconLock } from "./icons";
import { MATTER_MODE_SETTINGS, MODE_WARNING } from "@/lib/pipelineTypes";
import type { MatterModeSetting, PipelineMode, PipelineStep } from "@/lib/pipelineTypes";

export function CaseFlowTab({ matterId, closed = false }: { matterId: string; closed?: boolean }) {
  const { data, error, refresh, setData } = usePipeline(matterId);
  const [running, setRunning] = useState("");
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [modeError, setModeError] = useState("");
  const [clientModeError, setClientModeError] = useState("");
  const [savingClientMode, setSavingClientMode] = useState(false);

  const [forms, setForms] = useState<Record<string, StepFormKind>>({});

  const [focusBack, setFocusBack] = useState<{ opener: string; step: string; turn: number } | null>(null);
  const openers = useRef<Record<string, HTMLButtonElement | null>>({});
  const stepItems = useRef<Record<string, HTMLLIElement | null>>({});

  useEffect(() => {
    setResults({});
    setForms({});
    setClientModeError("");
  }, [matterId]);
  useEffect(() => {
    if (!focusBack) return;
    const opener = openers.current[focusBack.opener];
    if (opener && !opener.disabled) opener.focus();
    else stepItems.current[focusBack.step]?.focus();
  }, [focusBack]);

  const locked = lockedReason(data);

  async function run(step: PipelineStep, variant?: string) {
    const id = `${step.key}:${variant ?? ""}`;
    setRunning(id);
    try {
      const out = await runPipelineStep(matterId, step.key, variant);
      setResults((r) => ({ ...r, [step.key]: { ok: out.ok, message: out.message } }));
      if (out.pipeline) setData(out.pipeline);
    } catch (err) {
      setResults((r) => ({ ...r, [step.key]: { ok: false, message: err instanceof Error ? err.message : "The step did not run." } }));
    } finally {
      setRunning("");
      refresh();
    }
  }

  async function sendDraft(step: PipelineStep) {
    const id = `${step.key}:send`;
    setRunning(id);
    try {
      await sendGameDraft(matterId);
      setResults((r) => ({ ...r, [step.key]: { ok: true, message: "The email was sent." } }));
    } catch (err) {
      setResults((r) => ({ ...r, [step.key]: { ok: false, message: err instanceof Error ? err.message : "The email was not sent." } }));
    } finally {
      setRunning("");
      refresh();
    }
  }

  function toggleForm(step: PipelineStep, kind: StepFormKind) {
    if (running || locked) return;
    setForms((open) => toggleStepForm(open, step.key, kind));
  }

  function closeForm(step: PipelineStep, kind: StepFormKind) {
    setForms((open) => closeStepForm(open, step.key));
    setFocusBack((last) => ({ opener: `${step.key}:${kind}`, step: step.key, turn: (last?.turn ?? 0) + 1 }));
  }

  async function submitForm(step: PipelineStep, request: StepFormRequest): Promise<string> {
    if (locked) return locked;
    if (running) return "A step is running.";
    setRunning(`${step.key}:${request.kind}`);
    try {
      setData(await sendStepForm(matterId, step.key, request));
      setResults((r) => ({ ...r, [step.key]: { ok: true, message: stepFormDoneMessage(request) } }));
      closeForm(step, request.kind);
      return "";
    } catch (err) {
      return err instanceof Error && err.message ? err.message : stepFormFailedMessage(request.kind);
    } finally {
      setRunning("");
      refresh();
    }
  }

  async function changeMode(next: PipelineMode) {
    if (!data || next === data.mode || lockedReason(data)) return;
    setModeError("");
    try {
      await setPipelineMode(next, matterId);
      refresh();
    } catch (err) {
      setModeError(err instanceof Error ? err.message : "Could not change the mode.");
    }
  }

  async function changeClientMode(next: MatterModeSetting) {
    if (!data || next === matterSetting(data)) return;
    const reason = matterModeBlockedReason({ locked: lockedReason(data), busy: savingClientMode });
    if (reason) {
      setClientModeError(reason);
      return;
    }
    setClientModeError("");
    setSavingClientMode(true);
    try {
      await setMatterMode(matterId, next);
    } catch (err) {
      setClientModeError(err instanceof Error ? err.message : "Could not change this client's setting.");
    } finally {
      setSavingClientMode(false);
      refresh();
    }
  }

  function opens(step: PipelineStep, kind: StepFormKind, openForm: StepFormKind | undefined) {
    return {
      ref: (el: HTMLButtonElement | null) => {
        openers.current[`${step.key}:${kind}`] = el;
      },
      "aria-expanded": openForm === kind,
      "aria-controls": openForm === kind ? stepFormId(step.key, kind) : undefined,
      onClick: () => toggleForm(step, kind),
    };
  }

  async function refreshSteps() {
    setRefreshing(true);
    try {
      setData(await fetchPipeline(matterId, false, true));
    } catch (err) {
      setClientModeError(err instanceof Error ? err.message : "Could not refresh.");
    } finally {
      setRefreshing(false);
    }
  }

  if (error && !data) return <p className="cf2-error" role="alert">{error}</p>;
  if (!data) return <PipelineLoading />;
  const own = matterSetting(data);
  const mark = syncMark(data.sync);
  const setBy = matterModeSetBy(data);
  const firmSetBy = firmModeSetBy(data);

  return (
    <div className="cf2">
      <div className="cf2-bar">
        <h2 className="cf2-title">Case Flow</h2>
        <span className="cf2-mode-label" id="cf2-firm-mode-label">Whole firm</span>
        <div className="cf-segment cf2-modes" role="group" aria-labelledby="cf2-firm-mode-label" title={locked || undefined}>
          {(["manual", "auto"] as PipelineMode[]).map((m) => (
            <button key={m} type="button" className="cf-btn cf-btn--segment cf2-mode" aria-pressed={data.mode === m} disabled={locked !== ""} onClick={() => void changeMode(m)}>
              {data.mode === m ? <IconCircleDot aria-hidden="true" /> : <IconCircle aria-hidden="true" />}{" "}
              {m === "manual" ? "Manual" : "Auto"}
            </button>
          ))}
        </div>
        {firmSetBy && <small className="cf2-reason">{firmSetBy}</small>}
        {locked && (
          <span className="cf2-lock" role="img" title={locked} aria-label={locked}>
            <IconLock className="cf2-lock-icon" />
          </span>
        )}
      </div>
      {locked && <p className="cf2-lock-note">{locked}</p>}
      <p className="cf2-warning" data-mode={data.mode}>
        <strong>{data.mode === "auto" ? "Whole firm: Auto is on." : "Whole firm: Manual is on."}</strong> {MODE_WARNING}
      </p>
      {data.steps.some((s) => s.game) && (
        <p className="cf2-lock-note" data-testid="demo-send-note">
          {data.mode === "auto" ? (
            <>
              <strong>Demo, Auto:</strong> Case flow sends every email itself, after a pause to read it. <strong>In Manual:</strong> only the statement emails to the client send themselves, and every other email waits for you to press Send.
            </>
          ) : (
            <>
              <strong>Sent automatically:</strong> the statement emails to the client (Auto or Manual). <strong>Waiting for you to send:</strong> every other email, until you press Send. Switch to Auto and the demo sends those too.
            </>
          )}
        </p>
      )}
      {modeError && <p className="cf2-error" role="alert">{modeError}</p>}
      <div className="cf2-client-mode">
        <span className="cf2-mode-label" id="cf2-client-mode-label">This client</span>
        <div className="cf-segment cf2-modes" role="group" aria-labelledby="cf2-client-mode-label" title={locked || undefined}>
          {MATTER_MODE_SETTINGS.map((choice) => (
            <button
              key={choice}
              type="button"
              className="cf-btn cf-btn--segment cf2-mode cf2-client-choice"
              aria-pressed={own === choice}
              disabled={locked !== "" || savingClientMode}
              onClick={() => void changeClientMode(choice)}
            >
              {own === choice ? <IconCircleDot aria-hidden="true" /> : <IconCircle aria-hidden="true" />}{" "}
              {matterChoiceLabel(choice, data.mode)}
            </button>
          ))}
        </div>
        {setBy && <small className="cf2-reason">{setBy}</small>}
      </div>
      <p className="cf2-warning" data-mode={effectiveMode(data)} role="status">
        <strong>{effectiveMode(data) === "auto" ? "This client: Auto." : "This client: Manual."}</strong> {matterModeSentence(data)}
      </p>
      {autoStalledReason(data) && (
        <p className="cf2-warning" data-mode="manual" role="status">
          <strong>In effect Manual.</strong> Auto is on for this client, but nothing is advancing it: {autoStalledReason(data)}
        </p>
      )}
      {clientModeError && <p className="cf2-error" role="alert">{clientModeError}</p>}
      <div className="cf2-sync" data-attention={mark?.attention ? "true" : undefined} data-scanned={mark?.scanned === false ? "false" : "true"} title={mark?.title}>
        {mark && (
          <>
            <p className="cf2-sync-level"><strong><SyncGlyph level={mark.level} /> {mark.text}</strong></p>
            <p className="cf2-sync-text">
              <span>{mark.title}</span>
              {mark.attention && <span> Needs a look.</span>}
              {mark.stale && <span> ({STALE_TEXT})</span>}
              {mark.regressed.length > 0 && <span> Lost sync since the last scan:</span>}
            </p>
            {mark.regressed.length > 0 && (
              <ul>
                {mark.regressed.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            )}
          </>
        )}
        <div className="cf2-sync-main">
          <span aria-hidden="true" />
          <div className="cf2-sync-middle" />
          <p className="cf2-read no-print">
            {lastReadLabel(data.steps) ? `Steps still to do last read at ${lastReadLabel(data.steps)}. ` : ""}
            <button type="button" className="cf-btn cf-btn--link cf2-refresh" disabled={refreshing} onClick={() => void refreshSteps()}>
              {refreshing ? "Reading…" : "Refresh"}
            </button>
          </p>
        </div>
      </div>
      {error && <p className="cf2-error" role="alert">{error}</p>}

      <ol className="cf2-steps" data-locked={locked ? "true" : undefined}>
        {data.steps.map((step, i) => {
          const mark = statusMark(step.status);
          const result = results[step.key];

          const buttons =
            step.key === "amend" || step.status === "not_needed" ? [] : step.variants.length > 0 ? step.variants.map((v) => ({ key: v.key, label: v.label })) : [{ key: "", label: step.run_label }];
          const links = safeLinks(step.links);
          const openForm = shownStepForm(forms, step, locked);
          return (
            <li
              key={step.key}
              className="cf2-step"
              data-status={step.status}
              tabIndex={-1}
              ref={(el) => {
                stepItems.current[step.key] = el;
              }}
            >
              <div className="cf2-step-head">
                <span className="cf2-number" aria-hidden="true">
                  {step.number ?? i + 1}
                </span>
                <span className="cf2-step-label">{step.label}</span>
                {(() => {
                  const badge = attemptBadge(step);
                  return badge && (
                    <span className="cf2-tries" role="img" aria-label={badge.label} title={badge.label} data-stopped={badge.stopped ? "true" : "false"}>
                      <span className="cf2-tries-word" aria-hidden="true">{badge.text}</span>
                      {Array.from({ length: badge.total }, (_, n) => (
                        <span key={n} className="cf2-try" data-made={n < badge.made ? "true" : "false"} />
                      ))}
                    </span>
                  );
                })()}
                <span className="cf2-mark"><StatusShape shape={mark.shape} /> {mark.word}</span>
              </div>
              {step.summary && <p className="cf2-summary">{step.summary}</p>}
              {step.detail.length > 0 && (
                <ul className="cf2-detail">
                  {step.detail.map((line, n) => (
                    <li key={n}>{line}</li>
                  ))}
                </ul>
              )}
              {links.length > 0 && (
                <ul className="cf2-links" aria-label="Open">
                  {links.map((l) => (
                    <li key={l.url}>
                      <a href={l.url} target="_blank" rel="noreferrer">{l.label}</a>
                    </li>
                  ))}
                </ul>
              )}
              <div className="cf2-actions">
                {(step.can_send ? [] : buttons).map((b) => {
                  const id = `${step.key}:${b.key}`;
                  const isRunning = running === id;
                  const reason = runBlockedReason({ canRun: step.can_run, running: running !== "", locked });
                  return (
                    <span key={id} className="cf2-action">
                      <button type="button" className="cf-btn cf-btn--primary cf2-run" disabled={reason !== ""} title={reason || undefined} onClick={() => void run(step, b.key || undefined)}>
                        {isRunning ? "Running..." : b.label}
                      </button>
                      {reason && !isRunning && <small className="cf2-reason">{reason}</small>}
                    </span>
                  );
                })}
                {step.can_send && (
                  <span className="cf2-action">
                    <button
                      type="button"
                      className="cf-btn cf-btn--primary cf2-run cf2-send"
                      disabled={locked !== "" || running !== ""}
                      title="Send the drafted email, as a person pressing Send in Outlook"
                      onClick={() => void sendDraft(step)}
                    >
                      {running === `${step.key}:send` ? "Sending..." : step.send_label || "Send email"}
                    </button>
                  </span>
                )}
                {!step.game && canConfirmCourt(step) && (
                  <span className="cf2-action">
                    <button
                      type="button"
                      className="cf-btn cf-btn--primary cf2-run"
                      disabled={locked !== "" || running !== ""}
                      title={locked || "Record the court for the court email; nothing is drafted"}
                      {...opens(step, "confirm-court", openForm)}
                    >
                      {running === `${step.key}:confirm-court` ? "Saving..." : "Confirm court"}
                    </button>
                  </span>
                )}
                {!step.game && step.key === "serve" && step.status === "not_needed" && (
                  <span className="cf2-action">
                    <button
                      type="button"
                      className="cf-btn cf-btn--primary cf2-run"
                      disabled={locked !== "" || running !== ""}
                      title={locked || "Record that the respondent is to be served personally; Case flow then drafts the referrer email"}
                      {...opens(step, "require-service", openForm)}
                    >
                      {running === `${step.key}:require-service` ? "Saving..." : "Personal service needed"}
                    </button>
                  </span>
                )}
                {!step.game && step.key === "serve_other" && (
                  <span className="cf2-action">
                    <button
                      type="button"
                      className="cf-btn cf-btn--primary cf2-run"
                      disabled={locked !== "" || running !== ""}
                      title={locked || "Add a law firm, hospital or school to serve"}
                      {...opens(step, "add-recipient", openForm)}
                    >
                      {running === `${step.key}:add-recipient` ? "Saving..." : "Add service recipient"}
                    </button>
                  </span>
                )}
                {!step.game && canMarkDone(step) && (
                  <span className="cf2-action">
                    <button
                      type="button"
                      className="cf-btn cf-btn--secondary cf2-mark-done"
                      disabled={locked !== "" || running !== ""}
                      title={locked || "Record that this was done by hand, outside Case flow"}
                      {...opens(step, "mark-done", openForm)}
                    >
                      {running === `${step.key}:mark-done` ? "Saving..." : "Mark done"}
                    </button>
                  </span>
                )}
                {!step.game && canResetStep(step) && (
                  <span className="cf2-action">
                    <button
                      type="button"
                      className="cf-btn cf-btn--neutral cf2-reset-step"
                      disabled={locked !== "" || running !== ""}
                      title={locked || "Forget this step's mark only. It deletes no files, folders, drafts or envelopes."}
                      {...opens(step, "reset", openForm)}
                    >
                      {running === `${step.key}:reset` ? "Resetting..." : "Reset"}
                    </button>
                  </span>
                )}
              </div>
              {!step.game && step.key === "amend" && step.amend && (
                <CaseFlowAmendPanel
                  matterId={matterId}
                  step={step}
                  locked={locked}
                  running={running}
                  setRunning={setRunning}
                  setData={setData}
                  refresh={refresh}
                />
              )}
              {openForm && (
                <CaseFlowStepForm
                  key={`${step.key}:${openForm}`}
                  kind={openForm}
                  step={step}
                  busy={running === `${step.key}:${openForm}`}
                  blocked={stepFormBlockedReason({ running, busy: running === `${step.key}:${openForm}` })}
                  onSubmit={(request) => submitForm(step, request)}
                  onCancel={() => closeForm(step, openForm)}
                />
              )}
              {result && (
                <p className={result.ok ? "cf2-result" : "cf2-error"} role={result.ok ? "status" : "alert"}>
                  {result.ok ? "Done: " : "Not done: "}
                  {result.message}
                </p>
              )}
            </li>
          );
        })}
      </ol>
      <p className="cf2-note">Reset beside a step forgets only that step&apos;s mark, then checks the step again. It deletes no files, folders, drafts or envelopes. What ran is in the Activity log tab.</p>
    </div>
  );
}

function PipelineLoading() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds((Date.now() - started) / 1000), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <p className="cf2-empty cf2-loading" role="status" aria-live="polite">
      <span className="cf2-loading-dot" aria-hidden="true" /> {pipelineLoadingText(seconds)}
    </p>
  );
}
