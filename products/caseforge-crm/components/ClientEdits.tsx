"use client";

import { IconArrowRight, IconClose } from "./icons";
import { Fragment, createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { ClientEdit, ClientMatch, EditableField } from "@/lib/types";
import { CATEGORY_PILL_FLAGS, COURT_REFERENCE_BOXES, EDITABLE_FIELDS, FLAG_FIELDS, ORDER_TYPE_LABELS, editableFieldValue, fullNameOf, orderTypeTagsOf, orderTypesText } from "@/lib/types";
import { useReportUnsaved } from "@/lib/unsavedEdits";
import { clearDraft, draftTimeLabel, loadDraft, saveDraft, useFormDraft } from "@/lib/formDrafts";
import { describeFetchError } from "@/lib/networkError";
import { DraftRestoredNote } from "./DraftRestoredNote";

const NOTE_MAX_LENGTH = 100;

const SAVED_DRAFT_FORM = "client-edit-saved";

const HEADER_FLAG_NAMES = new Set(["flagged", "starred"]);
const NAME_PARTS = ["name_first", "name_middle", "name_last"];
const ADDRESS_PARTS = ["address_line1", "address_line2", "address_line3", "address_line4", "address_postcode"];
const ORDER_CODES = Object.keys(ORDER_TYPE_LABELS);

const STATUS_FLAG_NAMES = ["transferred", "dropped_out", "billed", "persistent_caller", "persistent_caller_respondent", "private_billing"];

function cleanValue(field: EditableField | undefined, raw: string): string {
  if (field?.kind === "courtrefs") return raw.split("\n").map((v) => v.trim()).filter(Boolean).join("\n");
  return raw.trim();
}

function splitCodes(value: string | undefined): string[] {
  const found = new Set((value ?? "").split(",").map((v) => v.trim()));
  return ORDER_CODES.filter((code) => found.has(code));
}

function displayValue(field: EditableField, raw: string): string {
  if (field.kind === "boolean") return raw === "1" ? "Yes" : "No";
  return raw || "(blank)";
}

export interface RowSaver {
  changes: () => string[];
  save: (note: string) => Promise<void>;
}

interface ClientEditState {
  matterId: string;
  editing: boolean;
  draft: Record<string, string>;
  setDraftValue: (fieldName: string, value: string) => void;
  note: string;
  setNote: (value: string) => void;
  submitting: boolean;
  error: string | null;
  setError: (message: string | null) => void;
  history: ClientEdit[];
  loading: boolean;
  startEdit: () => void;
  cancelEdit: () => void;

  saveAsDraft: () => void;

  draftSavedAt: number | null;
  submitChanges: () => Promise<void>;
  reload: () => Promise<void>;
  match: ClientMatch;

  restoredAt: number | null;

  registerSaver: (id: string, saver: RowSaver) => () => void;
}

const ClientEditContext = createContext<ClientEditState | null>(null);

export function useClientEdit(): ClientEditState | null {
  return useContext(ClientEditContext);
}

export function ClientEditProvider({
  match,
  onFieldUpdated,
  onHistoryLoaded,
  children,
}: {
  match: ClientMatch;

  onFieldUpdated?: (fieldName: string, newValue: string) => void;

  onHistoryLoaded?: (rows: ClientEdit[]) => void;
  children: ReactNode;
}) {
  const matterId = match.matter_id != null ? String(match.matter_id) : "";

  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState<ClientEdit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [draftSavedAt, setDraftSavedAt] = useState<number | null>(null);
  const [draftRestoredAt, setDraftRestoredAt] = useState<number | null>(null);
  const savers = useRef(new Map<string, RowSaver>());
  const registerSaver = useCallback((id: string, saver: RowSaver) => {
    savers.current.set(id, saver);
    return () => {
      if (savers.current.get(id) === saver) savers.current.delete(id);
    };
  }, []);

  const changedNow: Record<string, string> = {};
  if (editing) {
    for (const field of EDITABLE_FIELDS) {
      const value = draft[field.name] ?? "";
      if (cleanValue(field, value) !== cleanValue(field, editableFieldValue(match, field.name))) changedNow[field.name] = value;
    }
  }
  const dirty = editing && (note.trim() !== "" || Object.keys(changedNow).length > 0);
  useReportUnsaved(
    "client-edit",
    { label: "Client details", matterId, clientName: fullNameOf(match), place: "Client tab" },
    dirty,
  );

  const latestLoad = useRef("");
  const load = useCallback(async (id: string) => {
    if (!id) return;
    latestLoad.current = id;
    setLoading(true);
    setError(null);
    try {
      const historyRes = await fetch(`/api/clients/edits?matter_id=${encodeURIComponent(id)}`);
      if (!historyRes.ok) throw new Error("Could not load the change history");
      const rows = await historyRes.json();
      if (latestLoad.current === id) {
        setHistory(rows);
        onHistoryLoaded?.(rows);
      }
    } catch (err) {
      if (latestLoad.current === id) setError(describeFetchError(err, "Could not load the change history"));
    } finally {
      if (latestLoad.current === id) setLoading(false);
    }
  }, [onHistoryLoaded]);

  useEffect(() => {
    setEditing(false);
    setDraft({});
    setNote("");
    setHistory([]);
    setDraftRestoredAt(null);
    setDraftSavedAt(loadDraft(matterId, SAVED_DRAFT_FORM)?.savedAt ?? null);
    void load(matterId);
  }, [matterId, load]);

  const kept = useFormDraft<{ changes: Record<string, string>; note: string }>({
    matterId,
    formId: "client-edit",
    server: true,
    dirty,
    data: { changes: changedNow, note },
    restore: (saved) => {
      const initial: Record<string, string> = {};
      for (const field of EDITABLE_FIELDS) initial[field.name] = editableFieldValue(match, field.name);
      for (const [name, value] of Object.entries(saved.changes ?? {})) {
        if (name in initial && typeof value === "string") initial[name] = value;
      }
      setDraft(initial);
      setNote(typeof saved.note === "string" ? saved.note : "");
      setError(null);
      setEditing(true);
    },
  });

  function startEdit() {
    const initial: Record<string, string> = {};
    for (const field of EDITABLE_FIELDS) {
      initial[field.name] = editableFieldValue(match, field.name);
    }

    const saved = loadDraft<{ changes: Record<string, string>; note: string }>(matterId, SAVED_DRAFT_FORM);
    let savedNote = "";
    if (saved) {
      for (const [name, value] of Object.entries(saved.data.changes ?? {})) {
        if (name in initial && typeof value === "string") initial[name] = value;
      }
      savedNote = typeof saved.data.note === "string" ? saved.data.note : "";
      clearDraft(matterId, SAVED_DRAFT_FORM);
      setDraftSavedAt(null);
    }
    setDraftRestoredAt(saved ? saved.savedAt : null);
    setDraft(initial);
    setNote(savedNote);
    setError(null);
    setEditing(true);
  }

  function saveAsDraft() {
    if (!dirty) {
      setError("Nothing typed yet, so there is nothing to keep as a draft.");
      return;
    }
    const now = Date.now();
    saveDraft(matterId, SAVED_DRAFT_FORM, { changes: changedNow, note }, now);
    setDraftSavedAt(now);
    setEditing(false);
    setDraft({});
    setNote("");
    setError(null);
    setDraftRestoredAt(null);
  }

  async function submitChanges() {
    const differs = (field: EditableField) =>
      cleanValue(field, draft[field.name] ?? "") !== cleanValue(field, editableFieldValue(match, field.name));

    let changed = EDITABLE_FIELDS.filter(differs);

    const groupWritten = (parts: string[], derivedKey: string) => {
      if (match.extra?.[derivedKey] && changed.some((f) => parts.includes(f.name))) {
        changed = EDITABLE_FIELDS.filter((f) => changed.includes(f) || parts.includes(f.name));
      }
    };
    groupWritten(NAME_PARTS, "name_derived");
    groupWritten(ADDRESS_PARTS, "client_address_derived");

    const noteText = note.trim();
    const notesFieldEdited = changed.some((field) => field.name === "tracker_notes");
    const noteAsNote =
      noteText && !notesFieldEdited && noteText !== editableFieldValue(match, "tracker_notes").trim()
        ? noteText
        : "";
    const rowLines = [...savers.current.values()].flatMap((saver) => saver.changes());
    if (changed.length === 0 && !noteAsNote && rowLines.length === 0) {
      setEditing(false);
      return;
    }
    type Change = { name: string; label: string; before: string; after: string; field?: EditableField };
    const changes: Change[] = changed.map((field) =>
      field.kind === "ordertypes"
        ? {
            name: field.name,
            label: field.label,
            before: orderTypesText(orderTypeTagsOf(match)) || "(none ticked)",
            after: orderTypesText(splitCodes(draft[field.name])) || "(none ticked)",
            field,
          }
        : {
            name: field.name,
            label: field.label,
            before: displayValue(field, editableFieldValue(match, field.name)),
            after: displayValue(field, cleanValue(field, draft[field.name] ?? "")),
            field,
          },
    );
    const values: Record<string, string> = {};
    for (const field of changed) values[field.name] = cleanValue(field, draft[field.name] ?? "");
    if (changed.some((f) => f.kind === "ordertypes")) {

      const text = orderTypesText(splitCodes(draft.order_type_tags));
      values.order_requested_text = text;
      changes.push({
        name: "order_requested_text",
        label: "Matter (wording)",
        before: displayValue({} as EditableField, match.order_requested_text ?? ""),
        after: displayValue({} as EditableField, text),
      });
    }
    const summary = [
      ...changes.map((c) => `${c.label}: "${c.before}" → "${c.after}"`),
      ...rowLines,
      ...(noteAsNote ? [`New note: "${noteAsNote}"`] : []),
    ].join("\n");
    const changeCount = changes.length + rowLines.length + (noteAsNote ? 1 : 0);
    const confirmed = window.confirm(
      `Apply ${changeCount} change${changeCount === 1 ? "" : "s"}?\n\n${summary}`,
    );
    if (!confirmed) return;

    setSubmitting(true);
    setError(null);
    try {
      for (const change of changes) {
        const res = await fetch("/api/clients/edits", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            matter_id: matterId,
            field_name: change.name,
            new_value: values[change.name],
            note,
          }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}) as { error?: string });
          throw new Error(body.error || `Could not apply the change to ${change.label}`);
        }
        onFieldUpdated?.(change.name, values[change.name]);
      }
      for (const saver of savers.current.values()) await saver.save(note);
      if (changed.some((f) => NAME_PARTS.includes(f.name))) onFieldUpdated?.("name_derived", "");
      if (changed.some((f) => ADDRESS_PARTS.includes(f.name))) onFieldUpdated?.("client_address_derived", "");
      if (noteAsNote) {
        const res = await fetch("/api/clients/edits", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            matter_id: matterId,
            field_name: "tracker_notes",
            new_value: noteAsNote,
            note: "",
          }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}) as { error?: string });
          throw new Error(body.error || "Could not save the note");
        }
        onFieldUpdated?.("tracker_notes", noteAsNote);
      }
      setEditing(false);
      await load(matterId);
    } catch (err) {
      setError(describeFetchError(err, "Could not apply the changes"));
    } finally {
      setSubmitting(false);
    }
  }

  function setDraftValue(fieldName: string, value: string) {
    setDraft((prev) => ({ ...prev, [fieldName]: value }));
  }

  function cancelEdit() {
    setDraftRestoredAt(null);
    setEditing(false);
    setDraft({});
    setNote("");
    setError(null);
  }

  const state: ClientEditState = {
    matterId,
    editing,
    draft,
    setDraftValue,
    note,
    setNote,
    submitting,
    error,
    setError,
    history,
    loading,
    startEdit,
    cancelEdit,
    saveAsDraft,
    draftSavedAt,
    submitChanges,
    reload: () => load(matterId),
    match,
    restoredAt: kept.restoredAt ?? draftRestoredAt,
    registerSaver,
  };
  if (!matterId) return <>{children}</>;
  return <ClientEditContext.Provider value={state}>{children}</ClientEditContext.Provider>;
}

