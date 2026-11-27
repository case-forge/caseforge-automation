
import { EMAIL_VARIANTS, PIPELINE_STEP_KEYS, PIPELINE_STEP_LABELS, PIPELINE_STEP_NUMBERS, stepRef, stepRefCap } from "./pipelineTypes";
import type {
  AmendOpenRound,
  AmendStepInfo,
  MatterModeAnswer,
  MatterModeSetting,
  Pipeline,
  PipelineEvent,
  PipelineMode,
  PipelineRunResult,
  PipelineStep,
  PipelineStepKey,
} from "./pipelineTypes";

interface State {
  done: Set<string>;
  outside: Map<string, string>;
  events: PipelineEvent[];

  amendRounds: number;
  amendOpen: AmendOpenRound | null;

  amendTrouble: "" | "changed" | "nodraft";

  amendSigned: boolean;
}

const states = new Map<string, State>();

const matterModes = new Map<string, { setting: MatterModeSetting; by: string; at: string }>();
let mode: PipelineMode = "manual";
let seq = 0;

function stateFor(matterId: string): State {
  let s = states.get(matterId);
  if (!s) {
    s = { done: new Set(["record"]), outside: new Map(), events: [], amendRounds: 0, amendOpen: null, amendTrouble: "", amendSigned: false };
    s.events.push({
      event_id: "stub-e0-" + matterId,
      step: "record",
      status: "ok",
      summary: "Client details logged to the database.",
      by: "intake",
      mode: "auto",
      created_utc: new Date(Date.now() - 3_600_000).toISOString(),
      actor_kind: "automation",
    });

    s.events.push({
      event_id: "stub-e0a-" + matterId,
      step: "mode",
      status: "info",
      summary: "This client follows the firm-wide mode, set by Owner (CLI session).",
      by: "Owner (CLI session)",
      mode: "manual",
      created_utc: new Date(Date.now() - 1_800_000).toISOString(),
      actor_kind: "agent",
    });
    states.set(matterId, s);
  }
  return s;
}

const RUN_LABELS: Record<PipelineStepKey, string> = {
  record: "Check record",
  folder: "Generate folders",
  statement: "Draft statement",
  email: "Draft email",
  amend: "Prepare the amended statement",
  ws_sign: "Draft email for signature",
  court_pack: "Make court pack",
  court_email: "Draft court email",
  court_reply: "File court's reply",
  client_papers: "Draft email to the client",
  serve: "Draft email to referrer",
  serve_other: "Draft service email",
  sos_received: "File statement of service",
  sos_to_court: "Draft email to court",
  bundle: "Build bundle",
  ccl: "Make letter",
  brief: "Draft brief",
  book_counsel: "Draft request for counsel",
  mid_letter: "Draft outcome letter",
  closing_letter: "Draft closing letter",
};

const DETAIL: Record<PipelineStepKey, string[]> = {
  record: ["Company reference 260925/02FL", "Name, order type and folder are recorded."],
  folder: ["18 standard folders, the referral's papers and the unpacked zip.", "Only what is missing is added; nothing is overwritten."],
  statement: ["Spelling is corrected and a change list is kept."],
  email: ["Nothing is sent. The draft waits in Outlook for a person."],
  amend: [],
  ws_sign: ["One signing envelope per matter. Nothing is sent."],
  court_pack: ["The application forms need a person to finish and print them."],
  court_email: ["Drafted once: the Notice of Acting goes to court once."],
  court_reply: ["Filed in the Court-Orders folder. Nothing is replaced."],
  client_papers: ["The court's papers and the hearing date. A C8 form is never attached. Nothing is sent."],
  serve: ["A C8 form is never attached. Nothing is sent."],
  serve_other: ["Used only when a person adds a recipient."],
  sos_received: ["Each statement of service is filed on its own."],
  sos_to_court: ["One email to court per statement of service. Nothing is sent."],
  bundle: ["Built in the hearing folder once counsel is booked, or the working day before. A person reviews it."],
  ccl: ["A second letter is never made. Nothing is sent."],
  brief: ["One per hearing with counsel booked, saved in the counsel folder."],
  book_counsel: ["One request per hearing to the chambers on record. Nothing is sent."],
  mid_letter: ["One letter per hearing, from the order on file. Nothing is sent."],
  closing_letter: ["Once the final hearing's order is on file. Nothing is sent."],
};

