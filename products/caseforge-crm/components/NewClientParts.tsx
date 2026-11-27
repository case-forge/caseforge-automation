
import type { Ref } from "react";
import { cleanPhone, previewSections, type NewClientPreview } from "@/lib/newClient";

export type Category = { key: string; label: string };

export function NewClientChoice({ onEmail, onManual, onCancel }: { onEmail: () => void; onManual: () => void; onCancel: () => void }) {
  return (
    <div className="new-client-choice">
      <p className="new-client-note">How do you want to add the client?</p>
      <div className="new-client-actions new-client-actions--choice">
        <button type="button" className="cf-btn cf-btn--primary" onClick={onEmail}>Add client by email</button>
        <button type="button" className="cf-btn cf-btn--primary" onClick={onManual}>Add client manually</button>
        <button type="button" className="cf-btn cf-btn--flush dialog-button--quiet" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export function PhoneField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const check = cleanPhone(value);
  return (
    <label>
      Phone number (optional)
      <input
        type="tel"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
        inputMode="tel"
        placeholder="07700 900123 or +44 7700 900123"
        aria-invalid={check.ok ? undefined : true}
        aria-describedby="new-client-phone-note"
      />
      <span id="new-client-phone-note" className="new-client-note">
        {check.ok ? "Not needed to make the client. It is kept so they can be rung for an update before they sign." : check.error}
      </span>
    </label>
  );
}

export function PreviewCreateActions({
  ready, busy, blocked, hasPreview, onCancel, onPreview, onCreate,
}: {
  ready: boolean;
  busy: boolean;
  blocked?: boolean;
  hasPreview: boolean;
  onCancel: () => void;
  onPreview: () => void;
  onCreate: () => void;
}) {
  const off = !ready || busy || Boolean(blocked);
  return (
    <div className="new-client-actions">
      <button type="button" className="cf-btn cf-btn--flush dialog-button--quiet" onClick={onCancel}>Cancel</button>
      <button type="button" className={`cf-btn ${hasPreview ? "cf-btn--secondary" : "cf-btn--primary"}`} disabled={off} onClick={onPreview}>{busy && !hasPreview ? "Working…" : "Preview"}</button>
      {hasPreview && (
        <button type="button" className="cf-btn cf-btn--primary" disabled={off} onClick={onCreate}>{busy ? "Working…" : "Create"}</button>
      )}
    </div>
  );
}

export function PreviewBox({ preview }: { preview: NewClientPreview | null }) {
  if (!preview) return null;
  return (
    <div className="new-client-preview" aria-live="polite">
      <p className="new-client-preview-head">Preview: nothing has been made. Create would make:</p>
      {previewSections(preview).map((section) => (
        <div key={section.title}>
          <h3>{section.title}</h3>
          <ul>
            {section.lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export type ManualFormValues = {
  first: string;
  last: string;
  email: string;
  phone: string;
  category: string;
  middle: string;
  dob: string;
  nino: string;
  address1: string;
  address2: string;
  address3: string;
  address4: string;
  postcode: string;
  matterDetails: string;
};

export const BLANK_MANUAL_EXTRAS = {
  middle: "", dob: "", nino: "", address1: "", address2: "", address3: "", address4: "", postcode: "", matterDetails: "",
};

export function ManualFields({
  values, categories, onChange, firstRef, addressCheck, addressChecked, onAddressChecked,
}: {
  values: ManualFormValues;
  categories: Category[];
  onChange: (patch: Partial<ManualFormValues>) => void;
  firstRef?: Ref<HTMLInputElement>;
  addressCheck: boolean;
  addressChecked: boolean;
  onAddressChecked: (value: boolean) => void;
}) {
  return (
    <>
      <label>
        First name
        <input ref={firstRef} value={values.first} onChange={(e) => onChange({ first: e.target.value })} autoComplete="off" required />
      </label>
      <label>
        Middle name (optional)
        <input value={values.middle} onChange={(e) => onChange({ middle: e.target.value })} autoComplete="off" />
      </label>
      <label>
        Last name
        <input value={values.last} onChange={(e) => onChange({ last: e.target.value })} autoComplete="off" required />
      </label>
      <label>
        Date of birth (optional)
        <input
          value={values.dob}
          onChange={(e) => onChange({ dob: e.target.value })}
          autoComplete="off"
          inputMode="numeric"
          placeholder="20/09/1959"
        />
      </label>
      <label>
        NI number (optional)
        <input value={values.nino} onChange={(e) => onChange({ nino: e.target.value })} autoComplete="off" placeholder="AB 12 34 56 C" />
      </label>
      <label>
        Email (optional)
        <input type="email" value={values.email} onChange={(e) => onChange({ email: e.target.value })} autoComplete="off" />
      </label>
      <PhoneField value={values.phone} onChange={(phone) => onChange({ phone })} />
      <fieldset className="new-client-extras">
        <legend className="new-client-extras-head">Address (optional)</legend>
        <label>
          Address line 1
          <input value={values.address1} onChange={(e) => onChange({ address1: e.target.value })} autoComplete="off" />
        </label>
        <label>
          Address line 2
          <input value={values.address2} onChange={(e) => onChange({ address2: e.target.value })} autoComplete="off" />
        </label>
        <label>
          Address line 3
          <input value={values.address3} onChange={(e) => onChange({ address3: e.target.value })} autoComplete="off" />
        </label>
        <label>
          Address line 4
          <input value={values.address4} onChange={(e) => onChange({ address4: e.target.value })} autoComplete="off" />
        </label>
        <label>
          Postcode
          <input value={values.postcode} onChange={(e) => onChange({ postcode: e.target.value })} autoComplete="off" placeholder="SW1A 1AA" />
        </label>
      </fieldset>
      <label>
        Matter
        <select value={values.category} onChange={(e) => onChange({ category: e.target.value })} required>
          <option value="">Choose a matter</option>
          {categories.map((c) => (
            <option key={c.key} value={c.key}>{c.label}</option>
          ))}
        </select>
      </label>
      <label>
        Brief details of the matter (optional)
        <textarea
          value={values.matterDetails}
          onChange={(e) => onChange({ matterDetails: e.target.value })}
          rows={3}
          maxLength={1000}
        />
      </label>
      {addressCheck && (
        <label className="new-client-check">
          <input type="checkbox" checked={addressChecked} onChange={(e) => onAddressChecked(e.target.checked)} />
          I have checked this email address is the client&apos;s
        </label>
      )}
    </>
  );
}
