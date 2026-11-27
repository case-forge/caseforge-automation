"use client";

import { describeFetchError } from "@/lib/networkError";
import { useC8Guard } from "@/lib/c8Guard";
import { IconPlaceholder, IconShield } from "./icons";
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { StatusFlagPill } from "./StatusFlagPill";
import { PortalAlert } from "./PortalAlert";
import { portalAlertShows } from "@/lib/portalAlert";
import type { BillOfCostsResponse, ClientEdit, ClientMatch, SosStatusResponse } from "@/lib/types";
import {
  ORDER_TYPE_LABELS,
  pillFlagsToShow,
  addressBlocks,
  applyFieldUpdate,
  clientAddressLinesOf,
  concludedStatus,
  isDeleteLaterFolder,
  dateJoinedOf,
  formatDateForDisplay,
  fullNameOf,
  hasC8,
  c8Of,
  type C8Field,
  ninoOf,
  notesOf,
  orderTypeTagsOf,
  propertyOf,
  courtDetailsOf,
  referenceGroupsOf,
} from "@/lib/types";
import { SectionEditButton } from "./SectionEditButton";
import {
  ClientEditBar,
  ClientEditHistory,
  ClientEditProvider,
  FlagTicks,
  InlineStatus,
  InlineCourtReferences,
  InlineIdentityBoxes,
  InlineNameStack,
  InlineMatterSelect,
  InlineOrderTypes,
  InlineText,
  useClientEdit,
} from "./ClientEdits";
import { NotesHistory } from "./NotesHistory";
import { MatterCourt } from "./MatterCourt";
import { isNewClient } from "@/lib/newClient";
import { MATTER_FLAGS_CHANGED_EVENT } from "@/lib/draftFlag";
import { CopyButton } from "./CopyButton";
import { CallerIcons } from "./CallerTagBadge";
import { useMatterTasks } from "./MatterTasks";
import { LegalAidSection } from "./LegalAidSection";
import { INTRO_FOUND_EVENT, MatterMarkers } from "./MatterMarkers";
import { MatterMilestones } from "./MatterMilestones";
import { backgroundFetch } from "@/lib/loadingBar";
import { GRAPH_READ_CACHE_MS, useLazyFetch } from "@/lib/useLazyFetch";
import { summaryFetcher } from "@/lib/matterSummary";
import { openItemCount } from "@/lib/matterTasks";
import { carriedTab, drawerSwitchTab, landingTab, tabCount } from "@/lib/detailTabs";
import type { DetailTabId, LandingTabId } from "@/lib/detailTabs";
import { RowsSection } from "./ClientRows";
import { HearingsUpdatesTab } from "./MatterHearings";
import type { FocusHearing } from "./MatterHearings";
import { onlyCourtReference, londonTodayIso, splitMatterHearings } from "@/lib/hearings";
import { useMatterHearings } from "@/lib/useHearings";
import { notifyFlagsChanged } from "@/lib/useFlagCounts";
import { AttendanceNoteForm } from "./AttendanceNoteForm";
import { ActivityLogTab } from "./ActivityLogTab";
import { CaseFlowTab } from "./CaseFlowTab";
import { CaseReviewTab } from "./CaseReviewTab";
import { ScannerTab } from "./ScannerTab";
import { LexcelLetters } from "./LexcelLetters";
import { RemoveBillingButton } from "./RemoveBillingButton";
import { RemovedBillingItems } from "./RemovedBillingItems";
import { HeaderFlagToggles, type FlagKinds } from "./HeaderFlagToggles";
import { MatterNumberArrows } from "./MatterNumberArrows";
import { IconDrawer } from "./icons";
import { CurrentClientContext, confirmLeaveUnsaved } from "@/lib/unsavedEdits";
import { MergeClientButton } from "./MergeClientButton";
import { NearestHelp } from "./NearestHelp";
import { RemoveClientButton } from "./RemoveClientButton";
import dynamic from "next/dynamic";

const VergilTab = dynamic(() => import("./VergilTab").then((m) => m.VergilTab), { ssr: false });
import { ClientTodos } from "./ClientTodos";
import { SortHeader } from "./SortHeader";
import { SameNameHint, SameNameSuffix } from "./SameNameLabel";
import { companyReferenceOf } from "@/lib/sameName";
import { billDateValue, moneyValue, sortRows, useSort } from "@/lib/sortRows";
import type { VergilConversation } from "@/lib/vergilHistory";
import { normaliseOrderText } from "@/lib/orderText";

interface DetailPanelProps {
  match: ClientMatch | null;
  onFieldUpdated?: (fieldName: string, newValue: string) => void;

  openTab?: OpenTab | null;

  onOpenMatter?: (match: ClientMatch) => void;

  onShown?: (matterId: string, tab: string) => void;
}

export interface OpenTab {
  matterId: string;
  tab: FixedTab;

  hearingId?: number;
  nonce: number;
}