export const STUB_PORTAL_MATTER = "9002";
const PORTAL_VARIANT = { key: "portal_filed", label: "I have filed it through the portal" };

function buildSteps(s: State, matterId: string): PipelineStep[] {

  const passed = (key: string): boolean =>
    key === "amend" || key === "ws_sign"
      ? passed(PIPELINE_STEP_KEYS[PIPELINE_STEP_KEYS.indexOf(key as PipelineStepKey) - 1])
      : s.done.has(key) || s.outside.has(key) || (key === "serve_other" && !s.done.has(key));
  return PIPELINE_STEP_KEYS.map((key, i) => {
    if (key === "amend") return amendStep(s);
    const outside = s.outside.get(key);
    const done = s.done.has(key) || outside !== undefined;
    const previousDone = i === 0 || passed(PIPELINE_STEP_KEYS[i - 1]);
    const links = done ? [{ label: `Open the folder for ${stepRef(key)}`, url: `https://example.invalid/stub/${key}` }] : [];
    if ((key === "serve_other" || key === "ws_sign") && !done) {
      return {
        key,
        number: PIPELINE_STEP_NUMBERS[key],
        label: PIPELINE_STEP_LABELS[key],
        status: "not_needed",
        summary:
          key === "ws_sign"
            ? "Used only once the client has approved the draft statement (their reply recorded as approved)."
            : "Not needed: nobody else is to be served. Add a law firm, hospital or school only if one is, and this step drafts their email.",
        detail: [],
        can_run: false,
        run_label: RUN_LABELS[key],
        variants: [],
        outside: "",
        actor: "",
        links: [],
        resettable: false,
      };
    }
    if (key === "court_email" && matterId === STUB_PORTAL_MATTER && !done && previousDone) {
      return {
        key,
        number: PIPELINE_STEP_NUMBERS[key],
        label: PIPELINE_STEP_LABELS[key],
        status: "attention",
        summary: "Hull (Kingston upon Hull) takes applications only through the online portal, which only a person can use. File the application there, then mark it filed.",
        detail: ["Case flow drafts no court email for this court and never opens the portal.", `The forms from ${stepRef("court_pack")} are there to copy from. Press the button once it is filed.`],
        can_run: true,
        run_label: PORTAL_VARIANT.label,
        variants: [PORTAL_VARIANT],
        outside: "",
        actor: "you",
        links: [],
        resettable: false,
      };
    }
    return {
      key,
      number: PIPELINE_STEP_NUMBERS[key],
      label: PIPELINE_STEP_LABELS[key],
      status: done ? "done" : previousDone ? "todo" : "blocked",
      summary: outside ?? (done ? "Done." : previousDone ? "Ready to run." : "Waiting for the step before."),
      detail: done ? DETAIL[key] : [],
      auto_tries: !done && key === "email" ? 2 : 0,
      auto_max: !done && key === "email" ? 3 : 0,
      can_run: previousDone,
      run_label: RUN_LABELS[key],
      variants: key === "email" ? EMAIL_VARIANTS : [],
      outside: outside !== undefined ? "by_hand" : "",
      actor: done ? "" : previousDone ? "you" : "case flow",
      links,
      resettable: done,
    };
  });
}

function amendStep(s: State): PipelineStep {
  const open = s.amendOpen;

  const rounds = s.amendRounds + (open ? 1 : 0);
  const info: AmendStepInfo = {
    rounds,
    flagged: rounds >= 3,
    can_start: open === null && !s.amendSigned,
    start_blocked: open ? `Round ${open.round} is waiting: approve or discard it first.` : s.amendSigned ? SIGNED_ON_FILE : "",
    email_hint: "",
    open,
  };
  const marked = s.outside.get("amend");
  const detail = rounds ? [`Rounds so far: ${rounds}.`] : [];
  if (!open && s.amendSigned) detail.push(SIGNED_ON_FILE);
  return {
    key: "amend",
    number: PIPELINE_STEP_NUMBERS.amend,
    label: PIPELINE_STEP_LABELS.amend,
    status: open ? "attention" : marked !== undefined ? "done" : "not_needed",
    summary: marked !== undefined && !open
      ? marked
      : open
      ? open.status === "saved"
        ? `Round ${open.round}: the amended statement is saved; the email is not drafted yet. Approve again to draft it.`
        : `Round ${open.round} is ready for the owner. Nothing is saved or sent until it is approved.`
      : `${s.amendRounds ? `Round ${s.amendRounds} was approved and drafted. ` : ""}Used only when the client asks for changes to the draft statement.`,
    detail,
    can_run: false,
    run_label: RUN_LABELS.amend,
    variants: [],
    outside: marked !== undefined && !open ? "by_hand" : "",
    actor: open ? "you" : "",
    links: [],
    resettable: marked !== undefined && !open,
    amend: info,
  };
}

