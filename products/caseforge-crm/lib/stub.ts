
import { applyStubFlagRule } from "./stubFlagReasons";
import { stubMadeClients } from "./stubClients";
import { DEMO_FIRM } from "./stubFirm";
import type {
  ConcludedMattersResponse,
  AttendanceNoteCreateResponse,
  AttendanceNoteKind,
  AttendanceNoteStatus,
  BillOfCostsResponse,
  RestoreBillingItemResponse,
  ClientEdit,
  ClientMatch,
  ClientSearchResponse,
  FieldReviewFlag,
  FieldReviewQueueResponse,
  FrequentCallersResponse,
  MatterMarkersResponse,
  MatterTasksResponse,
  PersonMattersResponse,
  SosStatusResponse,
} from "./types";
import { CATEGORY_PILL_FLAGS, FLAG_FIELDS } from "./types";

export * from "./stubHearings";

const STUB_FIELD_LABELS: Record<string, string> = {
  name_first: "First name",
  name_middle: "Middle name",
  name_last: "Last name",
  client_canonical_name: "Full name (as used on documents)",
  dob_iso: "Date of birth",
  nino_canonical: "NI number",
  phone_primary: "Telephone",
  email_primary: "Email",
  address_line1: "Address line 1",
  address_line2: "Address line 2",
  address_line3: "Address line 3",
  address_line4: "Address line 4",
  address_postcode: "Postcode",
  client_role: "Client role",
  company_reference: "Company reference",
  court_references: "Court reference(s)",
  order_requested_text: "Application / order type",
  order_type_tags: "Order type tags",
  has_c8: "C8 confidentiality order",
  concluded: "Concluded",
  tracker_notes: "Notes",
  c8_phone: "C8 - telephone",
  c8_email: "C8 - email",
  c8_address: "C8 - address",
  children_summary: "Children",
  legal_aid_tracker_status: "Legal aid certificate status",
  live_matter_folder: "Matter folder location",
  order_types: "Order types",
  ...Object.fromEntries([...FLAG_FIELDS, ...CATEGORY_PILL_FLAGS].map((f) => [`flag:${f.name}`, f.label])),
};

export const STUB_EDITABLE_FIELDS = Object.keys(STUB_FIELD_LABELS);

const STUB_NOTE_MAX_LENGTH = 100;

const stubFlags = new Map<string, Record<string, boolean>>();

const stubPersonalFlags = new Map<string, Map<string, Record<string, boolean>>>();
const PERSONAL_FLAG_NAMES = ["flagged", "starred"];

const stubPersonalReasons = new Map<string, Map<string, Record<string, string>>>();

export const STUB_DRAFT_REASON = "Unfinished draft";

function personalFor(user: string, matterId: string): Record<string, boolean> {
  return stubPersonalFlags.get(user)?.get(matterId) ?? {};
}

export function stubFlagKinds(matterId: string, user = ""): {
  shared: Record<string, boolean>;
  personal: Record<string, boolean>;
  personal_reasons: Record<string, string>;
} {
  const pick = (record: Record<string, boolean>) =>
    Object.fromEntries(Object.entries(record).filter(([name, on]) => on && PERSONAL_FLAG_NAMES.includes(name)));
  return {
    shared: pick(stubFlags.get(matterId) ?? {}),
    personal: pick(personalFor(user, matterId)),
    personal_reasons: { ...(stubPersonalReasons.get(user)?.get(matterId) ?? {}) },
  };
}

export function stubFlagCounts(flags: string[], user = ""): Record<string, number> {
  const counts: Record<string, number> = {};
  const matters = new Set<string>([...stubFlags.keys(), ...(stubPersonalFlags.get(user)?.keys() ?? [])]);
  for (const flag of flags) {
    counts[flag] = [...matters].filter((id) => stubListFlags(id, user)[flag]).length;
  }
  return counts;
}

export function stubFlaggedMatters(flags: string[], user = ""): { results: ClientMatch[]; flags_by_matter: Record<string, string[]> } {
  const results = stubSearch("*").results.filter((row) => flags.some((flag) => stubListFlags(String(row.matter_id), user)[flag]));
  return {
    results,
    flags_by_matter: Object.fromEntries(
      results.map((row) => [
        String(row.matter_id),
        Object.entries(stubListFlags(String(row.matter_id), user)).filter(([name, on]) => on && flags.includes(name)).map(([name]) => name),
      ]),
    ),
  };
}

