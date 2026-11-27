"use client";

import { useState, type ReactNode } from "react";
import {
  asText,
  sameDraft,
  fieldForError,
  LEGAL_AID_RATE_PREFIX,
  readDraft,
  saveSettings,
  setOperation,
  type AppSetting,
  type AppSettingsView,
  type Draft,
  type Person,
  type Sendable,
} from "@/lib/appSettings";
import { IconLock } from "./icons";

function LockNote({ env }: { env: string }) {
  return (
    <p className="settings-field-lock">
      <IconLock aria-hidden="true" /> Set by environment ({env}). It cannot be changed here.
    </p>
  );
}

function initial(setting: AppSetting): Draft {
  if (setting.type === "people") return (setting.value as Person[]).map((p) => ({ ...p }));
  return setting.type === "bool" ? Boolean(setting.value) : setting.source === "default" ? "" : asText(setting.value);
}

function PeopleField({ setting, draft, error, disabled, onChange }: { setting: AppSetting; draft: Person[]; error: string; disabled: boolean; onChange: (value: Person[]) => void }) {
  const [editing, setEditing] = useState(false);
  const set = (i: number, patch: Partial<Person>) => onChange(draft.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <div className={error ? "settings-field settings-field--error" : "settings-field"}>
      <p className="settings-field-label">{setting.label}</p>
      {editing ? (
        <ul className="settings-people" aria-label={setting.label}>
          {draft.map((p, i) => (
            <li key={i} className="settings-person">
              <input className="settings-field-input" aria-label={`Name of solicitor ${i + 1}`} value={p.name} onChange={(e) => set(i, { name: e.target.value })} />
              <input className="settings-field-input" type="email" aria-label={`Email of solicitor ${i + 1}`} value={p.email} onChange={(e) => set(i, { email: e.target.value })} />
              <input className="settings-field-input" aria-label={`Role label of solicitor ${i + 1}`} value={p.role} onChange={(e) => set(i, { role: e.target.value })} />
              <button type="button" className="cf-btn cf-btn--flush cf-btn--small" disabled={draft.length < 2} onClick={() => onChange(draft.filter((_, j) => j !== i))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="settings-people settings-people--read" aria-label={setting.label}>
          {draft.map((p, i) => (
            <li key={i}>
              <strong>{p.name}</strong> <span className="settings-field-help">{p.email}{p.role ? `, ${p.role}` : ""}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="settings-field-help">{setting.help}</p>
      {!disabled && (
        <div className="settings-logo-actions">
          {editing ? (
            <>
              <button type="button" className="cf-btn cf-btn--secondary cf-btn--small" disabled={draft.length >= 20} onClick={() => onChange([...draft, { name: "", email: "", role: "" }])}>
                Add a solicitor
              </button>
              <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" onClick={() => setEditing(false)}>
                Done editing
              </button>
            </>
          ) : (
            <button type="button" className="cf-btn cf-btn--secondary cf-btn--small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
      )}
      {setting.locked && <LockNote env={setting.env} />}
      {error && (
        <p className="settings-field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function Field({
  setting,
  draft,
  error,
  disabled,
  onChange,
  names,
}: {
  setting: AppSetting;
  draft: Draft;
  error: string;
  disabled: boolean;
  onChange: (value: Draft) => void;
  names?: string[];
}) {
  const id = `setting-${setting.key}`;
  if (setting.type === "people") {
    return <PeopleField setting={setting} draft={draft as Person[]} error={error} disabled={disabled} onChange={onChange} />;
  }
  const describedBy = `${id}-help`;
  const common = { id, disabled, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined } as const;
  let control;
  if (setting.type === "bool") {
    control = (
      <div className="cf-segment" role="group" aria-label={setting.label}>
        <button type="button" className="cf-btn cf-btn--segment" aria-pressed={draft === true} disabled={disabled} onClick={() => onChange(true)}>
          On
        </button>
        <button type="button" className="cf-btn cf-btn--segment" aria-pressed={draft === false} disabled={disabled} onClick={() => onChange(false)}>
          Off
        </button>
      </div>
    );
  } else if (setting.type === "person_choice") {
    const options = names ?? setting.choices;
    control = (
      <select {...common} className="settings-field-input" value={String(draft || setting.value)} onChange={(e) => onChange(e.target.value)}>
        {options.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    );
  } else if (setting.type === "enum") {
    control = (
      <select {...common} className="settings-field-input" value={String(draft || setting.default)} onChange={(e) => onChange(e.target.value)}>
        {setting.choices.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    );
  } else {
    control = (
      <input
        {...common}
        className="settings-field-input"
        type={setting.type === "email" ? "email" : "text"}
        inputMode={setting.type === "int" ? "numeric" : undefined}
        value={String(draft as string)}
        placeholder={`Default: ${asText(setting.default)}`}
        maxLength={setting.max_length ?? undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <div className={error ? "settings-field settings-field--error" : "settings-field"}>
      <label className="settings-field-label" htmlFor={id}>
        {setting.label}
      </label>
      <div className="settings-field-control">{control}</div>
      <p id={describedBy} className="settings-field-help">
        {setting.help}
        {setting.restart_required ? " Applies to programs started after saving." : ""}
      </p>
      {setting.locked && <LockNote env={setting.env} />}
      {setting.env_invalid && !setting.locked && <p className="settings-field-lock">The environment value ({setting.env}) is not valid and is ignored.</p>}
      {error && (
        <p className="settings-field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function SettingsGroupPanel({ groups, view, onView, after }: { groups: string[]; view: AppSettingsView; onView: (view: AppSettingsView) => void; after?: ReactNode }) {
  const infos = groups.map((key) => view.groups.find((g) => g.key === key)).filter((g): g is NonNullable<typeof g> => Boolean(g));
  const settings = view.settings.filter((s) => groups.includes(s.group));
  const isOperations = groups.includes("operations");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState("");
  const canEdit = view.can_edit;

  const draftOf = (s: AppSetting): Draft => (s.key in drafts ? drafts[s.key] : initial(s));
  const changed = settings.filter((s) => s.writable && !s.locked && s.key in drafts && !sameDraft(drafts[s.key], initial(s)));
  const peopleSetting = settings.find((s) => s.type === "people");
  const solicitorNames = peopleSetting ? (draftOf(peopleSetting) as Person[]).map((p) => p.name.trim()).filter(Boolean) : undefined;

  const rateSettings = settings.filter((s) => s.key.startsWith(LEGAL_AID_RATE_PREFIX) && s.writable && !s.locked);
  const ratesEdited = rateSettings.some((s) => s.source !== "default" || s.key in drafts);

  async function restoreRates() {
    setErrors({});
    setFormError("");
    setNote("");
    setSaving(true);
    const result = await saveSettings(Object.fromEntries(rateSettings.map((s) => [s.key, ""])));
    setSaving(false);
    if (!result.ok) {
      setFormError(result.message);
      return;
    }
    setDrafts((d) => Object.fromEntries(Object.entries(d).filter(([key]) => !key.startsWith(LEGAL_AID_RATE_PREFIX))));
    onView(result.view);
    setNote("The standard legal aid rates are back.");
  }

  const [confirming, setConfirming] = useState("");

  async function flip(key: string, held: boolean) {
    setConfirming("");
    setFormError("");
    setNote("");
    setSaving(true);
    const result = await setOperation(key, held);
    setSaving(false);
    if (!result.ok) {
      setFormError(result.message);
      return;
    }
    onView(result.view);
    setNote(held ? "Held. It applies from now." : "Released. It applies from now.");
  }

  async function save() {
    const found: Record<string, string> = {};
    const values: Record<string, Sendable> = {};
    for (const s of changed) {
      const read = readDraft(s, drafts[s.key]);
      if (read.ok) values[s.key] = read.value;
      else found[s.key] = read.error;
    }
    setErrors(found);
    setFormError("");
    setNote("");
    if (Object.keys(found).length > 0 || Object.keys(values).length === 0) return;
    setSaving(true);
    const result = await saveSettings(values);
    setSaving(false);
    if (!result.ok) {
      const key = fieldForError(result.message, settings);
      if (key) setErrors({ [key]: result.message });
      else setFormError(result.message);
      return;
    }
    const restart = changed.some((s) => s.restart_required);
    setDrafts({});
    onView(result.view);
    setNote(restart ? "Saved. Programs already running use the old value until they are restarted." : "Saved. It applies from now.");
  }

  const status = isOperations ? view.status : [];
  return (
    <div className="settings-group">
      {infos.map((info) => (
        <p key={info.key} className="settings-group-intro">{info.description}</p>
      ))}
      {!canEdit && !isOperations && <p className="settings-group-intro">Only an administrator can change these.</p>}
      {settings.map((s) => (
        <Field
          key={s.key}
          setting={s}
          draft={draftOf(s)}
          names={solicitorNames}
          error={errors[s.key] ?? ""}
          disabled={!canEdit || s.locked || !s.writable || saving}
          onChange={(value) => {
            setDrafts((d) => ({ ...d, [s.key]: value }));
            setErrors((e) => ({ ...e, [s.key]: "" }));
            setNote("");
          }}
        />
      ))}
      {after}
      {status.map((st) => (
        <div key={st.key} className="settings-field">
          <p className="settings-field-label">{st.label}</p>
          <p className={st.held ? "settings-status settings-status--held" : "settings-status"}>{st.held ? `Held: ${st.reason}` : "Running"}</p>
          <p className="settings-field-help">{st.help}</p>
          {canEdit && (
            <div className="settings-logo-actions">
              {!st.held ? (
                <button type="button" className="cf-btn cf-btn--secondary cf-btn--small" disabled={saving} onClick={() => void flip(st.key, true)}>
                  Hold
                </button>
              ) : confirming === st.key ? (
                <>
                  <button type="button" className="cf-btn cf-btn--primary cf-btn--small" disabled={saving} onClick={() => void flip(st.key, false)}>
                    Confirm release
                  </button>
                  <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" onClick={() => setConfirming("")}>
                    Cancel
                  </button>
                </>
              ) : (
                <button type="button" className="cf-btn cf-btn--secondary cf-btn--small" disabled={saving} onClick={() => setConfirming(st.key)}>
                  Release
                </button>
              )}
            </div>
          )}
        </div>
      ))}
      {isOperations && (note || formError) && (
        <p className={formError ? "settings-field-error" : "settings-save-note"} role={formError ? "alert" : "status"}>
          {formError || note}
        </p>
      )}
      {isOperations && <p className="settings-field-help">{view.secrets_note}</p>}
      {settings.some((s) => s.writable) && canEdit && (
        <div className="settings-save">
          <button type="button" className="cf-btn cf-btn--primary" disabled={saving || changed.length === 0} onClick={() => void save()}>
            {saving ? "Saving" : "Save"}
          </button>
          {rateSettings.length > 0 && (
            <button type="button" className="cf-btn cf-btn--secondary" disabled={saving || !ratesEdited} onClick={() => void restoreRates()}>
              Restore standard rates
            </button>
          )}
          {changed.length > 0 && !saving && (
            <button type="button" className="cf-btn cf-btn--neutral" onClick={() => { setDrafts({}); setErrors({}); setFormError(""); }}>
              Discard changes
            </button>
          )}
          <span className="settings-save-note" role="status" aria-live="polite">
            {note}
          </span>
          {formError && (
            <span className="settings-field-error" role="alert">
              {formError}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
