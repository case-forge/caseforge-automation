"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useModalFocus } from "@/lib/modalFocus";
import { DialogClose } from "./DialogClose";

interface WsFile {
  item_id: string;
  name: string;
  modified: string;
  signed: boolean;
}

const DAY = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "2-digit", month: "short", year: "numeric" });

export function RecordSignedWs({ matterId, onRecorded }: { matterId: string; onRecorded: (file: WsFile) => void }) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<WsFile[] | null>(null);
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dialogRef = useModalFocus<HTMLDivElement>(open);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setFiles(null);
    setError("");
    fetch(`/api/clients/ws-candidates?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" })
      .then(async (res) => (res.ok ? ((await res.json()) as { files: WsFile[] }) : Promise.reject(new Error("bad"))))
      .then((body) => {
        if (!live) return;
        setFiles(body.files);
        setChosen(body.files.find((f) => f.signed)?.item_id ?? "");
      })
      .catch(() => live && setError("The client's folder could not be read. Try again in a moment."));
    return () => {
      live = false;
    };
  }, [open, matterId]);

  const close = () => setOpen(false);
  const record = async () => {
    const file = files?.find((f) => f.item_id === chosen);
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/clients/record-signed-ws", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter_id: matterId, item_id: file.item_id }),
      });
      if (!res.ok) throw new Error(String(res.status));
      onRecorded(file);
      setOpen(false);
    } catch {
      setError("It was not recorded. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className="cf-btn cf-btn--link record-ws-open" aria-haspopup="dialog" onClick={() => setOpen(true)}>
        Record signed WS
      </button>
      {open && createPortal(
        <div className="new-client-backdrop" role="presentation">
          <div
            ref={dialogRef}
            className="new-client-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="record-ws-title"
            onKeyDown={(event) => {
              if (event.key === "Escape") close();
            }}
          >
            <DialogClose onClose={close} />
            <h2 id="record-ws-title">Record the signed statement</h2>
            <p className="record-ws-hint">Choose the client&apos;s signed witness statement. The file is not renamed or moved.</p>
            {files === null && !error && <p>Reading Client&apos;s Docs…</p>}
            {files && files.length === 0 && <p>There is no PDF starting with WS in Client&apos;s Docs.</p>}
            {files && files.length > 0 && (
              <fieldset className="record-ws-files">
                <legend className="sr-only">WS files</legend>
                {files.map((f) => {
                  const ms = Date.parse(f.modified);
                  return (
                    <label key={f.item_id} className="record-ws-file">
                      <input type="radio" name="record-ws" value={f.item_id} checked={chosen === f.item_id} onChange={() => setChosen(f.item_id)} />
                      <span className="record-ws-name">{f.name}</span>
                      <span className="record-ws-meta">
                        {Number.isNaN(ms) ? "" : DAY.format(new Date(ms))} · {f.signed ? "reads as signed" : "does not read as signed"}
                      </span>
                    </label>
                  );
                })}
              </fieldset>
            )}
            {error && <p className="record-ws-error" role="alert">{error}</p>}
            <div className="new-client-actions">
              <button type="button" className="cf-btn cf-btn--flush dialog-button--quiet" onClick={close}>Cancel</button>
              <button type="button" className="cf-btn cf-btn--primary" disabled={busy || !chosen} onClick={() => void record()}>
                Record
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