export function stubListFlags(matterId: string, user = ""): Record<string, boolean> {
  const own = Object.fromEntries(Object.entries(personalFor(user, matterId)).filter(([, on]) => on));

  const derived: Record<string, boolean> = matterId === "9001" ? { portal: true } : {};
  return { ...(stubFlags.get(matterId) ?? {}), ...derived, ...own };
}

export function stubSosStatus(matterId: string): SosStatusResponse {
  return { matter_id: matterId, count: 0, draft_count: 0, items: [], folder_found: false };
}

export function stubPersonMatters(matterId: string): PersonMattersResponse {
  if (matterId === "9001" || matterId === "9004") {
    const rows = stubSearch("stub").results;
    const first = rows.find((row) => String(row.matter_id) === "9001");
    const second = rows.find((row) => String(row.matter_id) === "9004");
    if (first && second) return { matter_id: matterId, matters: [first, second] };
  }

  const own = stubSearch("stub").results.find((row) => String(row.matter_id) === matterId);
  return { matter_id: matterId, matters: own ? [own] : [] };
}

const STUB_CHARGING_RATES: BillOfCostsResponse["rates"] = [
  { category: "routine_letter_out", label: "Routine Letter Out", rate: "5.40", unit: "per item" },
  { category: "routine_letter_in", label: "Routine Letter In", rate: "2.70", unit: "per item" },
  { category: "telephone", label: "Telephone", rate: "5.40", unit: "per item" },
  { category: "attendance_preparation", label: "Attendance/Preparation", rate: "59.40", unit: "per hour" },
  { category: "attendance_counsel_court", label: "Attendance on Counsel/Court", rate: "32.40", unit: "per hour" },
  { category: "advocacy_court", label: "Advocacy at Court", rate: "59.40", unit: "per hour" },
  { category: "travelling_waiting", label: "Travelling/Waiting", rate: "28.80", unit: "per hour" },
];

const STUB_FILING_MS = 2500;
type StubNote = { draft_id: string; matter_id: string; item_date: string; description: string; party: string; created: number; createdUtc: string; fail: boolean; retried: boolean; billingRemoved: boolean; removedUtc: string; removedBy: string; noteText: string; edited: boolean; kind: AttendanceNoteKind };

const stubNotes: StubNote[] = ((globalThis as { __valStubNotes?: StubNote[] }).__valStubNotes ??= []);

const STUB_CALLER_LABELS: Record<string, string> = {
  court: "Court",
  counsel: "Counsel",
  client: "Client",
  respondent: "Respondent",
  other: "Other",
};

const STUB_NOTE_URL = "https://example.invalid/stub-attendance-note";

export function stubCreateAttendanceNote(
  matterId: string,
  caller: string,
  noteText = "",
  kind: AttendanceNoteKind = "call",
): AttendanceNoteCreateResponse {
  const now = new Date();
  const date = `${String(now.getDate()).padStart(2, "0")}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getFullYear()).slice(2)}`;
  const draftId = `STUB-AN-${stubNotes.length + 1}`;
  stubNotes.push({
    draft_id: draftId,
    matter_id: matterId,
    item_date: date,
    description: `Attendance note - Tel attendance with ${STUB_CALLER_LABELS[caller] ?? caller}`,
    party: caller,
    created: now.getTime(),
    createdUtc: now.toISOString(),

    fail: /stubfail/i.test(noteText),
    retried: false,
    billingRemoved: false,
    removedUtc: "",
    removedBy: "",
    noteText,
    edited: false,
    kind,
  });
  return { draft_id: draftId, matter_id: matterId, status: "pending" };
}