function useMatterFlags(
  matterId: string,
): [
  Record<string, boolean>,
  (flags: Record<string, boolean>) => void,
  Record<string, string>,
  (reasons: Record<string, string>) => void,
  FlagKinds,
  (kinds: FlagKinds) => void,
] {

  const { data, setData } = useLazyFetch<MatterFlagsBody>(
    matterId ? `/api/clients/matter-flags?matter_id=${encodeURIComponent(matterId)}` : null,
    {
      refreshEvent: MATTER_FLAGS_CHANGED_EVENT,
      refreshWhen: (event) => (event as CustomEvent<{ matterId?: string }>).detail?.matterId === matterId,
      fetcher: summaryFetcher(matterId, "flags"),
    },
  );
  const setFlags = (flags: Record<string, boolean>) => setData((current) => ({ ...current, flags }));
  const setReasons = (reasons: Record<string, string>) => setData((current) => ({ ...current, reasons }));
  const setKinds = (kinds: FlagKinds) =>
    setData((current) => ({ ...current, shared: kinds.shared, personal: kinds.personal, personal_reasons: kinds.personalReasons }));
  const kinds: FlagKinds = {
    shared: data?.shared ?? NO_FLAGS,
    personal: data?.personal ?? NO_FLAGS,
    personalReasons: data?.personal_reasons ?? NO_REASONS,
  };
  return [data?.flags ?? NO_FLAGS, setFlags, data?.reasons ?? NO_REASONS, setReasons, kinds, setKinds];
}

interface MatterFlagsBody {
  flags?: Record<string, boolean>;
  reasons?: Record<string, string>;
  shared?: Record<string, boolean>;
  personal?: Record<string, boolean>;
  personal_reasons?: Record<string, string>;
}
const NO_FLAGS: Record<string, boolean> = {};
const NO_REASONS: Record<string, string> = {};

function useSosStatus(matterId: string): { status: SosStatusResponse | null; failed: boolean } {
  const { data, failed } = useLazyFetch<SosStatusResponse>(
    matterId ? `/api/clients/sos-status?matter_id=${encodeURIComponent(matterId)}` : null,
    { cacheMs: GRAPH_READ_CACHE_MS },
  );
  return { status: data, failed };
}

function SosStatusField({ matterId }: { matterId: string }) {
  const { status, failed } = useSosStatus(matterId);
  if (failed || !status || !status.folder_found) {
    return (
      <div className="detail-field">
        <p className="detail-field-label">Statement of Service</p>
        <p className="detail-field-value detail-field-value--empty">
          {failed ? "Couldn't load, try reopening this client" : status ? "No live matter folder on record" : "Loading…"}
        </p>
      </div>
    );
  }
  if (status.items.length === 0) {
    return (
      <div className="detail-field">
        <p className="detail-field-label">Statement of Service</p>
        <p className="detail-field-value detail-field-value--empty">None filed yet</p>
      </div>
    );
  }
  return (
    <div className="detail-field">
      <p className="detail-field-label">Statement of Service</p>
      <p className="detail-field-value">
        {status.count} filed{status.draft_count > 0 ? ` · ${status.draft_count} draft` : ""}
      </p>
      {status.items.map((item, i) => (
        <p className="detail-field-value" key={i}>
          {item.web_url ? (
            <a href={item.web_url} target="_blank" rel="noreferrer">
              {formatDateForDisplay(item.modified_utc) || item.name}
            </a>
          ) : (
            formatDateForDisplay(item.modified_utc) || item.name
          )}
          {item.is_draft ? " (draft)" : ""}
        </p>
      ))}
    </div>
  );
}

function useBillOfCosts(matterId: string, refreshKey = 0): { bill: BillOfCostsResponse | null; failed: boolean } {
  const { data, failed } = useLazyFetch<BillOfCostsResponse>(
    matterId ? `/api/clients/bill-of-costs?matter_id=${encodeURIComponent(matterId)}` : null,
    { refreshKey, fetcher: summaryFetcher(matterId, "bill_of_costs") },
  );
  return { bill: data, failed };
}

