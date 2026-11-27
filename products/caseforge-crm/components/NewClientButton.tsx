"use client";

import { useEffect, useRef, useState } from "react";
import { useModalFocus } from "@/lib/modalFocus";
import { IconUserPlus } from "./icons";
import { HeaderOverflowEntry } from "./HeaderOverflow";
import { useDismiss } from "@/lib/dismiss";
import { cleanPhone, currentPreview, manualReady, type NewClientPreview } from "@/lib/newClient";
import { usePolledStore } from "@/lib/polledStore";
import { newPressId, pendingBadgeLabel, pendingCountsStore, resumedLines, type ResumedNewClient } from "@/lib/pendingNewClients";
import { PendingNewClients } from "./PendingNewClients";
import { BLANK_MANUAL_EXTRAS, ManualFields, NewClientChoice, PhoneField, PreviewBox, PreviewCreateActions, type Category } from "./NewClientParts";
import { DialogClose } from "./DialogClose";

type Made = ResumedNewClient;
type Mode = "choose" | "email" | "manual";
type ManualMade = { matter_id: string; category: string; folder: string };

const ADDRESS_CHECK = "[address-check] ";

export function NewClientButton() {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const [listOpen, setListOpen] = useState(false);
  const { data: counts } = usePolledStore(pendingCountsStore);
  const unsent = counts?.unsent ?? 0;
  const overdue = counts?.overdue ?? 0;
  const waiting = counts?.waiting ?? 0;
  const [categories, setCategories] = useState<Category[]>([]);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [mode, setMode] = useState<Mode>("choose");
  const [extras, setExtras] = useState(BLANK_MANUAL_EXTRAS);
  const [manualMade, setManualMade] = useState<ManualMade | null>(null);
  const phoneCheck = cleanPhone(phone);
  const [category, setCategory] = useState("");
  const [sendRif, setSendRif] = useState(false);
  const [sendLaif, setSendLaif] = useState(false);
  const [preview, setPreview] = useState<{ key: string; data: NewClientPreview } | null>(null);

  function openDialog() {
    setMode("choose");
    setOpen(true);
  }

  function choose(next: Mode) {
    setError("");
    setPreview(null);
    setAddressCheck(false);
    setAddressChecked(false);
    setMode(next);
  }

  function openList() {
    close();
    setListOpen(true);
  }

  function closeList() {
    setListOpen(false);
    pendingCountsStore.refresh();
  }
  const [addressCheck, setAddressCheck] = useState(false);
  const [addressChecked, setAddressChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [made, setMade] = useState<Made | null>(null);
  const firstRef = useRef<HTMLInputElement>(null);

  const pressRef = useRef<{ key: string; id: string }>({ key: "", id: "" });

  useEffect(() => {
    if (!open || mode === "choose") return;
    firstRef.current?.focus();
    if (categories.length > 0) return;
    let cancelled = false;
    void fetch("/api/new-client")
      .then((res) => (res.ok ? res.json() : { categories: [] }))
      .then((body) => {
        if (!cancelled) setCategories((body.categories ?? []) as Category[]);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open, mode, categories.length]);

  function close() {
    setOpen(false);
    setError("");
    setAddressCheck(false);
    setAddressChecked(false);
    setPreview(null);
    if (made || manualMade) {
      setMade(null);
      setManualMade(null);
      pressRef.current = { key: "", id: "" };
      setFirst("");
      setLast("");
      setEmail("");
      setPhone("");
      setExtras(BLANK_MANUAL_EXTRAS);
      setCategory("");
      setSendRif(false);
      setSendLaif(false);
    }
  }

  useDismiss(open, () => close(), dialogRef);
  useModalFocus(open, dialogRef);

  async function send(asPreview: boolean) {
    if (busy) return;
    setBusy(true);
    setError("");
    if (!asPreview) setPreview(null);
    const sentKey = formKey;
    const manual = mode === "manual";
    if (!manual && !asPreview && pressRef.current.key !== formKey) pressRef.current = { key: formKey, id: newPressId() };
    try {
      const common = {
        first_name: first,
        last_name: last,
        email,
        ...(phoneCheck.ok && phoneCheck.value ? { phone: phoneCheck.value } : {}),
        category,
        address_checked: addressChecked,
        preview: asPreview,
      };
      const manualFields = {
        middle_name: extras.middle,
        dob: extras.dob,
        nino: extras.nino,
        address_line1: extras.address1,
        address_line2: extras.address2,
        address_line3: extras.address3,
        address_line4: extras.address4,
        postcode: extras.postcode,
        matter_details: extras.matterDetails,
      };
      const res = await fetch(manual ? "/api/new-client/manual" : "/api/new-client", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          manual ? { ...common, ...manualFields } : { ...common, send_rif: sendRif, send_laif: sendLaif, ...(asPreview ? {} : { request_id: pressRef.current.id }) },
        ),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const fallback = asPreview
          ? "The preview could not be made. Nothing was made."
          : manual
            ? "The client could not be added."
            : "The new client could not be opened.";
        const message = String(body.error ?? fallback);
        if (message.startsWith(ADDRESS_CHECK)) {
          setAddressCheck(true);
          setError(message.slice(ADDRESS_CHECK.length));
        } else {
          setError(message);
        }
        return;
      }
      if (asPreview) setPreview({ key: sentKey, data: body as NewClientPreview });
      else if (manual) setManualMade(body as ManualMade);
      else {
        setMade(body as Made);
        pendingCountsStore.refresh();
      }
    } catch {
      setError(
        asPreview
          ? "The preview could not be made. Nothing was made."
          : manual
            ? "The client was not finished. The folder may already have been made: look for it, and check the client is not on file, before pressing Create again."
            : "The new client was not finished. Press Create again to carry on: nothing is made twice.",
      );
    } finally {
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (ready && !busy && !(addressCheck && !addressChecked)) void send(true);
  }

  const formKey = JSON.stringify([mode, first, last, email, phone, category, sendRif, sendLaif, addressChecked, extras]);
  const shownPreview = currentPreview(preview, formKey);

  const ready =
    mode === "manual"
      ? manualReady({ first, last, category, phone })
      : Boolean(first.trim() && last.trim() && email.trim() && category && phoneCheck.ok);

  return (
    <>
      <button
        type="button"
        className="cf-btn cf-btn--flush attention-button attention-button--newclient"
        data-header-measure=""
        data-active={waiting > 0}
        data-overdue={overdue > 0}
        aria-label={pendingBadgeLabel(waiting, unsent, overdue)}
        title="New client"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={openDialog}
      >
        <IconUserPlus aria-hidden="true" />
        {waiting > 0 && (
          <span className="attention-count" aria-hidden="true">
            {waiting}
          </span>
        )}
      </button>
      <HeaderOverflowEntry
        icon={<IconUserPlus aria-hidden="true" />}
        label="New client"
        ariaLabel={pendingBadgeLabel(waiting, unsent, overdue)}
        count={waiting}
        tone="attention-button--newclient"
        active={waiting > 0}
        expanded={open}
        onClick={openDialog}
      />
      {listOpen && <PendingNewClients onClose={closeList} />}
      {open && (
        <div className="new-client-backdrop" role="presentation">
          <div
            ref={dialogRef}
            className="new-client-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-client-title"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") close();
            }}
          >
            {!(made || manualMade) && <DialogClose onClose={close} />}
            <h2 id="new-client-title">New client</h2>
            {waiting > 0 && !made && (
              <p className="new-client-waiting">
                <button type="button" className="cf-btn cf-btn--link new-client-waiting-link" onClick={openList}>
                  {waiting} waiting for their New Client Form{unsent > 0 ? `, ${unsent} email${unsent === 1 ? "" : "s"} not sent` : ""}
                </button>
              </p>
            )}
            {manualMade ? (
              <div className="new-client-done">
                <p>
                  Client added under {manualMade.category}
                  (matter {manualMade.matter_id}). Their folder and record are made. No email was drafted or sent.
                </p>
                <div className="new-client-actions">
                  <button type="button" className="cf-btn cf-btn--primary" onClick={close}>Done</button>
                </div>
              </div>
            ) : mode === "choose" ? (
              <NewClientChoice onEmail={() => choose("email")} onManual={() => choose("manual")} onCancel={close} />
            ) : made ? (
              <div className="new-client-done">
                <p>
                  Folder made under {made.category}. {made.drafts.length === 1 ? "One draft is" : `${made.drafts.length} drafts are`} waiting
                  in Outlook to read and send, with a link for each form:
                </p>
                <ul>
                  {made.drafts.map((d) => (
                    <li key={d.documents}>{d.documents}</li>
                  ))}
                </ul>
                {made.resumed && (
                  <div className="new-client-resumed" role="status">
                    {resumedLines(made).map((line) => (
                      <p key={line}>{line}</p>
                    ))}
                  </div>
                )}
                <p className="new-client-note">
                  The client is added to the CRM when their signed New Client Form comes back, so they are not in the search yet.
                  Until then they are listed under the number on this button.
                </p>
                <div className="new-client-actions">
                  {made.drafts[0]?.web_link && (
                    <a href={made.drafts[0].web_link} target="_blank" rel="noreferrer">
                      Open the draft
                    </a>
                  )}
                  <button type="button" className="cf-btn cf-btn--neutral" onClick={openList}>Waiting clients</button>
                  <button type="button" className="cf-btn cf-btn--primary" onClick={close}>Done</button>
                </div>
              </div>
            ) : mode === "manual" ? (
              <form onSubmit={submit}>
                <ManualFields
                  values={{ first, last, email, phone, category, ...extras }}
                  categories={categories}
                  onChange={(patch) => {
                    if (patch.first !== undefined) setFirst(patch.first);
                    if (patch.last !== undefined) setLast(patch.last);
                    if (patch.email !== undefined) setEmail(patch.email);
                    if (patch.phone !== undefined) setPhone(patch.phone);
                    if (patch.category !== undefined) setCategory(patch.category);
                    const extraPatch: Partial<typeof BLANK_MANUAL_EXTRAS> = {};
                    for (const key of Object.keys(BLANK_MANUAL_EXTRAS) as (keyof typeof BLANK_MANUAL_EXTRAS)[]) {
                      const value = patch[key];
                      if (value !== undefined) extraPatch[key] = value;
                    }
                    if (Object.keys(extraPatch).length > 0) setExtras((current) => ({ ...current, ...extraPatch }));
                  }}
                  firstRef={firstRef}
                  addressCheck={addressCheck}
                  addressChecked={addressChecked}
                  onAddressChecked={setAddressChecked}
                />
                {error && <p className="new-client-error" role="alert">{error}</p>}
                <PreviewBox preview={shownPreview} />
                <p className="new-client-note">
                  This makes the client&apos;s folder and record now, from what you type. Nothing is emailed and no forms are sent.
                  Anything left blank stays blank. Preview shows what would be made, and makes nothing.
                </p>
                <PreviewCreateActions
                  ready={Boolean(ready)}
                  busy={busy}
                  blocked={addressCheck && !addressChecked}
                  hasPreview={Boolean(shownPreview)}
                  onCancel={close}
                  onPreview={() => void send(true)}
                  onCreate={() => void send(false)}
                />
              </form>
            ) : (
              <form onSubmit={submit}>
                <label>
                  First name
                  <input ref={firstRef} value={first} onChange={(e) => setFirst(e.target.value)} autoComplete="off" required />
                </label>
                <label>
                  Last name
                  <input value={last} onChange={(e) => setLast(e.target.value)} autoComplete="off" required />
                </label>
                <label>
                  Email
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" required />
                </label>
                <PhoneField value={phone} onChange={setPhone} />
                <label>
                  Matter
                  <select value={category} onChange={(e) => setCategory(e.target.value)} required>
                    <option value="">Choose a matter</option>
                    {categories.map((c) => (
                      <option key={c.key} value={c.key}>{c.label}</option>
                    ))}
                  </select>
                </label>
                <div className="new-client-extras" role="group" aria-labelledby="new-client-extras-head">
                  <p id="new-client-extras-head" className="new-client-extras-head">
                    Also include, each with its own link in the same email:
                  </p>
                  <label className="new-client-check">
                    <input type="checkbox" checked={sendRif} onChange={(e) => setSendRif(e.target.checked)} />
                    Opponent Info Form
                  </label>
                  <label className="new-client-check">
                    <input type="checkbox" checked={sendLaif} onChange={(e) => setSendLaif(e.target.checked)} />
                    Legal Aid Info Form
                  </label>
                </div>
                {addressCheck && (
                  <label className="new-client-check">
                    <input type="checkbox" checked={addressChecked} onChange={(e) => setAddressChecked(e.target.checked)} />
                    I have checked this email address is the client&apos;s
                  </label>
                )}
                {error && <p className="new-client-error" role="alert">{error}</p>}
                <PreviewBox preview={shownPreview} />
                <p className="new-client-note">
                  This makes the folder and leaves one unsent draft in Outlook with the New Client Form and Letter of Authority, and
                  any form ticked above. The client&apos;s record is made when the signed New Client Form comes back.
                  Preview shows what would be made, and makes nothing; Create appears once you have previewed the form.
                </p>
                <PreviewCreateActions
                  ready={Boolean(ready)}
                  busy={busy}
                  blocked={addressCheck && !addressChecked}
                  hasPreview={Boolean(shownPreview)}
                  onCancel={close}
                  onPreview={() => void send(true)}
                  onCreate={() => void send(false)}
                />
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
