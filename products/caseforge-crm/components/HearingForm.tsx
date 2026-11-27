"use client";

import type { HearingFormValues, HearingMode, HearingNotice } from "@/lib/hearings";
import { HEARING_MODES, HEARING_NOTICES } from "@/lib/hearings";

export function HearingForm({
  values,
  onChange,
  errors,
  warnings,
  idPrefix,
  disabled = false,
  autoFocusField,
}: {
  values: HearingFormValues;
  onChange: (next: HearingFormValues) => void;
  errors: Record<string, string>;
  warnings: string[];
  idPrefix: string;
  disabled?: boolean;
  autoFocusField?: keyof HearingFormValues;
}) {
  function set<K extends keyof HearingFormValues>(key: K, value: HearingFormValues[K]) {
    onChange({ ...values, [key]: value });
  }

  function field(
    key: keyof HearingFormValues,
    label: string,
    opts: { type?: string; placeholder?: string; inputMode?: "numeric" | "text"; autoComplete?: string; wide?: boolean } = {},
  ) {
    const id = `${idPrefix}-${key}`;
    const error = errors[key];
    return (
      <div className={`hearing-form-field${opts.wide ? " hearing-form-field--wide" : ""}`}>
        <label htmlFor={id} className="hearing-form-label">
          {label}
        </label>
        <input
          id={id}
          className="edit-input"
          type={opts.type ?? "text"}
          inputMode={opts.inputMode}
          value={String(values[key] ?? "")}
          placeholder={opts.placeholder}
          disabled={disabled}
          autoComplete={opts.autoComplete ?? "off"}
          autoFocus={autoFocusField === key}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(e) => set(key, e.target.value as never)}
        />
        {error && (
          <p id={`${id}-error`} className="hearing-form-error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="hearing-form">
      <div className="hearing-form-grid">
        {field("case_ref", "Court case number", { placeholder: "e.g. AB26F11111" })}
        {field("matter_id", "Matter ID (optional)", { inputMode: "numeric" })}
        {field("hearing_date", "Date", { type: "date" })}
        {field("hearing_time", "Time (24-hour)", { type: "time", placeholder: "14:00" })}
        {field("duration_minutes", "Duration (minutes)", { inputMode: "numeric", placeholder: "Not stated" })}
        {field("hearing_type", "Hearing type", { placeholder: "e.g. FHDRA, Directions" })}
        {field("order_types", "Order types", { placeholder: "e.g. NMO/OO" })}
        <div className="hearing-form-field">
          <label htmlFor={`${idPrefix}-mode`} className="hearing-form-label">
            Mode
          </label>
          <select
            id={`${idPrefix}-mode`}
            className="edit-input"
            value={values.mode}
            disabled={disabled}
            onChange={(e) => set("mode", e.target.value as HearingMode)}
          >
            {HEARING_MODES.map((mode) => (
              <option key={mode.value} value={mode.value}>
                {mode.label}
              </option>
            ))}
          </select>
        </div>
        <div className="hearing-form-field">
          <label htmlFor={`${idPrefix}-notice`} className="hearing-form-label">
            Notice
          </label>
          <select
            id={`${idPrefix}-notice`}
            className="edit-input"
            value={values.notice}
            disabled={disabled}
            onChange={(e) => set("notice", e.target.value as HearingNotice)}
          >
            {HEARING_NOTICES.map((notice) => (
              <option key={notice.value} value={notice.value}>
                {notice.label}
              </option>
            ))}
          </select>
        </div>
        {field("court", "Court", { wide: true })}
        {field("applicant", "Applicant")}
        {field("respondent", "Respondent")}
        {field("counsel", "Counsel")}
        {field("chambers", "Chambers")}
        {field("join_url", "Join link", { type: "url", placeholder: "https://", wide: true })}
        <div className="hearing-form-field hearing-form-field--wide">
          <label htmlFor={`${idPrefix}-notes`} className="hearing-form-label">
            Notes
          </label>
          <textarea
            id={`${idPrefix}-notes`}
            className="edit-input edit-textarea"
            rows={3}
            value={values.notes}
            disabled={disabled}
            onChange={(e) => set("notes", e.target.value)}
          />
        </div>
        <div className="hearing-form-field hearing-form-field--wide edit-form-checkbox-field">
          <label className="edit-form-checkbox-label">
            <input
              type="checkbox"
              checked={values.is_final}
              disabled={disabled}
              onChange={(e) => set("is_final", e.target.checked)}
            />
            Final hearing
          </label>
        </div>
      </div>
      {warnings.length > 0 && (
        <ul className="hearing-form-warnings" role="status">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
