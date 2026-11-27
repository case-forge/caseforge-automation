"use client";

import { useEffect, useState } from "react";
import { changeFolderLock, confirmQuestion, exclusionLabel, exclusionPath, fetchFolderLocks, alreadyExcluded } from "@/lib/folderLocks";
import type { FolderLocks, PendingChange } from "@/lib/folderLocks";

export function ExcludedFoldersPanel() {
  const [locks, setLocks] = useState<FolderLocks | null>(null);
  const [failed, setFailed] = useState(false);
  const [book, setBook] = useState("");
  const [sub, setSub] = useState("");
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    fetchFolderLocks()
      .then((rows) => live && setLocks(rows))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  const path = exclusionPath(book, sub, typed);
  const duplicate = !!locks && !!path && alreadyExcluded(locks, path);

  async function confirm() {
    if (!pending) return;
    const change = pending;
    setPending(null);
    setSaving(true);
    setMessage("");
    setError("");
    try {
      setLocks(await changeFolderLock(change.path, change.kind === "add"));
      setMessage(change.kind === "add" ? `Automation will not change ${exclusionLabel(change.path)}.` : `Automation may work in ${exclusionLabel(change.path)} again.`);
      if (change.kind === "add") {
        setSub("");
        setTyped("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the list.");
    } finally {
      setSaving(false);
    }
  }

  function ask(next: PendingChange) {
    setMessage("");
    setError("");
    setPending(next);
  }

  const question = pending && (
    <span className="folder-lock-confirm" role="alert">
      <span className="folder-lock-confirm-text">{confirmQuestion(pending)}</span>
      <button type="button" className="cf-btn cf-btn--neutral" onClick={() => void confirm()}>
        {pending.kind === "add" ? "Yes, leave it alone" : "Yes, allow it"}
      </button>
      <button type="button" className="cf-btn cf-btn--flush" onClick={() => setPending(null)}>
        Cancel
      </button>
    </span>
  );

  return (
    <div className="settings-box" role="group" aria-label="Folders not to touch">
      <p className="settings-box-label">Folders not to touch</p>
      <p className="settings-note">
        Automation does not create, move, rename or delete anything in these folders, or in the folders inside them. Attendance notes, client care letters and
        case summaries are still saved. A billed matter is never changed, whatever this list says.
      </p>
      {failed ? (
        <p className="detail-field-value detail-field-value--empty">Couldn&apos;t read the list</p>
      ) : !locks ? (
        <p className="detail-field-value detail-field-value--empty">Checking…</p>
      ) : (
        <>
          {locks.locked.length === 0 ? (
            <p className="detail-field-value detail-field-value--empty">No folder is on the list.</p>
          ) : (
            <ul className="folder-lock-list" aria-label="Excluded folders">
              {locks.locked.map((l) => (
                <li key={l.path} className="settings-box-row folder-lock-row">
                  <span className="folder-lock-name">{exclusionLabel(l.path)}</span>
                  {pending?.kind === "remove" && pending.path === l.path ? (
                    question
                  ) : (
                    <button type="button" className="cf-btn cf-btn--neutral" disabled={saving} onClick={() => ask({ kind: "remove", path: l.path })}>
                      Remove
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <div className="folder-lock-add" role="group" aria-label="Add a folder">
            <label className="folder-lock-field">
              <span>Folder</span>
              <select
                value={book}
                onChange={(e) => {
                  setBook(e.target.value);
                  setSub("");
                }}
              >
                <option value="">Choose a folder</option>
                {locks.books.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </label>
            <label className="folder-lock-field">
              <span>Inside it</span>
              <select value={sub} onChange={(e) => setSub(e.target.value)} disabled={!book}>
                <option value="">The whole folder</option>
                {(locks.children[book] ?? []).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="folder-lock-field">
              <span>Deeper path (optional)</span>
              <input type="text" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="e.g. Court bundle/Drafts" disabled={!book} />
            </label>
            {pending?.kind === "add" ? (
              question
            ) : (
              <button type="button" className="cf-btn cf-btn--neutral" disabled={!path || duplicate || saving} onClick={() => ask({ kind: "add", path })}>
                Add to the list
              </button>
            )}
          </div>
          {duplicate && <p className="settings-note">That folder is already covered by the list.</p>}
        </>
      )}
      {message && (
        <p className="settings-note" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="client-edits-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