export function ClientEditBar({
  flagTicks,
  clientActions,
}: {

  flagTicks?: ReactNode;

  clientActions?: ReactNode;
}) {
  const ed = useClientEdit();
  if (!ed) return null;
  return (
    <div className="client-edits client-edits--bar" data-unsaved-source="client-edit">
      {(flagTicks || (!ed.editing && ed.draftSavedAt !== null)) && (
        <div className="client-edits-header">
          {!ed.editing && ed.draftSavedAt !== null && (
            <span className="edit-form-hint" role="status">
              Draft kept at {draftTimeLabel(ed.draftSavedAt)}. Use the edit icon beside a heading to carry on.
            </span>
          )}
          {flagTicks}
        </div>
      )}
      {ed.error && <p className="client-edits-error" role="alert">{ed.error}</p>}
      {ed.editing && <DraftRestoredNote savedAt={ed.restoredAt} saveLabel="Apply changes" onDiscard={ed.cancelEdit} />}
      {ed.editing && (
        <div className="edit-form edit-form--bar">
          <p className="edit-form-hint">
            Change the details below where they are shown. You&apos;ll be asked to confirm before anything changes.
          </p>
          <label className="detail-field-label" htmlFor="edit-note">
            Note (optional, {NOTE_MAX_LENGTH} characters max)
          </label>
          <input
            id="edit-note"
            className="edit-input"
            value={ed.note}
            maxLength={NOTE_MAX_LENGTH}
            onChange={(e) => ed.setNote(e.target.value)}
            placeholder="Why this change, e.g. casing was wrong on import"
            autoComplete="off"
          />
          <div className="edit-form-actions">
            <button
              type="button"
              className="cf-btn cf-btn--primary"
              onClick={ed.submitChanges}
              disabled={ed.submitting}
            >
              {ed.submitting ? "Applying..." : "Apply changes"}
            </button>
            <button type="button" className="cf-btn cf-btn--flush" onClick={ed.cancelEdit} disabled={ed.submitting}>
              Cancel
            </button>
            <span className="client-edits-more">
              <button type="button" className="cf-btn cf-btn--neutral" onClick={ed.saveAsDraft} disabled={ed.submitting}>
                Save as draft
              </button>
              {clientActions}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

async function postFlag(matterId: string, flagName: string, isSet: boolean) {
  const res = await fetch("/api/clients/matter-flags", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, flag_name: flagName, is_set: isSet }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}) as { error?: string });
    throw new Error(body.error || "Could not update that flag");
  }
  const body = await res.json();
  return { flags: (body.flags ?? {}) as Record<string, boolean>, reasons: (body.reasons ?? {}) as Record<string, string> };
}