function stubRound(round: number, by: string, emailText: string, earlierRounds: number): AmendOpenRound {
  const asked = emailText.trim().slice(0, 140);
  return {
    round,
    status: "prepared",
    prepared_by: by,
    prepared_utc: new Date().toISOString(),
    paragraphs: [
      {
        id: "p4",
        para: 4,
        before: "On 3 March the Respondent came to my flat at about 9pm and shouted at me through the door.",
        after: "On 3 March the Respondent came to my flat at about 10pm and shouted at me through the door for twenty minutes.",
        why: "The client asked for this (paragraph 4).",
        client_words: "It was 10pm not 9pm, and he was there for about twenty minutes.",
        flags: [],
      },
      {
        id: "p7",
        para: 7,
        before: "I reported the incident to the police the next day. I was given a crime reference number. An officer visited me a week later.",
        after: "I reported the incident to the police the next day and was given a crime reference number. I feel the police did not take it seriously.",
        why: "The client asked for this (paragraph 7).",
        client_words: "Please say the police did not take it seriously.",
        flags: [
          { kind: "review", text: "\"An officer visited me a week later.\" is not in the new text." },
          { kind: "editorial", text: "\"I feel the police did not take it seriously\" is opinion rather than fact." },
        ],
      },
      {
        id: "p9",
        para: 9,
        before: "Our son, aged 6, attends Example Primary School.",
        after: "Our son, aged 7, attends Example Primary School.",
        why: "Same event as paragraph 2: confirmed by a yes/no check.",
        client_words: "My son had his birthday, he is 7 now.",
        flags: earlierRounds > 0 ? [{ kind: "asked_again", text: `Asked for in round ${earlierRounds} too.` }] : [],
      },
      {
        id: "new1",
        para: null,
        before: "",
        after: "Since the application, the Respondent has sent me messages through a friend asking me to drop the case.",
        why: "The client asked for a new paragraph at the end.",
        client_words: asked || "Can you add that he keeps sending me messages through a friend?",
        flags: [{ kind: "facts_unread", text: "The messages are not in the client's folder; nobody has read them." }],
      },
    ],
    questions: [
      { para: null, type: "question_to_solicitor", client_words: "When will the court give us a hearing date?" },
      { para: 7, type: "asks_advice", client_words: "Should I go back to the police about the messages?" },
    ],
    unplaced: [{ type: "change", client_words: "The bit about the car is wrong.", why: "No paragraph mentions a car." }],
    db_updates: [{ field: "a child's age (children)", current: "6", proposed: "7", para: 9, quote: "he is 7 now" }],
    repeats: earlierRounds > 0 ? [{ para: 9, client_words: "My son is 7 now.", earlier_round: earlierRounds, in_text_now: false }] : [],
    notes: ["Stub round: synthetic text only, nothing was read from a real statement."],
  };
}

export const STUB_AMEND_WORDS = { signed: "STUB-SIGNED", changed: "STUB-CHANGED", nodraft: "STUB-NODRAFT" } as const;
const SIGNED_ON_FILE = "The signed statement is on file: a change now is a person's job.";

export function stubAmendPrepare(matterId: string, by: string, emailText: string): Pipeline | { error: string } {
  const s = stateFor(matterId);
  if (s.amendOpen) return { error: `round ${s.amendOpen.round} is waiting for the owner: approve or discard it first` };
  if (s.amendSigned) return { error: SIGNED_ON_FILE };
  if (emailText.includes(STUB_AMEND_WORDS.signed)) {

    s.amendSigned = true;
    return { error: SIGNED_ON_FILE };
  }
  s.amendTrouble = emailText.includes(STUB_AMEND_WORDS.changed) ? "changed" : emailText.includes(STUB_AMEND_WORDS.nodraft) ? "nodraft" : "";
  s.amendOpen = stubRound(s.amendRounds + 1, by, emailText, s.amendRounds);
  seq += 1;
  const summary = `Round ${s.amendOpen.round} of changes to the statement prepared by ${by}. Nothing was saved or sent.`;
  s.events.push({ event_id: `stub-e${seq}`, step: "amend", status: "info", summary, by, mode, actor_kind: "person", created_utc: new Date().toISOString() });
  return stubPipeline(matterId);
}