function stubStateOf(note: (typeof stubNotes)[number]): AttendanceNoteStatus {
  const elapsed = Date.now() - note.created;
  const done = elapsed >= STUB_FILING_MS;
  const failed = done && note.fail && !note.retried;
  return {
    draft_id: note.draft_id,
    matter_id: note.matter_id,
    state: failed ? "failed" : done ? "filed" : "filing",
    an_url: done && !failed ? STUB_NOTE_URL : null,
    billing_item_id: done && !failed ? `STUB-BILL-${note.draft_id}` : null,
    billing_removed: note.billingRemoved,
    error: failed ? "The document could not be uploaded to SharePoint. Try again." : null,
    created_utc: note.createdUtc,
    kind: note.kind,
  };
}

export function stubAttendanceNoteStatus(draftId: string): AttendanceNoteStatus | null {
  const note = stubNotes.find((n) => n.draft_id === draftId);
  return note ? stubStateOf(note) : null;
}

export function stubRecentAttendanceNotes(matterId: string): AttendanceNoteStatus[] {
  return stubNotes
    .filter((n) => n.matter_id === matterId && !n.edited)
    .map(stubStateOf)
    .reverse();
}

export function stubDeleteAttendanceNoteBilling(draftId: string, by = ""): AttendanceNoteStatus | { error: string } {
  const note = stubNotes.find((n) => n.draft_id === draftId);
  if (!note) return { error: "no such draft" };
  if (stubStateOf(note).state !== "filed") return { error: `draft ${draftId} is not filed, so there is no charge to remove` };
  if (!note.billingRemoved) {

    note.billingRemoved = true;
    note.removedUtc = new Date().toISOString();
    note.removedBy = by || "client-viewer";
  }
  return stubStateOf(note);
}

export function stubRestoreBillingItem(itemId: string, by = ""): RestoreBillingItemResponse | { error: string } {
  const note = stubNotes.find((n) => `STUB-BILL-${n.draft_id}` === itemId);
  if (!note) return { error: `no such billing item: ${itemId}` };
  if (note.billingRemoved) {
    note.billingRemoved = false;
    note.removedUtc = "";
    note.removedBy = "";
  }
  return { item_id: itemId, on_bill: true, restored_utc: new Date().toISOString(), restored_by: by || "client-viewer" };
}

export function stubRetryAttendanceNote(draftId: string): AttendanceNoteStatus | { error: string } {
  const note = stubNotes.find((n) => n.draft_id === draftId);
  if (!note) return { error: "no such note" };
  note.retried = true;
  note.created = Date.now();
  return stubStateOf(note);
}

export function stubFrequentCallers(): FrequentCallersResponse {
  return { results: [], an_counts: {}, pinned_matters: [] };
}

export function stubBillOfCosts(matterId: string): BillOfCostsResponse {
  const created = stubNotes.filter((n) => n.matter_id === matterId && stubStateOf(n).state === "filed" && !n.billingRemoved);
  const net = (created.length * 23.76).toFixed(2);
  const vat = (created.length * 4.75).toFixed(2);
  return {
    matter_id: matterId,
    client_name: "",
    categories: created.length
      ? [
          {
            category: "attendance_preparation",
            label: "Attendance/Preparation",
            items: created.map((c) => ({
              item_date: c.item_date,
              description: c.description,
              net_amount: "23.76",
              vat_amount: "4.75",
              document_url: STUB_NOTE_URL,
              attendance_draft_id: c.draft_id,
              party: c.party,
            })),
            subtotal_net: net,
            subtotal_vat: vat,
          },
        ]
      : [],
    parties: [],
    rates: STUB_CHARGING_RATES,
    total_net: net,
    total_vat: vat,
    total_gross: (Number(net) + Number(vat)).toFixed(2),
    item_count: created.length,
    removed: stubNotes
      .filter((n) => n.matter_id === matterId && n.billingRemoved)
      .sort((a, b) => b.removedUtc.localeCompare(a.removedUtc))
      .map((n) => ({
        item_id: `STUB-BILL-${n.draft_id}`,
        item_date: n.item_date,
        description: n.description,
        category_label: "Attendance/Preparation",
        net_amount: "23.76",
        vat_amount: "4.75",
        removed_utc: n.removedUtc,
        removed_by: n.removedBy,
      })),
  };
}

