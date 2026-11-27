"use client";

import { useEffect, useRef, useState } from "react";
import { londonTodayIso } from "@/lib/hearings";
import type { HearingFormValues } from "@/lib/hearings";
import { detectHearing } from "@/lib/hearingDetection";
import type { DetectedHearing } from "@/lib/hearingDetection";
import { cleanExtract, hearingDefaults } from "@/lib/hearingExtract";
import type { HearingExtract } from "@/lib/hearingExtract";
import { MIN_NOTE_MINUTES, SERVER_DEFAULT_MINUTES, formatTimeSpent, loadDefaultTime, minutesForPages, timeFromMinutes, totalMinutes } from "@/lib/anTime";
import { loadMinutesPerPage } from "@/lib/minutesPerPage";
import type { AnTime } from "@/lib/anTime";
import { hearingsHost, useHearingsVersion } from "@/lib/hearingsHost";
import { listedHearingsFor } from "@/lib/hearingDetection";
import type { Hearing } from "@/lib/hearings";
import { useMatterHearings } from "@/lib/useHearings";
import { buildAnTodo, buildMarkedTodos } from "@/lib/anTodo";
import type { MarkedTodo } from "@/lib/anTodo";
import { createTodo } from "@/lib/todos";
import { DOC_KINDS, DOC_OTHER_MAX, CUSTOM_FOLDER_MAX, OTHER_FOLDER, buildCreateBody, docOtherReady, extraFolders, folderValue, offeredFolders, otherFolderKind, partyReady, takesParty } from "@/lib/anFolder";
import { RecentAttendanceNotes } from "./RecentAttendanceNotes";
import type { TakenBackNote } from "./RecentAttendanceNotes";
import { flushPush, restoreIfLocalEmpty, schedulePush } from "@/lib/anBackup";
import { setDraftFlag } from "@/lib/draftFlag";
import type { AttendanceCaller, AttendanceNoteCreateResponse, AttendanceNoteKind } from "@/lib/types";
import {
  ATTENDANCE_CALLERS,
  ATTENDANCE_CALLER_LABELS,
  ATTENDANCE_CREATE_KINDS,
  ATTENDANCE_KIND_LABELS,
  DEFAULT_MINUTES_PER_PAGE,
  ATTENDANCE_NOTE_PLACEHOLDER,
  ATTENDANCE_WHO_LEGEND,
  currentKind,
  isAttendanceKind,
  takesPages,
} from "@/lib/types";
import type { AnDraft, AnFormState } from "@/lib/anDrafts";
import {
  clearWorkingCopy,
  deleteDraft,
  forgetSent,
  formatDraftTime,
  hasUnfinishedDraft,
  isBlankAnForm,
  isWorkingFromDraft,
  kindOf,
  loadDrafts,
  loadWorkingCopy,
  markWorkingFromDraft,
  rememberSent,
  saveDraft,
  saveWorkingCopy,
} from "@/lib/anDrafts";