export function stubAmendApprove(matterId: string, by: string, round: number, answers: string, keepOriginal: string[], edits: Record<string, string> = {}): PipelineRunResult | { error: string } {
  const s = stateFor(matterId);
  const open = s.amendOpen;
  if (!open || open.round !== round) return { error: `round ${round} is not waiting for the owner` };
  const kept = open.paragraphs.filter((p) => keepOriginal.includes(p.id)).length;
  if (open.status === "prepared" && kept === open.paragraphs.length) return { error: "every change is kept as the original: discard the round instead" };
  const unknown = Object.keys(edits).find((id) => !open.paragraphs.some((p) => p.id === id));
  if (unknown) return { error: `${unknown} is not a paragraph of this round` };
  const editedIds = open.status === "prepared" ? open.paragraphs.filter((p) => edits[p.id] !== undefined && !keepOriginal.includes(p.id)).map((p) => p.id) : [];
  if (s.amendTrouble === "changed") return { error: "the statement has changed since this round was prepared: discard it and prepare it again" };
  if (s.amendTrouble === "nodraft") {

    s.amendTrouble = "";
    open.status = "saved";
    for (const p of open.paragraphs) {
      if (editedIds.includes(p.id)) Object.assign(p, { model_after: p.after, after: edits[p.id].trim(), edited: true });
    }
    seq += 1;
    const message = `Round ${round} approved by ${by}: the amended statement is saved, but the email was not drafted (the stub's mailbox refused it). Approve again to draft it.`;
    s.events.push({ event_id: `stub-e${seq}`, step: "amend", status: "failed", summary: message, by, mode, actor_kind: "person", created_utc: new Date().toISOString() });
    return { ok: false, message, links: [], pipeline: stubPipeline(matterId) };
  }
  s.amendRounds = open.round;
  s.amendOpen = null;
  seq += 1;
  const summary = `Round ${round}: the amended statement is saved${kept ? ` (${kept} kept as the original)` : ""}${editedIds.length ? ` (${editedIds.length} in your own words)` : ""} and the email to the client is drafted as AI DRAFTED${answers.trim() ? ", with your answers" : ""}. Nothing was sent.`;
  const links = [
    { label: "Open the amended statement", url: "https://example.invalid/stub/amend/statement" },
    { label: "Open the draft email", url: "https://example.invalid/stub/amend/draft" },
  ];
  s.events.push({ event_id: `stub-e${seq}`, step: "amend", status: "ok", summary, by, mode, actor_kind: "person", created_utc: new Date().toISOString(), links });
  return { ok: true, message: summary, links, pipeline: stubPipeline(matterId) };
}

export function stubAmendDiscard(matterId: string, by: string, round: number): Pipeline | { error: string } {
  const s = stateFor(matterId);
  if (!s.amendOpen || s.amendOpen.round !== round) return { error: `round ${round} is not waiting for the owner` };
  if (s.amendOpen.status !== "prepared") return { error: `round ${round}'s statement is already saved: approve it again to draft the email` };
  s.amendOpen = null;
  s.amendTrouble = "";
  seq += 1;
  s.events.push({ event_id: `stub-e${seq}`, step: "amend", status: "info", summary: `Round ${round} discarded by ${by}.`, by, mode, actor_kind: "person", created_utc: new Date().toISOString() });
  return stubPipeline(matterId);
}

export function stubPipeline(matterId: string): Pipeline {
  const s = stateFor(matterId);
  const own = matterModes.get(matterId);
  const setting = own?.setting ?? "inherit";
  return {
    matter_id: matterId,
    client_name: matterId === "603" ? "Dana Echotest" : "Stub Testperson",
    mode,
    matter_mode: setting,
    matter_mode_by: own?.by ?? "",
    matter_mode_at: own?.at ?? "",
    effective_mode: setting === "inherit" ? mode : setting,
    steps: buildSteps(s, matterId),
    events: [...s.events],

    waiting: matterId.startsWith("wait-") ? { state: matterId.slice(5), label: `WAITING FOR ${matterId.slice(5).toUpperCase()}` } : { state: "", label: "" },
  };
}