export function FlagTicks({
  flags,
  flagReasons,
  onFlagsChanged,
  status,
}: {
  status?: boolean;

  flags: Record<string, boolean>;

  flagReasons?: Record<string, string>;
  onFlagsChanged: (flags: Record<string, boolean>, reasons?: Record<string, string>) => void;
}) {
  const ed = useClientEdit();
  const [togglingFlag, setTogglingFlag] = useState<string | null>(null);
  if (!ed) return null;
  const { matterId } = ed;
  const shown = FLAG_FIELDS.filter(
    (f) => !HEADER_FLAG_NAMES.has(f.name) && STATUS_FLAG_NAMES.includes(f.name) === Boolean(status),
  );

  async function toggleFlag(flagName: string, nextValue: boolean) {
    setTogglingFlag(flagName);
    ed?.setError(null);
    try {
      const res = await fetch("/api/clients/matter-flags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter_id: matterId, flag_name: flagName, is_set: nextValue }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}) as { error?: string });
        throw new Error(body.error || "Could not update that flag");
      }
      const body = await res.json();
      onFlagsChanged(body.flags ?? {}, body.reasons ?? {});
      await ed?.reload();
    } catch (err) {
      ed?.setError(describeFetchError(err, "Could not update that flag"));
    } finally {
      setTogglingFlag(null);
    }
  }

  if (shown.length === 0) return null;
  const Wrap = status ? Fragment : "div";
  return (
    <Wrap {...(status ? {} : { className: "client-edits-flags" })}>
      {shown.map((flag) => (
        <label key={flag.name} className="client-edits-flag">
          <input
            type="checkbox"
            checked={flags[flag.name] ?? false}
            disabled={togglingFlag === flag.name}
            onChange={(e) => toggleFlag(flag.name, e.target.checked)}
          />
          {flag.label}
          {flags[flag.name] && flagReasons?.[flag.name] && (
            <span className="client-edits-flag-reason"> ({flagReasons[flag.name]})</span>
          )}
        </label>
      ))}
    </Wrap>
  );
}

