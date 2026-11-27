"use client";

import { useEffect, useState } from "react";
import { fetchClientScans } from "@/lib/scanResolver";
import type { ClientScan } from "@/lib/scanResolver";
import { ScanConfirm } from "./ScanConfirm";
import { addCommonTitle, PREVIEW_HEIGHT, PREVIEW_WIDTH, scanCommonDocument, scanOrder, removeCommonTitle, undoVirtualScan, useVirtualScanner, virtualScannerFileUrl, virtualScannerPreviewUrl } from "@/lib/virtualScanner";
import { alreadyScanned, copiesWarning, lastOrderLine, MAX_COPIES, measuredWords, parseCopies, scanBlockedReason, ukShortDate } from "@/lib/virtualScannerTypes";
import type { CommonDocument, LastOrder, VirtualScan } from "@/lib/virtualScannerTypes";

interface Outcome {
  ok: boolean;
  message: string;
}

function StockPreview({ doc }: { doc: CommonDocument }) {
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  return (
    <div className="vscan-viewer">
      {state === "failed" ? (
        <p className="cf2-error" role="alert">The first page could not be shown. Open the whole document instead.</p>
      ) : (
        <div className="vscan-page" data-state={state} aria-busy={state === "loading"}>
          {/* eslint-disable-next-line @next/next/no-img-element -- the hub already sizes it; an authenticated API picture gains nothing from the optimiser */}
          <img
            src={virtualScannerPreviewUrl(doc.document_id)}
            width={PREVIEW_WIDTH}
            height={PREVIEW_HEIGHT}
            loading="lazy"
            decoding="async"
            alt={`First page of ${doc.title}`}
            onLoad={() => setState("ready")}
            onError={() => setState("failed")}
          />
        </div>
      )}
      <a href={virtualScannerFileUrl(doc.document_id)} target="_blank" rel="noopener noreferrer">
        Open the whole document <span className="cf2-note">(opens in a new tab)</span>
      </a>
    </div>
  );
}