export function stubRun(matterId: string, step: string, by: string, variant: string): { ok: boolean; message: string; pipeline: Pipeline } | { error: string } {
  if (!PIPELINE_STEP_KEYS.includes(step as PipelineStepKey)) return { error: `unknown step: ${step}` };
  if (step === "amend") return { error: `${stepRef("amend")} is prepared and approved from its own panel` };
  if (step === "email" && !EMAIL_VARIANTS.some((v) => v.key === variant)) return { error: "choose which email to draft" };
  const s = stateFor(matterId);
  seq += 1;
  const label = PIPELINE_STEP_LABELS[step as PipelineStepKey];
  const summary =
    variant === PORTAL_VARIANT.key
      ? `Filed through the portal of Hull (Kingston upon Hull), marked by ${by}. No court email was drafted.`
      : `${label}.`;
  s.done.add(step);
  const links = variant === PORTAL_VARIANT.key ? [] : [{ label: "Open what this step made", url: `https://example.invalid/stub/${step}/made` }];
  s.events.push({ event_id: `stub-e${seq}`, step, status: "ok", summary, by, mode, actor_kind: "person", created_utc: new Date().toISOString(), links });
  return { ok: true, message: summary, pipeline: stubPipeline(matterId) };
}

export function stubResetStep(matterId: string, step: string, by: string): Pipeline | { error: string } {
  if (!PIPELINE_STEP_KEYS.includes(step as PipelineStepKey)) return { error: `unknown step: ${step}` };
  const s = stateFor(matterId);
  if (step === "amend" && !s.outside.has("amend")) return { error: `${stepRef("amend")} has no mark to forget: its rounds are approved or discarded` };
  s.done.delete(step);
  s.outside.delete(step);
  seq += 1;
  const summary = `${stepRefCap(step as PipelineStepKey)}'s mark forgotten by ${by}. Nothing was deleted.`;
  s.events.push({ event_id: `stub-e${seq}`, step, status: "reset", summary, by, mode, actor_kind: "person", created_utc: new Date().toISOString() });
  return stubPipeline(matterId);
}

export function stubMarkDone(matterId: string, step: string, by: string, note: string): Pipeline | { error: string } {
  if (!PIPELINE_STEP_KEYS.includes(step as PipelineStepKey)) return { error: `unknown step: ${step}` };
  const s = stateFor(matterId);
  if (step === "amend" && s.amendOpen) return { error: `round ${s.amendOpen.round} of ${stepRef("amend")} is waiting: approve or discard it first` };
  if (s.done.has(step) || s.outside.has(step)) return { error: "this step is already done" };
  const day = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/London" });
  const summary = `Done outside Case flow by ${by} on ${day}.`;
  s.outside.set(step, summary);
  seq += 1;
  s.events.push({ event_id: `stub-e${seq}`, step, status: "outside", summary: note ? `${summary} Note: ${note}` : summary, by, mode, actor_kind: "person", created_utc: new Date().toISOString() });
  return stubPipeline(matterId);
}

export function stubNote(matterId: string, step: string, by: string, summary: string): Pipeline {
  const s = stateFor(matterId);
  seq += 1;
  s.events.push({ event_id: `stub-e${seq}`, step, status: "info", summary, by, mode, actor_kind: "person", created_utc: new Date().toISOString() });
  return stubPipeline(matterId);
}

export function stubSetMode(next: string): { mode: PipelineMode } | { error: string } {
  if (next !== "manual" && next !== "auto") return { error: "mode must be manual or auto" };
  mode = next;
  return { mode };
}

export function stubSetMatterMode(matterId: string, setting: string, by: string): MatterModeAnswer | { error: string } {
  if (setting !== "inherit" && setting !== "auto" && setting !== "manual") return { error: "the client's setting must be inherit, auto or manual" };
  const who = by.trim();
  if (!who) return { error: "type your name first" };
  const at = new Date().toISOString();
  matterModes.set(matterId, { setting, by: who, at });
  const words = setting === "inherit" ? "follows the firm-wide mode" : setting === "auto" ? "is on Auto" : "is on Manual";
  stubNote(matterId, "mode", who, `This client ${words}, set by ${who}.`);
  return { matter_id: matterId, setting, by: who, at, mode, effective_mode: setting === "inherit" ? mode : setting };
}