export function ClientEditHistory() {
  const ed = useClientEdit();
  if (!ed) return null;
  const { history, loading } = ed;
  return (
    <div className="client-edits">
      {!loading && history.length > 0 && (
        <details className="proposal-history" open={history.length <= 3}>
          <summary>Recent changes ({history.length})</summary>
          <ul className="proposal-list proposal-list--resolved">
            {history.map((h) => (
              <li className="proposal-item proposal-item--resolved" key={h.edit_id}>
                <p className="proposal-item-field">{h.field_label}</p>
                <p className="proposal-item-diff">
                  <span className="proposal-item-old">{h.old_value || "Not on record"}</span>
                  {" "}<IconArrowRight aria-hidden="true" />{" "}
                  <span className="proposal-item-new">{h.new_value}</span>
                </p>
                {h.note && <p className="proposal-item-note">{h.note}</p>}
                <p className="proposal-item-meta">Changed by {h.edited_by || "unknown"}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function InlineText({ name, label, multiline }: { name: string; label: string; multiline?: boolean }) {
  const ed = useClientEdit();
  if (!ed?.editing) return null;
  const common = {
    id: `edit-${name}`,
    "aria-label": label,
    placeholder: multiline ? undefined : label,
    className: multiline ? "edit-input edit-textarea" : "edit-input",
    type: EDITABLE_FIELDS.find((f) => f.name === name)?.kind === "date" ? "date" : undefined,
    value: ed.draft[name] ?? "",
    onChange: (e: { target: { value: string } }) => ed.setDraftValue(name, e.target.value),
  };
  return multiline ? <textarea {...common} rows={4} /> : <input {...common} autoComplete="off" />;
}

export function InlineOrderTypes() {
  const ed = useClientEdit();
  if (!ed?.editing) return null;
  const draft = ed.draft.order_type_tags;
  return (
    <div className="edit-form-ordertypes" role="group" aria-label="Matter">
      {ORDER_CODES.map((code) => (
        <label key={code} className="edit-form-checkbox-label">
          <input
            type="checkbox"
            checked={splitCodes(draft).includes(code)}
            onChange={(e) => {
              const set = new Set(splitCodes(draft));
              if (e.target.checked) set.add(code);
              else set.delete(code);
              ed.setDraftValue("order_type_tags", ORDER_CODES.filter((c) => set.has(c)).join(","));
            }}
          />
          {ORDER_TYPE_LABELS[code]}
        </label>
      ))}
    </div>
  );
}

const MATTER_CHOICES = CATEGORY_PILL_FLAGS.filter((flag) => flag.name.startsWith("cat_"));

export function InlineMatterSelect({
  flags,
  onFlagsChanged,
}: {
  flags: Record<string, boolean>;
  onFlagsChanged: (flags: Record<string, boolean>, reasons?: Record<string, string>) => void;
}) {
  const ed = useClientEdit();
  const [busy, setBusy] = useState(false);
  if (!ed?.editing) return null;
  const { matterId } = ed;
  const active = MATTER_CHOICES.filter((choice) => flags[choice.name]);
  const available = MATTER_CHOICES.filter((choice) => !flags[choice.name]);

  async function change(flag: string, on: boolean) {
    setBusy(true);
    ed?.setError(null);
    try {
      const latest = await postFlag(matterId, flag, on);
      onFlagsChanged(latest.flags, latest.reasons);
      await ed?.reload();
    } catch (err) {
      ed?.setError(err instanceof Error ? err.message : "Could not update that matter");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="edit-matter-select-group">
      {active.map((choice) => (
        <span key={choice.name} className="edit-matter-chip">
          {choice.label}
          <button
            type="button"
            className="edit-matter-chip-remove"
            aria-label={`Remove ${choice.label}`}
            disabled={busy}
            onClick={() => void change(choice.name, false)}
          >
            <IconClose aria-hidden="true" width={12} height={12} />
          </button>
        </span>
      ))}
      {available.length > 0 && (
        <select
          className="edit-input edit-matter-select"
          aria-label="Add matter"
          value=""
          disabled={busy}
          onChange={(e) => e.target.value && void change(e.target.value, true)}
        >
          <option value="">Add matter</option>
          {available.map((choice) => (
            <option key={choice.name} value={choice.name}>
              {choice.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export function InlineStatus(flagProps: {
  flags: Record<string, boolean>;
  flagReasons?: Record<string, string>;
  onFlagsChanged: (flags: Record<string, boolean>, reasons?: Record<string, string>) => void;
}) {
  const ed = useClientEdit();
  if (!ed?.editing) return null;
  return (
    <div className="client-edits-flags client-edits-flags--status">
      <label className="client-edits-flag" htmlFor="edit-concluded">
        <input
          id="edit-concluded"
          type="checkbox"
          checked={(ed.draft.concluded ?? "0") === "1"}
          onChange={(e) => ed.setDraftValue("concluded", e.target.checked ? "1" : "0")}
        />
        Concluded
      </label>
      <FlagTicks {...flagProps} status />
    </div>
  );
}

export function InlineNameStack() {
  const ed = useClientEdit();
  if (!ed?.editing) return null;
  return (
    <div className="detail-field detail-field--editing">
      <div className="detail-field-head">
        <p className="detail-field-label">Name</p>
      </div>
      <div className="edit-inline-stack">
        {NAME_PARTS.map((name) => (
          <InlineText key={name} name={name} label={EDITABLE_FIELDS.find((f) => f.name === name)?.label ?? name} />
        ))}
      </div>
    </div>
  );
}

export function InlineCourtReferences() {
  const ed = useClientEdit();
  const [count, setCount] = useState<number | null>(null);
  const editing = Boolean(ed?.editing);
  useEffect(() => {
    if (!editing) setCount(null);
  }, [editing]);
  if (!ed?.editing) return null;
  const lines = (ed.draft.court_references ?? "").split("\n");
  const shown = Math.min(COURT_REFERENCE_BOXES, Math.max(1, count ?? 0, lines.filter((l) => l.trim()).length));
  const boxes = Array.from({ length: shown }, (_, i) => lines[i] ?? "");
  return (
    <div className="edit-inline-stack">
      {boxes.map((box, i) => (
        <input
          key={i}
          className="edit-input"
          aria-label={`Court reference ${i + 1}`}
          value={box}
          onChange={(e) => ed.setDraftValue("court_references", boxes.map((b, j) => (j === i ? e.target.value : b)).join("\n"))}
          autoComplete="off"
        />
      ))}
      {shown < COURT_REFERENCE_BOXES && (
        <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setCount(shown + 1)}>
          Add
        </button>
      )}
    </div>
  );
}

export function InlineIdentityBoxes() {
  const ed = useClientEdit();
  if (!ed?.editing) return null;
  const names = ["nino_canonical", "client_role"];
  return (
    <>
      {names.map((name) => {
        const field = EDITABLE_FIELDS.find((f) => f.name === name);
        if (!field) return null;
        const value = ed.draft[name] ?? "";
        return (
          <div className="detail-field detail-field--editing" key={name}>
            <label className="detail-field-label" htmlFor={`edit-${name}`}>
              {field.label}
            </label>
            {field.kind === "select" ? (
              <select id={`edit-${name}`} className="edit-input" value={value} onChange={(e) => ed.setDraftValue(name, e.target.value)}>
                <option value="" />
                { }
                {value && !(field.options ?? []).includes(value) && <option value={value}>{value}</option>}
                {(field.options ?? []).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : (
              <InlineText name={name} label={field.label} />
            )}
          </div>
        );
      })}
    </>
  );
}