function todayDisplay(): string {
  return new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function longDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export function AttendanceNoteForm({
  matterId,
  clientName,
  clientRole,
  caseRef,
  autoFocus = false,
  onCreated,
  onHearingAdded,
}: {
  matterId: string;
  clientName: string;
  clientRole: string;

  caseRef: string;
  autoFocus?: boolean;
  onCreated: () => void;
  onHearingAdded: () => void;
}) {

  const [initial] = useState(() => loadWorkingCopy(matterId));
  const [caller, setCaller] = useState<AttendanceCaller | "">(initial.caller);
  const [callerOther, setCallerOther] = useState(initial.callerOther);
  const [kind, setKind] = useState<AttendanceNoteKind>(kindOf(initial));
  const [pagesText, setPagesText] = useState("");

  const [docKind, setDocKind] = useState("");
  const [docOther, setDocOther] = useState("");

  const [folder, setFolder] = useState("");
  const [folderOther, setFolderOther] = useState("");
  const [foundFolders, setFoundFolders] = useState<{ name: string; code: string }[]>([]);
  useEffect(() => {
    let live = true;
    fetch(`/api/attendance-notes/folders?matter_id=${encodeURIComponent(matterId)}`)
      .then((r) => (r.ok ? r.json() : { folders: [] }))
      .then((b) => { if (live) setFoundFolders(Array.isArray(b.folders) ? b.folders : []); })
      .catch(() => {});
    return () => { live = false; };
  }, [matterId]);
  const folderToSend = folderValue(folder, folderOther);

  const [minutesPerPage, setMinutesPerPage] = useState(DEFAULT_MINUTES_PER_PAGE);
  const [noteText, setNoteText] = useState(initial.noteText);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [queued, setQueued] = useState(false);
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [drafts, setDrafts] = useState<AnDraft[]>(() => loadDrafts(matterId));
  const [showDrafts, setShowDrafts] = useState(false);
  const [draftSavedAt, setDraftSavedAt] = useState("");

  const [time, setTime] = useState<AnTime>(() => loadDefaultTime() ?? { hours: "", minutes: "" });
  const [showTime, setShowTime] = useState(false);
  const [detected, setDetected] = useState<DetectedHearing | null>(null);
  const [extract, setExtract] = useState<HearingExtract | null>(null);
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [hearingAdded, setHearingAdded] = useState(false);

  const matterHearings = useMatterHearings(matterId);

  const writes = useHearingsVersion();
  useEffect(() => {
    if (writes > 0) matterHearings.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [writes]);
  const [addAnyway, setAddAnyway] = useState<string[]>([]);

  const [todoDismissed, setTodoDismissed] = useState<string[]>([]);
  const [todoAdded, setTodoAdded] = useState<string[]>([]);
  const [todoBusy, setTodoBusy] = useState(false);
  const [todoError, setTodoError] = useState("");
  const textRef = useRef<HTMLTextAreaElement>(null);
  function apply(form: AnFormState) {
    setCaller(form.caller);
    setKind(kindOf(form));
    setCallerOther(form.callerOther);
    setNoteText(form.noteText);
  }

  useEffect(() => {
    if (autoFocus) textRef.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    let cancelled = false;
    void loadMinutesPerPage().then((n) => {
      if (!cancelled) setMinutesPerPage(n);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    saveWorkingCopy(matterId, { caller, callerOther, noteText, kind });
  }, [matterId, caller, callerOther, noteText, kind]);

  const restoreDone = useRef(false);
  useEffect(() => {
    let cancelled = false;
    restoreDone.current = false;
    void restoreIfLocalEmpty(matterId).then((restored) => {
      if (!cancelled && restored) {
        if (restored.working) apply(restored.working);
        setDrafts(restored.drafts);
        syncDraftFlag();
      }
      restoreDone.current = true;
    });
    return () => {
      cancelled = true;
      flushPush(matterId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId]);

  useEffect(() => {
    if (restoreDone.current) schedulePush(matterId);
  }, [matterId, caller, callerOther, noteText, kind, drafts]);

  useEffect(() => {
    if (isBlankAnForm({ caller, callerOther, noteText }) && isWorkingFromDraft(matterId)) {
      markWorkingFromDraft(matterId, false);
      syncDraftFlag();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId, caller, callerOther, noteText]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDetected(detectHearing(noteText, londonTodayIso())), 400);
    return () => window.clearTimeout(timer);
  }, [noteText]);

  const detectedKey = detected ? `${detected.date}|${detected.time ?? ""}` : "";

  const [settledText, setSettledText] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setSettledText(noteText), 1200);
    return () => window.clearTimeout(timer);
  }, [noteText]);
  useEffect(() => {
    if (!detectedKey) {
      setExtract(null);
      return;
    }
    const controller = new AbortController();
    fetch("/api/hearing-extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: settledText, today: londonTodayIso() }),
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((body) => setExtract(body ? cleanExtract(body) : null))
      .catch(() => undefined);
    return () => controller.abort();
  }, [detectedKey, settledText]);

  function changeTime(next: AnTime) {
    setTime(next);
  }

  function changePages(text: string) {
    const clean = text.replace(/\D/g, "").slice(0, 4);
    setPagesText(clean);
    const minutes = clean ? minutesForPages(Number(clean), minutesPerPage) : null;
    if (minutes !== null) setTime(timeFromMinutes(minutes));
  }

  function changeKind(next: AttendanceNoteKind) {
    setKind(next);
  }

  const timeEntered = time.hours.trim() !== "" || time.minutes.trim() !== "";
  const minutesSpent = totalMinutes(time);
  const timeInvalid = timeEntered && minutesSpent === null;

  const shownMinutes = minutesSpent !== null && takesPages(kind) ? Math.max(minutesSpent, MIN_NOTE_MINUTES) : minutesSpent;
  const timeLabel = shownMinutes !== null ? formatTimeSpent(shownMinutes) : `${SERVER_DEFAULT_MINUTES} mins (default)`;

  const offerKey = detected ? `${detected.date}|${detected.time ?? ""}` : "";
  const offer = detected && !dismissed.includes(offerKey) && !hearingAdded ? detected : null;
  const listedMatches: Hearing[] = offer && !addAnyway.includes(offerKey) ? listedHearingsFor(matterHearings.hearings, offer) : [];
  const defaultsForHearing: Partial<HearingFormValues> = offer
    ? hearingDefaults(offer, extract, { matterId, caseRef, name: clientName, role: clientRole })
    : {};

  const todoDraft = detected && !todoDismissed.includes(offerKey) && !todoAdded.includes(offerKey) ? buildAnTodo(noteText, detected) : null;
  async function addTodo() {
    if (!todoDraft) return;
    const matter = Number(matterId);
    setTodoBusy(true);
    setTodoError("");
    try {
      await createTodo({
        title: todoDraft.title,
        matterId: Number.isFinite(matter) ? matter : null,
        due: todoDraft.due,
        dueHasTime: todoDraft.dueHasTime,
      });
      setTodoAdded((keys) => [...keys, offerKey]);
    } catch (err) {
      setTodoError(err instanceof Error ? err.message : "Could not add the task.");
    } finally {
      setTodoBusy(false);
    }
  }

  const [markedDismissed, setMarkedDismissed] = useState<string[]>([]);
  const [markedAdded, setMarkedAdded] = useState<string[]>([]);
  const [markedBusy, setMarkedBusy] = useState("");
  const [markedError, setMarkedError] = useState("");
  const allMarked = buildMarkedTodos(noteText);
  const markedTodos = allMarked.filter((item) => !markedDismissed.includes(item.key) && !markedAdded.includes(item.key));

  const plain = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  const draftCoveredByList = !!todoDraft && allMarked.some((m) => plain(todoDraft.title).includes(plain(m.title)) || plain(m.title).includes(plain(todoDraft.title)));
  async function addMarkedTodo(item: MarkedTodo) {
    const matter = Number(matterId);
    setMarkedBusy(item.key);
    setMarkedError("");
    try {
      await createTodo({ title: item.title, matterId: Number.isFinite(matter) ? matter : null, due: item.due ?? undefined, dueHasTime: item.dueHasTime });
      setMarkedAdded((keys) => [...keys, item.key]);
    } catch (err) {
      setMarkedError(err instanceof Error ? err.message : "Could not add the task.");
    } finally {
      setMarkedBusy("");
    }
  }

  const hasPages = takesPages(kind);

  const pagesNumber = /^\d+$/.test(pagesText) && Number(pagesText) >= 1 && Number(pagesText) <= 5000 ? Number(pagesText) : 0;
  const pagesInvalid = pagesText !== "" && (pagesNumber === 0 || minutesForPages(pagesNumber, minutesPerPage) === null);
  const form: AnFormState = { caller, callerOther, noteText, kind };
  const ready = partyReady(kind, caller, callerOther) && (!hasPages || docOtherReady(docKind, docOther)) && folderToSend !== "" && noteText.trim() !== "" && !timeInvalid && !(hasPages && (pagesInvalid || minutesSpent === null));

  function syncDraftFlag() {
    void setDraftFlag(matterId, hasUnfinishedDraft(matterId));
  }

  function saveAsDraft() {
    if (isBlankAnForm(form)) return;
    const draft = saveDraft(matterId, form);
    setDrafts(loadDrafts(matterId));
    setDraftSavedAt(draft.savedAt);
    setQueued(false);
    clearWorkingCopy(matterId);
    markWorkingFromDraft(matterId, false);
    apply({ caller: "", callerOther: "", noteText: "", kind: "call" });
    syncDraftFlag();
  }

  function takeBackNote(note: TakenBackNote) {
    if (!isBlankAnForm(form)) saveDraft(matterId, form);
    setDrafts(loadDrafts(matterId));
    apply({
      caller: (ATTENDANCE_CALLERS as readonly string[]).includes(note.caller) ? (note.caller as AttendanceCaller) : "",
      callerOther: note.callerOther,
      noteText: note.noteText,
      kind: isAttendanceKind(note.kind) ? currentKind(note.kind) : "call",
    });
    if (note.timeMinutes) setTime(timeFromMinutes(note.timeMinutes));
    markWorkingFromDraft(matterId, true);
    setQueued(false);
    setError("");
    setDraftSavedAt("");
    syncDraftFlag();
    textRef.current?.focus();
  }

  function openDraft(draft: AnDraft) {

    if (!isBlankAnForm(form)) saveDraft(matterId, form);
    deleteDraft(matterId, draft.id);
    setDrafts(loadDrafts(matterId));
    apply({ caller: draft.caller, callerOther: draft.callerOther, noteText: draft.noteText, kind: kindOf(draft) });
    markWorkingFromDraft(matterId, true);
    syncDraftFlag();
    setShowDrafts(false);
    setDraftSavedAt("");
    setQueued(false);
    textRef.current?.focus();
  }

  function removeDraft(id: string) {
    setDrafts(deleteDraft(matterId, id));
    syncDraftFlag();
  }

  async function create() {
    if (!ready || saving) return;
    setSaving(true);
    setError("");
    setQueued(false);
    setDraftSavedAt("");
    try {
      const res = await fetch("/api/attendance-notes/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          buildCreateBody({
            matterId,
            kind,
            caller,
            callerOther,
            noteText,
            minutesSpent,
            pages: hasPages ? pagesNumber : 0,
            docKind,
            docOther,
            folder: folderToSend,
          }),
        ),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || "Could not create the attendance note.");

      const accepted = body as AttendanceNoteCreateResponse;
      setQueued(true);

      rememberSent(matterId, accepted.draft_id, form);
      clearWorkingCopy(matterId);
      markWorkingFromDraft(matterId, false);
      apply({ caller: "", callerOther: "", noteText: "", kind: "call" });
      setPagesText("");
      setDocKind("");
      setDocOther("");
      setFolder("");
      setFolderOther("");
      syncDraftFlag();
      setRefreshSignal((n) => n + 1);
    } catch (err) {

      setError(err instanceof Error ? err.message : "Could not create the attendance note.");
    } finally {
      setSaving(false);
    }
  }

  const pagesField = (
    <label className="an-form-pages-field">
      <span className="an-form-legend an-form-legend--auto">Pages</span>
      <input
        className="edit-input an-form-pages"
        name="an-pages"
        inputMode="numeric"
        value={pagesText}
        disabled={saving}
        maxLength={4}
        aria-label="Number of pages"
        aria-invalid={pagesInvalid || undefined}
        onChange={(e) => changePages(e.target.value)}
      />
    </label>
  );

  return (
    <form
      className="an-form no-print"
      onSubmit={(e) => {
        e.preventDefault();
        void create();
      }}
    >
      <div className="an-form-head">
        <h3 className="detail-section-title">New attendance note</h3>
        <span className="an-form-date">Date of call: {todayDisplay()}</span>
        <button
          type="button"
          className="an-form-drafts-toggle"
          aria-expanded={showDrafts}
          disabled={drafts.length === 0}
          onClick={() => setShowDrafts((open) => !open)}
        >
          View drafts{drafts.length > 0 ? ` (${drafts.length})` : ""}
        </button>
      </div>

      {showDrafts && drafts.length > 0 && (
        <ul className="an-drafts" aria-label="Saved drafts">
          {drafts.map((draft) => (
            <li key={draft.id} className="an-draft">
              <button type="button" className="an-draft-open" onClick={() => openDraft(draft)}>
                <span className="an-draft-when">{formatDraftTime(draft.savedAt)}</span>
                <span className="an-draft-who">
                  {kindOf(draft) !== "call" ? `${ATTENDANCE_KIND_LABELS[kindOf(draft)]}: ` : ""}
                  {draft.caller === "other"
                    ? draft.callerOther || "Other"
                    : draft.caller
                      ? ATTENDANCE_CALLER_LABELS[draft.caller]
                      : "No party chosen"}
                </span>
                <span className="an-draft-text">{draft.noteText.trim().split("\n")[0] || "(empty)"}</span>
              </button>
              <button type="button" className="cf-btn cf-btn--flush cf-btn--danger cf-btn--small" onClick={() => removeDraft(draft.id)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}

      { }
      <div className="an-form-callers-row">
      <label className="an-form-kinds">
        <span className="an-form-legend">Note type</span>
        <select
          className="edit-input an-form-select an-form-compact"
          name="an-kind"
          value={kind}
          disabled={saving}
          onChange={(e) => changeKind(e.target.value as typeof kind)}
        >
          {(ATTENDANCE_CREATE_KINDS.includes(kind as (typeof ATTENDANCE_CREATE_KINDS)[number]) ? ATTENDANCE_CREATE_KINDS : [...ATTENDANCE_CREATE_KINDS, kind]).map((option) => (
            <option key={option} value={option}>{ATTENDANCE_KIND_LABELS[option]}</option>
          ))}
        </select>
      </label>
      {takesParty(kind) && (
      <fieldset className="an-form-callers" disabled={saving}>
        <legend className="an-form-legend">{ATTENDANCE_WHO_LEGEND}</legend>
        <select
          className="edit-input an-form-select an-form-compact"
          name="an-caller"
          aria-label={ATTENDANCE_WHO_LEGEND}
          value={caller}
          onChange={(e) => setCaller(e.target.value as typeof caller)}
        >
          <option value="" disabled>Choose…</option>
          {ATTENDANCE_CALLERS.map((option) => (
            <option key={option} value={option}>{ATTENDANCE_CALLER_LABELS[option]}</option>
          ))}
        </select>
        { }
        <input
          type="text"
          className="an-form-other"
          data-shown={caller === "other"}
          value={callerOther}
          onChange={(e) => setCallerOther(e.target.value)}
          placeholder="Who was it?"
          aria-label="Name of the party"
          tabIndex={caller === "other" ? 0 : -1}
          aria-hidden={caller !== "other"}
        />
      </fieldset>
      )}
      {!takesParty(kind) && (
        <>
          <label className="an-form-kinds">
            <span className="an-form-legend an-form-legend--auto">Doc type</span>
            <select
              className="edit-input an-form-select an-form-compact"
              name="an-doc-type"
              aria-label="Doc type"
              value={docKind}
              disabled={saving}
              onChange={(e) => setDocKind(e.target.value)}
            >
              <option value="">Choose…</option>
              {DOC_KINDS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <input
            type="text"
            className="an-form-other"
            name="an-doc-other"
            data-shown={docKind === "other"}
            value={docOther}
            maxLength={DOC_OTHER_MAX}
            disabled={saving}
            onChange={(e) => setDocOther(e.target.value)}
            placeholder="What was it?"
            aria-label="What the document was"
            tabIndex={docKind === "other" ? 0 : -1}
            aria-hidden={docKind !== "other"}
          />
          {pagesField}
        </>
      )}
      { }
      <fieldset className="an-form-callers" disabled={saving}>
        <legend className="an-form-legend">Folder</legend>
        <select
          className="edit-input an-form-select an-form-compact"
          name="an-folder"
          aria-label="Folder"
          aria-required="true"
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
        >
          <option value="" disabled>Choose…</option>
          {offeredFolders(foundFolders).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
          {extraFolders(foundFolders).map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
          <option value={OTHER_FOLDER}>Other</option>
        </select>
        <input
          type="text"
          className="an-form-other"
          data-shown={folder === OTHER_FOLDER}
          name="an-folder-other"
          value={folderOther}
          maxLength={CUSTOM_FOLDER_MAX}
          onChange={(e) => setFolderOther(e.target.value)}
          placeholder="Folder name"
          aria-label="Folder name"
          title={otherFolderKind(folderOther) === "FLA" ? "Goes in the FLA folder" : otherFolderKind(folderOther) === "CA" ? "Goes in the CA folder" : otherFolderKind(folderOther) === "" && folderOther.trim() !== "" ? "That names FLA and CA orders together. Pick one." : "A folder with this name"}
          aria-invalid={otherFolderKind(folderOther) === "" && folderOther.trim() !== "" ? true : undefined}
          tabIndex={folder === OTHER_FOLDER ? 0 : -1}
          aria-hidden={folder !== OTHER_FOLDER}
        />
      </fieldset>
      <div className="an-form-time">
          { }
          { }
          <span className="an-form-time-boxes" data-shown={showTime}>
              <input
                type="text"
                inputMode="numeric"
                className="an-form-time-box"
                value={time.hours}
                onChange={(e) => changeTime({ ...time, hours: e.target.value.replace(/\D/g, "").slice(0, 2) })}
                placeholder="hh"
                aria-label="Hours spent"
                aria-invalid={timeInvalid || undefined}
              />
              <span aria-hidden="true">:</span>
              <input
                type="text"
                inputMode="numeric"
                className="an-form-time-box"
                value={time.minutes}
                onChange={(e) => changeTime({ ...time, minutes: e.target.value.replace(/\D/g, "").slice(0, 2) })}
                placeholder="mm"
                aria-label="Minutes spent"
                aria-invalid={timeInvalid || undefined}
              />
          </span>
          <button
            type="button"
            className="an-form-time-toggle"
            aria-expanded={showTime}
            onClick={() => setShowTime((open) => !open)}
          >
            Time spent: {timeLabel}
          </button>
        </div>
      </div>

      <textarea
        ref={textRef}
        className="an-form-text"
        rows={5}
        value={noteText}
        onChange={(e) => setNoteText(e.target.value)}
        placeholder={ATTENDANCE_NOTE_PLACEHOLDER[kind]}
        aria-label="Attendance note content"
        disabled={saving}
      />

      {timeInvalid && (
        <p className="an-form-error" role="alert">
          Time spent needs whole hours (0 to 99) and minutes (0 to 59).
        </p>
      )}

      {offer && listedMatches.length > 0 && (
        <div className="an-hearing-offer" role="status">
          <span>
            {listedMatches.length === 1 ? "A hearing is already listed" : `${listedMatches.length} hearings are already listed`} on{" "}
            <strong>
              {longDate(offer.date)}
              {offer.time ? `, ${offer.time}` : ""}
            </strong>
            {listedMatches.length === 1 && listedMatches[0].court ? ` at ${listedMatches[0].court}` : ""}. Edit it instead of adding another?
          </span>
          {listedMatches.map((hearing) => (
            <button key={hearing.hearing_id} type="button" className="cf-btn cf-btn--secondary" onClick={() => hearingsHost.openEdit(hearing)}>
              {listedMatches.length === 1 ? "Edit hearing" : `Edit ${hearing.hearing_time ? hearing.hearing_time.slice(0, 5) : "hearing"}`}
            </button>
          ))}
          <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setAddAnyway((keys) => [...keys, offerKey])}>
            Add a different hearing
          </button>
          <button type="button" className="cf-btn cf-btn--flush" onClick={() => setDismissed((d) => [...d, offerKey])}>
            Dismiss
          </button>
        </div>
      )}
      {offer && listedMatches.length === 0 && (
        <div className="an-hearing-offer" role="status">
          <span>
            Add a Hearing on{" "}
            <strong>
              {longDate(offer.date)}
              {offer.time ? `, ${offer.time}` : ""}
            </strong>{" "}
            for {clientName || "this client"}?
          </span>
          <button type="button" className="cf-btn cf-btn--secondary" onClick={() =>
              hearingsHost.openCreate({
                matterId,
                clientName,
                defaults: defaultsForHearing,
                known: matterHearings.hearings,
                intro: caseRef ? undefined : "This client's record has no single court number, so type it in.",
                onCreated: () => {
                  setHearingAdded(true);
                  onHearingAdded();
                },
              })
            }>
            Add hearing
          </button>
          <button type="button" className="cf-btn cf-btn--flush" onClick={() => setDismissed((d) => [...d, offerKey])}>
            Dismiss
          </button>
        </div>
      )}
      {hasPages && pagesInvalid && (
        <p className="an-form-error" role="alert">
          Pages needs a whole number that comes to under 100 hours.
        </p>
      )}
      {todoDraft && detected && !draftCoveredByList && (
        <div className="an-hearing-offer" role="status">
          <span>
            Add to To do: <strong>{todoDraft.title}</strong>, due{" "}
            <strong>
              {longDate(detected.date)}
              {todoDraft.dueHasTime ? `, ${detected.time ?? ""}` : ""}
            </strong>
            ?
          </span>
          <button type="button" className="cf-btn cf-btn--secondary" disabled={todoBusy} onClick={() => void addTodo()}>
            {todoBusy ? "Adding..." : "Add to To do"}
          </button>
          <button type="button" className="cf-btn cf-btn--flush" onClick={() => setTodoDismissed((d) => [...d, offerKey])}>
            Dismiss
          </button>
          {todoError && (
            <span className="an-form-error" role="alert">
              {todoError}
            </span>
          )}
        </div>
      )}
      {detected && todoAdded.includes(offerKey) && (
        <p className="an-form-filed" role="status">
          Added to To do.
        </p>
      )}
      {markedTodos.map((item) => (
        <div className="an-hearing-offer" role="status" key={item.key}>
          <span>
            Add to To do: <strong>{item.title}</strong>
            {item.due ? (
              <>
                , due <strong>{longDate(item.due.slice(0, 10))}</strong>
              </>
            ) : null}
            ?
          </span>
          <button type="button" className="cf-btn cf-btn--secondary" disabled={markedBusy !== ""} onClick={() => void addMarkedTodo(item)}>
            {markedBusy === item.key ? "Adding..." : "Add to To do"}
          </button>
          <button type="button" className="cf-btn cf-btn--flush" onClick={() => setMarkedDismissed((d) => [...d, item.key])}>
            Dismiss
          </button>
        </div>
      ))}
      {markedError && (
        <p className="an-form-error" role="alert">
          {markedError}
        </p>
      )}
      {markedAdded.length > 0 && (
        <p className="an-form-filed" role="status">
          {markedAdded.length === 1 ? "Added to To do." : `${markedAdded.length} tasks added to To do.`}
        </p>
      )}
      {hearingAdded && (
        <p className="an-form-filed" role="status">
          Hearing added to the calendar.
        </p>
      )}

      <div className="an-form-actions">
        <button type="submit" className="cf-btn cf-btn--primary an-form-submit" data-umami-event="attendance-note-create" data-umami-event-folder={folderToSend === "FLA" || folderToSend === "CA" ? folderToSend : "other"} disabled={!ready || saving}>
          {saving ? "Saving..." : "Create attendance note"}
        </button>
        <button
          type="button"
          className="cf-btn cf-btn--neutral"
          disabled={isBlankAnForm(form) || saving}
          onClick={saveAsDraft}
        >
          Save as draft
        </button>
        {error && (
          <span className="an-form-error" role="alert">
            {error}
          </span>
        )}
        {draftSavedAt && !error && (
          <span className="an-form-filed" role="status">
            Draft saved {formatDraftTime(draftSavedAt)}
          </span>
        )}
        {queued && !error && (
          <span className="an-form-filed" role="status">
            Saved. Filing now.
          </span>
        )}
      </div>

      <RecentAttendanceNotes
        matterId={matterId}
        refreshSignal={refreshSignal}
        onFiled={onCreated}
        onEdit={takeBackNote}
        onNoteFiled={(draftId) => forgetSent(matterId, draftId)}
      />

    </form>
  );
}
