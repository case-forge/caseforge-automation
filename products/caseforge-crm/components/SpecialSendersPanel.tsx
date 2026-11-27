"use client";

import { useEffect, useRef, useState } from "react";
import { MAX_MARK_LETTERS, senderInitials } from "@/lib/specialSenderRules";
import type { SenderMark } from "@/lib/specialSenderRules";
import {
  fetchSpecialSenders,
  refreshSpecialSenders,
  removeSenderLogo,
  saveSpecialSenders,
  uploadSenderLogo,
  type SpecialSender,
} from "@/lib/specialSenders";
import { SpecialSenderBadge } from "./SenderBadge";

type Row = { key: string; id?: string; name: string; domains: string; new_clients: boolean; logo: string; mark: SenderMark | null };

const LETTER_COLOUR = "#ffffff";
const BACKGROUND_COLOUR = "#1a4f8c";

function defaultMark(name: string): SenderMark {
  const text = senderInitials(name).replace(/[^A-Z0-9]/g, "").slice(0, MAX_MARK_LETTERS) || "A";
  return { text, colours: [...text].map(() => LETTER_COLOUR), background: BACKGROUND_COLOUR };
}

let counter = 0;
const toRow = (s: SpecialSender): Row => ({ key: s.id, id: s.id, name: s.name, domains: s.domains.join(", "), new_clients: s.new_clients, logo: s.logo, mark: s.mark });
const blank = (): Row => ({ key: `new${++counter}`, name: "", domains: "", new_clients: false, logo: "", mark: null });
const domainList = (text: string): string[] => text.split(/[\s,;]+/).map((d) => d.trim()).filter(Boolean);

function MarkMaker({ row, onChange }: { row: Row; onChange: (mark: SenderMark | null) => void }) {
  const mark = row.mark;
  if (!mark) return null;
  function setText(raw: string) {
    const text = raw.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, MAX_MARK_LETTERS);
    if (!text) {
      onChange({ ...mark!, text: "", colours: [] });
      return;
    }
    const colours = [...text].map((_, i) => mark!.colours[i] ?? mark!.colours[mark!.colours.length - 1] ?? LETTER_COLOUR);
    onChange({ ...mark!, text, colours });
  }
  return (
    <span className="special-senders-maker">
      <label className="special-senders-field">
        <span>Letters (1 to {MAX_MARK_LETTERS})</span>
        <input type="text" value={mark.text} maxLength={MAX_MARK_LETTERS} size={4} onChange={(e) => setText(e.target.value)} aria-label={`Letters for ${row.name || "this sender"}`} />
      </label>
      {[...mark.text].map((letter, i) => (
        <label key={i} className="special-senders-colour">
          <span>{letter}</span>
          <input
            type="color"
            value={mark.colours[i] ?? LETTER_COLOUR}
            aria-label={`Colour of the letter ${letter}`}
            onChange={(e) => onChange({ ...mark, colours: mark.colours.map((c, j) => (j === i ? e.target.value : c)) })}
          />
        </label>
      ))}
      <label className="special-senders-colour">
        <span>Background</span>
        <input type="color" value={mark.background} aria-label="Background colour" onChange={(e) => onChange({ ...mark, background: e.target.value })} />
      </label>
    </span>
  );
}

