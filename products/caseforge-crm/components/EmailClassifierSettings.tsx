"use client";

import { useCallback, useEffect, useState } from "react";
import { loadAppSettings } from "@/lib/appSettings";
import {
  addEntry,
  auditLine,
  groupLists,
  kindOf,
  loadEmailClassifier,
  removeAdded,
  saveEmailClassifier,
  stopUsing,
  useAgain,
  type EmailClassifierBody,
  type EmailClassifierView,
} from "@/lib/emailClassifier";
import { IconClose, IconPlus } from "./icons";

interface ListProps {
  name: string;
  view: EmailClassifierView;
  canEdit: boolean;
  message: string;
  onSave: (name: string, body: EmailClassifierBody) => Promise<boolean>;
}

function ListBlock({ name, view, canEdit, message, onSave }: ListProps) {
  const [draft, setDraft] = useState("");
  const list = view.lists[name];
  const kind = kindOf(name);
  async function add() {
    if (!draft.trim()) return;
    if (await onSave(name, addEntry(view, name, draft))) setDraft("");
  }
  return (
    <div className="eclf-list">
      <h4 className="eclf-kind">{kind}</h4>
      <details className="eclf-builtin">
        <summary>
          Built-in {kind.toLowerCase()} ({list.default.length})
        </summary>
        <ul className="eclf-entries">
          {list.default.map((entry) => {
            const stopped = list.removed.includes(entry);
            return (
              <li key={entry} className="eclf-entry" data-stopped={stopped ? "true" : undefined}>
                <span className="eclf-text">{entry}</span>
                {canEdit && (
                  <button
                    type="button"
                    className="cf-btn cf-btn--neutral cf-btn--small"
                    aria-label={`${stopped ? "Use again" : "Stop using"} ${entry}`}
                    onClick={() => void onSave(name, stopped ? useAgain(view, name, entry) : stopUsing(view, name, entry))}
                  >
                    {stopped ? "Use again" : "Stop using"}
                  </button>
                )}
                {!canEdit && stopped && <span className="eclf-note">Not in use</span>}
              </li>
            );
          })}
        </ul>
      </details>
      {list.added.length > 0 && (
        <ul className="eclf-chips" aria-label={`Your own ${kind.toLowerCase()}`}>
          {list.added.map((entry) => (
            <li key={entry} className="eclf-chip">
              <span className="eclf-text">{entry}</span>
              {canEdit && (
                <button
                  type="button"
                  className="cf-btn cf-btn--icon cf-btn--small"
                  aria-label={`Remove ${entry}`}
                  title={`Remove ${entry}`}
                  onClick={() => void onSave(name, removeAdded(view, name, entry))}
                >
                  <IconClose width={14} height={14} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <div className="eclf-add">
          <label className="eclf-add-label" htmlFor={`eclf-add-${name}`}>
            Add to {kind.toLowerCase()}
          </label>
          <div className="eclf-add-row">
            <input
              id={`eclf-add-${name}`}
              type="text"
              className="edit-input eclf-input"
              value={draft}
              maxLength={200}
              aria-invalid={message ? true : undefined}
              aria-describedby={message ? `eclf-msg-${name}` : undefined}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void add();
                }
              }}
            />
            <button type="button" className="cf-btn cf-btn--primary cf-btn--small" aria-label={`Add to ${kind.toLowerCase()}`} onClick={() => void add()}>
              <IconPlus width={14} height={14} /> Add
            </button>
          </div>
          {message && (
            <p id={`eclf-msg-${name}`} className="eclf-error" role="alert">
              {message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function ClassifierLists({ view, canEdit, errors, onSave }: { view: EmailClassifierView; canEdit: boolean; errors: Record<string, string>; onSave: ListProps["onSave"] }) {
  return (
    <div className="eclf">
      <p className="eclf-intro">
        The classifier sorts incoming email into the right route using these sender and keyword lists. Add your own, or stop using a built-in entry. A
        change reaches the classifier within a minute.
      </p>
      {!canEdit && <p className="eclf-note">Only an administrator can change these lists; you can read them here.</p>}
      {groupLists(view).map((group) => (
        <section key={group.label} className="eclf-group" aria-labelledby={`eclf-h-${group.names[0]}`}>
          <h3 id={`eclf-h-${group.names[0]}`} className="eclf-title">
            {group.label}
          </h3>
          {group.feeds && <p className="eclf-feeds">Feeds the {group.feeds} route</p>}
          {group.names.map((name) => (
            <ListBlock key={name} name={name} view={view} canEdit={canEdit} message={errors[name] ?? ""} onSave={onSave} />
          ))}
        </section>
      ))}
      <section className="eclf-group" aria-labelledby="eclf-recent">
        <h3 id="eclf-recent" className="eclf-title">
          Recent changes
        </h3>
        {view.audit.length === 0 ? (
          <p className="eclf-note">No changes yet.</p>
        ) : (
          <ul className="eclf-audit">
            {view.audit.map((row, index) => (
              <li key={index}>{auditLine(row)}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export function EmailClassifierSettings() {
  const [view, setView] = useState<EmailClassifierView | null>(null);
  const [canEdit, setCanEdit] = useState(false);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    void Promise.all([loadEmailClassifier(), loadAppSettings()]).then(([lists, app]) => {
      if (cancelled) return;
      if (lists.state === "ok") setView(lists.view);
      else setFailed(true);
      setCanEdit(app.state === "ok" && app.view.can_edit);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  const save = useCallback(
    async (name: string, body: EmailClassifierBody): Promise<boolean> => {
      if (busy) return false;
      setBusy(true);
      const result = await saveEmailClassifier(body);
      setBusy(false);
      setErrors(result.ok ? {} : { [name]: result.message });
      if (result.ok) setView(result.view);
      return result.ok;
    },
    [busy],
  );
  if (failed && !view) return <p role="alert">The classifier lists could not be loaded. Try again shortly.</p>;
  if (!view) return <p>Loading the classifier lists</p>;
  return <ClassifierLists view={view} canEdit={canEdit} errors={errors} onSave={save} />;
}
