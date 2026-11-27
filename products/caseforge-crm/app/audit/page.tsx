"use client";

import { ActorKindLabel } from "@/components/ActorKindLabel";
import { BackToHome } from "@/components/BackToHome";
import { ClearableSearch } from "@/components/ClearableSearch";
import { AuditFolderView } from "@/components/AuditFolderView";
import { IconArrowRight, IconAuditLog, IconFolderTree } from "@/components/icons";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  DAY_CHOICES,
  PAGE_SIZE,
  changeParts,
  loadAuditTrail,
  sourceLabel,
  whenLabel,
  type AuditKind,
  type AuditRow,
  type AuditTrail,
} from "@/lib/auditTrail";

const KINDS: { id: AuditKind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "person", label: "People" },
  { id: "agent", label: "Agents" },
  { id: "automation", label: "Automation" },
];

function Change({ row }: { row: AuditRow }) {
  const parts = changeParts(row);
  return (
    <div className="audit-change">
      <span className="audit-action">{row.action}</span>
      {"from" in parts ? (
        <span className="audit-move">
          <span className="audit-place">{parts.from}</span>
          <span className="audit-to">
            <IconArrowRight className="audit-arrow" />
            <span className="audit-place">{parts.to}</span>
          </span>
        </span>
      ) : (
        parts.what && <span className="audit-place">{parts.what}</span>
      )}
      {row.where && !("from" in parts) && row.where !== parts.what && <span className="audit-where">{row.where}</span>}
    </div>
  );
}

function AuditList({ tabs }: { tabs: ReactNode }) {
  const [kind, setKind] = useState<AuditKind>("all");
  const [days, setDays] = useState<number>(7);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [meta, setMeta] = useState<AuditTrail | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "hidden" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(async (offset: number) => {
    const mine = ++generation.current;
    setBusy(true);
    const result = await loadAuditTrail({ kind, days, q: query, offset, limit: PAGE_SIZE });
    if (mine !== generation.current) return;
    setBusy(false);
    if (result.state !== "ok") {
      setState(result.state);
      return;
    }
    setState("ok");
    setMeta(result.data);
    setRows((prev) => (offset === 0 ? result.data.rows : [...prev, ...result.data.rows]));
  }, [kind, days, query]);

  useEffect(() => {
    void load(0);
  }, [load]);

  const back = (
    <p className="review-mail-back">
      <BackToHome />
    </p>
  );

  if (state === "hidden") {
    return (
      <main className="audit-trail">
        {back}
        <p className="audit-muted">There is nothing to show here.</p>
      </main>
    );
  }

  const counts = meta?.counts ?? { person: 0, agent: 0, automation: 0 };
  const countFor = (id: AuditKind) => (id === "all" ? counts.person + counts.agent + counts.automation : counts[id] ?? 0);

  return (
    <main className="audit-trail">
      {back}
      <div className="audit-head">
        <h1>Audit trail</h1>
        <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={() => void load(0)}>
          {busy ? "Loading" : "Refresh"}
        </button>
      </div>
      {tabs}
      <p className="audit-muted">What changed, and who or what did it. Microsoft&apos;s log and ours are joined: a change both saw is one row.</p>
      <div className="audit-controls">
        <div className="audit-kinds" role="group" aria-label="Who made the change">
          {KINDS.map(({ id, label }) => (
            <button key={id} type="button" className="cf-btn cf-btn--chip audit-kind" aria-pressed={kind === id} onClick={() => setKind(id)}>
              {label} <span className="audit-count">{countFor(id)}</span>
            </button>
          ))}
        </div>
        <label className="audit-field">
          <span className="audit-muted">Period</span>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {DAY_CHOICES.map((d) => (
              <option key={d} value={d}>
                {d === 1 ? "Last day" : `Last ${d} days`}
              </option>
            ))}
          </select>
        </label>
        <ClearableSearch
          wrapClassName="audit-search-wrap"
          className="audit-search"
          placeholder="Search who, what or where"
          value={search}
          onValueChange={setSearch}
          clearLabel="Clear the search"
          aria-label="Search the audit trail"
        />
      </div>
      {state === "error" && (
        <p className="audit-muted" role="status">
          The audit trail could not be loaded just now. Try Refresh in a minute.
        </p>
      )}
      {state === "ok" && rows.length === 0 && !busy && <p className="audit-muted">No changes match.</p>}
      {rows.length > 0 && (
        <div className="audit-table-wrap">
          <table className="audit-table">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Who</th>
                <th scope="col">What happened</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={`audit-row audit-row--${row.kind || "unrecorded"}`}>
                  <td className="audit-when">{whenLabel(row.at)}</td>
                  <td className="audit-who">
                    <ActorKindLabel kind={row.kind} />
                    <span>{row.who}</span>
                    {row.likely_crm_user && row.likely_crm_user !== row.who && <span className="audit-muted">Same address as {row.likely_crm_user} in the CRM</span>}
                  </td>
                  <td>
                    <Change row={row} />
                  </td>
                  <td className="audit-seen">
                    <span>{sourceLabel(row.seen_by)}</span>
                    {row.ip && <span className="audit-muted">{row.ip}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {meta && rows.length < meta.total && (
        <p>
          <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={() => void load(rows.length)}>
            Show more ({meta.total - rows.length} left)
          </button>
        </p>
      )}
    </main>
  );
}

type View = "list" | "folders";

function AuditViews() {
  const search = useSearchParams();
  const [view, setView] = useState<View>(search.get("view") === "folders" ? "folders" : "list");

  const choose = (next: View) => {
    setView(next);
    try {
      window.history.replaceState(null, "", next === "folders" ? "?view=folders" : window.location.pathname);
    } catch {

    }
  };

  const tabs = (
    <div className="audit-views" role="group" aria-label="Audit view">
      <button type="button" className="cf-btn cf-btn--chip audit-view" aria-pressed={view === "list"} onClick={() => choose("list")}>
        <IconAuditLog aria-hidden="true" /> List
      </button>
      <button type="button" className="cf-btn cf-btn--chip audit-view" aria-pressed={view === "folders"} onClick={() => choose("folders")}>
        <IconFolderTree aria-hidden="true" /> Folders
      </button>
    </div>
  );

  return view === "folders" ? <AuditFolderView tabs={tabs} /> : <AuditList tabs={tabs} />;
}

export default function AuditPage() {
  return (
    <Suspense fallback={null}>
      <AuditViews />
    </Suspense>
  );
}