export function stubSetFlag(input: {
  matterId: string;
  flagName: string;
  isSet: boolean;
  setBy: string;
  reason?: string;
  onlyIfReason?: string;

  user?: string;

  scope?: string;
}): Record<string, boolean> {
  if (![...FLAG_FIELDS, ...CATEGORY_PILL_FLAGS].some((f) => f.name === input.flagName)) {
    throw new Error(`unknown flag_name ${input.flagName}`);
  }
  const user = input.user ?? "";
  if (PERSONAL_FLAG_NAMES.includes(input.flagName)) {

    const clearShared = () => {
      if (!stubFlags.get(input.matterId)?.[input.flagName]) return;
      stubFlags.set(input.matterId, { ...stubFlags.get(input.matterId), [input.flagName]: false });
      applyStubFlagRule(input.matterId, input.flagName, false, true, "", "");
    };
    const mine = stubPersonalFlags.get(user) ?? new Map<string, Record<string, boolean>>();
    const myReasons = stubPersonalReasons.get(user) ?? new Map<string, Record<string, string>>();
    const reasonsNow = { ...(myReasons.get(input.matterId) ?? {}) };
    const held = personalFor(user, input.matterId)[input.flagName] === true;
    const text = input.flagName === "flagged" ? (input.reason ?? "").trim().slice(0, 200) : "";
    if (input.isSet) {
      if (!(held && text === STUB_DRAFT_REASON)) {
        mine.set(input.matterId, { ...personalFor(user, input.matterId), [input.flagName]: true });
        if (text) reasonsNow[input.flagName] = text;
        else delete reasonsNow[input.flagName];
      }
    } else if (input.scope === "shared") {
      clearShared();
    } else if (!input.onlyIfReason || reasonsNow[input.flagName] === input.onlyIfReason) {
      mine.set(input.matterId, { ...personalFor(user, input.matterId), [input.flagName]: false });
      delete reasonsNow[input.flagName];
      if (input.flagName === "starred") clearShared();
    }
    myReasons.set(input.matterId, reasonsNow);
    stubPersonalFlags.set(user, mine);
    stubPersonalReasons.set(user, myReasons);
    return stubListFlags(input.matterId, user);
  }
  const existing = stubFlags.get(input.matterId) ?? {};
  const wasSet = existing[input.flagName] ?? false;
  if (!applyStubFlagRule(input.matterId, input.flagName, input.isSet, wasSet, input.reason ?? "", input.onlyIfReason ?? "")) {
    return stubListFlags(input.matterId, user);
  }
  const next = { ...existing, [input.flagName]: input.isSet };
  stubFlags.set(input.matterId, next);

  stubEditSeq += 1;
  const historyExisting = stubEdits.get(input.matterId) ?? [];
  stubEdits.set(input.matterId, [
    {
      edit_id: `STUB-EDIT-${stubEditSeq}`,
      matter_id: input.matterId,
      field_name: `flag:${input.flagName}`,
      field_label: STUB_FIELD_LABELS[`flag:${input.flagName}`] ?? input.flagName,
      old_value: wasSet ? "Yes" : "No",
      new_value: input.isSet ? "Yes" : "No",
      note: "",
      edited_by: input.setBy,
      created_at: new Date().toISOString(),
    },
    ...historyExisting,
  ]);
  return stubListFlags(input.matterId, user);
}

const stubEdits = new Map<string, ClientEdit[]>();
let stubEditSeq = 0;

export function stubListEdits(matterId: string): ClientEdit[] {
  return stubEdits.get(matterId) ?? [];
}

export function stubRecordEdit(input: {
  matterId: string;
  fieldName: string;
  newValue: string;
  note: string;
  editedBy: string;
}): ClientEdit {
  if (!STUB_EDITABLE_FIELDS.includes(input.fieldName)) {
    throw new Error(`unknown field_name ${input.fieldName}`);
  }
  stubEditSeq += 1;
  const existing = stubEdits.get(input.matterId) ?? [];
  const oldValue = existing.find((e) => e.field_name === input.fieldName)?.new_value ?? null;
  const row: ClientEdit = {
    edit_id: `STUB-EDIT-${stubEditSeq}`,
    matter_id: input.matterId,
    field_name: input.fieldName,
    field_label: STUB_FIELD_LABELS[input.fieldName] ?? input.fieldName,
    old_value: oldValue,
    new_value: input.newValue,
    note: input.note.slice(0, STUB_NOTE_MAX_LENGTH),
    edited_by: input.editedBy,
    created_at: new Date().toISOString(),
  };
  stubEdits.set(input.matterId, [row, ...existing]);
  return row;
}

