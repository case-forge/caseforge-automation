"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  backendLabel,
  changeLine,
  formatCap,
  formatCost,
  formatSeconds,
  loadModelRoles,
  type LoadResult,
  resetRoleModel,
  saveRoleModel,
  type ModelRoleRow,
  type ModelRolesView,
} from "@/lib/modelRoles";

interface Pending {
  row: ModelRoleRow;
  next: string;
  reset: boolean;
}

function ConfirmDialog({ pending, busy, onConfirm, onCancel }: { pending: Pending; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => confirmRef.current?.focus(), []);
  const line = changeLine(pending.row, pending.next);
  return (
    <div className="board-confirm-backdrop" role="presentation" onPointerDown={(event) => event.target === event.currentTarget && !busy && onCancel()}>
      <div
        className="board-confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="models-confirm-title"
        onKeyDown={(event) => event.key === "Escape" && !busy && onCancel()}
      >
        <h2 id="models-confirm-title" className="board-confirm-title">
          {pending.reset ? "Put this job back to its default model?" : "Change the model for this job?"}
        </h2>
        <ul className="models-confirm-list">
          <li>
            <strong>{line.purpose}</strong>
            <span className="models-change">
              <code>{line.from}</code> <span aria-hidden="true">→</span>
              <span className="models-sr"> becomes </span> <code>{line.to}</code>
            </span>
          </li>
        </ul>
        <p className="board-confirm-note">The next model call for this job uses it. Nothing already written is changed. The change is recorded with your name.</p>
        <div className="models-confirm-actions">
          <button type="button" className="cf-btn cf-btn--neutral" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" ref={confirmRef} className="cf-btn cf-btn--primary" onClick={onConfirm} disabled={busy}>
            {busy ? "Saving" : "Confirm change"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Use({ row, days }: { row: ModelRoleRow; days: number }) {
  if (!row.stats) return <span className="models-muted">Not available</span>;
  const { calls, failures, p50_seconds: p50, cost_usd: cost } = row.stats;
  if (calls === 0) return <span className="models-muted">No calls in {days} days</span>;
  return (
    <span className="models-use">
      <span>{calls} {calls === 1 ? "call" : "calls"}</span>
      <span>Median {formatSeconds(p50)}</span>
      <span className={failures > 0 ? "models-warn" : undefined}>{failures} failed</span>
      <span>{formatCost(cost)}</span>
    </span>
  );
}

export function ModelsPanel() {
  const [view, setView] = useState<ModelRolesView | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState("");

  const apply = useCallback((result: LoadResult) => {
    if (result.state === "ok") {
      setView(result.view);
      setFailed(false);
    } else {
      setFailed(true);
    }
  }, []);
  useEffect(() => {
    let cancelled = false;
    void loadModelRoles().then((result) => !cancelled && apply(result));
    return () => {
      cancelled = true;
    };
  }, [apply]);

  if (failed && !view) return <p role="alert">The model list could not be loaded. Try again shortly.</p>;
  if (!view) return <p>Loading the models</p>;

  const canEdit = view.can_edit;

  function startEdit(row: ModelRoleRow) {
    setEditing(row.role);
    setDraft(row.model);
    setDone("");
    setErrors((e) => ({ ...e, [row.role]: "" }));
  }
  function stopEdit() {
    setEditing(null);
    setDraft("");
  }
  async function confirm() {
    if (!pending) return;
    const { row, next, reset } = pending;
    setBusy(true);
    const result = reset ? await resetRoleModel(row.role) : await saveRoleModel(row.role, next, row.model);
    setBusy(false);
    setPending(null);
    if (result.ok) {
      setErrors((e) => ({ ...e, [row.role]: "" }));
      setDone(`${row.purpose}: now uses ${reset ? row.default_model : next}. It applies from the next call.`);
      stopEdit();
    } else {
      setErrors((e) => ({ ...e, [row.role]: result.message }));
    }
    apply(await loadModelRoles());
  }

  return (
    <div className="models-panel">
      <p className="models-intro">
        Every job a model does for the firm, and the model doing it now. {view.stats_available ? `Use is counted over the last ${view.stats_days} days.` : "Use over recent days is not available just now."}{" "}
        {canEdit ? "Use Edit on a row to swap its model for another one already in use." : "Changing a model needs an administrator."}
      </p>
      <div className="models-live" role="status" aria-live="polite">
        {done}
      </div>
      <table className="models-table">
        <caption className="models-sr">Model roles</caption>
        <thead>
          <tr>
            <th scope="col">Job</th>
            <th scope="col">Model</th>
            <th scope="col">Runs on</th>
            <th scope="col">Spend cap</th>
            <th scope="col">Last {view.stats_days} days</th>
            {canEdit && <th scope="col">Change</th>}
          </tr>
        </thead>
        <tbody>
          {view.roles.map((row) => {
            const isEditing = editing === row.role;
            const error = errors[row.role];
            return (
              <tr key={row.role} className={isEditing ? "models-row models-row--editing" : "models-row"}>
                <th scope="row" data-label="Job">
                  <span className="models-purpose">{row.purpose}</span>
                  <span className="models-role">
                    {row.role} · {row.tier === "large" ? "larger job" : "smaller job"}
                  </span>
                </th>
                <td data-label="Model">
                  {isEditing ? (
                    <select aria-label={`Model for ${row.purpose}`} value={draft} onChange={(e) => setDraft(e.target.value)} className="models-select">
                      <option value={row.model}>{row.model} (now)</option>
                      {row.candidates.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <code className="models-id">{row.model || "Not set"}</code>
                  )}
                  <span className={`models-source models-source--${row.source}`}>{row.source_text}</span>
                  {row.overridden && row.default_model && <span className="models-muted">Default: {row.default_model}</span>}
                </td>
                <td data-label="Runs on">
                  <span>{backendLabel(row)}</span>
                  <span className="models-muted">{row.retention.text}</span>
                </td>
                <td data-label="Spend cap">{formatCap(row.spend_cap)}</td>
                <td data-label={`Last ${view.stats_days} days`}>
                  <Use row={row} days={view.stats_days} />
                </td>
                {canEdit && (
                  <td data-label="Change" className="models-actions">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          className="cf-btn cf-btn--primary cf-btn--small"
                          disabled={draft === row.model}
                          onClick={() => setPending({ row, next: draft, reset: false })}
                        >
                          Save
                        </button>
                        <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" onClick={stopEdit}>
                          Cancel
                        </button>
                        {row.overridden && (
                          <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={() => setPending({ row, next: row.default_model, reset: true })}>
                            Reset to default
                          </button>
                        )}
                      </>
                    ) : row.swappable ? (
                      <button type="button" className="cf-btn cf-btn--secondary cf-btn--small" onClick={() => startEdit(row)} aria-label={`Edit the model for ${row.purpose}`}>
                        Edit
                      </button>
                    ) : (
                      <>
                        {row.overridden && (
                          <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={() => setPending({ row, next: row.default_model, reset: true })}>
                            Reset to default
                          </button>
                        )}
                        <span className="models-muted">{row.note}</span>
                      </>
                    )}
                    {error && (
                      <span className="models-error" role="alert">
                        {error}
                      </span>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {pending && <ConfirmDialog pending={pending} busy={busy} onConfirm={() => void confirm()} onCancel={() => setPending(null)} />}
    </div>
  );
}
