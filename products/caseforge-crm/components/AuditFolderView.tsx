"use client";

import { ActorKindLabel } from "@/components/ActorKindLabel";
import { BackToHome } from "@/components/BackToHome";
import { ClearableSearch } from "@/components/ClearableSearch";
import { IconArrowRight, IconAutomation, IconBot, IconChevronDown, IconChevronRight, IconExternalLink, IconFile, IconFlag, IconFolder, IconFolderOpen, IconPerson } from "@/components/icons";
import { useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode, type SVGProps } from "react";
import { ACTOR_KINDS, actorKindWord, type ActorKind } from "@/lib/actorKind";
import {
  GROUPS,
  buildTree,
  carryPinned,
  dayLabel,
  flagKindsOf,
  folderPaths,
  groupOf,
  groupWord,
  hasRecord,
  loadAuditFolders,
  rollupSentence,
  rollupTotal,
  setFolderFlag,
  type AuditFolders,
  type FolderEvent,
  type FolderFlag,
  type FolderItem,
  type Group,
  type GroupFilter,
  type TreeNode,
} from "@/lib/auditFolders";
import { whenLabel } from "@/lib/auditTrail";

const BIG_FOLDER = 250;

const REFRESH_MS = 60_000;

function clock(date: Date): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

interface Actions {
  client: string;
  selected: string;
  onSelect: (path: string) => void;
  onFlag: (item: FolderItem) => void;
}

function linkFor(client: string, item: FolderItem): string {
  return `/api/audit-folders/link?client=${encodeURIComponent(client)}&path=${encodeURIComponent(item.path)}`;
}

function OpenLink({ client, item }: { client: string; item: FolderItem }) {
  if (item.removed || !item.indexed) return null;
  const href = linkFor(client, item);
  return (
    <a className="audit-open" href={href} target="_blank" rel="noopener noreferrer" aria-label={`Open ${item.name} in SharePoint`} title="Open in SharePoint">
      <IconExternalLink aria-hidden="true" />
    </a>
  );
}

function Who({ event }: { event: FolderEvent }) {
  return (
    <span className="audit-who-line">
      <ActorKindLabel kind={event.kind} />
      <span>{event.who}</span>
    </span>
  );
}

function Place({ path, outside }: { path: string; outside?: boolean }) {
  return (
    <span className="audit-place">
      {outside && <span className="audit-muted">another folder: </span>}
      {path}
    </span>
  );
}

function Rollup({ node }: { node: TreeNode }) {
  const total = rollupTotal(node.rollup);
  if (total === 0 && node.removedBelow === 0) return null;
  return (
    <span className="audit-roll" title={rollupSentence(node.rollup)}>
      <span className="audit-roll-bar" aria-hidden="true">
        {GROUPS.filter((g) => node.rollup[g] > 0).map((g) => (
          <span key={g} className={`audit-roll-seg audit-roll-seg--${g}`} style={{ flexGrow: node.rollup[g] }} />
        ))}
      </span>
      <span className="audit-muted">
        {total} {total === 1 ? "file" : "files"}
        {node.removedBelow > 0 ? `, ${node.removedBelow} removed` : ""}
      </span>
      <span className="audit-visually-hidden">{rollupSentence(node.rollup)}</span>
    </span>
  );
}

function FlagBox({ item, onFlag }: { item: FolderItem; onFlag: (item: FolderItem) => void }) {

  const mine = item.flags.person;

  const locked = item.removed && mine === undefined;
  return (
    <input
      type="checkbox"
      className="audit-flag"
      checked={mine !== undefined}
      disabled={locked}
      onChange={() => onFlag(item)}
      aria-label={`Flag ${item.name} as wrong or not belonging here`}
      title={mine ? `Flagged by ${mine.by}, ${dayLabel(mine.at)}. Untick to clear.` : "Flag as wrong or not belonging here"}
    />
  );
}

const KIND_ICONS: Record<ActorKind, ComponentType<SVGProps<SVGSVGElement>>> = { person: IconPerson, agent: IconBot, automation: IconAutomation };

function FlagMarks({ item }: { item: FolderItem }) {
  const kinds = flagKindsOf(item);
  if (kinds.length === 0) return null;
  return (
    <span className="audit-flagmarks">
      {kinds.map((kind) => {
        const flag = item.flags[kind] as FolderFlag;
        const Icon = KIND_ICONS[kind];
        return (
          <span key={kind} className={`audit-flagmark audit-flagmark--${kind}`} title={`${actorKindWord(kind)} flag by ${flag.by.split("@")[0]}, ${dayLabel(flag.at)}${flag.note ? `: ${flag.note}` : ""}`}>
            <IconFlag filled className="audit-flagmark-flag" />
            <Icon className="audit-flagmark-kind" />
            <span className="audit-visually-hidden">
              {actorKindWord(kind)} flag by {flag.by}
              {flag.note ? `: ${flag.note}` : ""}
            </span>
          </span>
        );
      })}
    </span>
  );
}

