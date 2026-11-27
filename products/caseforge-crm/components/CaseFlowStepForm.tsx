"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { useSignedInName } from "@/lib/editorName";
import { courtSuggestionLabel } from "@/lib/pipelineDisplay";
import { FIELD_LIMITS, blankStepForm, checkStepForm, stepFormCopy } from "@/lib/pipelineForms";
import type { StepFormErrors, StepFormField, StepFormKind, StepFormRequest, StepFormValues } from "@/lib/pipelineForms";
import { SERVICE_RECIPIENT_KINDS } from "@/lib/pipelineTypes";
import type { PipelineStep } from "@/lib/pipelineTypes";

export function stepFormId(stepKey: string, kind: StepFormKind): string {
  return `cf2-form-${stepKey}-${kind}`;
}

function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="cf2-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <small className="cf2-field-hint" id={`${id}-hint`}>{hint}</small>}
      {error && <small className="cf2-field-error" id={`${id}-error`} role="alert">{error}</small>}
    </div>
  );
}

function describedBy(id: string, hint: boolean, error: boolean): string | undefined {
  return [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
}

export interface CaseFlowStepFormViewProps {
  kind: StepFormKind;
  step: PipelineStep;
  values: StepFormValues;
  errors: StepFormErrors;

  serverError: string;

  busy: boolean;

  blocked: string;

  who: string;
  onChange: (field: StepFormField, value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

export function CaseFlowStepFormView({ kind, step, values, errors, serverError, busy, blocked, who, onChange, onSubmit, onCancel }: CaseFlowStepFormViewProps) {
  const id = stepFormId(step.key, kind);
  const copy = stepFormCopy(kind, step, values, who);
  const suggestions = step.court_suggestions ?? [];

  function onKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (!busy) onCancel();
    } else if (event.key === "Enter" && event.target instanceof HTMLSelectElement) {

      event.preventDefault();
      event.currentTarget.requestSubmit();
    }
  }

  function text(field: StepFormField, label: string, limit: number, extra?: { hint?: string; email?: boolean }) {
    const fieldId = `${id}-${field}`;
    const error = errors[field];
    return (
      <Field id={fieldId} label={label} hint={extra?.hint} error={error}>
        <input
          id={fieldId}
          type="text"
          inputMode={extra?.email ? "email" : undefined}
          autoComplete="off"
          spellCheck={extra?.email ? false : undefined}
          value={values[field]}
          maxLength={limit}
          disabled={busy}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(fieldId, Boolean(extra?.hint), Boolean(error))}
          onChange={(e) => onChange(field, e.target.value)}
        />
      </Field>
    );
  }

  return (
    <form
      className="cf2-form"
      id={id}
      noValidate
      aria-labelledby={`${id}-title`}
      aria-busy={busy || undefined}
      data-kind={kind}
      onKeyDown={onKeyDown}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <p className="cf2-form-title" id={`${id}-title`}>{copy.title}</p>
      <p className="cf2-form-explain">{copy.explain}</p>

      {kind === "mark-done" && text("note", "Note (optional)", FIELD_LIMITS.note, { hint: `${values.note.length} of ${FIELD_LIMITS.note} characters` })}

      {kind === "confirm-court" && (
        <>
          {text("court", "Court", FIELD_LIMITS.court, { hint: "The court's name as the court finder gives it. Leave it empty to give only its email." })}
          {suggestions.length > 0 ? (
            <ul className="cf2-suggestions" aria-label="Courts the court finder suggests">
              {suggestions.map((s) => (
                <li key={s.name}>
                  <button type="button" className="cf-btn cf-btn--neutral cf2-suggestion" aria-pressed={values.court.trim() === s.name} disabled={busy} onClick={() => onChange("court", s.name)}>
                    {courtSuggestionLabel(s)}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cf2-form-explain">No suggestion from the court finder.</p>
          )}
          {text("email", "Court's email (optional)", FIELD_LIMITS.email, { hint: "Leave it empty to use the court finder's.", email: true })}
        </>
      )}

      {kind === "add-recipient" && (
        <>
          <Field id={`${id}-kind`} label="Who they are" error={errors.kind}>
            <select
              id={`${id}-kind`}
              value={values.kind}
              disabled={busy}
              aria-invalid={errors.kind ? true : undefined}
              aria-describedby={describedBy(`${id}-kind`, false, Boolean(errors.kind))}
              onChange={(e) => onChange("kind", e.target.value)}
            >
              {SERVICE_RECIPIENT_KINDS.map((k) => (
                <option key={k} value={k}>{k.charAt(0).toUpperCase() + k.slice(1)}</option>
              ))}
            </select>
          </Field>
          {text("recipient", "Their name", FIELD_LIMITS.recipient)}
          {text("email", "Their email address", FIELD_LIMITS.email, { email: true })}
        </>
      )}

      {serverError && (
        <p className="cf2-error" role="alert">
          Not done: {serverError}
        </p>
      )}
      <div className="cf2-form-buttons">
        <button type="submit" className="cf-btn cf-btn--primary cf2-run" disabled={busy || blocked !== ""} title={blocked || undefined}>
          {busy ? copy.busy : copy.submit}
        </button>
        <button type="button" className="cf-btn cf-btn--neutral cf2-reset-step" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        {blocked && !busy && <small className="cf2-reason">{blocked}</small>}
      </div>
    </form>
  );
}

export function CaseFlowStepForm({
  kind,
  step,
  busy,
  blocked,
  onSubmit,
  onCancel,
}: {
  kind: StepFormKind;
  step: PipelineStep;
  busy: boolean;
  blocked: string;
  onSubmit: (request: StepFormRequest) => Promise<string>;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<StepFormValues>(() => blankStepForm(kind, step));
  const [errors, setErrors] = useState<StepFormErrors>({});
  const [serverError, setServerError] = useState("");

  const [refusals, setRefusals] = useState(0);
  const holder = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const first = holder.current?.querySelector<HTMLElement>("input, select, button[type=submit]");
    const wrong = refusals > 0 ? holder.current?.querySelector<HTMLElement>('[aria-invalid="true"]') : null;
    (wrong ?? first)?.focus();
  }, [refusals]);

  const who = useSignedInName();

  async function submit() {
    if (busy || blocked) return;
    const checked = checkStepForm(kind, values);
    setServerError("");
    if ("errors" in checked) {
      setErrors(checked.errors);
      setRefusals((n) => n + 1);
      return;
    }
    setErrors({});
    const failure = await onSubmit(checked.request);
    if (failure) {
      setServerError(failure);
      setRefusals((n) => n + 1);
    }
  }

  return (
    <div ref={holder} className="cf2-form-holder">
      <CaseFlowStepFormView
        kind={kind}
        step={step}
        values={values}
        errors={errors}
        serverError={serverError}
        busy={busy}
        blocked={blocked}
        who={who}
        onChange={(field, value) => {
          setValues((v) => ({ ...v, [field]: value }));

          const cleared: string[] = kind === "confirm-court" && field === "email" ? ["email", "court"] : [field];
          setErrors((e) => (cleared.some((key) => key in e) ? Object.fromEntries(Object.entries(e).filter(([key]) => !cleared.includes(key))) : e));
        }}
        onSubmit={() => void submit()}
        onCancel={onCancel}
      />
    </div>
  );
}
