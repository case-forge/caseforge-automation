"use client";

import { useEffect, useState } from "react";
import { makeLexcelLetter, setLexcelAuto, useLexcel } from "@/lib/lexcel";
import { REGENERATE_QUESTION, autoLine, checklistGaps, generateBlockedReason, generateLabel, lexcelRow, openingRegenerate } from "@/lib/lexcelTypes";
import type { LexcelKind, LexcelLetter } from "@/lib/lexcelTypes";
import { safeLinks } from "@/lib/pipelineDisplay";
import type { PipelineLink, PipelineVariant } from "@/lib/pipelineTypes";
import { IconCheck } from "./icons";

interface Outcome {
  ok: boolean;
  message: string;
  offers: PipelineVariant[];
  links: PipelineLink[];
}

const ROWS: { kind: LexcelKind; label: string }[] = [
  { kind: "opening", label: "Opening client care letter" },
  { kind: "mid", label: "Court outcome letter" },
  { kind: "closing", label: "Closing letter" },
];

export function LexcelLetters({ matterId }: { matterId: string }) {
  const { data, error, setData, refresh } = useLexcel(matterId);
  const [running, setRunning] = useState("");
  const [hearingKey, setHearingKey] = useState("");
  const [outcomes, setOutcomes] = useState<Partial<Record<LexcelKind, Outcome>>>({});

  const [confirming, setConfirming] = useState<LexcelKind | "">("");

  useEffect(() => {
    setOutcomes({});
    setConfirming("");
  }, [matterId]);

  async function make(letter: LexcelLetter, variant?: string, confirmed = false) {
    if (running) return;
    const again = generateLabel(letter) === "Regenerate";
    const gaps = checklistGaps(letter);
    const missing = gaps.length > 0 ? ` Missing: ${gaps.map((g) => g.label.toLowerCase()).join(", ")}.` : "";
    if (!confirmed && !window.confirm(`${again ? "Make this letter again" : letter.button} for this client? It is made as a draft beside any existing letter: nothing is sent and nothing is replaced.${missing}`)) return;
    setRunning(`${letter.kind}:${variant ?? ""}`);
    try {
      const out = await makeLexcelLetter(matterId, letter.kind, variant);
      setData(out.lexcel);
      setOutcomes((o) => ({ ...o, [letter.kind]: { ok: out.ok, message: out.message, offers: out.offers ?? [], links: out.links ?? [] } }));
    } catch (err) {
      setOutcomes((o) => ({ ...o, [letter.kind]: { ok: false, message: err instanceof Error ? err.message : "The letter was not made.", offers: [], links: [] } }));
    } finally {
      setRunning("");
    }
  }

  async function switchAuto(letter: LexcelLetter, resume: boolean) {
    if (running) return;
    if (!resume && !window.confirm(`Cancel the automatic client care letter for this client? Case flow will not make it by itself. Make now still makes it.`)) return;
    setRunning(`${letter.kind}:auto`);
    try {
      const out = await setLexcelAuto(matterId, resume);
      setOutcomes((o) => ({ ...o, [letter.kind]: { ok: out.ok, message: out.message, offers: [], links: [] } }));
      refresh();
    } catch (err) {
      setOutcomes((o) => ({ ...o, [letter.kind]: { ok: false, message: err instanceof Error ? err.message : "That did not go through.", offers: [], links: [] } }));
    } finally {
      setRunning("");
    }
  }

  const failed = error !== "" && !data;
  return (
    <>
      <div className="detail-grid lexcel-rows">
        {ROWS.map((fixed) => {
          const letter = data?.letters.find((l) => l.kind === fixed.kind);
          const view = lexcelRow(letter, failed);
          const outcome = outcomes[fixed.kind];
          const reason = generateBlockedReason({ canGenerate: view.canGenerate, running: running !== "", made: letter?.made === true });
          const regen = openingRegenerate(letter, { confirming: confirming === fixed.kind, running: running.startsWith(`${fixed.kind}:`), outcome });

          const extra = [...safeLinks(view.more), ...safeLinks(outcome?.links).filter((l) => l.url !== view.url && !view.more.some((m) => m.url === l.url))];
          return (
            <div key={fixed.kind} className="detail-field matter-marker lexcel-row" data-state={view.state}>
              <p className="detail-field-label" title="Made by the system as a draft, on request. Nothing is sent. The client's folders are not searched for one.">
                {fixed.label}
              </p>
              <p className="matter-marker-value">
                <span className="matter-marker-box" aria-hidden="true">
                  {view.state === "received" && <IconCheck width={13} height={13} strokeWidth={3} />}
                </span>
                {view.url ? (
                  <a className="matter-marker-link" href={view.url} target="_blank" rel="noreferrer" title={`${view.title} Open the letter.`}>
                    {view.text}
                  </a>
                ) : (
                  <span title={view.title || undefined}>{view.text}</span>
                )}
              </p>
              {(() => {

                const counting = autoLine(letter);
                if (counting) return <p className="lexcel-auto" data-held={letter?.auto?.held || letter?.auto?.cancelled ? "yes" : "no"}>{counting}</p>;
                const gaps = checklistGaps(letter);
                const all = letter?.checklist ?? [];
                if (all.length === 0) return null;
                return (
                  <ul className="lexcel-checklist" aria-label={`Before generating: ${gaps.length === 0 ? "nothing missing" : `${gaps.length} to note`}`}>
                    {all.map((c) => (
                      <li key={c.key} data-ok={c.ok ? "yes" : "no"} title={c.ok ? undefined : c.note}>
                        <span aria-hidden="true">{c.ok ? "\u2713" : "!"}</span> {c.label}
                        {!c.ok && c.note ? <span className="lexcel-checklist-note"> {c.note}</span> : null}
                      </li>
                    ))}
                  </ul>
                );
              })()}
              {extra.length > 0 && (
                <ul className="lexcel-links" aria-label="Open">
                  {extra.map((l) => (
                    <li key={l.url}>
                      <a href={l.url} target="_blank" rel="noreferrer">{l.label}</a>
                    </li>
                  ))}
                </ul>
              )}
              <div className="lexcel-actions">
                {fixed.kind === "mid" && (letter?.hearings?.length ?? 0) > 0 && (
                  <select
                    className="edit-input lexcel-hearing"
                    aria-label="Hearing to make the letter for"
                    value={hearingKey}
                    onChange={(event) => setHearingKey(event.target.value)}
                  >
                    <option value="">Next hearing without a letter</option>
                    {(letter?.hearings ?? []).map((h) => (
                      <option key={h.key} value={h.key}>{h.label}</option>
                    ))}
                  </select>
                )}
                <button
                  type="button"
                  className="cf-btn cf-btn--neutral lexcel-generate"
                  disabled={!letter || reason !== "" || regen?.disabled === true}
                  data-regenerate={regen?.state}
                  title={reason || regen?.title || (letter ? `${letter.button}, as a draft. Nothing is sent and nothing is replaced.` : undefined)}
                  onClick={() => {
                    if (!letter) return;
                    if (regen) return setConfirming(fixed.kind);
                    void make(letter, fixed.kind === "mid" && hearingKey ? hearingKey : generateLabel(letter) === "Regenerate" && !(fixed.kind === "mid" && letter.can_make) ? "regenerate" : undefined);
                  }}
                >
                  {running.startsWith(`${fixed.kind}:`) && running !== `${fixed.kind}:auto` ? "Generating…" : autoLine(letter) ? "Make now" : generateLabel(letter)}
                </button>
                {letter && autoLine(letter) && (
                  <button
                    type="button"
                    className="cf-btn cf-btn--neutral lexcel-auto-switch"
                    disabled={running !== ""}
                    title={letter.auto?.cancelled ? "Let Case flow make the letter by itself again." : "Stop Case flow making the letter by itself. Make now still makes it."}
                    onClick={() => void switchAuto(letter, letter.auto?.cancelled === true)}
                  >
                    {letter.auto?.cancelled ? "Switch back on" : "Cancel"}
                  </button>
                )}
                {letter &&
                  (outcome?.offers ?? []).map((offer) => (
                    <button key={offer.key} type="button" className="cf-btn cf-btn--neutral lexcel-offer" disabled={running !== ""} onClick={() => void make(letter, offer.key)}>
                      {running === `${fixed.kind}:${offer.key}` ? "Generating…" : offer.label}
                    </button>
                  ))}
              </div>
              {regen?.state === "confirming" && letter && (
                <div className="lexcel-confirm" role="group" aria-label="Make the opening letter again?">
                  <p>{REGENERATE_QUESTION}</p>
                  <div className="lexcel-actions">
                    <button
                      type="button"
                      className="cf-btn cf-btn--secondary lexcel-confirm-yes"
                      onClick={() => {
                        setConfirming("");
                        void make(letter, "regenerate", true);
                      }}
                    >
                      Yes, make a new letter
                    </button>
                    <button type="button" className="cf-btn cf-btn--flush lexcel-confirm-no" onClick={() => setConfirming("")}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              {regen?.state === "refused" && <p className="lexcel-note lexcel-locked">Regenerate is not available: {regen.title}</p>}
              {view.note && <p className="lexcel-note">{view.note}</p>}
              {outcome && (
                <p className={outcome.ok ? "lexcel-result" : "client-edits-error lexcel-refusal"} role={outcome.ok ? "status" : "alert"}>
                  {outcome.ok ? "Done: " : /^not made\b/i.test(outcome.message) ? "" : "Not made: "}
                  {outcome.message}
                </p>
              )}
            </div>
          );
        })}
      </div>
      {error && data && <p className="client-edits-error" role="alert">{error}</p>}
    </>
  );
}