function Logo({ row, onChanged, onError }: { row: Row; onChanged: () => void; onError: (message: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  async function pick(file: File | undefined) {
    if (!file || !row.id) return;
    setBusy(true);
    try {
      await uploadSenderLogo(row.id, file);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "The logo was not saved.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }
  async function remove() {
    if (!row.id) return;
    setBusy(true);
    try {
      await removeSenderLogo(row.id);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "The logo was not removed.");
    } finally {
      setBusy(false);
    }
  }
  if (!row.id) return <span className="special-senders-hint">Save first, then upload a picture.</span>;
  return (
    <span className="special-senders-logo">
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden onChange={(e) => void pick(e.target.files?.[0])} aria-label={`Logo file for ${row.name}`} />
      <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={busy} onClick={() => input.current?.click()}>
        {row.logo ? "Change picture" : "Upload a picture"}
      </button>
      {row.logo && (
        <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={busy} onClick={() => void remove()}>
          Remove picture
        </button>
      )}
    </span>
  );
}

export function SpecialSendersPanel() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchSpecialSenders().then(
      (list) => !cancelled && setRows(list.map(toRow)),
      (err: unknown) => !cancelled && setError(err instanceof Error ? err.message : "The special senders could not be loaded."),
    );
    return () => {
      cancelled = true;
    };
  }, []);

  function change(key: string, patch: Partial<Row>) {
    setSaved("");
    setRows((current) => (current ?? []).map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }
  function move(index: number, by: number) {
    setSaved("");
    setRows((current) => {
      const next = [...(current ?? [])];
      const target = index + by;
      if (target < 0 || target >= next.length) return next;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }
  async function reloadLogos() {
    setError("");
    try {
      const list = await refreshSpecialSenders();
      setRows((current) => (current ?? []).map((r) => {
        const fresh = list.find((s) => s.id === r.id);
        return fresh ? { ...r, logo: fresh.logo, mark: fresh.mark } : r;
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The special senders could not be loaded.");
    }
  }
  async function save() {
    if (!rows || busy) return;
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const list = await saveSpecialSenders(rows.map((r) => ({ ...(r.id ? { id: r.id } : {}), name: r.name, domains: domainList(r.domains), new_clients: r.new_clients, mark: r.mark })));
      setRows(list.map(toRow));
      setSaved("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The special senders were not saved.");
    } finally {
      setBusy(false);
    }
  }

  if (!rows) return error ? <p role="alert">{error}</p> : <p>Loading the special senders</p>;
  return (
    <div className="special-senders">
      <p className="special-senders-intro">
        Senders you want to spot at a glance. A notification from one gets its logo beside the name, and the Notification board can sort them first in this
        order. A sender is recognised by the email domains it writes from, by the clients it refers, or both.
      </p>
      {rows.length === 0 && <p>No special sender yet.</p>}
      <ul className="special-senders-list">
        {rows.map((row, index) => (
          <li key={row.key} className="special-senders-row">
            <SpecialSenderBadge sender={{ id: row.id ?? row.key, name: row.name || "?", domains: [], new_clients: false, logo: row.mark ? "" : row.logo, mark: row.mark }} />
            <label className="special-senders-field">
              <span>Name</span>
              <input type="text" value={row.name} maxLength={40} onChange={(e) => change(row.key, { name: e.target.value })} />
            </label>
            <label className="special-senders-field special-senders-field--wide">
              <span>Email domains (separate with commas)</span>
              <input type="text" value={row.domains} placeholder="chambers.example" onChange={(e) => change(row.key, { domains: e.target.value })} />
            </label>
            <label className="special-senders-check">
              <input type="checkbox" checked={row.new_clients} onChange={(e) => change(row.key, { new_clients: e.target.checked })} />
              <span>Clients this sender refers (new client notifications)</span>
            </label>
            <span className="special-senders-logo-choice" role="group" aria-label={`Logo for ${row.name || "this sender"}`}>
              <button type="button" className="cf-btn cf-btn--chip" aria-pressed={row.mark !== null} onClick={() => change(row.key, { mark: row.mark ?? defaultMark(row.name) })}>
                Make letters
              </button>
              <button type="button" className="cf-btn cf-btn--chip" aria-pressed={row.mark === null} onClick={() => change(row.key, { mark: null })}>
                Picture
              </button>
            </span>
            {row.mark ? <MarkMaker row={row} onChange={(mark) => change(row.key, { mark })} /> : <Logo row={row} onChanged={() => void reloadLogos()} onError={setError} />}
            <span className="special-senders-actions">
              <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move ${row.name || "this sender"} up`}>
                Up
              </button>
              <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={index === rows.length - 1} onClick={() => move(index, 1)} aria-label={`Move ${row.name || "this sender"} down`}>
                Down
              </button>
              <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" onClick={() => { setSaved(""); setRows((current) => (current ?? []).filter((r) => r.key !== row.key)); }}>
                Remove
              </button>
            </span>
          </li>
        ))}
      </ul>
      <div className="special-senders-foot">
        <button type="button" className="cf-btn cf-btn--neutral" onClick={() => { setSaved(""); setRows((current) => [...(current ?? []), blank()]); }}>
          Add a special sender
        </button>
        <button type="button" className="cf-btn cf-btn--primary" disabled={busy} onClick={() => void save()}>
          {busy ? "Saving…" : "Save"}
        </button>
        {saved && <span role="status">{saved}</span>}
      </div>
      {error && <p className="new-client-error" role="alert">{error}</p>}
    </div>
  );
}