function BillOfCostsSection({
  matterId,
  clientName,
  caseReference,
}: {
  matterId: string;
  clientName: string;
  caseReference: string;
}) {
  const [refresh, setRefresh] = useState(0);
  const { bill, failed } = useBillOfCosts(matterId, refresh);

  const partySort = useSort<"label" | "count" | "net" | "vat">(null);
  const itemSort = useSort<"date" | "description" | "net" | "vat">(null);

  const [showRates, setShowRates] = useState(false);
  if (!bill) {
    return (
      <p className="detail-field-value detail-field-value--empty">
        {failed ? "Couldn't load, try reopening this client" : "Loading…"}
      </p>
    );
  }

  const ratesTable = (
    <div className="billing-rates">
      <button
        type="button"
        className="cf-btn cf-btn--flush cf-btn--small no-print"
        aria-expanded={showRates}
        onClick={() => setShowRates((v) => !v)}
      >
        {showRates ? "Hide charging rates" : "Show charging rates"}
      </button>
      <table className={`billing-rates-table${showRates ? "" : " billing-rates-table--closed"}`}>
        <caption>{bill.billing_basis === "private" ? "Charging rates (private)" : "Charging rates"}</caption>
        <tbody>
          {bill.rates.map((rate) => (
            <tr key={rate.category}>
              <td>{rate.label}</td>
              <td className="billing-table-amount">{rate.rate === "TBC" ? "TBC" : `£${rate.rate}`} {rate.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <>
      <div className="billing-actions no-print">
        <a
          className="cf-btn cf-btn--neutral"
          href={`/api/clients/bill-of-costs/export?matter_id=${encodeURIComponent(matterId)}`}
          download
          title="Download the itemised bill as a CSV file"
        >
          Export CSV
        </a>
        <button type="button" className="cf-btn cf-btn--neutral" onClick={() => window.print()}>
          Print
        </button>
      </div>
      <div className="billing-print-area">
        <div className="billing-print-header">
          <h2>{clientName || bill.client_name}</h2>
          {caseReference && <p>Case No. {caseReference}</p>}
        </div>
        {bill.billing_basis === "private" && (
          <p className="billing-basis">Privately billed: new lines are charged at the private rates.</p>
        )}
        {ratesTable}
        {(bill.rate_tbc?.length ?? 0) > 0 && (
          <div className="billing-rate-tbc">
            <p>Waiting for a private rate (in no total):</p>
            <ul>
              {bill.rate_tbc?.map((line) => (
                <li key={line.item_id}>{line.item_date} {line.description}</li>
              ))}
            </ul>
          </div>
        )}
        {bill.parties.length > 0 && (
          <div className="billing-table-wrap">
            <table className="billing-table">
              <caption className="billing-table-caption">Correspondence, by who it was with</caption>
              <thead>
                <tr>
                  <th><SortHeader label="Routine" sortKey="label" sort={partySort.sort} onSort={partySort.toggle} /></th>
                  <th className="billing-table-amount"><SortHeader label="No." sortKey="count" sort={partySort.sort} onSort={partySort.toggle} /></th>
                  <th className="billing-table-amount"><SortHeader label="Net (£)" sortKey="net" sort={partySort.sort} onSort={partySort.toggle} /></th>
                  <th className="billing-table-amount"><SortHeader label="VAT (£)" sortKey="vat" sort={partySort.sort} onSort={partySort.toggle} /></th>
                </tr>
              </thead>
              <tbody>
                {bill.parties.map((party) => (
                  <Fragment key={party.party}>
                    <tr className="billing-table-category-row">
                      <td colSpan={4}>{party.label}</td>
                    </tr>
                    {sortRows(party.lines, partySort.sort, (l, k) => (k === "label" ? l.label : k === "count" ? l.count : moneyValue(k === "net" ? l.net : l.vat))).map((line) => (
                      <tr key={line.label}>
                        <td>{line.label}</td>
                        <td className="billing-table-amount">{line.count}</td>
                        <td className="billing-table-amount">{line.net}</td>
                        <td className="billing-table-amount">{line.vat}</td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {bill.item_count === 0 ? (
          <p className="detail-field-value detail-field-value--empty">Nothing billed on record for this matter yet</p>
        ) : (
          <div className="billing-table-wrap">
            <table className="billing-table">
              <thead>
                <tr>
                  <th><SortHeader label="Date" sortKey="date" sort={itemSort.sort} onSort={itemSort.toggle} /></th>
                  <th><SortHeader label="Description" sortKey="description" sort={itemSort.sort} onSort={itemSort.toggle} /></th>
                  <th className="billing-table-amount"><SortHeader label="Net (£)" sortKey="net" sort={itemSort.sort} onSort={itemSort.toggle} /></th>
                  <th className="billing-table-amount"><SortHeader label="VAT (£)" sortKey="vat" sort={itemSort.sort} onSort={itemSort.toggle} /></th>
                </tr>
              </thead>
              <tbody>
                {bill.categories.map((cat) => (
                  <Fragment key={cat.category}>
                    <tr className="billing-table-category-row">
                      <td colSpan={4}>{cat.label}</td>
                    </tr>
                    {sortRows(cat.items, itemSort.sort, (it, k) =>
                      k === "date" ? billDateValue(it.item_date) : k === "description" ? it.description : moneyValue(k === "net" ? it.net_amount : it.vat_amount),
                    ).map((item, i) => (
                      <tr key={i}>
                        <td>{item.item_date}</td>
                        <td>
                          {item.document_url ? (
                            <a href={item.document_url} target="_blank" rel="noreferrer" title="Open the email or note this line bills, in SharePoint">
                              {item.description}
                            </a>
                          ) : (
                            item.description
                          )}
                          {item.schedule ? <span className="billing-table-schedule"> (Schedule {item.schedule})</span> : null}
                          {item.possible_double_bill ? (
                            <span className="billing-table-double" title="Another line in this group points at the same email or document"> Possible double bill</span>
                          ) : null}
                          {item.attendance_draft_id && (
                            <>
                              {" "}
                              <RemoveBillingButton draftId={item.attendance_draft_id} onRemoved={() => setRefresh((n) => n + 1)} />
                            </>
                          )}
                        </td>
                        <td className="billing-table-amount">{item.net_amount}</td>
                        <td className="billing-table-amount">{item.vat_amount}</td>
                      </tr>
                    ))}
                    <tr className="billing-table-subtotal-row">
                      <td colSpan={2}>Subtotal</td>
                      <td className="billing-table-amount">{cat.subtotal_net}</td>
                      <td className="billing-table-amount">{cat.subtotal_vat}</td>
                    </tr>
                  </Fragment>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={2}>Total</td>
                  <td className="billing-table-amount">{bill.total_net}</td>
                  <td className="billing-table-amount">{bill.total_vat}</td>
                </tr>
                <tr>
                  <td colSpan={2}>Total including VAT</td>
                  <td className="billing-table-amount" colSpan={2}>{bill.total_gross}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>
      <RemovedBillingItems items={bill.removed ?? []} onRestored={() => setRefresh((n) => n + 1)} />
    </>
  );
}

function C8Checkbox({ label, on, guarded, onToggle }: { label: string; on: boolean; guarded?: boolean; onToggle: (next: boolean) => void }) {
  return (
    <span className="detail-field-c8-wrap">
      {guarded && (
        <span
          className="detail-field-c8-shield"
          role="img"
          aria-label="C8 shield"
          title="C8 shield: this client has C8 protection on at least one detail, so every detail is treated as C8 while the guard is on, whatever is ticked here. Turn the guard off in Settings, under the apps menu. The tick itself is unchanged."
        >
          <IconShield aria-hidden="true" width={15} height={15} />
        </span>
      )}
      <label className="detail-field-c8" title={`C8: ${label} is withheld from the other party`}>
        <input type="checkbox" checked={on} onChange={(e) => onToggle(e.target.checked)} />
        C8
      </label>
    </span>
  );
}

interface C8Control {

  on: boolean;

  ticked: boolean;

  guarded: boolean;
  onToggle: (next: boolean) => void;
}

export function isPlaceholderReference(value: string | null | undefined): boolean {
  return /(^|[\s,])PLACEHOLDER-/i.test(value ?? "");
}

function Field({
  label,
  value,
  c8,
  editName,
  editMultiline,
  editControl,
  editInHead,
}: {
  label: string;
  value: string | null | undefined;

  editName?: string;
  editMultiline?: boolean;

  editControl?: ReactNode;

  editInHead?: boolean;

  c8?: C8Control;
}) {
  const has = value != null && value !== "";
  const placeholder = isPlaceholderReference(value);
  const inline = useClientEdit()?.editing && (editName || editControl);
  return (
    <div className={`detail-field${inline ? " detail-field--editing" : ""}${c8?.on ? " detail-field--c8-sensitive" : ""}${placeholder ? " detail-field--placeholder" : ""}`}>
      <div className="detail-field-head">
        <p className="detail-field-label">
          {placeholder && (
            <span
              className="detail-field-placeholder-icon"
              role="img"
              aria-label="Placeholder"
              title="Placeholder: this reference was made up so a letter could be made without one. Replace it with the real reference when it is known."
            >
              <IconPlaceholder aria-hidden="true" width={15} height={15} />
            </span>
          )}
          {label}
        </p>
        <span className="detail-field-head-tools">
          {c8 && <C8Checkbox label={label.toLowerCase()} on={c8.ticked} guarded={c8.guarded} onToggle={c8.onToggle} />}
          {inline && editInHead && editControl}
        </span>
      </div>
      {inline ? (
        editInHead ? null : editControl ?? <InlineText name={editName ?? ""} label={label} multiline={editMultiline} />
      ) : (
        <div className="detail-field-value-row">
          <p className={`detail-field-value${has ? "" : " detail-field-value--empty"}`}>
            {has ? value : "Not on record"}
          </p>
          {has && <CopyButton text={value} label={label} />}
        </div>
      )}
    </div>
  );
}

function ClientAddressField({ match, c8 }: { match: ClientMatch; c8: C8Control }) {
  const structured = clientAddressLinesOf(match);
  const matterId = match.matter_id != null ? String(match.matter_id) : "";
  const editing = useClientEdit()?.editing ?? false;
  const className = `detail-field${c8.on ? " detail-field--c8-sensitive" : ""}${editing ? " detail-field--editing" : ""}`;
  const c8Tool = <C8Checkbox label="address" on={c8.ticked} guarded={c8.guarded} onToggle={c8.onToggle} />;
  if (editing) {
    return (
      <div className={className}>
        <div className="detail-field-head">
          <p className="detail-field-label">Address</p>
          <span className="detail-field-head-tools">{c8Tool}</span>
        </div>
        <div className="edit-inline-stack">
          <InlineText name="address_line1" label="Address line 1" />
          <InlineText name="address_line2" label="Address line 2" />
          <InlineText name="address_line3" label="Address line 3" />
          <InlineText name="address_line4" label="Address line 4" />
          <InlineText name="address_postcode" label="Postcode" />
        </div>
      </div>
    );
  }
  if (structured.length > 0) {
    return (
      <div className={className}>
        <div className="detail-field-head">
          <p className="detail-field-label">Address</p>
          <span className="detail-field-head-tools">
            {c8Tool}
          </span>
        </div>
        <div className="detail-field-value-row">
          <div>
            {structured.map((line, i) => (
              <p key={i} className="detail-field-value">{line}</p>
            ))}
          </div>
          <span className="address-tools">
            <CopyButton text={structured.join(", ")} label="address" />
          </span>
        </div>
      </div>
    );
  }
  const fallback = addressBlocks(match).find((block) => /applicant/i.test(block.heading));
  return (
    <div className={className}>
      <div className="detail-field-head">
        <p className="detail-field-label">Address</p>
        <span className="detail-field-head-tools">
          {c8Tool}
        </span>
      </div>
      {fallback ? (
        <div className="detail-field-value-row">
          <div>
            {fallback.lines.map((line, i) => <p key={i} className="detail-field-value">{line}</p>)}
          </div>
          <span className="address-tools">
            <CopyButton text={fallback.lines.join(", ")} label="address" />
          </span>
        </div>
      ) : (
        <div className="detail-field-value-row">
          <p className="detail-field-value detail-field-value--empty">Not on record</p>
        </div>
      )}
    </div>
  );
}

function useIntroLink(matterId: string): string {
  const [url, setUrl] = useState("");

  useEffect(() => {
    setUrl("");
    if (!matterId) return;
    let cancelled = false;
    const accept = (value: unknown) => {
      if (!cancelled && typeof value === "string" && value.startsWith("https://")) setUrl(value);
    };
    backgroundFetch(`/api/clients/intro-link?matter_id=${encodeURIComponent(matterId)}`)
      .then((res) => (res.ok ? res.json() : { url: "" }))
      .then((body: { url?: string }) => accept(body.url))
      .catch(() => undefined);
    function onFound(event: Event) {
      const detail = (event as CustomEvent<{ matterId?: string; url?: string }>).detail;
      if (detail?.matterId === matterId) accept(detail.url);
    }
    window.addEventListener(INTRO_FOUND_EVENT, onFound);
    return () => {
      cancelled = true;
      window.removeEventListener(INTRO_FOUND_EVENT, onFound);
    };
  }, [matterId]);

  return url;
}

function ClientRoleLine({ matterId, role }: { matterId: string; role: string }) {
  const introUrl = useIntroLink(matterId);
  const other = role && role.trim().toLowerCase() !== "applicant" ? role : "";
  if (!introUrl && !other) return null;
  return (
    <>
      {introUrl && (
        <a className="detail-subtitle-link" href={introUrl} target="_blank" rel="noopener noreferrer" title="Open the referral info">
          Referral Info
        </a>
      )}
      {introUrl && other && " · "}
      {other && <strong>{other}</strong>}
    </>
  );
}

export type FixedTab = DetailTabId;

const MAIN_TABS: [FixedTab, string][] = [
  ["client", "Client"],
  ["details", "Details"],
  ["caseflow", "Case Flow"],
  ["attendance", "Attendance Notes"],
  ["todo", "To Do"],
];

const EXTRA_TABS: [FixedTab, string][] = [
  ["vergil", "Vergil"],
  ["scanner", "Scanner"],
  ["billing", "Billing"],
  ["hearings", "Hearings"],
  ["updates", "Updates"],
  ["case-review", "Case review"],
  ["activity", "Activity log"],
];
const MAIN_IDS = MAIN_TABS.map(([id]) => id);
const EXTRA_IDS = EXTRA_TABS.map(([id]) => id);
const ALL_IDS = [...MAIN_IDS, ...EXTRA_IDS];

const tabMemory: { tab: FixedTab | null; lastMain: FixedTab | null; lastExtra: FixedTab | null } = {
  tab: null,
  lastMain: null,
  lastExtra: null,
};

export function resetTabMemory(): void {
  tabMemory.tab = null;
  tabMemory.lastMain = null;
  tabMemory.lastExtra = null;
}

interface CaseTab {
  matterId: string;
  label: string;
}

function caseLabelOf(row: ClientMatch, index: number, total: number): string {
  const court = referenceGroupsOf(row).court[0];
  if (court) return court;
  return total > 1 ? `Case ${index + 1}` : "Case";
}

export function DetailPanel({ match, onFieldUpdated, openTab, onOpenMatter, onShown }: DetailPanelProps) {
  if (!match) {
    return (
      <div className="detail-pane">
        <div className="detail-card detail-empty">
          Select a result to see the client record.
        </div>
      </div>
    );
  }
  return (
    <CaseSwitcher
      match={match}
      onFieldUpdated={onFieldUpdated}
      openTab={openTab}
      onOpenMatter={onOpenMatter}
      onShown={onShown}
    />
  );
}

const NO_MATTERS: ClientMatch[] = [];

function CaseSwitcher({ match, onFieldUpdated, openTab, onOpenMatter, onShown }: { match: ClientMatch } & Omit<DetailPanelProps, "match">) {
  const parentId = match.matter_id != null ? String(match.matter_id) : "";

  const personMatters = useLazyFetch<{ matters?: ClientMatch[] }>(
    parentId ? `/api/clients/person-matters?matter_id=${encodeURIComponent(parentId)}` : null,
    { fetcher: summaryFetcher(parentId, "person_matters") },
  );
  const rows = personMatters.data?.matters ?? NO_MATTERS;
  const setRows = (update: (current: ClientMatch[]) => ClientMatch[]) =>
    personMatters.setData((current) => ({ ...current, matters: update(current?.matters ?? []) }));

  const [selected, setSelected] = useState({ parentId, caseId: "" });
  const selectedCaseId = selected.parentId === parentId ? selected.caseId : "";
  const setSelectedCaseId = (caseId: string) => setSelected({ parentId, caseId });

  const openedNonce = useRef(0);
  useEffect(() => {
    if (!openTab || openTab.nonce === openedNonce.current) return;
    if (openTab.matterId === parentId) {
      openedNonce.current = openTab.nonce;
      if (confirmLeaveUnsaved()) setSelected({ parentId, caseId: "" });
    } else if (rows.some((row) => String(row.matter_id) === openTab.matterId)) {
      openedNonce.current = openTab.nonce;
      if (confirmLeaveUnsaved()) setSelected({ parentId, caseId: openTab.matterId });
    }
  }, [openTab, rows, parentId]);

  const caseRows: ClientMatch[] = rows.length
    ? rows.map((row) => (String(row.matter_id) === parentId ? match : row))
    : [match];
  if (rows.length && !rows.some((row) => String(row.matter_id) === parentId)) caseRows.unshift(match);

  const shown = caseRows.find((row) => String(row.matter_id) === selectedCaseId) ?? match;
  const shownId = shown.matter_id != null ? String(shown.matter_id) : "";
  const cases: CaseTab[] = caseRows.map((row, i) => ({
    matterId: row.matter_id != null ? String(row.matter_id) : "",
    label: caseLabelOf(row, i, caseRows.length),
  }));

  function handleFieldUpdated(fieldName: string, newValue: string) {
    if (shownId === parentId) {
      onFieldUpdated?.(fieldName, newValue);
      return;
    }
    setRows((current) => current.map((row) => (String(row.matter_id) === shownId ? applyFieldUpdate(row, fieldName, newValue) : row)));
  }

  return (
    <DetailPanelBody
      match={shown}
      cases={cases}
      onSelectCase={setSelectedCaseId}
      onFieldUpdated={handleFieldUpdated}
      openTab={openTab}
      onOpenMatter={onOpenMatter}
      onShown={onShown}
    />
  );
}

function DetailPanelBody({
  match,
  cases,
  onSelectCase,
  onFieldUpdated,
  openTab,
  onOpenMatter,
  onShown,
}: {
  match: ClientMatch;
  cases: CaseTab[];
  onSelectCase: (matterId: string) => void;
} & Omit<DetailPanelProps, "match">) {
  const nino = ninoOf(match);
  const dateJoined = dateJoinedOf(match);
  const property = propertyOf(match);
  const c8 = hasC8(match);
  const concluded = concludedStatus(match);
  const references = referenceGroupsOf(match);
  const courtDetails = courtDetailsOf(match);
  const orderTags = orderTypeTagsOf(match);
  const notes = notesOf(match);
  const [editRows, setEditRows] = useState<ClientEdit[]>([]);
  const matterId = match.matter_id != null ? String(match.matter_id) : "";
  const [flags, setFlags, flagReasons, setFlagReasons, flagKinds, setFlagKinds] = useMatterFlags(matterId);

  const [detailTab, setDetailTab] = useState<FixedTab>(() => carriedTab(tabMemory.tab, ALL_IDS));
  const [vergilOpenedFor, setVergilOpenedFor] = useState("");

  const onExtraPage = EXTRA_IDS.includes(detailTab);
  useEffect(() => {
    tabMemory.tab = detailTab;
    if (EXTRA_IDS.includes(detailTab)) tabMemory.lastExtra = detailTab;
    else tabMemory.lastMain = detailTab;
  }, [detailTab]);
  useEffect(() => {
    if (matterId) onShown?.(matterId, detailTab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matterId, detailTab]);

  useEffect(() => {
    if (detailTab === "vergil") setVergilOpenedFor(matterId);
  }, [detailTab, matterId]);

  const landedNonce = useRef(0);
  const landMatterId = match.matter_id != null ? String(match.matter_id) : "";

  const [focusHearing, setFocusHearing] = useState<FocusHearing | null>(null);
  useEffect(() => {
    if (!openTab || openTab.nonce === landedNonce.current || openTab.matterId !== landMatterId) return;
    landedNonce.current = openTab.nonce;

    if (!confirmLeaveUnsaved()) return;
    setDetailTab(landingTab(openTab.tab));
    setFocusHearing(openTab.hearingId != null ? { hearingId: openTab.hearingId, nonce: openTab.nonce } : null);
  }, [openTab, landMatterId]);
  const [c8Error, setC8Error] = useState<string | null>(null);

  async function toggleC8(field: C8Field, next: boolean) {
    setC8Error(null);
    try {
      const res = await fetch("/api/clients/edits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter_id: matterId, field_name: field, new_value: next ? "1" : "0", note: "" }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}) as { error?: string });
        throw new Error(body.error || "Could not change C8");
      }
      onFieldUpdated?.(field, next ? "1" : "0");
    } catch (err) {
      setC8Error(describeFetchError(err, "Could not change C8"));
    }
  }
  const [c8Guard] = useC8Guard();
  const c8Control = (field: C8Field): C8Control => {
    const ticked = c8Of(match, field);
    const guarded = c8Guard && c8 && !ticked;
    return { on: ticked || guarded, ticked, guarded, onToggle: (next) => void toggleC8(field, next) };
  };

  const matterHearings = useMatterHearings(match.matter_id);
  const upcomingHearings = splitMatterHearings(matterHearings.hearings, londonTodayIso()).upcomingScheduled;
  const matterTasks = useMatterTasks(matterId);
  const openUpdates = openItemCount(matterTasks);
  const tabsRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const strip = tabsRef.current;
    if (!strip) return;
    function onWheel(event: WheelEvent) {
      if (!strip || strip.scrollWidth <= strip.clientWidth) return;
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      event.preventDefault();
      strip.scrollLeft += event.deltaY;
    }
    strip.addEventListener("wheel", onWheel, { passive: false });
    return () => strip.removeEventListener("wheel", onWheel);
  }, []);

  const [resumeConversation, setResumeConversation] = useState<VergilConversation | undefined>(undefined);

  const [freshChatFor, setFreshChatFor] = useState("");
  const [chatNonce, setChatNonce] = useState(0);

  useEffect(() => {
    setResumeConversation(undefined);
    setFreshChatFor("");
  }, [matterId]);

  const clientName = fullNameOf(match);
  const tabLabel = [...MAIN_TABS, ...EXTRA_TABS].find(([id]) => id === detailTab)?.[1] ?? "";
  const currentClient = useMemo(
    () => ({ matterId, clientName, tab: tabLabel ? `${tabLabel} tab` : "" }),
    [matterId, clientName, tabLabel],
  );

  function tabButton(id: FixedTab, label: string) {

    const { count, ariaLabel } =
      id === "hearings" ? tabCount(label, upcomingHearings, "upcoming hearing", "upcoming hearings")
      : id === "updates" ? tabCount(label, openUpdates, "open update", "open updates")
      : { count: 0, ariaLabel: undefined };
    return (
      <button
        key={id}
        type="button"
        role="tab"
        className="cf-btn cf-btn--flush detail-tab-button"
        data-active={detailTab === id}
        aria-label={ariaLabel}
        onClick={() => {
          if (id !== detailTab && !confirmLeaveUnsaved()) return;
          setDetailTab(id);
        }}
      >
        {label}
        {count > 0 && (
          <>
            {" "}
            <span className="detail-tab-count">{count}</span>
          </>
        )}
      </button>
    );
  }

  return (
    <CurrentClientContext.Provider value={currentClient}>
    <div className="detail-pane">
      <div className="detail-card">
        <div className="detail-card-scroll" data-tab={detailTab}>
          <div className="detail-title-row">
            <h2 className="detail-title">
              {fullNameOf(match)}
              <SameNameSuffix row={match} />
              <CopyButton text={fullNameOf(match)} label="name" />
              <CallerIcons flags={flags} />
              {isNewClient(match) && <span className="detail-title-new">New</span>}
              {c8 && <span className="detail-title-c8" title="C8 confidentiality flag - do not disclose contact details to the respondent">C8</span>}
              {concluded && (
                <span
                  className="detail-title-concluded"
                  title={
                    concluded.source === "closed_at"
                      ? "Recorded closed in the database"
                      : "Filed under a Concluded folder - no closure date recorded in the database yet"
                  }
                >
                  Concluded
                </span>
              )}
              {isDeleteLaterFolder(match) && (
                <span className="detail-title-to-delete" title="Filed in a Delete Later folder">TO DELETE</span>
              )}
              {orderTags.map((code) => (
                <span key={code} className="detail-title-order" title={ORDER_TYPE_LABELS[code]}>{code}</span>
              ))}
              {pillFlagsToShow(flags, orderTags.length > 0).map((flag) => (
                <StatusFlagPill key={flag.name} flag={flag} className="detail-title-status-flag" plainTitle={flag.label} />
              ))}
            </h2>
            <div className="detail-title-actions no-print">
              { }
              <span className="detail-title-referral"><ClientRoleLine matterId={matterId} role={match.client_role ?? ""} /></span>
              {onOpenMatter && <MatterNumberArrows matterId={matterId} onOpenMatter={onOpenMatter} />}
              {cases.length > 1 && (
                <select
                  className="case-select"
                  aria-label="Case"
                  title="Switch to another of this client's cases"
                  value={matterId}
                  onChange={(event) => {
                    if (confirmLeaveUnsaved()) onSelectCase(event.target.value);
                  }}
                >
                  {cases.map((c) => (
                    <option key={c.matterId} value={c.matterId}>
                      {c.label}
                    </option>
                  ))}
                </select>
              )}
              <HeaderFlagToggles
                key={matterId}
                matterId={matterId}
                flags={flags}
                reasons={flagReasons}
                kinds={flagKinds}
                onKinds={setFlagKinds}
                onChanged={(next, reasons, settled) => {
                  setFlags(next);
                  setFlagReasons(reasons);
                  if (settled) notifyFlagsChanged();
                }}
              />
              <button
                type="button"
                className="cf-btn cf-btn--icon header-flag-toggle header-extra-toggle"
                title={onExtraPage ? "Back to the client's main details" : "Extra details: Vergil, scanner, billing, hearings, updates, case review, activity log"}
                aria-label={
                  onExtraPage
                    ? "Back to the main details"
                    : upcomingHearings + openUpdates > 0
                      ? `Extra details, ${upcomingHearings + openUpdates} to look at`
                      : "Extra details"
                }
                onClick={() => {
                  if (!confirmLeaveUnsaved()) return;
                  setDetailTab(drawerSwitchTab({
                    onExtraPage,
                    lastMain: tabMemory.lastMain,
                    lastExtra: tabMemory.lastExtra,
                    mainTabs: MAIN_IDS,
                    extraTabs: EXTRA_IDS,
                  }));
                }}
              >
                <IconDrawer open={onExtraPage} className="header-flag-toggle-icon" aria-hidden="true" />
                {!onExtraPage && upcomingHearings + openUpdates > 0 && (
                  <span className="detail-tab-count">{upcomingHearings + openUpdates}</span>
                )}
              </button>
            </div>
          </div>
          <SameNameHint row={{ ...match, company_reference: companyReferenceOf(match.extra) }} className="detail-same-name-hint" />
          {matterId && portalAlertShows(flags, !!concluded) && <PortalAlert key={`portal-alert-${matterId}`} matterId={matterId} />}

          <nav ref={tabsRef} className="detail-tabs no-print" role="tablist">
            {(onExtraPage ? EXTRA_TABS : MAIN_TABS).map(([id, label]) => tabButton(id, label))}
          </nav>

          {detailTab === "client" && (
            <ClientEditProvider
              key={matterId}
              match={match}
              onFieldUpdated={onFieldUpdated}
              onHistoryLoaded={setEditRows}
            >
              <ClientEditBar
                flagTicks={
                  <FlagTicks
                    flags={flags}
                    flagReasons={flagReasons}
                    onFlagsChanged={(next, reasons) => {
                      setFlags(next);
                      setFlagReasons(reasons ?? {});
                      notifyFlagsChanged();
                    }}
                  />
                }
                clientActions={
                  <>
                    <MergeClientButton key={`merge-${matterId}`} matterId={matterId} />
                    <RemoveClientButton key={`remove-${matterId}`} matterId={matterId} clientName={fullNameOf(match)} />
                  </>
                }
              />
              <h3 className="detail-section-title detail-section-title--with-edit" data-section="basics"><span>Basics</span><SectionEditButton section="Basics" sectionKey="basics" /></h3>
              <div className="detail-grid">
                <InlineNameStack />
                <Field
                  label="Matter"
                  value={orderTags.map((c) => ORDER_TYPE_LABELS[c]).join(", ") || normaliseOrderText(match.order_requested_text) || null}
                  editControl={
                    <>
                      <InlineOrderTypes />
                      <InlineMatterSelect
                        flags={flags}
                        onFlagsChanged={(next, reasons) => {
                          setFlags(next);
                          setFlagReasons(reasons ?? {});
                          notifyFlagsChanged();
                        }}
                      />
                    </>
                  }
                />
                <Field
                  label="Court reference(s)"
                  value={references.court.join(", ") || null}
                  editControl={<InlineCourtReferences />}
                />
                <Field label="Court" value={courtDetails.name} />
                <Field label="Court email" value={courtDetails.email} />
                <InlineIdentityBoxes />
                <Field label="Date joined" value={dateJoined} />
                <Field label="Date of birth" value={match.dob_iso} editName="dob_iso" />
                <Field label="Company reference" value={references.company[0] ?? null} editName="company_reference" />
                {references.other.length > 0 && (
                  <Field label="Other reference(s)" value={references.other.join(", ")} />
                )}
                <Field
                  label="Status"
                  editControl={
                    <InlineStatus
                      flags={flags}
                      flagReasons={flagReasons}
                      onFlagsChanged={(next, reasons) => {
                        setFlags(next);
                        setFlagReasons(reasons ?? {});
                        notifyFlagsChanged();
                      }}
                    />
                  }
                  value={
                    concluded
                      ? concluded.source === "closed_at"
                        ? concluded.label
                        : "Concluded (folder, no date on record)"
                      : null
                  }
                />
              </div>

              <h3 className="detail-section-title detail-section-title--with-edit" data-section="contact"><span>Contact</span><SectionEditButton section="Contact" sectionKey="contact" /></h3>
              <div className="detail-grid">
                <Field label="Telephone" value={match.phone_primary} c8={c8Control("c8_phone")} editName="phone_primary" />
                <Field label="Email" value={match.email_primary} c8={c8Control("c8_email")} editName="email_primary" />
                <ClientAddressField match={match} c8={c8Control("c8_address")} />
              </div>
              {c8Error && <p className="client-edits-error" role="alert">{c8Error}</p>}

              <h3 className="detail-section-title detail-section-title--with-edit" data-section="opponents"><span>Opponent / other parties</span><SectionEditButton section="Opponent / other parties" sectionKey="opponents" /></h3>
              <RowsSection key={`parties-${matterId}`} kind="parties" matterId={matterId} clientRole={match.client_role} />
              <h3 className="detail-section-title detail-section-title--with-edit" data-section="children"><span>Children</span><SectionEditButton section="Children" sectionKey="children" /></h3>
              <RowsSection key={`children-${matterId}`} kind="children" matterId={matterId} />

              <h3 className="detail-section-title detail-section-title--with-edit" data-section="notes"><span>Notes</span><SectionEditButton section="Notes" sectionKey="notes" /></h3>
              <div className="detail-grid">
                <Field label="Notes" value={notes} editName="tracker_notes" editMultiline />
              </div>
              <NotesHistory rows={editRows} matterId={matterId} />

              <ClientEditHistory />
            </ClientEditProvider>
          )}

          {detailTab === "details" && (
            <>
              <h3 className="detail-section-title">Case</h3>
              <div className="detail-grid">
                <SosStatusField matterId={matterId} />
                <MatterMarkers key={matterId} matterId={matterId} />
                {matterId && <MatterMilestones key={`milestones-${matterId}`} matterId={matterId} />}
                {matterId && <MatterCourt key={`court-${matterId}`} matterId={matterId} />}
              </div>
              {matterId && <NearestHelp key={`nearest-${matterId}`} matterId={matterId} />}
              <h3 className="detail-section-title">Property &amp; means</h3>
              <div className="detail-grid">
                <Field label="Housing" value={property} />
              </div>
              <LegalAidSection key={`legal-aid-${matterId}`} matterId={matterId} nino={nino} />
              {matterId && (
                <>
                  <h3 className="detail-section-title">Lexcel</h3>
                  <LexcelLetters key={`lexcel-${matterId}`} matterId={matterId} />
                </>
              )}
            </>
          )}

          {detailTab === "caseflow" && matterId && <CaseFlowTab key={matterId} matterId={matterId} closed={concluded !== null} />}

          {detailTab === "activity" && matterId && <ActivityLogTab key={matterId} matterId={matterId} />}

          {detailTab === "case-review" && matterId && <CaseReviewTab key={matterId} matterId={matterId} />}

          {(detailTab === "hearings" || detailTab === "updates") && (
            <HearingsUpdatesTab
              key={`${detailTab}-${matterId}`}
              view={detailTab}
              state={matterHearings}
              caseRef={onlyCourtReference(references.court)}
              tasks={matterTasks}
              focusHearing={focusHearing}
            />
          )}

          {detailTab === "scanner" && matterId && <ScannerTab key={matterId} matterId={matterId} />}

          {detailTab === "todo" && matterId && Number.isFinite(Number(matterId)) && <ClientTodos key={matterId} matterId={Number(matterId)} />}

          {detailTab === "attendance" && (
            <AttendanceNoteForm
              key={matterId}
              matterId={matterId}
              clientName={fullNameOf(match)}
              clientRole={match.client_role ?? ""}
              caseRef={onlyCourtReference(references.court)}

              onCreated={() => {}}
              onHearingAdded={matterHearings.refresh}
            />
          )}

          {detailTab === "billing" && (
            <BillOfCostsSection
              matterId={matterId}
              clientName={fullNameOf(match)}
              caseReference={references.court.join(", ")}
            />
          )}

          {matterId && vergilOpenedFor === matterId && (

            <div className="vergil-tab-host" hidden={detailTab !== "vergil"}>
              <VergilTab
                key={`${matterId}:${resumeConversation?.sessionId ?? "auto"}:${chatNonce}`}
                match={match}
                resume={resumeConversation}
                startFresh={freshChatFor === matterId && !resumeConversation}
                onNewChat={() => {
                  setResumeConversation(undefined);
                  setFreshChatFor(matterId);
                  setChatNonce((n) => n + 1);
                }}
                onResumeConversation={setResumeConversation}
              />
            </div>
          )}
        </div>
      </div>
    </div>
    </CurrentClientContext.Provider>
  );
}
