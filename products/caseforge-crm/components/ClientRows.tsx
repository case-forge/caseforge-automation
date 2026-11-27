"use client";

import { describeFetchError } from "@/lib/networkError";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  CHILD_FIELDS,
  PARTY_FIELDS,
  addressLinesOfText,
  normalisePr,
  reconcileParty,
  type RowField,
} from "@/lib/types";
import { useCurrentClient, useReportUnsaved } from "@/lib/unsavedEdits";
import { useClientEdit } from "./ClientEdits";
import { CopyButton } from "./CopyButton";
import { ROLE_CHOICES, roleChoiceOf, roleOtherTextOf, roleToStore } from "@/lib/partyFields";

type Row = Record<string, string>;

interface SummaryBox {
  label: string;
  values: string[];
}

const PARTY_NAME_PARTS = [
  ["name_first", "First name"],
  ["name_middle", "Middle name"],
  ["name_last", "Last name"],
  ["aka_name", "Alias"],
] as const;
const NAME_PARTS = [
  ["name_first", "First name"],
  ["name_middle", "Middle name"],
  ["name_last", "Last name"],
] as const;
const ADDRESS_PARTS = [
  ["address_line1", "Address line 1"],
  ["address_line2", "Address line 2"],
  ["address_line3", "Address line 3"],
  ["address_line4", "Address line 4"],
  ["address_postcode", "Postcode"],
] as const;
const WORK_ADDRESS_PARTS = [
  ["work_address_line1", "Work address line 1"],
  ["work_address_line2", "Work address line 2"],
  ["work_address_line3", "Work address line 3"],
  ["work_address_line4", "Work address line 4"],
  ["work_address_postcode", "Work postcode"],
] as const;

const lined = (row: Row, parts: readonly (readonly [string, string])[]) =>
  parts.map(([name]) => row[name] ?? "").filter(Boolean);

const nameOf = (row: Row) =>
  NAME_PARTS.map(([name]) => row[name] ?? "").filter(Boolean).join(" ") || row.display_name || row.child_name || "";

export function isClientParty(role: string, clientRole: string | null | undefined): boolean {
  const r = role.trim().toLowerCase();
  if (!r) return false;
  const own = (clientRole ?? "").trim().toLowerCase();
  if (own) return r === own || r === "client";
  return r === "client" || r === "applicant";
}

interface RowKind {
  endpoint: "parties" | "children";
  idKey: string;
  listKey: string;
  fields: RowField[];
  noun: string;
  addLabel: string;
  emptyLabel: string;
  unsavedLabel: string;

  prefill: (row: Row) => Row;

  blank: (clientRole: string | null | undefined) => Row;

  summary: (row: Row) => { title: string; boxes: SummaryBox[] };
}

const PARTY_KIND: RowKind = {
  endpoint: "parties",
  idKey: "party_id",
  listKey: "parties",
  fields: PARTY_FIELDS,
  noun: "party",
  addLabel: "Add opponent / other party",
  emptyLabel: "No opponent on record",
  unsavedLabel: "Opponent / other parties",
  prefill: (row) => reconcileParty(row),

  blank: (clientRole) => ({ role: (clientRole ?? "").trim().toLowerCase() === "respondent" ? "Applicant" : "Respondent" }),
  summary: (stored) => {
    const row = reconcileParty(stored);
    const name = nameOf(row);
    const addressParts = lined(row, ADDRESS_PARTS);
    const address = addressParts.length > 0 ? addressParts : addressLinesOfText(row.address_text);
    return {
      title: row.role || "Other party",
      boxes: [
        { label: "Name", values: [name, row.aka_name ? `Alias ${row.aka_name}` : ""].filter(Boolean) },
        { label: "Party", values: [row.role || "Other party"] },
        { label: "Date of birth", values: [row.dob_iso] },
        { label: "Telephone", values: [row.phone_primary] },
        { label: "Email", values: [row.email_primary] },
        { label: "Address", values: address },
        { label: "Work address", values: lined(row, WORK_ADDRESS_PARTS) },
      ].map((box) => ({ ...box, values: box.values.filter(Boolean) })),
    };
  },
};