function FlagReasons({ item }: { item: FolderItem }) {
  const notes = flagKindsOf(item).filter((kind) => kind !== "person" && item.flags[kind]?.note);
  if (notes.length === 0) return null;
  return (
    <span className="audit-flagnotes">
      {notes.map((kind) => (
        <span key={kind} className="audit-flagnote">
          <span className="audit-muted">{actorKindWord(kind)}: </span>
          {item.flags[kind]?.note}
        </span>
      ))}
    </span>
  );
}

function MadeBy({ item, days }: { item: FolderItem; days: number }) {
  const edited = item.edits > 0 && item.last_edit ? `. Edited ${item.edits === 1 ? "once" : `${item.edits} times`}, last by ${item.last_edit.who}` : "";
  if (item.created) {
    return (
      <div className="audit-cell">
        <Who event={item.created} />
        <span className="audit-muted">
          {item.created.action} {dayLabel(item.created.at)}
          {edited}
        </span>
      </div>
    );
  }
  return (
    <div className="audit-cell">
      <span className="audit-muted">
        {item.removed ? "Not on record here" : `No record in the last ${days} days`}
        {edited}
      </span>
    </div>
  );
}

function PutHere({ item }: { item: FolderItem }) {
  if (item.removed && item.removed_by) {
    return (
      <div className="audit-cell">
        <Who event={item.removed_by} />
        <span className="audit-muted">
          {item.removed_by.action === "Deleted" ? "Deleted" : "Moved away"} {dayLabel(item.removed_by.at)}
        </span>
        {item.moved_to && (
          <span className="audit-move">
            <IconArrowRight className="audit-arrow" />
            <Place path={item.moved_to} outside={item.to_outside} />
          </span>
        )}
      </div>
    );
  }
  if (item.removed) {
    return (
      <div className="audit-cell">
        <span className="audit-muted">
          {item.unseen ? "Gone from the folder. Microsoft's log has not shown who yet; it is copied each night." : item.flag_gone ? "Flagged earlier; it is no longer in this folder." : ""}
        </span>
      </div>
    );
  }
  if (item.placed) {
    return (
      <div className="audit-cell">
        <Who event={item.placed} />
        <span className="audit-muted">
          {item.placed.action} here {dayLabel(item.placed.at)}
        </span>
        {item.placed.from && (
          <span className="audit-move">
            <span className="audit-muted">from</span>
            <Place path={item.placed.from} outside={item.placed.from_outside} />
          </span>
        )}
      </div>
    );
  }
  return (
    <div className="audit-cell">
      <span className="audit-muted">{item.created ? "Not moved" : ""}</span>
    </div>
  );
}