const STUB_SAME_NAME_ROWS: ClientMatch[] = [
  {
    matter_id: "9011",
    client_name: "Stub Samename",
    matter_name: "Non-Molestation Order",
    client_role: "Applicant",
    case_reference: "ZZ24F88888",
    reference_summary: "court_family: ZZ24F88888 | company: EFL-STUB-0011",
    email_primary: null,
    phone_primary: null,
    dob_iso: "1984-06-02",
    address_summary: null,
    party_summary: "Applicant: Stub Samename",
    matched_party_summary: "Applicant: Stub Samename",
    legal_aid_tracker_status: null,
    closed_at: null,
    same_name_index: 1,
    same_name_count: 2,
    same_name_birth_year: 1984,
    same_name_ref: "EFL-STUB-0011",
    extra: { company_reference: "EFL-STUB-0011" },
  },
  {
    matter_id: "9012",
    client_name: "Stub Samename",
    matter_name: "Child Arrangements",
    client_role: "Applicant",
    case_reference: null,
    reference_summary: "company: EFL-STUB-0012",
    email_primary: null,
    phone_primary: null,
    dob_iso: "1991-11-30",
    address_summary: null,
    party_summary: "Applicant: Stub Samename",
    matched_party_summary: "Applicant: Stub Samename",
    legal_aid_tracker_status: null,
    closed_at: null,
    same_name_index: 2,
    same_name_count: 2,
    same_name_birth_year: 1991,
    same_name_ref: "EFL-STUB-0012",
    extra: { company_reference: "EFL-STUB-0012" },
  },
];

export function stubSearch(query: string): ClientSearchResponse {
  if (query.trim().toUpperCase() === "STUB_ERROR") {
    throw new Error("stub error path");
  }

  const testperson: ClientMatch = {
    matter_id: "9001",
    client_name: "Stub Testperson",
    matter_name: "Domestic Abuse",
    client_role: "Applicant",
    case_reference: "ZZ21D00000",
    reference_summary: "court_family: ZZ21D00000",
    email_primary: "stub@example.invalid",
    phone_primary: "07700 900000",
    dob_iso: "1990-01-01",
    address_summary: "Applicant: 1 Example Street, Testville, TE1 1ST",
    party_summary: "Applicant: Stub Testperson | Respondent: Stub Otherperson",
    matched_party_summary: "Applicant: Stub Testperson",
    order_requested_text: "NON-MOLESTATION ORDER",
    legal_aid_tracker_status: "Full certificate",
    closed_at: null,
    extra: {
      nino_canonical: "AB123456C",
      fee_earner: DEMO_FIRM.principal_initials,
      has_c8: true,
      children_summary: "1 child (age 6)",

      order_type_tags: "NMO,CAO",
      primary_person_id: "9101",
      created_utc: "2025-03-04T10:15:00",
    },
  };
  const fixed: ClientMatch[] = [
      testperson,

      {
        ...testperson,
        matter_id: "9004",
        matter_name: "Child Arrangements",
        client_role: "Respondent",
        case_reference: "ZZ22C11111",
        reference_summary: "court_family: ZZ22C11111",
        party_summary: "Applicant: Stub Otherperson | Respondent: Stub Testperson",
        matched_party_summary: "Respondent: Stub Testperson",
        order_requested_text: "CHILD ARRANGEMENTS ORDER",
        extra: { ...testperson.extra, created_utc: "2026-07-21T09:00:00" },
      },
      {
        matter_id: "9002",
        client_name: "Second Stubperson",
        matter_name: "Child Arrangements",
        client_role: "Respondent",
        case_reference: null,
        email_primary: null,
        phone_primary: null,
        dob_iso: null,
        address_summary: null,
        party_summary: "Respondent: Second Stubperson",
        matched_party_summary: "Respondent: Second Stubperson",
        legal_aid_tracker_status: null,
        closed_at: "2026-01-15",
        extra: {},
      },
      {
        matter_id: "9003",
        client_name: "Third Stubperson",
        matter_name: "Non-Molestation Order",
        client_role: "Applicant",
        case_reference: "ZZ21D33333",
        email_primary: null,
        phone_primary: null,
        dob_iso: null,
        address_summary: null,
        party_summary: "Applicant: Third Stubperson | Respondent: Stub Testperson",
        matched_party_summary: "Respondent: Stub Testperson",
        legal_aid_tracker_status: "Applied for",
        closed_at: null,
        extra: {},
      },
      ...STUB_SAME_NAME_ROWS,
  ];
  const results = [...fixed, ...stubMadeClients(query)];
  return { query, resolved_query: query, source: "sql", count: results.length, results };
}