const CHILD_KIND: RowKind = {
  endpoint: "children",
  idKey: "child_id",
  listKey: "children",
  fields: CHILD_FIELDS,
  noun: "child",
  addLabel: "Add child",
  emptyLabel: "No children on record",
  unsavedLabel: "Children",
  prefill: (row) => ({ ...reconcileParty(row), parental_responsibility: normalisePr(row.parental_responsibility ?? "") }),
  blank: () => ({}),
  summary: (row) => {
    const boxes: SummaryBox[] = [
      { label: "Name", values: [nameOf(row)].filter(Boolean) },

      { label: "PR", values: [normalisePr(row.parental_responsibility ?? "") || "Client"] },
      { label: "Date of birth", values: [row.dob_iso].filter(Boolean) },
      { label: "Sex", values: [row.gender].filter(Boolean) },
    ];
    if (row.lives_with) boxes.push({ label: "Lives with", values: [row.lives_with] });
    if (row.notes) boxes.push({ label: "Notes", values: [row.notes] });
    return { title: row.child_name || "Child", boxes };
  },
};

function useRows(kind: RowKind, matterId: string) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!matterId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/clients/${kind.endpoint}?matter_id=${encodeURIComponent(matterId)}`);
      if (!res.ok) throw new Error("Could not load these records");
      const body = await res.json();
      setRows(body[kind.listKey] ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load these records");
    } finally {
      setLoading(false);
    }
  }, [kind.endpoint, kind.listKey, matterId]);
  useEffect(() => {
    setRows([]);
    void load();
  }, [load]);
  return { rows, loading, error, reload: load };
}

async function post(path: string, payload: Row | Record<string, string>, failure: string) {
  let res: Response;
  try {
    res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  } catch (err) {
    throw new Error(describeFetchError(err, failure));
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}) as { error?: string });
    throw new Error(body.error || failure);
  }
}

function Box({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="detail-field detail-field--editing">
      <div className="detail-field-head">
        <p className="detail-field-label">{label}</p>
      </div>
      {children}
    </div>
  );
}

function Stack({ label, parts, draft, set }: { label: string; parts: readonly (readonly [string, string])[]; draft: Row; set: (name: string, value: string) => void }) {
  return (
    <Box label={label}>
      <div className="edit-inline-stack">
        {parts.map(([name, text]) => (
          <input key={name} className="edit-input" aria-label={text} placeholder={text} value={draft[name] ?? ""} onChange={(e) => set(name, e.target.value)} autoComplete="off" />
        ))}
      </div>
    </Box>
  );
}

function Single({ label, name, draft, set, type }: { label: string; name: string; draft: Row; set: (name: string, value: string) => void; type?: string }) {
  return (
    <Box label={label}>
      <input className="edit-input" aria-label={label} type={type ?? "text"} value={draft[name] ?? ""} onChange={(e) => set(name, e.target.value)} autoComplete="off" />
    </Box>
  );
}

function Pick({ field, label, draft, set }: { field: RowField; label?: string; draft: Row; set: (name: string, value: string) => void }) {
  const value = draft[field.name] ?? "";
  const text = label ?? field.label;
  return (
    <Box label={text}>
      <select className="edit-input" aria-label={text} value={value} onChange={(e) => set(field.name, e.target.value)}>
        <option value="" />
        {(field.options ?? []).map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
        {value && !(field.options ?? []).includes(value) && <option value={value}>{value}</option>}
      </select>
    </Box>
  );
}

function RoleBox({ draft, set }: { draft: Row; set: (name: string, value: string) => void }) {
  const role = draft.role ?? "";
  const [other, setOther] = useState(roleChoiceOf(role) === "Other");
  const choice = other ? "Other" : roleChoiceOf(role);
  return (
    <Box label="Party">
      <select
        className="edit-input"
        aria-label="Party"
        value={choice}
        onChange={(e) => {
          const next = e.target.value;
          setOther(next === "Other");
          set("role", next === "Other" ? roleOtherTextOf(role) : next);
        }}
      >
        {choice === "" && <option value="" />}
        {ROLE_CHOICES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      {choice === "Other" && (
        <input className="edit-input" aria-label="Role (other)" placeholder="Role" value={roleOtherTextOf(role)} onChange={(e) => set("role", e.target.value)} autoComplete="off" />
      )}
    </Box>
  );
}

export function RowsSection({
  kind,
  matterId,
  clientRole,
  onChanged,
}: {
  kind: "parties" | "children";
  matterId: string;
  clientRole?: string | null;
  onChanged?: () => void;
}) {
  const config = kind === "parties" ? PARTY_KIND : CHILD_KIND;
  const ed = useClientEdit();
  const editing = Boolean(ed?.editing);
  const { rows, loading, error, reload } = useRows(config, matterId);
  const shown = kind === "parties" ? rows.filter((row) => !isClientParty(String(row.role ?? ""), clientRole)) : rows;

  const [originals, setOriginals] = useState<Record<string, Row>>({});
  const [drafts, setDrafts] = useState<Record<string, Row>>({});
  const [adds, setAdds] = useState<{ key: string; draft: Row }[]>([]);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const addCounter = useRef(0);

  useEffect(() => {
    if (!editing) {
      setOriginals({});
      setDrafts({});
      setAdds([]);
      setRemoved(new Set());
      return;
    }
    const nextOriginals: Record<string, Row> = {};
    const nextDrafts: Record<string, Row> = {};
    for (const row of shown) {
      const id = row[config.idKey];
      const loaded: Row = {};
      for (const f of config.fields) loaded[f.name] = row[f.name] ?? "";
      nextOriginals[id] = loaded;
      nextDrafts[id] = { ...loaded, ...config.prefill({ ...row, ...loaded }) };
    }
    setOriginals(nextOriginals);
    setDrafts(nextDrafts);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, rows]);

  const changedParts = (id: string): string[] => {
    const draft = drafts[id];
    const original = originals[id];
    if (!draft || !original) return [];
    return config.fields.filter((f) => (draft[f.name] ?? "").trim() !== (original[f.name] ?? "").trim()).map((f) => f.name);
  };
  const filledAdds = adds.filter(({ draft }) => config.fields.some((f) => f.name !== "role" && (draft[f.name] ?? "").trim() !== ""));

  const changes = (): string[] => {
    const lines: string[] = [];
    for (const row of shown) {
      const id = row[config.idKey];
      const title = nameOf(drafts[id] ?? row) || config.summary(row).title;
      if (removed.has(id)) lines.push(`Remove ${config.noun} "${title}"`);
      else {
        const parts = changedParts(id);
        if (parts.length > 0) {
          const labels = config.fields.filter((f) => parts.includes(f.name)).map((f) => f.label);
          lines.push(`${title} (${config.noun}): ${labels.join(", ")}`);
        }
      }
    }
    for (const { draft } of filledAdds) lines.push(`Add ${config.noun} "${nameOf(draft) || "(no name)"}"`);
    return lines;
  };

  const save = async (note: string) => {
    for (const row of shown) {
      const id = row[config.idKey];
      if (removed.has(id)) {
        await post(`/api/clients/${config.endpoint}/remove`, { matter_id: matterId, [config.idKey]: id }, "Could not remove that");
        continue;
      }
      const parts = changedParts(id);
      if (parts.length === 0) continue;
      const changed: Row = {};
      for (const name of parts) changed[name] = name === "role" ? roleToStore(drafts[id][name] ?? "") : (drafts[id][name] ?? "");
      await post(
        `/api/clients/${config.endpoint}/update`,
        { matter_id: matterId, [config.idKey]: id, ...changed, note },
        "Could not save that change",
      );
    }
    for (const { draft } of filledAdds) {
      await post(`/api/clients/${config.endpoint}`, { matter_id: matterId, ...draft, ...(kind === "parties" ? { role: roleToStore(draft.role ?? "") } : {}), note }, "Could not add that");
    }
    await reload();
    onChanged?.();
  };

  const latest = useRef({ changes, save });
  latest.current = { changes, save };
  const register = ed?.registerSaver;
  useEffect(() => {
    if (!register) return;
    return register(config.endpoint, {
      changes: () => latest.current.changes(),
      save: (note) => latest.current.save(note),
    });
  }, [register, config.endpoint]);

  const client = useCurrentClient();
  useReportUnsaved(
    `row-editor-${config.endpoint}`,
    {
      label: config.unsavedLabel,
      matterId,
      clientName: client?.matterId === matterId ? client.clientName : undefined,
      place: client?.matterId === matterId ? client.tab : undefined,
    },
    editing && changes().length > 0,
  );

  const setRowValue = (id: string, name: string, value: string) =>
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], [name]: value } }));
  const setAddValue = (key: string, name: string, value: string) =>
    setAdds((prev) => prev.map((a) => (a.key === key ? { ...a, draft: { ...a.draft, [name]: value } } : a)));
  const startAdd = () => {
    const draft: Row = {};
    for (const f of config.fields) draft[f.name] = "";
    setAdds((prev) => [...prev, { key: `new-${addCounter.current++}`, draft: { ...draft, ...config.blank(clientRole) } }]);
  };

  const form = (draft: Row, set: (name: string, value: string) => void, remove: ReactNode) => (
    <div className="row-editor-row row-editor-row--editing">
      <div className="detail-grid">
        {kind === "parties" ? (
          <>
            <Stack label="Name" parts={PARTY_NAME_PARTS} draft={draft} set={set} />
            <RoleBox draft={draft} set={set} />
            <Single label="Date of birth" name="dob_iso" type="date" draft={draft} set={set} />
            <Single label="Telephone" name="phone_primary" draft={draft} set={set} />
            <Single label="Email" name="email_primary" draft={draft} set={set} />
            <Stack label="Address" parts={ADDRESS_PARTS} draft={draft} set={set} />
            <Stack label="Work address" parts={WORK_ADDRESS_PARTS} draft={draft} set={set} />
          </>
        ) : (
          <>
            <Stack label="Name" parts={NAME_PARTS} draft={draft} set={set} />
            <Pick field={CHILD_FIELDS.find((f) => f.name === "parental_responsibility") as RowField} label="PR" draft={draft} set={set} />
            <Single label="Date of birth" name="dob_iso" type="date" draft={draft} set={set} />
            <Pick field={CHILD_FIELDS.find((f) => f.name === "gender") as RowField} label="Sex" draft={draft} set={set} />
            <Pick field={CHILD_FIELDS.find((f) => f.name === "lives_with") as RowField} draft={draft} set={set} />
          </>
        )}
      </div>
      <div className="row-editor-form-foot">{remove}</div>
    </div>
  );

  const body = loading ? (
    <p className="detail-field-value detail-field-value--empty">Loading…</p>
  ) : shown.length === 0 && adds.length === 0 ? (
    <div className="detail-grid">
      <div className="detail-field">
        <p className="detail-field-value detail-field-value--empty">{config.emptyLabel}</p>
      </div>
    </div>
  ) : (
    shown.map((row) => {
      const id = row[config.idKey];
      if (editing && drafts[id]) {
        const gone = removed.has(id);
        const toggle = (
          <button
            type="button"
            className="cf-btn cf-btn--flush cf-btn--danger row-editor-remove"
            onClick={() =>
              setRemoved((prev) => {
                const next = new Set(prev);
                if (gone) next.delete(id);
                else next.add(id);
                return next;
              })
            }
          >
            {gone ? "Keep" : "Remove"}
          </button>
        );
        return (
          <div key={id} className={gone ? "row-editor-removed" : undefined}>
            {form(drafts[id], (name, value) => setRowValue(id, name, value), toggle)}
          </div>
        );
      }
      const { boxes } = config.summary(row);
      return (
        <div className="row-editor-row row-editor-row--editing" key={id}>
          <div className="detail-grid">
            {boxes.map((box) => (
              <div className="detail-field" key={box.label}>
                <div className="detail-field-head">
                  <p className="detail-field-label">{box.label}</p>
                </div>
                <div className="row-editor-line-with-tool">
                  <div>
                    {box.values.length === 0 ? (
                      <p className="detail-field-value detail-field-value--empty">Not on record</p>
                    ) : (
                      box.values.map((value, i) => (
                        <p className="detail-field-value" key={i}>
                          {value}
                        </p>
                      ))
                    )}
                  </div>
                  {box.values.length > 0 && <CopyButton text={box.values.join(", ")} label={box.label.toLowerCase()} />}
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    })
  );

  return (
    <div className="row-editor" data-unsaved-source={`row-editor-${config.endpoint}`}>
      {error && <p className="client-edits-error" role="alert">{error}</p>}
      {body}
      {editing &&
        adds.map(({ key, draft }) => (
          <div key={key}>
            {form(draft, (name, value) => setAddValue(key, name, value), (
              <button type="button" className="cf-btn cf-btn--flush cf-btn--danger row-editor-remove" onClick={() => setAdds((prev) => prev.filter((a) => a.key !== key))}>
                Remove
              </button>
            ))}
          </div>
        ))}
      {editing && (
        <button type="button" className="cf-btn cf-btn--neutral row-editor-add" onClick={startAdd}>
          {config.addLabel}
        </button>
      )}
    </div>
  );
}