function Node({ node, depth, collapsed, toggle, days, actions }: { node: TreeNode; depth: number; collapsed: Set<string>; toggle: (path: string) => void; days: number; actions: Actions }) {
  const indent = { paddingInlineStart: `calc(${depth} * var(--sp-4))` };
  const item = node.item;
  if (node.type === "folder") {
    const expanded = !collapsed.has(node.path);
    return (
      <li role="treeitem" aria-expanded={expanded} aria-selected={false} className="audit-treeitem">
        <div className={`audit-node audit-node--folder${item && flagKindsOf(item).length > 0 ? " is-flagged" : ""}`}>
          <span className="audit-flagcell">{item && <FlagBox item={item} onFlag={actions.onFlag} />}</span>
          <button type="button" className="audit-toggle" onClick={() => toggle(node.path)} aria-label={`${node.name}, ${expanded ? "open" : "closed"}`}>
            <span className="audit-name" style={indent}>
              {expanded ? <IconChevronDown className="audit-chevron" /> : <IconChevronRight className="audit-chevron" />}
              {expanded ? <IconFolderOpen className="audit-kindicon" /> : <IconFolder className="audit-kindicon" />}
              <span className="audit-name-text">{node.name}</span>
              {item && <FlagMarks item={item} />}
            </span>
            <Rollup node={node} />
          </button>
          {item && <OpenLink client={actions.client} item={item} />}
        </div>
        {expanded && node.children.length > 0 && (
          <ul role="group" className="audit-tree-list">
            {node.children.map((child) => (
              <Node key={child.path} node={child} depth={depth + 1} collapsed={collapsed} toggle={toggle} days={days} actions={actions} />
            ))}
          </ul>
        )}
      </li>
    );
  }
  const file = item as FolderItem;
  const group: Group = file.removed ? "unrecorded" : groupOf(file);
  const selected = actions.selected === file.path;
  return (
    <li role="treeitem" aria-selected={selected} className="audit-treeitem">
      <div className={`audit-node audit-node--file audit-node--${group}${file.removed ? " is-removed" : ""}${flagKindsOf(file).length > 0 ? " is-flagged" : ""}${selected ? " is-selected" : ""}`}>
        <span className="audit-flagcell">
          <FlagBox item={file} onFlag={actions.onFlag} />
        </span>
        <span className="audit-name" style={indent}>
          <span className="audit-chevron" aria-hidden="true" />
          {file.removed || !file.indexed ? (
            <button type="button" className="audit-select" aria-pressed={selected} onClick={() => actions.onSelect(file.path)}>
              <IconFile className="audit-kindicon" />
              <span className="audit-name-text">{node.name}</span>
            </button>
          ) : (
            <a
              className="audit-select audit-select--link"
              href={linkFor(actions.client, file)}
              target="_blank"
              rel="noopener noreferrer"
              title="Open in SharePoint"
              aria-current={selected ? "true" : undefined}
              onClick={() => actions.onSelect(file.path)}
            >
              <IconFile className="audit-kindicon" />
              <span className="audit-name-text">{node.name}</span>
            </a>
          )}
          {file.removed && <span className="audit-tag">Removed</span>}
          {!file.removed && !file.indexed && <span className="audit-tag">New</span>}
          {file.stale && <span className="audit-tag">Changed since you looked</span>}
          <FlagMarks item={file} />
          <FlagReasons item={file} />
        </span>
        <MadeBy item={file} days={days} />
        <PutHere item={file} />
      </div>
    </li>
  );
}