export function stubFieldReviewQueue(): FieldReviewQueueResponse {
  const flag = (matterId: string, fieldName: string, fieldLabel: string, note: string): FieldReviewFlag => ({
    review_id: `stub-review-${matterId}-${fieldName}`,
    matter_id: matterId,
    client_name: matterId === "9001" ? "Stub Testperson" : "Third Stubperson",
    field_name: fieldName,
    field_label: fieldLabel,
    value_snapshot: "",
    note,
    flagged_by: "Stub Caseworker",
    flagged_at: "2026-09-20T09:00:00Z",
    resolved_by: null,
    resolved_at: null,
  });

  const results: ClientMatch[] = [
    {
      matter_id: "9001",
      client_name: "Stub Testperson",
      matter_name: "Domestic Abuse",
      client_role: "Applicant",
      case_reference: "ZZ21D00000",
      reference_summary: "court_family: ZZ21D00000",
      email_primary: "stub@example.invalid",
      phone_primary: "07700 900000",
      dob_iso: "1990-01-01",
      address_summary: "Applicant: 1 Example Street, Testville, TE1 1ST",
      party_summary: "Applicant: Stub Testperson | Respondent: Stub Otherperson",
      matched_party_summary: "Applicant: Stub Testperson",
      legal_aid_tracker_status: "Full certificate",
      closed_at: null,
      extra: { nino_canonical: "AB123456C", fee_earner: DEMO_FIRM.principal_initials, has_c8: true, children_summary: "1 child (age 6)", order_type_tags: "NMO,CAO" },
    },
    {
      matter_id: "9003",
      client_name: "Third Stubperson",
      matter_name: "Non-Molestation Order",
      client_role: "Applicant",
      case_reference: "ZZ21D33333",
      email_primary: null,
      phone_primary: null,
      dob_iso: null,
      address_summary: null,
      party_summary: "Applicant: Third Stubperson | Respondent: Stub Testperson",
      matched_party_summary: "Respondent: Stub Testperson",
      legal_aid_tracker_status: "Applied for",
      closed_at: null,
      extra: {},
    },
  ];

  return {
    results,
    flags_by_matter: {
      "9001": [
        flag("9001", "address_line1", "Address line 1", "Post came back undelivered. Check with the client."),
        flag("9001", "dob_iso", "Date of birth", "Doesn't match the referral"),
      ],
      "9003": [flag("9003", "phone_primary", "Telephone", "No number on file yet")],
    },
  };
}

function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

export function stubVergilAskStream(question: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const chunks = [
    `Thanks for asking about this matter. `,
    `You said: "${question.slice(0, 120)}". `,
    `(This is the offline stub response, CASEFORGE_HUB_API_STUB=1: no real Goose session ran.)`,
  ];
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(encoder.encode(sseFrame("session", { session_id: "goose_stub" })));
      for (const chunk of chunks) {
        await new Promise((resolve) => setTimeout(resolve, 150));
        controller.enqueue(encoder.encode(sseFrame("delta", { text: chunk })));
      }
      controller.enqueue(encoder.encode(sseFrame("done", {})));
      controller.close();
    },
  });
}

