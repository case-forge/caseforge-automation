"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type FolderMapEntry,
  type FolderMapPreview,
  type FolderMapView,
  loadFolderMap,
  localProblems,
  previewFolderMap,
  resetFolderMap,
  saveFolderMap,
} from "@/lib/folderMap";

export function FolderMapPanel() {
  const [view, setView] = useState<FolderMapView | null>(null);
  const [failed, setFailed] = useState(false);
  const [rows, setRows] = useState<FolderMapEntry[]>([]);
  const [preview, setPreview] = useState<FolderMapPreview | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const adopt = useCallback((next: FolderMapView) => {
    setView(next);
    setRows(next.entries.map((e) => ({ ...e })));
    setPreview(next.preview);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void loadFolderMap().then((result) => {
      if (cancelled) return;
      if (result.state === "ok") adopt(result.view);
      else setFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [adopt]);

  const problems = localProblems(rows, view?.max_name, view?.max_entries);
  const clean = Object.keys(problems).length === 0;

  useEffect(() => {
    if (!view || !clean) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      void previewFolderMap(rows).then((result) => {
        if (cancelled) return;
        if (result.ok) {
          setPreview(result.value);
          setError("");
        } else {
          setError(result.message);
        }
      });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [rows, clean, view]);

  if (failed && !view) return <p role="alert">The folder map could not be loaded. Try again shortly.</p>;
  if (!view) return <p>Loading the folder map</p>;

  const canEdit = view.can_edit;
  const changed = JSON.stringify(rows) !== JSON.stringify(view.entries);

  const update = (index: number, patch: Partial<FolderMapEntry>) => {
    setMessage("");
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };
  const move = (index: number, by: number) => {
    setRows((current) => {
      const target = index + by;
      if (target < 0 || target >= current.length) return current;
      const next = current.slice();
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  async function save() {
    setBusy(true);
    const result = await saveFolderMap(rows);
    setBusy(false);
    if (result.ok) {
      adopt(result.value);
      setError("");
      setMessage("Saved. New clients opened from now on get this map. Existing folders are unchanged.");
    } else {
      setError(result.message);
    }
  }
  async function reset() {
    setBusy(true);
    const result = await resetFolderMap();
    setBusy(false);
    if (result.ok) {
      adopt(result.value);
      setError("");
      setMessage("Back to the standard map for new clients. Existing folders are unchanged.");
    } else {
      setError(result.message);
    }
  }

  return (
    <div className="folder-map-panel">
      <p className="models-intro">
        The subfolders a new client gets. {view.note} The client's surname is added after each name.{" "}
        {canEdit ? "Change a name, add or remove a folder, then Save." : "Changing the map needs an administrator."}
        {view.changed_at ? ` Last changed by ${view.changed_by || "an administrator"}.` : ""}
      </p>
      <div role="status" aria-live="polite">{message}</div>
      {error && <p role="alert">{error}</p>}
      {problems[-1] && <p role="alert">{problems[-1]}</p>}
      <table className="models-table">
        <caption className="models-sr">Folders made for a new client</caption>
        <thead>
          <tr>
            <th scope="col">Folder name</th>
            <th scope="col">One per order</th>
            {canEdit && <th scope="col">Change</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="models-row">
              <td data-label="Folder name">
                {canEdit ? (
                  <input
                    type="text"
                    value={row.name}
                    maxLength={view.max_name + 20}
                    aria-label={`Folder ${index + 1} name`}
                    aria-invalid={problems[index] ? true : undefined}
                    onChange={(event) => update(index, { name: event.target.value })}
                  />
                ) : (
                  <code>{row.name}</code>
                )}
                {problems[index] && <div role="alert" className="models-warn">{problems[index]}</div>}
              </td>
              <td data-label="One per order">
                <input
                  type="checkbox"
                  checked={row.per_order}
                  disabled={!canEdit}
                  aria-label={`Folder ${index + 1}: one for each order`}
                  onChange={(event) => update(index, { per_order: event.target.checked })}
                />
              </td>
              {canEdit && (
                <td data-label="Change">
                  <button type="button" className="cf-btn cf-btn--neutral" onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move folder ${index + 1} up`}>
                    Up
                  </button>{" "}
                  <button type="button" className="cf-btn cf-btn--neutral" onClick={() => move(index, 1)} disabled={index === rows.length - 1} aria-label={`Move folder ${index + 1} down`}>
                    Down
                  </button>{" "}
                  <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setRows((c) => c.filter((_, i) => i !== index))} aria-label={`Remove folder ${index + 1}`}>
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {canEdit && (
        <div className="models-confirm-actions">
          <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setRows((c) => [...c, { name: "", per_order: false }])} disabled={rows.length >= view.max_entries}>
            Add a folder
          </button>
          <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setRows(view.entries.map((e) => ({ ...e })))} disabled={!changed || busy}>
            Undo edits
          </button>
          <button type="button" className="cf-btn cf-btn--neutral" onClick={() => void reset()} disabled={view.is_default || busy}>
            Back to the standard map
          </button>
          <button type="button" className="cf-btn cf-btn--primary" onClick={() => void save()} disabled={!changed || !clean || busy}>
            {busy ? "Saving" : "Save"}
          </button>
        </div>
      )}
      {preview && (
        <section aria-labelledby="folder-map-preview">
          <h3 id="folder-map-preview">What a new client would get</h3>
          <p className="models-muted">
            For a client called {preview.surname} with the orders {preview.orders.join(" and ")}. With no order known: {preview.without_orders.length} folders.
          </p>
          {preview.warnings.map((w) => (
            <p key={w} className="models-warn">{w}</p>
          ))}
          <ul>
            {preview.folders.map((f) => (
              <li key={f}><code>{f}</code></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