export function AuditFolderView({ tabs }: { tabs: ReactNode }) {
  const [folder, setFolder] = useState("");
  const [data, setData] = useState<AuditFolders | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "hidden" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [group, setGroup] = useState<GroupFilter>("all");
  const [onlyChanged, setOnlyChanged] = useState(true);
  const [flagKinds, setFlagKinds] = useState<ReadonlySet<ActorKind>>(new Set());
  const [clientsFlagged, setClientsFlagged] = useState(false);
  const [clientSearch, setClientSearch] = useState("");
  const [text, setText] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState("");
  const [flagError, setFlagError] = useState(false);
  const [reloads, setReloads] = useState(0);
  const pinnedRef = useRef(pinned);
  const shownFolder = useRef("");

  useEffect(() => {
    pinnedRef.current = pinned;
  }, [pinned]);

  useEffect(() => {
    let current = true;
    void loadAuditFolders(folder).then((result) => {
      if (!current) return;
      setBusy(false);
      if (result.state === "hidden") {
        setState("hidden");
        return;
      }
      if (result.state === "error") {

        setRefreshFailed(true);
        setState((prev) => (prev === "ok" ? "ok" : "error"));
        return;
      }
      setRefreshFailed(false);
      setState("ok");
      setUpdatedAt(new Date());
      const sameFolder = shownFolder.current === folder;
      shownFolder.current = folder;
      setData((prev) => {
        const next = result.data;
        if (sameFolder && prev?.folder && next.folder && prev.folder.name === next.folder.name) {
          return { ...next, folder: { ...next.folder, items: carryPinned(prev.folder.items, next.folder.items, pinnedRef.current) } };
        }
        return next;
      });
      if (!sameFolder) {
        const items = result.data.folder?.items ?? [];
        const open = { group: "all", onlyChanged: false, text: "", flagKinds: new Set<ActorKind>(), keep: new Set<string>() } as const;
        setCollapsed(items.length > BIG_FOLDER ? new Set(folderPaths(buildTree(items, open))) : new Set());
        setPinned(new Set());
        setSelected("");
      }
    });
    return () => {
      current = false;
    };
  }, [folder, reloads]);

  useEffect(() => {
    const again = () => {
      if (document.visibilityState === "visible") setReloads((n) => n + 1);
    };
    const timer = window.setInterval(again, REFRESH_MS);
    document.addEventListener("visibilitychange", again);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", again);
    };
  }, []);

  const choose = (name: string) => {
    setBusy(true);
    setFolder(name);
  };
  const refresh = () => {
    setBusy(true);
    setReloads((n) => n + 1);
  };
  const pin = (path: string) => setPinned((prev) => (prev.has(path) ? prev : new Set(prev).add(path)));
  const select = (path: string) => {
    setSelected(path);
    pin(path);
  };

  const tree = data?.folder ?? null;
  const patchFlag = (path: string, flag: FolderFlag | null) =>
    setData((prev) => {
      if (!prev?.folder) return prev;
      const items = prev.folder.items.map((i) => {
        if (i.path !== path) return i;
        const flags = { ...i.flags };
        if (flag) flags.person = flag;
        else delete flags.person;
        return { ...i, flags };
      });
      const by_kind = { ...prev.folder.summary.flags_by_kind, person: items.filter((i) => i.flags.person).length };
      return { ...prev, folder: { ...prev.folder, items, summary: { ...prev.folder.summary, flagged: items.filter((i) => flagKindsOf(i).length > 0).length, flags_by_kind: by_kind } } };
    });
  const flag = async (item: FolderItem) => {
    if (!tree) return;
    const setting = item.flags.person === undefined;
    setFlagError(false);
    pin(item.path);
    patchFlag(item.path, setting ? { by: "you", at: new Date().toISOString(), note: "" } : null);
    const ok = await setFolderFlag(tree.name, item, setting);
    if (!ok) {
      patchFlag(item.path, item.flags.person ?? null);
      setFlagError(true);
      return;
    }
    setReloads((n) => n + 1);
  };

  const root = useMemo(() => (tree ? buildTree(tree.items, { group, onlyChanged, text, flagKinds, keep: pinned }) : null), [tree, group, onlyChanged, text, flagKinds, pinned]);
  const hiddenCount = useMemo(
    () => (tree && onlyChanged && flagKinds.size === 0 ? tree.items.filter((i) => i.type === "file" && !i.removed && !hasRecord(i) && flagKindsOf(i).length === 0 && !pinned.has(i.path)).length : 0),
    [tree, onlyChanged, flagKinds, pinned],
  );
  const clients = useMemo(() => {
    const needle = clientSearch.trim().toLowerCase();
    return (data?.clients ?? []).filter((c) => (!needle || c.name.toLowerCase().includes(needle)) && (!clientsFlagged || c.flagged > 0));
  }, [data, clientSearch, clientsFlagged]);

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

  const days = data?.days ?? 90;
  const toggle = (path: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (!next.delete(path)) next.add(path);
      return next;
    });
  const summary = tree?.summary;
  const countFor = (id: GroupFilter) => (!summary ? 0 : id === "all" ? rollupTotal(summary) : summary[id]);
  const actions: Actions = { client: tree?.name ?? "", selected, onSelect: select, onFlag: (item) => void flag(item) };

  return (
    <main className="audit-trail">
      {back}
      <div className="audit-head">
        <h1>Audit trail</h1>
        <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={refresh}>
          {busy ? "Loading" : "Refresh"}
        </button>
      </div>
      {tabs}
      <p className="audit-muted">
        Pick a client folder to see who created each file and who put it where it is now. The colour is whoever put the file there. Tick a file to flag it as wrong or not belonging;
        a flag stays until someone clears it. Last {days} days: the log goes back no further, so older files show no record.
      </p>
      <p className="audit-muted" role="status">
        Updated {updatedAt ? clock(updatedAt) : "just now"}, and again every minute while this page is open
        {refreshFailed ? " (the last refresh failed, so this is what was loaded before)" : ""}. Changes our own workers make show within a minute. What people do in OneDrive comes from Microsoft&apos;s
        log, copied each night and known up to {data?.microsoft_through ? whenLabel(data.microsoft_through) : "an unknown time"}: until then a file a person moved shows as gone, or with no record.
      </p>
      {state === "error" && (
        <p className="audit-muted" role="status">
          The folder view could not be loaded just now. Try Refresh in a minute.
        </p>
      )}
      {flagError && (
        <p className="audit-muted" role="alert">
          The flag could not be saved, so nothing was changed.
        </p>
      )}
      <div className="audit-folders">
        <nav className="audit-clients" aria-label="Client folders">
          <ClearableSearch
            wrapClassName="audit-search-wrap"
            className="audit-search"
            placeholder="Find a client folder"
            value={clientSearch}
            onValueChange={setClientSearch}
            clearLabel="Clear the search"
            aria-label="Find a client folder"
          />
          <label className="audit-field">
            <input type="checkbox" checked={clientsFlagged} onChange={(e) => setClientsFlagged(e.target.checked)} />
            <span>Only folders with flags</span>
          </label>
          <ul className="audit-client-list">
            {clients.map((c) => (
              <li key={c.name}>
                <button type="button" className="cf-btn cf-btn--flush audit-client" aria-current={c.name === folder ? "true" : undefined} onClick={() => choose(c.name)}>
                  <span className="audit-client-name">{c.name}</span>
                  <span className="audit-client-counts">
                    {c.flagged > 0 && (
                      <span className="audit-client-count" title={`${c.flagged} flagged`}>
                        <IconFlag filled className="audit-client-flag" />
                        {c.flagged}
                        <span className="audit-visually-hidden"> flagged</span>
                      </span>
                    )}
                    {GROUPS.filter((g) => g !== "unrecorded" && c[g] > 0).map((g) => (
                      <span key={g} className="audit-client-count" title={`${c[g]} put there by ${groupWord(g).toLowerCase()}`}>
                        <span className={`audit-dot audit-dot--${g}`} aria-hidden="true" />
                        {c[g]}
                        <span className="audit-visually-hidden"> by {groupWord(g).toLowerCase()}</span>
                      </span>
                    ))}
                  </span>
                </button>
              </li>
            ))}
            {clients.length === 0 && state === "ok" && <li className="audit-muted">No client folder matches.</li>}
          </ul>
        </nav>
        <section className="audit-tree-pane" aria-label="Folder contents">
          {!tree && <p className="audit-muted">{state === "loading" ? "Loading" : "Choose a client folder on the left."}</p>}
          {tree && root && (
            <>
              <h2 className="audit-folder-title">{tree.name}</h2>
              <div className="audit-controls">
                <div className="audit-kinds" role="group" aria-label="Who put the file there">
                  {(["all", ...GROUPS] as GroupFilter[]).map((id) => (
                    <button key={id} type="button" className="cf-btn cf-btn--chip audit-kind" aria-pressed={group === id} onClick={() => setGroup(id)}>
                      {id !== "all" && <span className={`audit-dot audit-dot--${id}`} aria-hidden="true" />}
                      {id === "all" ? "All" : groupWord(id)} <span className="audit-count">{countFor(id)}</span>
                    </button>
                  ))}
                  {ACTOR_KINDS.map((kind) => {
                    const Icon = KIND_ICONS[kind];
                    return (
                      <button
                        key={kind}
                        type="button"
                        className="cf-btn cf-btn--chip audit-kind"
                        aria-pressed={flagKinds.has(kind)}
                        aria-label={`Flagged by ${actorKindWord(kind).toLowerCase()}`}
                        onClick={() =>
                          setFlagKinds((prev) => {
                            const next = new Set(prev);
                            if (!next.delete(kind)) next.add(kind);
                            return next;
                          })
                        }
                      >
                        <IconFlag filled className="audit-chip-flag audit-chip-flag--red" />
                        <Icon className="audit-chip-kind" /> <span className="audit-count">{summary?.flags_by_kind[kind] ?? 0}</span>
                      </button>
                    );
                  })}
                </div>
                <ClearableSearch
                  wrapClassName="audit-search-wrap"
                  className="audit-search"
                  placeholder="Search file names"
                  value={text}
                  onValueChange={setText}
                  clearLabel="Clear the search"
                  aria-label="Search file names in this folder"
                />
              </div>
              <div className="audit-controls">
                <label className="audit-field">
                  <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
                  <span>Only files with a change on record</span>
                </label>
                <button type="button" className="cf-btn cf-btn--secondary" onClick={() => setCollapsed(new Set(folderPaths(root)))}>
                  Collapse all
                </button>
                <button type="button" className="cf-btn cf-btn--secondary" onClick={() => setCollapsed(new Set())}>
                  Expand all
                </button>
              </div>
              {hiddenCount > 0 && (
                <p className="audit-muted">
                  {hiddenCount} {hiddenCount === 1 ? "file has" : "files have"} no change in the last {days} days and {hiddenCount === 1 ? "is" : "are"} hidden. Flagged and clicked files always stay.
                </p>
              )}
              {tree.truncated && <p className="audit-muted">This folder is too large to show in full; the first part is shown.</p>}
              {root.children.length === 0 ? (
                <p className="audit-muted">Nothing here matches.</p>
              ) : (
                <div className="audit-tree-wrap">
                  <div className="audit-tree-head" aria-hidden="true">
                    <span>Flag</span>
                    <span>Name</span>
                    <span>Made by</span>
                    <span>Put here by</span>
                  </div>
                  <ul role="tree" aria-label={`${tree.name}, who made and who placed each file`} className="audit-tree-list audit-tree-root">
                    {root.children.map((child) => (
                      <Node key={child.path} node={child} depth={0} collapsed={collapsed} toggle={toggle} days={days} actions={actions} />
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}