export function stubMatterTasks(matterId: string): MatterTasksResponse {
  const none: MatterTasksResponse = { matter_id: matterId, configured: true, open_complaints: 0, open_updates: 0, open_settlements: 0, items: [] };
  if (process.env.CASEFORGE_STUB_ATTENTION_DEMO !== "1") return none;
  const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();
  if (matterId === "9003") {
    const plain = { complaint_domain: "", settlement_stage: "", deadline: "", importance: "normal", web_link: "https://example.invalid/stub-email", kind: "update" };
    return {
      ...none,
      open_updates: 1,
      items: [
        { ...plain, task_id: "stub-v2", subject: "Bundle", summary: "Asks when the bundle will be ready.", status: "completed", created: hoursAgo(24 * 20) },
        { ...plain, task_id: "stub-v1", subject: "Contact", summary: "Says the handover went ahead as ordered.", status: "notStarted", created: hoursAgo(5) },
      ],
    };
  }
  if (matterId !== "9001") return none;
  const long =
    "The client writes that the respondent has contacted her again through a relative, asks whether this breaches the order, " +
    "and wants to know what evidence to keep. She also says the next contact handover is this weekend and asks for advice before then.";
  const base = { complaint_domain: "", settlement_stage: "", deadline: "", importance: "normal", web_link: "https://example.invalid/stub-email" };
  const items: MatterTasksResponse["items"] = [
    { ...base, task_id: "stub-u4", kind: "update", subject: "Earlier note", summary: "Sent the hearing date she was given at court.", status: "completed", created: hoursAgo(24 * 400) },
    { ...base, task_id: "stub-u3", kind: "update", subject: "Contact through a relative", summary: long, status: "notStarted", created: hoursAgo(72) },
    { ...base, task_id: "stub-u2", kind: "complaint", complaint_domain: "documenso_process", subject: "Signing link", summary: "Says the signing link would not open on her phone and she has tried three times. " + long, status: "notStarted", created: hoursAgo(26) },
    { ...base, task_id: "stub-u1", kind: "update", subject: "New address", summary: "Has moved and gives a new postal address; asks that letters go there from now on. " + long, status: "notStarted", created: hoursAgo(2), deadline: "Fri 10 Oct" },
  ];
  return { ...none, open_complaints: 1, open_updates: 2, items };
}

export function stubMatterMarkers(matterId: string): MatterMarkersResponse {
  const missing = { status: "missing" as const, date: "" };
  const received = (daysAgo: number) => ({
    status: "received" as const,
    date: new Date(Date.now() - daysAgo * 86_400_000).toISOString(),
    url: "https://example.invalid/stub-document",
  });
  if (process.env.CASEFORGE_STUB_ATTENTION_DEMO === "1") {
    if (matterId === "9001") return { matter_id: matterId, loa: received(5), initial_ws: received(9), intro: received(12) };
    if (matterId === "9003") return { matter_id: matterId, loa: missing, initial_ws: received(2), intro: missing };
  }
  return { matter_id: matterId, loa: missing, initial_ws: missing, intro: missing };
}

export * from "./stubAttention";

export function stubEditAttendanceNote(draftId: string): { error: string } | {
  draft_id: string; matter_id: string; caller: string; caller_other: string; note_text: string; time_minutes: number | null; kind: AttendanceNoteKind;
} {
  const note = stubNotes.find((n) => n.draft_id === draftId);
  if (!note) return { error: "no such draft" };
  if (stubStateOf(note).state === "filed") return { error: "that attendance note has already been filed" };
  note.edited = true;
  return { draft_id: note.draft_id, matter_id: note.matter_id, caller: note.party, caller_other: "", note_text: note.noteText, time_minutes: null, kind: note.kind };
}

export function stubConcludedMatters(offset: number, limit: number): ConcludedMattersResponse {
  const total = 120;
  const template = stubSearch("stub").results[0];
  const end = Math.min(total, offset + limit);
  const results = [];
  for (let i = offset; i < end; i += 1) {
    results.push({ ...template, matter_id: String(9100 + i), client_name: `Concluded Stubperson ${i + 1}`, closed_at: "2026-01-01T00:00:00Z" });
  }
  return { results, total, next_offset: end < total ? end : null };
}

export function stubRaiseAutomaticFlag(matterId: string, reason: string): void {
  stubFlags.set(matterId, { ...(stubFlags.get(matterId) ?? {}), flagged: true });
  applyStubFlagRule(matterId, "flagged", true, false, reason, "");
}

if (process.env.STUB_DEMO_AUTO_FLAG === "1") stubRaiseAutomaticFlag("9002", "Client complaint to deal with");