export function ScannerTab({ matterId }: { matterId: string }) {
  const { data, error, refresh } = useVirtualScanner(matterId);
  const [dates, setDates] = useState<Record<string, string>>({});
  const [copies, setCopies] = useState<Record<string, string>>({});
  const [viewing, setViewing] = useState("");
  const [busy, setBusy] = useState("");
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [newTitle, setNewTitle] = useState("");
  const [titleOutcome, setTitleOutcome] = useState<Outcome | null>(null);

  const [waiting, setWaiting] = useState<ClientScan[]>([]);
  const [waitingError, setWaitingError] = useState("");
  useEffect(() => {
    let cancelled = false;
    fetchClientScans(matterId)
      .then((scans) => {
        if (!cancelled) {
          setWaiting(scans);
          setWaitingError("");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setWaitingError(err instanceof Error ? err.message : "Could not look for this client's waiting scans.");
      });
    return () => {
      cancelled = true;
    };
  }, [matterId]);

  if (error && !data) return <p className="cf2-error" role="alert">{error}</p>;
  if (!data) return <p className="cf2-empty">Loading the virtual scanner...</p>;

  const today = data.today;
  const dateOf = (doc: CommonDocument) => dates[doc.document_id] ?? today;

  async function press(doc: CommonDocument) {
    setBusy(doc.document_id);
    try {
      const out = await scanCommonDocument(matterId, doc.document_id, dateOf(doc), parseCopies(copies[doc.document_id] ?? "1"));
      setOutcomes((o) => ({ ...o, [doc.document_id]: { ok: true, message: out.message } }));
      refresh();
    } catch (err) {
      setOutcomes((o) => ({ ...o, [doc.document_id]: { ok: false, message: err instanceof Error ? err.message : "Nothing was scanned." } }));
    } finally {
      setBusy("");
    }
  }

  async function undo(p: VirtualScan) {
    if (!window.confirm(`Undo ${p.file_name}? The copy moves into the client's 000 Removed folder and the charge comes off the bill. Nothing is deleted.`)) return;
    setBusy(p.scan_id);
    try {
      const out = await undoVirtualScan(p.scan_id);

      setOutcomes((o) => {
        const next = { ...o, [p.scan_id]: { ok: true, message: out.message } };
        delete next[p.document_id];
        return next;
      });
      refresh();
    } catch (err) {
      setOutcomes((o) => ({ ...o, [p.scan_id]: { ok: false, message: err instanceof Error ? err.message : "The scan was not undone." } }));
    } finally {
      setBusy("");
    }
  }

  async function pressScanOrder(order: LastOrder) {
    const key = `order:${order.folder}/${order.name}`;
    setBusy(key);
    try {
      let out = await scanOrder(matterId, order);
      if (out.needs_confirm && window.confirm(`${out.message}\n\nTell Case flow about this order as well?`)) {
        out = await scanOrder(matterId, order, true);
      }
      setOutcomes((o) => ({ ...o, [key]: { ok: out.ok, message: out.message } }));
      if (out.ok) refresh();
    } catch (err) {
      setOutcomes((o) => ({ ...o, [key]: { ok: false, message: err instanceof Error ? err.message : "Case flow was not told." } }));
    } finally {
      setBusy("");
    }
  }

  async function addTitle() {
    if (!newTitle.trim()) return;
    setBusy("title");
    try {
      const out = await addCommonTitle(newTitle.trim());
      setTitleOutcome({ ok: true, message: `Added "${out.title}". It has no stock copy yet: put the PDF in ${data!.folder || "the Common Scanned Docs folder"} under the same title to scan it.` });
      setNewTitle("");
      refresh();
    } catch (err) {
      setTitleOutcome({ ok: false, message: err instanceof Error ? err.message : "The title was not added." });
    } finally {
      setBusy("");
    }
  }

  async function removeTitle(doc: CommonDocument) {
    if (!window.confirm(`Take "${doc.title}" off the list? It is kept on record and can be typed in again.`)) return;
    setBusy(doc.document_id);
    try {
      await removeCommonTitle(doc);
      refresh();
    } catch (err) {
      setOutcomes((o) => ({ ...o, [doc.document_id]: { ok: false, message: err instanceof Error ? err.message : "The title was not removed." } }));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="cf2 vscan">
      <div className="cf2-bar">
        <h2 className="cf2-title">Scanner</h2>
        <button type="button" className="cf-btn cf-btn--neutral" onClick={refresh} title="Read the folders and waiting scans again">
          Refresh
        </button>
      </div>
      <section className="vscan-orders" aria-label="Last order">
        <h3 className="vscan-subtitle">Last order filed</h3>
        {data.last_order ? (
          <p className="vscan-last">
            {data.last_order.web_url ? (
              <a className="vscan-title" href={data.last_order.web_url} target="_blank" rel="noreferrer">{data.last_order.name}</a>
            ) : (
              <span className="vscan-title">{data.last_order.name}</span>
            )}
            <span className="cf2-note"> {lastOrderLine(data.last_order)}, in {data.last_order.folder}.</span>
          </p>
        ) : (
          <p className="cf2-empty">No court order or notice of hearing found in the Court-Orders folder.</p>
        )}
        {data.orders_expected.length > 0 && (
          <ul className="vscan-hints" aria-label="Orders expected">
            {data.orders_expected.map((o) => <li key={o.hearing_date}>{o.line}</li>)}
          </ul>
        )}
        {waiting.length > 0 && (
          <>
            <h3 className="vscan-subtitle">Waiting in Scanned Docs, probably this client&apos;s</h3>
            <ul className="vscan-list" aria-label="Waiting scans estimated to be this client's">
              {waiting.map((w) => (
                <li key={w.id} className="vscan-row">
                  <div className="vscan-head">
                    {w.web_url ? <a href={w.web_url} target="_blank" rel="noreferrer" className="vscan-title">{w.name}</a> : <span className="vscan-title">{w.name}</span>}
                  </div>
                  <ScanConfirm scan={w} onlyMatterId={matterId} onFiled={refresh} />
                </li>
              ))}
            </ul>
          </>
        )}
        {waitingError && <p className="cf2-error" role="alert">{waitingError}</p>}
        {data.scan_hints.filter((h) => !waiting.some((w) => w.name === h.name)).length > 0 && (
          <>
            <h3 className="vscan-subtitle">Waiting in Scanned Docs</h3>
            <ul className="vscan-hints" aria-label="Waiting scans that may be this client's">
              {data.scan_hints.filter((h) => !waiting.some((w) => w.name === h.name)).map((h) => (
                <li key={h.name}>
                  {h.web_url ? <a href={h.web_url} target="_blank" rel="noreferrer">{h.name}</a> : <span>{h.name}</span>}: {h.line}.{" "}
                  <span className="cf2-note">{h.label} To use it for Scan order, file it into the Court-Orders folder first.</span>
                </li>
              ))}
            </ul>
          </>
        )}
        {data.hint_errors.map((e) => <p key={e} className="cf2-error" role="alert">{e}</p>)}
      </section>

      <section className="vscan-orders" aria-label="Scan order">
        <h3 className="vscan-subtitle">Scan order</h3>
        <p className="cf2-note">
          An order that came on paper, with no email or soft copy: pick it from the Court-Orders folder and press Scan order. Case flow
          then treats it as the court&apos;s reply, as if it had come by email, and the next steps wait for their own press. Nothing is sent.
        </p>
        {data.orders.length === 0 ? (
          <p className="cf2-empty">No order in the Court-Orders folder to pick.</p>
        ) : (
          <ul className="vscan-list" aria-label="Orders to scan">
            {data.orders.map((o) => {
              const key = `order:${o.folder}/${o.name}`;
              const outcome = outcomes[key];
              return (
                <li key={key} className="vscan-row">
                  <div className="vscan-head">
                    <span className="vscan-title">{o.name}</span>
                    {o.recorded && <span className="vscan-tag">Case flow told</span>}
                  </div>
                  <p className="cf2-note">{lastOrderLine(o)}, in {o.folder}.</p>
                  <div className="vscan-actions">
                    <button type="button" className="cf-btn cf-btn--secondary" disabled={busy !== "" || Boolean(o.recorded)} onClick={() => pressScanOrder(o)}>
                      {busy === key ? "Telling Case flow..." : "Scan order"}
                    </button>
                  </div>
                  {outcome && <p className={outcome.ok ? "cf2-note" : "cf2-error"} role={outcome.ok ? "status" : "alert"}>{outcome.message}</p>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <h3 className="vscan-subtitle">Virtual scanner</h3>
      <p className="cf2-note">
        A common document that came in for this client: give the date it came in and press Scan. An unaltered copy is filed in{" "}
        {data.court_orders_folder || "the client's Court-Orders folder"} and billed as a routine letter in (plus perusal, when over the character limit) for each copy posted to us. Nothing is stamped or sent.
      </p>

      {!data.can_scan && <p className="cf2-error" role="alert">{data.refusal}</p>}
      {data.folder_error && <p className="cf2-error" role="alert">{data.folder_error}</p>}

      {data.documents.length === 0 ? (
        <p className="cf2-empty">No common documents yet. Put stock PDFs in {data.folder || "the Common Scanned Docs folder"}, or add a title below.</p>
      ) : (
        <ul className="vscan-list" aria-label="Common documents">
          {data.documents.map((doc) => {
            const date = dateOf(doc);
            const blocked = scanBlockedReason(data, doc, date, today);
            const earlier = alreadyScanned(data.scans, doc.document_id, date);
            const outcome = outcomes[doc.document_id];
            return (
              <li key={doc.document_id} className="vscan-row">
                <div className="vscan-head">
                  <span className="vscan-title">{doc.title}</span>
                  {!doc.has_file && <span className="vscan-tag">No stock copy yet</span>}
                  {doc.also_named.length > 0 && <span className="vscan-also">Also in the folder as {doc.also_named.join(", ")}</span>}
                </div>
                <div className="vscan-actions">
                  <label className="vscan-date">
                    Came in
                    <input
                      type="date"
                      value={date}
                      max={today}
                      onChange={(e) => setDates((d) => ({ ...d, [doc.document_id]: e.target.value }))}
                      disabled={!doc.has_file || !data.can_scan}
                    />
                  </label>
                  <label className="vscan-date">
                    Copies posted
                    <input
                      type="number"
                      min={1}
                      max={MAX_COPIES}
                      step={1}
                      value={copies[doc.document_id] ?? "1"}
                      onChange={(e) => setCopies((c) => ({ ...c, [doc.document_id]: e.target.value }))}
                      disabled={!doc.has_file || !data.can_scan}
                    />
                  </label>
                  <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setViewing(viewing === doc.document_id ? "" : doc.document_id)} aria-expanded={viewing === doc.document_id}>
                    {viewing === doc.document_id ? "Hide" : "View"}
                  </button>
                  <button
                    type="button"
                    className="cf-btn cf-btn--secondary"
                    disabled={Boolean(blocked) || busy !== ""}
                    title={blocked || (earlier ? `Already scanned for ${ukShortDate(date)}: pressing again files and bills nothing` : "")}
                    onClick={() => press(doc)}
                  >
                    {busy === doc.document_id ? "Scanning..." : "Scan"}
                  </button>
                  {!doc.has_file && (
                    <button type="button" className="cf-btn cf-btn--flush cf-btn--danger" disabled={busy !== ""} onClick={() => removeTitle(doc)}>
                      Remove title
                    </button>
                  )}
                </div>
                {copiesWarning(parseCopies(copies[doc.document_id] ?? "1")) && (
                  <p className="cf2-error" role="alert">{copiesWarning(parseCopies(copies[doc.document_id] ?? "1"))}</p>
                )}
                {earlier && !outcome && <p className="cf2-note">Already scanned for {ukShortDate(date)}: {earlier.file_name}.</p>}
                {outcome && (
                  <p className={outcome.ok ? "cf2-note" : "cf2-error"} role={outcome.ok ? "status" : "alert"}>
                    {outcome.message}
                  </p>
                )}
                {viewing === doc.document_id &&
                  (doc.has_file ? (
                    <StockPreview doc={doc} />
                  ) : (
                    <p className="cf2-empty vscan-viewer">{doc.title}: no stock copy.</p>
                  ))}
              </li>
            );
          })}
        </ul>
      )}
      {data.other_files.length > 0 && (
        <p className="cf2-note">Not scannable (PDFs only): {data.other_files.join(", ")}.</p>
      )}

      <details className="vscan-add">
        <summary>Add a document by title</summary>
        <p className="cf2-note">For a document with no stock copy yet. Admins only.</p>
        <div className="vscan-actions">
          <input type="text" value={newTitle} maxLength={150} placeholder="Title" aria-label="Title" onChange={(e) => setNewTitle(e.target.value)} />
          <button type="button" className="cf-btn cf-btn--neutral" disabled={!newTitle.trim() || busy !== ""} onClick={addTitle}>
            Add
          </button>
        </div>
        {titleOutcome && <p className={titleOutcome.ok ? "cf2-note" : "cf2-error"}>{titleOutcome.message}</p>}
      </details>

      <h3 className="vscan-subtitle">Scanned for this client</h3>
      {data.scans.length === 0 ? (
        <p className="cf2-empty">Nothing scanned yet.</p>
      ) : (
        <ul className="vscan-list" aria-label="Scanned for this client">
          {data.scans.map((p) => {
            const outcome = outcomes[p.scan_id];
            return (
              <li key={p.scan_id} className="vscan-row" data-status={p.status}>
                <div className="vscan-head">
                  {p.filed_url && p.status === "filed" ? (
                    <a className="vscan-title" href={p.filed_url} target="_blank" rel="noreferrer">{p.file_name}</a>
                  ) : (
                    <span className="vscan-title">{p.file_name}</span>
                  )}
                  {p.status === "undone" && <span className="vscan-tag">Undone</span>}
                </div>
                <p className="cf2-note">
                  Came in {ukShortDate(p.date_received)}. {p.copies} {p.copies === 1 ? "copy" : "copies"}. Scanned by {p.pressed_by}. {measuredWords(p)}.
                  {p.status === "undone" ? ` Undone by ${p.undone_by}.` : ""}
                </p>
                {p.billing_note && <p className="cf2-note">Billing: {p.billing_note}</p>}
                {p.status === "filed" && (
                  <div className="vscan-actions">
                    <button type="button" className="cf-btn cf-btn--neutral" disabled={busy !== ""} onClick={() => undo(p)}>
                      {busy === p.scan_id ? "Undoing..." : "Undo"}
                    </button>
                  </div>
                )}
                {outcome && <p className={outcome.ok ? "cf2-note" : "cf2-error"}>{outcome.message}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
