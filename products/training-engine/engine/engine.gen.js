
import { createStubEnv } from "./dom-stub.js";

export const V1_BUILD = "2026-09-24.5";

export const SEEDS = {"checklist":{"tag":"div","cls":"checklist"},"statusText":{"tag":"span","cls":"status"},"openCrmBtn":{"tag":"button","cls":"icon-circle-btn"},"newMatterBtn":{"tag":"button","cls":"icon-circle-btn new-matter-btn"},"stageJumpSelect":{"tag":"select","cls":"stage-jump"},"hintToggleBtn":{"tag":"button","cls":"icon-circle-btn header-tool-btn"},"resetAllBtn":{"tag":"button","cls":"icon-circle-btn header-tool-btn"},"updateBanner":{"tag":"div","cls":"refresh-banner"},"sessionStaleBanner":{"tag":"div","cls":"refresh-banner refresh-banner-stale"},"caseBoard":{"tag":"section","cls":"case-board"},"caseBoardColumns":{"tag":"div","cls":"case-board-columns"},"inboxCount":{"tag":"span"},"emptyInbox":{"tag":"div","cls":"empty"},"emailRows":{"tag":"div"},"closeSelect":{"tag":"select"},"emailViewerPanel":{"tag":"section","cls":"panel viewer"},"viewerTitle":{"tag":"span"},"emptyViewer":{"tag":"div","cls":"empty"},"message":{"tag":"article","cls":"message"},"messageSubject":{"tag":"h2"},"casePills":{"tag":"span","cls":"case-pills"},"messageFrom":{"tag":"strong"},"messageTo":{"tag":"strong"},"messageSubjectMeta":{"tag":"strong"},"messageReceived":{"tag":"strong"},"fakeWarning":{"tag":"div","cls":"fake-warning"},"referralBody":{"tag":"div"},"zipAttachment":{"tag":"div","cls":"attachment-row"},"attachmentName":{"tag":"div","cls":"file-name"},"referralGreeting":{"tag":"p"},"introText":{"tag":"div","cls":"intro-text"},"referralSignoff":{"tag":"span"},"incomingBody":{"tag":"div"},"winScreen":{"tag":"div","cls":"win-screen"},"clientDraftPane":{"tag":"article","cls":"message"},"clientDraftSubject":{"tag":"h2"},"clientDraftPills":{"tag":"span","cls":"case-pills"},"clientDraftFrom":{"tag":"strong"},"clientDraftTo":{"tag":"strong"},"clientDraftCcLabel":{"tag":"span"},"clientDraftCc":{"tag":"strong"},"clientDraftSubjectMeta":{"tag":"strong"},"clientDraftDropZone":{"tag":"div","cls":"draft-drop-zone"},"clientDraftDropText":{"tag":"span"},"clientDraftAttachments":{"tag":"div","cls":"draft-attachments"},"clientDraftStatus":{"tag":"div","cls":"draft-status"},"clientDraftSendBtn":{"tag":"button","cls":"primary"},"clientDraftBody":{"tag":"div","cls":"draft-body"},"sortFoldersBtn":{"tag":"button","cls":"sort-btn active"},"sortFoldersLabel":{"tag":"span"},"explorerTree":{"tag":"div","cls":"tree"},"modalBackdrop":{"tag":"div","cls":"modal-backdrop"},"modalTitle":{"tag":"h3"},"modalBody":{"tag":"div","cls":"modal-body"},"modalCloseBtn":{"tag":"button"},"stepCard":{"tag":"aside","cls":"step-card"},"stepCardTitle":{"tag":"span","cls":"step-card-title"},"stepCardClose":{"tag":"button","cls":"step-card-close"},"stepCardLabel":{"tag":"p","cls":"step-card-label"},"stepCardWhy":{"tag":"p","cls":"step-card-why"},"stepCardReal":{"tag":"p","cls":"step-card-real"},"buildBadge":{"tag":"div","cls":"badge build-badge-corner"}};

export function createEngine(savedStorage) {
  const __env = createStubEnv(savedStorage, SEEDS);
  const document = __env.document;
  const window = __env.window;
  const localStorage = __env.localStorage;
  const navigator = window.navigator;
  const location = window.location;
  const URL = __env.URL;
  const Blob = __env.Blob;
  const requestAnimationFrame = window.requestAnimationFrame;
  const cancelAnimationFrame = window.cancelAnimationFrame;
  const setInterval = window.setInterval;
  const clearInterval = window.clearInterval;
  const setTimeout = window.setTimeout;
  const clearTimeout = window.clearTimeout;
  const alert = window.alert;
  const confirm = window.confirm;
  const prompt = window.prompt;
  const matchMedia = window.matchMedia;
  const getComputedStyle = window.getComputedStyle;

const MAX_EMAILS = 6;

const CLOSED_LABELS = { concluded: "Concluded", transferred: "Transferred", "dropped-out": "Dropped out" };

function trainingToday() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

const APP_BUILD = "2026-09-24.5";
let fallbackHearingDates = null;
const STATE_STORAGE_KEY = "caseforge-training-state-v2";

const TEMPLATES = [
  { name: "Brief to Counsel", ext: "docx" },
  { name: "Case Summary", ext: "docx" },
  { name: "Chronology", ext: "docx" },
  { name: "Cover Page", ext: "docx" },
  { name: "Draft Non-Molestation Order", ext: "docx" },
  { name: "Draft Occupation Order", ext: "docx" },
  { name: "Draft Prohibited Steps Order", ext: "docx" },
  { name: "Letter of Authority", ext: "pdf" },
  { name: "Notice of Acting", ext: "pdf" },
  { name: "Witness Statement", ext: "docx" }
];

const BUNDLE_SECTIONS = [
  { key: "cover", title: "A - Cover page" },
  { key: "summary", title: "B - Summary and chronology" },
  { key: "applications", title: "C - Applications, notices and orders" },
  { key: "statements", title: "D - Witness statement" },
  { key: "service", title: "E - Statement of Service" }
];

const HEARING_TEMPLATE_NAMES = new Set(["Cover Page", "Case Summary", "Chronology", "Brief to Counsel"]);
const CLIENT_DOC_TEMPLATE_NAMES = new Set(["Witness Statement"]);

const ZIP_BUNDLED_DOCUMENT_NAMES = {
  witnessStatement: "Witness Statement",
  fl401: "FL401",
  c100: "C100",
  c1a: "C1A"
};
const REFERRAL_STAGE = "referral";
const STAGE_ORDER = [REFERRAL_STAGE, "client-response", "court-response", "counsel-response", "process-server-response", "process-server-invoice", "counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"];

const ORDER_GRANTED_WEIGHTS = [
  { round: 1, weight: 45 },
  { round: 2, weight: 45 },
  { round: 3, weight: 10 }
];

const PSO_ONLY_GRANTED_WEIGHTS = [
  { round: 1, weight: 10 },
  { round: 2, weight: 75 },
  { round: 3, weight: 15 }
];
const LATER_ONLY_GRANTED_WEIGHTS = [
  { round: 1, weight: 0 },
  { round: 2, weight: 80 },
  { round: 3, weight: 20 }
];
function orderGrantedWeights(orderTypes) {
  const keys = (orderTypes || []).map((order) => order.key);
  if (!keys.length || keys.includes("nmo")) return ORDER_GRANTED_WEIGHTS;
  return keys.includes("pso") ? PSO_ONLY_GRANTED_WEIGHTS : LATER_ONLY_GRANTED_WEIGHTS;
}
const MIN_HEARING_ROUNDS = 2;
const MAX_HEARING_ROUNDS = 4;

const FAMILY_ORDERS = [
  { key: "nmo", label: "Non-Molestation Order" },
  { key: "oo", label: "Occupation Order" }
];

const CHILDREN_ORDERS = [
  { key: "cao", label: "Child Arrangements Order" },
  { key: "pso", label: "Prohibited Steps Order" },
  { key: "sio", label: "Specific Issue Order" }
];

const COURT_OUTCOMES = [
  { key: "granted-without-notice", label: "Order granted without notice" },
  { key: "without-notice-hearing", label: "Court listed a without-notice hearing first" },
  { key: "with-notice-hearing", label: "Court listed a with-notice hearing" }
];

let emails = [];
let activeEmailId = null;

let idCounter = 1;
let nodeCounter = 1;
let folderSortAscending = true;
let c8ReferralCount = 0;
let c8NextInterval = 3;
let suppressNextStateSave = false;
let sessionReferrers = [];
const buildBadge = document.getElementById("buildBadge");
const statusText = document.getElementById("statusText");
const newMatterBtn = document.getElementById("newMatterBtn");
const stageJumpSelect = document.getElementById("stageJumpSelect");
const inboxCount = document.getElementById("inboxCount");
const emptyInbox = document.getElementById("emptyInbox");
const emailRows = document.getElementById("emailRows");
const emptyViewer = document.getElementById("emptyViewer");
const viewerTitle = document.getElementById("viewerTitle");
const sortFoldersBtn = document.getElementById("sortFoldersBtn");
const sortFoldersLabel = document.getElementById("sortFoldersLabel");
const message = document.getElementById("message");
const winScreen = document.getElementById("winScreen");
const messageSubject = document.getElementById("messageSubject");
const messageSubjectMeta = document.getElementById("messageSubjectMeta");
const messageReceived = document.getElementById("messageReceived");
const messageFrom = document.getElementById("messageFrom");
const messageTo = document.getElementById("messageTo");
const casePills = document.getElementById("casePills");
const fakeWarning = document.getElementById("fakeWarning");
const referralBody = document.getElementById("referralBody");
const referralSignoff = document.getElementById("referralSignoff");
buildBadge.textContent = `Build ${APP_BUILD}`;
const incomingBody = document.getElementById("incomingBody");
const introText = document.getElementById("introText");
const attachmentName = document.getElementById("attachmentName");
const zipAttachment = document.getElementById("zipAttachment");
const explorerTree = document.getElementById("explorerTree");
const checklist = document.getElementById("checklist");
const modalBackdrop = document.getElementById("modalBackdrop");
const modalTitle = document.getElementById("modalTitle");
const modalBody = document.getElementById("modalBody");
const modalCloseBtn = document.getElementById("modalCloseBtn");
const clientDraftPane = document.getElementById("clientDraftPane");
const clientDraftSubject = document.getElementById("clientDraftSubject");
const clientDraftSubjectMeta = document.getElementById("clientDraftSubjectMeta");
const clientDraftPills = document.getElementById("clientDraftPills");
const clientDraftFrom = document.getElementById("clientDraftFrom");
const clientDraftTo = document.getElementById("clientDraftTo");
const clientDraftCcLabel = document.getElementById("clientDraftCcLabel");
const clientDraftCc = document.getElementById("clientDraftCc");
const clientDraftBody = document.getElementById("clientDraftBody");
const clientDraftDropZone = document.getElementById("clientDraftDropZone");
const clientDraftDropText = document.getElementById("clientDraftDropText");
const clientDraftAttachments = document.getElementById("clientDraftAttachments");
const clientDraftStatus = document.getElementById("clientDraftStatus");
const clientDraftSendBtn = document.getElementById("clientDraftSendBtn");
const resetAllBtn = document.getElementById("resetAllBtn");
const referralGreeting = document.getElementById("referralGreeting");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function pick(items) {
  return items[randomInt(0, items.length - 1)];
}

function shuffle(items) {
  return [...items].sort(() => Math.random() - 0.5);
}

function pickSome(items, min, max) {
  const count = randomInt(min, Math.min(max, items.length));
  return shuffle(items).slice(0, count);
}

function uniqueId(prefix) {
  return `${prefix}-${idCounter++}`;
}

function generateOrgName(prefix, suffix) {
  return `${pick(DATA.orgPrefixes)}${pick(DATA.orgMidwords).charAt(0).toUpperCase() + pick(DATA.orgMidwords).slice(1)} ${suffix}`;
}

function generateChamberName() {
  return `${pick(DATA.orgPrefixes)}${pick(DATA.orgMidwords).charAt(0).toUpperCase() + pick(DATA.orgMidwords).slice(1)} ${pick(DATA.chambersSuffixes)}`;
}

function generateLawFirmName() {
  return `${pick(DATA.orgPrefixes)}${pick(DATA.orgMidwords).charAt(0).toUpperCase() + pick(DATA.orgMidwords).slice(1)} ${pick(DATA.lawFirmSuffixes)}`;
}

function generateProcessServerName() {
  return `${pick(DATA.orgPrefixes)}${pick(DATA.orgMidwords).charAt(0).toUpperCase() + pick(DATA.orgMidwords).slice(1)} ${pick(DATA.processServerSuffixes)}`;
}

function generateCourtName() {
  return `${pick(DATA.orgPrefixes)}${pick(DATA.orgMidwords).charAt(0).toUpperCase() + pick(DATA.orgMidwords).slice(1)} Family Court`;
}

function generateReferrerName() {
  return `${pick(DATA.referrerPrefixes)} ${pick(DATA.referrerMidwords)} ${pick(DATA.referrerSuffixes)}`;
}

function initSessionReferrers() {
  sessionReferrers = [
    { name: generateReferrerName(), email: "training.referrals@primary-intake.example.test", signoff: "Training Referral Team" },
    { name: generateReferrerName(), email: "training.referrals@secondary-intake.example.test", signoff: "Training Support Team" },
    { name: generateReferrerName(), email: "training.referrals@tertiary-intake.example.test", signoff: "Training Service Team" },
    { name: generateReferrerName(), email: "training.referrals@quaternary-intake.example.test", signoff: "Training Support Desk" }
  ];
}

function newProgressState() {
  return { finishedAt: null };
}

function newNode(type, name, children = []) {
  return {
    id: `node-${nodeCounter++}`,
    type,
    name,
    children,
    sourceParentId: null
  };
}

function progressFor(email) {
  if (!email.workspace.score) email.workspace.score = newProgressState();
  return email.workspace.score;
}

function titleCaseName(first, surname) {
  return `${first} ${surname}`;
}

function initials(name) {
  return name.split(/\s+/).map((part) => part.charAt(0).toUpperCase()).join("");
}

function formatDateShort(date) {
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${day}/${month}/${date.getFullYear()}`;
}

function isoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function nextWorkingDay(date) {
  const next = new Date(date);
  while (next.getDay() === 0 || next.getDay() === 6) next.setDate(next.getDate() + 1);
  return next;
}

function makeHearingDates() {
  const dates = [];
  let hearingDate = nextWorkingDay(addDays(trainingToday(), randomInt(2, 7)));
  for (let index = 0; index < MAX_HEARING_ROUNDS; index += 1) {
    dates.push({
      date: isoDate(hearingDate),
      method: Math.random() < 0.5 ? "Remote hearing (CVP)" : "In-person"
    });
    hearingDate = nextWorkingDay(addDays(hearingDate, index === 0 ? randomInt(7, 21) : randomInt(14, 35)));
  }
  return dates;
}

function birthDate(minYear, maxYear) {
  return new Date(randomInt(minYear, maxYear), randomInt(0, 11), randomInt(1, 28));
}

function fakeAddress() {
  return `${randomInt(4, 88)} ${pick(DATA.streets)}, ${pick(DATA.towns)}, ZZ${randomInt(1, 9)} ${randomInt(1, 9)}AA`;
}

function fakePhone() {
  return `07000 ${randomInt(100000, 999999)}`;
}

function fakeNino() {
  const letters = "ABCEGHJKLMNPRSTWXYZ";
  return `${pick(letters)}${pick(letters)} ${randomInt(10, 99)} ${randomInt(10, 99)} ${randomInt(10, 99)} ${pick(["A", "B", "C", "D"])}`;
}

function fakeSortCode() {
  return `${randomInt(10, 99)}-${randomInt(10, 99)}-${randomInt(10, 99)}`;
}

function fakeAccountNumber() {
  return String(randomInt(10000000, 99999999));
}

function slugify(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function makeChildren(surname) {
  return pickSome(DATA.childFirst, 1, 3).map((first) => ({
    name: titleCaseName(first, surname),
    dob: formatDateShort(birthDate(2014, 2024)),
    pr: pick(["Yes", "No", "Not stated"]),
    sex: pick(["Female", "Male", "Not stated"])
  }));
}

function makeBanks() {
  return pickSome(DATA.banks, 1, 1).map((bank) => {
    const accountNumber = fakeAccountNumber();
    return {
      institution: bank,
      sortCode: fakeSortCode(),
      accountNumber,
      ending: accountNumber.slice(-4),
      amount: `GBP ${randomInt(8, 420)}.${String(randomInt(0, 99)).padStart(2, "0")}`,
      source: pick(["current account", "savings account", "benefit account"])
    };
  });
}

function makeCounselDetails() {
  const first = pick([...DATA.applicantFirst, ...DATA.respondentFirst]);
  const surname = pick(DATA.surnames);
  const chambersName = generateChamberName();
  return {
    counselName: `${pick(DATA.counselTitles)} ${titleCaseName(first, surname)}`,
    chambersName,
    clerkEmail: `clerks@${slugify(chambersName)}.example.test`
  };
}

function makeLawFirmDetails() {
  const solicitorName = titleCaseName(pick([...DATA.applicantFirst, ...DATA.respondentFirst]), pick(DATA.surnames));
  const name = generateLawFirmName();
  return {
    name,
    solicitorName,
    solicitorEmail: `${slugify(solicitorName)}@${slugify(name)}.example.test`,
    phone: `020 ${randomInt(3000, 9999)} ${randomInt(1000, 9999)}`,
    pbaNumber: `PBA 00${randomInt(10000, 99999)}`
  };
}

function makeProcessServerDetails() {
  const name = generateProcessServerName();
  const slug = slugify(name);
  return {
    name,
    serviceEmail: `service@${slug}.example.test`,
    accountsEmail: `accounts@${slug}.example.test`,
    signoff: `${name} Service Desk`
  };
}

function makeCourtDetails() {
  const name = generateCourtName();
  const slug = slugify(name);
  return {
    name,
    email: `family@${slug}.example.test`,
    signoff: `${name} Training Desk`,
    address: `${randomInt(1, 60)} ${pick(DATA.courtStreets)}, ${pick(DATA.towns)}, ZZ${randomInt(1, 9)} ${randomInt(1, 9)}ZZ`,
    caseReference: `ZZ${randomInt(24, 26)}F${String(randomInt(1, 99999)).padStart(5, "0")}`,
    hearingTime: pick(DATA.hearingTimes)
  };
}

function lawFirmDetails(referral) {
  if (!referral.lawFirm) referral.lawFirm = makeLawFirmDetails();
  return referral.lawFirm;
}

function processServerDetails(referral) {
  if (!referral.processServer) referral.processServer = makeProcessServerDetails();
  return referral.processServer;
}

function courtDetails(referral) {
  if (!referral.court) referral.court = makeCourtDetails();
  return referral.court;
}

function makeReferralSource() {
  return pick(sessionReferrers);
}

function referralSourceIsCurrent(source) {
  return Boolean(source && sessionReferrers.some((item) => item.name === source.name));
}

function makeC8Withheld() {
  const fields = pickSome(["address", "phone", "email"], 1, 3);
  return {
    address: fields.includes("address"),
    phone: fields.includes("phone"),
    email: fields.includes("email")
  };
}

function shouldCreateC8(hasChildren) {
  c8ReferralCount += 1;
  const due = c8ReferralCount >= c8NextInterval;
  const opportunistic = Math.random() < (hasChildren ? 0.18 : 0.08);
  if (!due && !opportunistic) return false;
  c8ReferralCount = 0;
  c8NextInterval = randomInt(2, 4);
  return true;
}

function randomMatterKind() {
  const roll = Math.random();
  if (roll < 0.4) return "family";
  if (roll < 0.75) return "children";
  return "combined";
}

function randomCourtOutcome(finalRound = MIN_HEARING_ROUNDS) {
  if (finalRound <= MIN_HEARING_ROUNDS) return "granted-without-notice";
  return Math.random() < 0.5 ? "without-notice-hearing" : "with-notice-hearing";
}

function courtOutcomeMeta(key) {
  return COURT_OUTCOMES.find((outcome) => outcome.key === key) || COURT_OUTCOMES[0];
}

function makeOrders(kind) {
  if (kind === "family") {
    return pickSome(FAMILY_ORDERS, 1, 2);
  }
  if (kind === "children") {
    return pickSome(CHILDREN_ORDERS, 1, 3);
  }
  return [
    ...pickSome(FAMILY_ORDERS, 1, 2),
    ...pickSome(CHILDREN_ORDERS, 1, 3)
  ];
}

function usedApplicantNames() {
  return new Set(emails.map((email) => String(email.referral.applicant || "").toLowerCase()));
}

function uniqueApplicantName(reservedNames) {
  const allNames = shuffle(DATA.applicantFirst.flatMap((first) => DATA.surnames.map((surname) => titleCaseName(first, surname))));
  const available = allNames.find((name) => !reservedNames.has(name.toLowerCase()));
  if (available) return available;
  return titleCaseName(pick(DATA.applicantFirst), pick(DATA.surnames));
}

function generateReferral(kind, reservedNames = new Set()) {
  const source = makeReferralSource();
  const applicant = uniqueApplicantName(reservedNames);
  reservedNames.add(applicant.toLowerCase());
  const surname = applicant.split(" ").slice(-1)[0];
  const respondentSurname = Math.random() < 0.62 ? surname : pick(DATA.surnames);
  const respondent = titleCaseName(pick(DATA.respondentFirst), respondentSurname);
  const orderTypes = makeOrders(kind);
  const hasChildren = orderTypes.some((order) => ["cao", "pso", "sio"].includes(order.key));
  const hasFamily = orderTypes.some((order) => ["nmo", "oo"].includes(order.key));
  const children = hasChildren ? makeChildren(surname) : [];
  const c8 = shouldCreateC8(hasChildren);
  const withheld = c8 ? makeC8Withheld() : { address: false, phone: false, email: false };
  const applicantAddress = fakeAddress();
  const applicantPhone = fakePhone();
  const applicantEmail = `${applicant.toLowerCase().replaceAll(" ", ".")}.training@example.test`;
  const respondentAddress = fakeAddress();
  const banks = makeBanks();
  const property = pick(["Rent", "Rent", "Own", "N/A"]);
  const valueOrMortgage = property === "Own" ? `GBP ${randomInt(126000, 320000)} value / GBP ${randomInt(40000, 190000)} mortgage` : "N/A";
  const rentOrMortgage = property === "N/A" ? "N/A" : `GBP ${randomInt(575, 1325)} pcm`;
  const matterLabel = kind === "combined" ? "children and family matter" : `${kind} matter`;
  const restriction = pick([
    "N/A",
    `Bail conditions until ${formatDateShort(addDays(trainingToday(), randomInt(1, 4) * 30 + randomInt(1, 27)))}`,
    "Previous protective notice expired last month; no current restriction",
    "Police advised applicant to seek urgent protective order"
  ]);
  const referral = {
    id: uniqueId("email"),
    kind,
    matterLabel,
    applicant,
    respondent,
    surname: surname.toUpperCase(),
    initials: initials(applicant),
    source,
    subject: `New Client - ${applicant}`,
    time: new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date()),
    orderTypes,
    hasChildren,
    hasFamily,
    children,
    c8,
    withheld,
    applicantDob: formatDateShort(birthDate(1984, 2002)),
    applicantAddress,
    applicantPhone,
    applicantEmail,
    applicantNino: fakeNino(),
    benefits: pick(DATA.benefits),
    wages: pick(DATA.jobs),
    maintenance: hasChildren ? pick(DATA.maintenance) : "N/A",
    childcare: hasChildren ? pick(DATA.childcare) : "N/A",
    car: pick(DATA.cars),
    banks,
    property,
    valueOrMortgage,
    rentOrMortgage,
    respondentDob: formatDateShort(birthDate(1978, 2001)),
    respondentPhone: fakePhone(),
    respondentAddress,
    respondentWorkAddress: pick(DATA.workPlaces),
    restrictions: restriction,
    lawFirm: makeLawFirmDetails(),
    processServer: makeProcessServerDetails(),
    court: makeCourtDetails(),
    hearingDates: makeHearingDates(),
    counsel: makeCounselDetails()
  };
  referral.orderRequired = orderTypes.map((order) => order.label).join(" and ");
  referral.childrenText = children.length
    ? children.map((child) => `${child.name} DOB ${child.dob} PR ${child.pr} sex ${child.sex}`).join("; ")
    : "N/A";
  referral.furtherInfo = [
    `Fictional ${matterLabel} referral for intake training only.`,
    c8 ? `C8 marker present. Withheld fields: ${withheldSummary(withheld)}.` : "No C8 marker in this fake referral.",
    hasFamily ? "Family Act material includes protective order documents where required." : "",
    hasChildren ? "Children Act material includes child application documents where required." : ""
  ].filter(Boolean).join(" ");
  return {
    referral,
    workspace: {
      score: newProgressState(),
      root: null,
      selectedId: null,
      clientDraft: null,
      drafts: {},
      activeDraftType: "client",
      inboxStage: REFERRAL_STAGE,
      incomingAttachments: [],
      incomingByStage: {},
      closedAs: null,
      clientResponseMode: null,

      statementRevisionsLeft: null,
      statementRevision: 0,
      courtOutcome: null,
      courtHasOrder: null,
      courtNoaIncluded: null,
      hearingRound: 1,
      finalHearingRound: randomFinalHearingRound(orderTypes),
      clientResponsePrinted: false,
      courtApplicationPrinted: false,
      courtResponsePrinted: false,
      counselRequestPrinted: false,
      counselOfferPrinted: false,
      counselBriefPrinted: false,
      hearingCounselDocsSaved: false,
      postHearingOrderSaved: false,
      postHearingOrderClientPrinted: false,
      postHearingProcessServerPrinted: false,
      counselFeeNoteSaved: false,
      counselFeeNoteEmailPrinted: false,
      processServerRequestPrinted: false,
      processServerResponsePrinted: false,
      processServerInvoiceEmailPrinted: false,
      courtBundlePrinted: false,
      bundleCreated: false,
      bundleSections: null,
      lastGuidedStep: null
    }
  };
}

function withheldSummary(withheld) {
  return ["address", "phone", "email"].filter((field) => withheld[field]).join(", ");
}

function displayApplicantField(referral, field, value) {
  if (!referral.c8 || !referral.withheld[field]) return value;
  return "WITHHELD - C8";
}

function fieldLine(label, value = "") {
  const suffix = value ? ` ${escapeHtml(value)}` : "";
  return `<strong>${escapeHtml(label)}:</strong>${suffix}`;
}

function bankDetailsHtml(referral) {
  return referral.banks
    .map((bank) => escapeHtml(`${bank.institution}: sort code ${bank.sortCode}, account ${bank.accountNumber}, amount ${bank.amount}, source ${bank.source}`))
    .join("\n");
}

function introBodyHtml(referral) {
  const e = escapeHtml;

  const has = (v) => {
    const t = String(v == null ? "" : v).trim();
    return t !== "" && !/^(n\/a|none|nil|no\b.*|not stated|not paid|unknown|-|zero)$/i.test(t);
  };
  const sentence = (text) => (text ? `${text}.` : "");
  const joinList = (items) => items.join(", ");

  const who = has(referral.applicantDob) ? `${e(referral.applicant)}, born ${e(referral.applicantDob)},` : e(referral.applicant);
  const asking = has(referral.orderRequired) ? `${who} is asking for help with: ${e(referral.orderRequired)}` : who.replace(/,$/, "");

  const contact = [
    has(referral.applicantAddress) ? `address ${e(displayApplicantField(referral, "address", referral.applicantAddress))}` : "",
    has(referral.applicantPhone) ? `phone ${e(displayApplicantField(referral, "phone", referral.applicantPhone))}` : "",
    has(referral.applicantEmail) ? `email ${e(displayApplicantField(referral, "email", referral.applicantEmail))}` : "",
    has(referral.applicantNino) ? `NI number ${e(referral.applicantNino)}` : "",
  ].filter(Boolean);

  const money = [
    has(referral.benefits) ? `benefits are ${e(referral.benefits)}` : "",
    has(referral.wages) ? `wages ${e(referral.wages)}` : "",
    has(referral.maintenance) ? `maintenance ${e(referral.maintenance)}` : "",
    has(referral.childcare) ? `childcare ${e(referral.childcare)}` : "",
    has(referral.car) ? `a car: ${e(referral.car)}` : "",
  ].filter(Boolean);

  const housing = [
    referral.property === "Own" ? "the client owns the home" : referral.property === "Rent" ? "the home is rented" : "",
    has(referral.valueOrMortgage) ? `valued at, or owing, ${e(referral.valueOrMortgage)}` : "",
    has(referral.rentOrMortgage) ? `with ${e(referral.rentOrMortgage)} going out on it` : "",
  ].filter(Boolean);

  const banks = Array.isArray(referral.banks) && referral.banks.length ? bankDetailsHtml(referral) : "";

  const other = [
    has(referral.respondentDob) ? `born ${e(referral.respondentDob)}` : "",
    has(referral.respondentPhone) ? `phone ${e(referral.respondentPhone)}` : "",
    has(referral.respondentAddress) ? `living at ${e(referral.respondentAddress)}` : "",
    has(referral.respondentWorkAddress) ? `working at ${e(referral.respondentWorkAddress)}` : "",
  ].filter(Boolean);

  const paragraphs = [
    has(referral.furtherInfo) ? e(referral.furtherInfo) : "",
    [sentence(asking), has(referral.restrictions) ? sentence(e(referral.restrictions)) : ""].filter(Boolean).join(" "),
    contact.length ? sentence(`For contact: ${joinList(contact)}`) : "",
    has(referral.childrenText) ? sentence(`Children: ${e(String(referral.childrenText).trim())}`) : "",
    [money.length ? sentence(`On money: ${joinList(money)}`) : "", housing.length ? sentence(`On housing, ${joinList(housing)}`) : ""].filter(Boolean).join(" "),
    banks ? `Accounts held:\n${banks}` : "",
    has(referral.respondent) ? sentence(`The other party is ${[e(referral.respondent), ...other].join(", ")}`) : "",
  ].filter(Boolean);
  return paragraphs.join("\n\n");
}

function rootFolderName(referral) {
  return referral.applicant;
}

function preliminaryName(referral) {
  return `Preliminary-Docs-${referral.surname}`;
}

function clientCorrespondenceName(referral) {
  return `Correspondences-with-Client-${referral.surname}`;
}

function clientResponseHome(referral, documentName) {
  return /^LOA[\s._-]SIGNED/i.test(String(documentName || "")) ? preliminaryName(referral) : clientDocsName(referral);
}

function clientDocsName(referral) {
  return `Client's-Docs-${referral.surname}`;
}

function laaEvidenceName(referral, email = null) {
  return `LAA-Evidence-${referral.surname}`;
}

function invoicesName(referral) {
  return `Invoices-and-Fee-Notes-${referral.surname}`;
}

function courtCorrespondenceName(referral) {
  return `Correspondences-with-Court-${referral.surname}`;
}

function counselCorrespondenceName(referral) {
  return `Correspondences-with-Counsel-${referral.surname}`;
}

const ORDER_TYPE_KEYS = ["nmo", "oo", "cao", "pso", "sio"];

function orderTypeKeys(referral) {
  return referral.orderTypes.map((order) => order.key).filter((key) => ORDER_TYPE_KEYS.includes(key));
}

function courtOrdersFolderName(referral, key) {
  return `Court-Orders-(${key.toUpperCase()})-${referral.surname}`;
}

function courtOrdersFolderNames(referral) {
  const keys = orderTypeKeys(referral);
  return keys.length ? keys.map((key) => courtOrdersFolderName(referral, key)) : [`Court-Orders-${referral.surname}`];
}

function orderKeyForDocument(referral, documentName) {
  const name = String(documentName || "");
  const keys = orderTypeKeys(referral);
  const labelled = name.match(/^SEALED (.+?) - /i);
  if (labelled) {
    const order = referral.orderTypes.find((o) => String(o.label).toLowerCase() === labelled[1].toLowerCase());
    if (order && keys.includes(order.key)) return order.key;
  }
  if (/^SEALED-FL401\b/i.test(name)) return keys.find((key) => ["nmo", "oo"].includes(key)) || null;
  if (/^SEALED-(?:C100|C1A)\b/i.test(name)) return keys.find((key) => ["cao", "pso", "sio"].includes(key)) || null;
  return null;
}

function courtOrdersName(referral, documentName = "") {
  const keys = orderTypeKeys(referral);
  if (!keys.length) return `Court-Orders-${referral.surname}`;
  return courtOrdersFolderName(referral, orderKeyForDocument(referral, documentName) || keys[0]);
}

function processServerName(referral) {
  return `Correspondences-with-Process-Server-${referral.surname}`;
}

function normaliseHearingEntry(entry) {
  if (typeof entry === "string") return { date: entry, method: "In-person" };
  if (entry && typeof entry.date === "string") return { date: entry.date, method: entry.method || "In-person" };
  return null;
}

function hearingDatesFor(referral) {
  if (!referral) {
    if (!fallbackHearingDates) fallbackHearingDates = makeHearingDates();
    return fallbackHearingDates;
  }
  const entries = Array.isArray(referral.hearingDates)
    ? referral.hearingDates.map(normaliseHearingEntry)
    : [];
  referral.hearingDates = entries.length >= MAX_HEARING_ROUNDS && entries.every(Boolean)
    ? entries
    : makeHearingDates();
  return referral.hearingDates;
}

function hearingEntryForRound(referralOrRound = 1, maybeRound = null) {
  const hasReferral = referralOrRound && typeof referralOrRound === "object";
  const referral = hasReferral ? referralOrRound : null;
  const round = hasReferral ? maybeRound : referralOrRound;
  const dates = hearingDatesFor(referral);
  return dates[Math.max(0, Math.min(dates.length - 1, Number(round || 1) - 1))];
}

function hearingDateForRound(referralOrRound = 1, maybeRound = null) {
  return hearingEntryForRound(referralOrRound, maybeRound).date;
}

function currentHearingRound(email) {
  if (!email || !email.workspace) return 1;
  return Math.max(1, Math.min(MAX_HEARING_ROUNDS, Number(email.workspace.hearingRound) || 1));
}

function randomFinalHearingRound(orderTypes) {
  const weights = orderGrantedWeights(orderTypes);
  const total = weights.reduce((sum, item) => sum + item.weight, 0);
  let roll = Math.random() * total;
  for (const item of weights) {
    roll -= item.weight;
    if (roll < 0) return item.round + 1;
  }
  return MIN_HEARING_ROUNDS;
}

function finalHearingRound(email) {
  if (!email || !email.workspace) return MAX_HEARING_ROUNDS;
  const existing = Number(email.workspace.finalHearingRound);
  if (existing >= MIN_HEARING_ROUNDS && existing <= MAX_HEARING_ROUNDS) return existing;
  email.workspace.finalHearingRound = randomFinalHearingRound(email.referral && email.referral.orderTypes);
  return email.workspace.finalHearingRound;
}

function isFinalHearingRound(email) {
  return currentHearingRound(email) >= finalHearingRound(email);
}

function serviceRequired(email) {
  return Boolean(email && (email.workspace.courtHasOrder || email.workspace.postHearingOrderSaved));
}

function hearingDateParts(referralOrRound = 1, maybeRound = null) {
  const [year, month, day] = hearingDateForRound(referralOrRound, maybeRound).split("-");
  return { year, month, day };
}

function hearingDateDisplay(referralOrRound = 1, maybeRound = null) {
  const { year, month, day } = hearingDateParts(referralOrRound, maybeRound);
  return `${day}/${month}/${year}`;
}

function hearingDateSlug(referralOrRound = 1, maybeRound = null) {
  return hearingDateForRound(referralOrRound, maybeRound);
}

function serviceDateSlug(email) {
  const round = currentHearingRound(email);
  const serviceDate = new Date(`${hearingDateForRound(email.referral, round)}T12:00:00`);
  serviceDate.setDate(serviceDate.getDate() - 2);
  const year = serviceDate.getFullYear();
  const month = String(serviceDate.getMonth() + 1).padStart(2, "0");
  const day = String(serviceDate.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isPostHearingServiceCycle(email) {

  return Boolean(email && email.workspace.postHearingOrderSaved);
}

function processServerServiceDateSlug(email) {
  return isPostHearingServiceCycle(email)
    ? hearingDateSlug(email.referral, currentHearingRound(email))
    : serviceDateSlug(email);
}

function hearingFolderName(referral, round = 1) {
  return `${hearingDateSlug(referral, round)} - Hearing`;
}

function currentHearingFolderName(email) {
  return hearingFolderName(email.referral, currentHearingRound(email));
}

function bundleDestinationFolder(email, create = false) {
  if (!email || !email.workspace.root) return null;
  let hearingFolder = childByName(email.workspace.root, currentHearingFolderName(email), "folder");
  if (!hearingFolder && create) {
    hearingFolder = ensureFolder(email.workspace.root, currentHearingFolderName(email));
  }
  return hearingFolder;
}

function hearingBundleObject(email) {
  if (!email) return null;
  return {
    id: "generated-hearing-bundle",
    type: "file",
    name: hearingBundleName(email.referral),
    children: []
  };
}

function currentHearingDateDisplay(email) {
  return hearingDateDisplay(email.referral, currentHearingRound(email));
}

function hearingMethodForRound(referralOrRound = 1, maybeRound = null) {
  return hearingEntryForRound(referralOrRound, maybeRound).method;
}

function currentHearingMethod(email) {
  return hearingMethodForRound(email.referral, currentHearingRound(email));
}

function introPdfName(referral) {
  return `intro.${referral.surname}.pdf`;
}

function onboardingPdfName(referral) {
  return `1[out]onboarding-${referral.surname}.pdf`;
}

function clientResponsePdfName(referral, email = null) {
  return `2[in]client-response-${referral.surname}.pdf`;
}

function courtApplicationPdfName(referral) {
  return `1[out]application-to-court-${referral.surname}.pdf`;
}

function courtOrdersEmailPdfName(referral, email = null) {
  return `2[in]court-orders-${referral.surname}.pdf`;
}

function counselOfferPdfName(referral, email = null) {
  return `2[in]counsel-offer-${referral.surname}.pdf`;
}

function processServerResponsePdfName(email) {
  return `2[in]statement-of-service-email-${processServerServiceDateSlug(email)}-${email.referral.surname}.pdf`;
}

function processServerInvoiceEmailPdfName(email) {
  return `3[in]${slugify(processServerDetails(email.referral).name)}-invoice-email-${processServerServiceDateSlug(email)}-${email.referral.surname}.pdf`;
}

function statementOfServiceName(email) {
  return `Statement of Service - ${processServerServiceDateSlug(email)} - ${email.referral.surname}.pdf`;
}

function processServerInvoiceName(email) {
  return `${processServerDetails(email.referral).name} Invoice - ${processServerServiceDateSlug(email)} - ${email.referral.surname}.pdf`;
}

function hearingBundleName(referral) {
  return `Hearing Bundle - ${referral.surname}.pdf`;
}

function coverPageName(referral, ext = "docx") {
  return `Cover Page - ${referral.surname}.${ext}`;
}

function briefToCounselName(referral) {
  return `Brief to Counsel - ${referral.surname}.docx`;
}

function chronologyName(referral) {
  return `Chronology - ${referral.surname}.docx`;
}

function caseSummaryName(referral) {
  return `Case Summary - ${referral.surname}.docx`;
}

function draftOrderFromCounselName(email) {
  return `Draft Order - ${hearingDateSlug(email.referral, currentHearingRound(email))} - ${email.referral.surname}.docx`;
}

function attendanceNoteFromCounselName(email) {
  return `Attendance Note - ${hearingDateSlug(email.referral, currentHearingRound(email))} - ${email.referral.surname}.docx`;
}

function postHearingSealedOrderName(email) {
  const label = isFinalHearingRound(email) ? "Sealed Final Order" : "Sealed Directions Order";
  return `${label} - ${hearingDateSlug(email.referral, currentHearingRound(email))} - ${email.referral.surname}.pdf`;
}

function counselFeeNoteName(email) {
  return `Counsel Fee Note and Invoice - ${hearingDateSlug(email.referral, currentHearingRound(email))} - ${email.referral.surname}.pdf`;
}

function counselHearingEmailPdfName(email) {
  return `4[in]counsel-hearing-email-${hearingDateSlug(email.referral, currentHearingRound(email))}-${email.referral.surname}.pdf`;
}

function postHearingCourtEmailPdfName(email) {
  return `4[in]sealed-order-email-${hearingDateSlug(email.referral, currentHearingRound(email))}-${email.referral.surname}.pdf`;
}

function counselFeeNoteEmailPdfName(email) {
  return `5[in]counsel-fee-note-${hearingDateSlug(email.referral, currentHearingRound(email))}-${email.referral.surname}.pdf`;
}

function zipName(referral) {
  return "Client files.zip";
}

function c8DocumentName(referral) {
  return `C8.${referral.surname}.pdf`;
}

function requiredFolders(email) {
  const referral = email.referral;
  const attendance = orderTypeKeys(referral).map((key) => `Attendance-Notes-(${key.toUpperCase()})-${referral.surname}`);
  return [
    `Lexcel-Docs-${referral.surname}`,
    clientDocsName(referral),
    clientCorrespondenceName(referral),
    counselCorrespondenceName(referral),
    courtCorrespondenceName(referral),
    `Correspondences-with-LAA-${referral.surname}`,
    `Correspondences-with-Other-Side-${referral.surname}`,
    processServerName(referral),
    invoicesName(referral),
    laaEvidenceName(referral, email),
    `Other-Side's-Docs-${referral.surname}`,
    preliminaryName(referral),
    ...courtOrdersFolderNames(referral),
    ...attendance
  ];
}

function normaliseFolderKey(name) {
  return String(name || "").toLowerCase().replace(/[\s_-]+/g, "");
}

function closestConventionalFolderName(email, typedName) {
  const typedKey = normaliseFolderKey(typedName);
  if (typedKey.length < 4) return null;
  const names = [...requiredFolders(email), currentHearingFolderName(email)];
  return names.find((name) => {
    if (name === typedName) return false;
    const key = normaliseFolderKey(name);
    return key === typedKey || key.includes(typedKey) || typedKey.includes(key);
  }) || null;
}

function packContents(referral) {
  const imageNodes = [
    newNode("image", "Client ID.png"),
    newNode("image", "Respondent photo.png")
  ];

  const evidenceNodes = laaEvidenceNames(referral).map((name) => newNode(/\.png$/i.test(name) ? "image" : "file", name));

  const extraDocs = [];
  if (referral.orderTypes.some((order) => ["nmo", "oo"].includes(order.key))) {
    extraDocs.push(newNode("file", `${ZIP_BUNDLED_DOCUMENT_NAMES.fl401}.${referral.surname}.pdf`));
  }
  if (referral.orderTypes.some((order) => ["cao", "pso", "sio"].includes(order.key))) {
    extraDocs.push(newNode("file", `${ZIP_BUNDLED_DOCUMENT_NAMES.c100}.${referral.surname}.pdf`));
    extraDocs.push(newNode("file", `${ZIP_BUNDLED_DOCUMENT_NAMES.c1a}.${referral.surname}.pdf`));
  }
  if (referral.c8) {

    extraDocs.push(newNode("file", c8DocumentName(referral)));
  }
  return [...imageNodes, ...extraDocs, ...evidenceNodes];
}

function firstName(fullName) {
  return String(fullName || "").split(/\s+/)[0] || fullName;
}

function caseName(referral) {
  return `${referral.applicant} -V- ${referral.respondent}`;
}

function orderLabelForKey(key) {
  const order = [...FAMILY_ORDERS, ...CHILDREN_ORDERS].find((item) => item.key === key);
  return order ? order.label : "Order";
}

function courtApplicationTitle(referral) {
  return `Application for ${orderLabels(referral)} - Without Notice`;
}

function courtApplicationSubject(referral) {
  return `Without Notice | Application for ${orderLabels(referral)} | ${caseName(referral)}`;
}

function orderLabels(referral, keys = null) {
  const wanted = keys ? new Set(keys) : null;
  const labels = referral.orderTypes
    .filter((order) => !wanted || wanted.has(order.key))
    .map((order) => order.label);
  if (labels.length <= 1) return labels[0] || "Order";
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

function orderDocumentNames(referral) {
  return referral.orderTypes
    .filter((order) => ["nmo", "oo", "cao", "pso", "sio"].includes(order.key))
    .map((order) => `SEALED ${order.label} - ${referral.surname}.pdf`);
}

function incomingAttachment(name) {
  return {
    id: uniqueId("attachment"),
    name,
    saved: false
  };
}

function nameKey(name) {
  return String(name || "").toLowerCase().replace(/[\s._-]+/g, " ");
}

function isWitnessStatementKey(key) { return key.includes("witness statement") || /^ws(?: |$)/.test(key); }
function isLetterOfAuthorityKey(key) { return key.includes("letter of authority"); }
function isNoticeOfActingKey(key) { return key.includes("notice of acting"); }
function isDraftOrderKey(key) { return /^draft /.test(key) && (key.includes("order") || /\b(?:nmo|oo|pso)\b/.test(key)); }

function attachmentExt(name) {
  const match = String(name || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : "";
}

function createIncomingNode(attachment) {
  const ext = attachmentExt(attachment.name);
  const type = ["png", "jpg", "jpeg"].includes(ext) ? "image" : "file";
  return newNode(type, attachment.name);
}

function signedWsName(referral, ext = "pdf") {
  return `WS.SIGNED-${referral.surname}.${ext}`;
}

function signedLoaName(referral, ext = "pdf") {
  return `LOA.SIGNED-${referral.surname}.${ext}`;
}

const MAX_STATEMENT_REVISIONS = 3;
const STATEMENT_REVISION_WEIGHTS = [
  { revisions: 0, weight: 60 },
  { revisions: 1, weight: 30 },
  { revisions: 2, weight: 10 }
];

function randomStatementRevisions() {
  const total = STATEMENT_REVISION_WEIGHTS.reduce((sum, item) => sum + item.weight, 0);
  let roll = Math.random() * total;
  for (const item of STATEMENT_REVISION_WEIGHTS) {
    roll -= item.weight;
    if (roll < 0) return Math.min(MAX_STATEMENT_REVISIONS, item.revisions);
  }
  return 1;
}

const STATEMENT_CHANGE_REQUESTS = [
  "Please correct the dates in paragraph 3, they are a week out.",
  "Please add that the last incident was in the evening, not the afternoon.",
  "Please remove the sentence about my employer, I would rather it was not in."
];

function canShowRevision(email) {
  return email.workspace.inboxStage === "client-response" &&
    email.workspace.clientResponseMode === "revision" &&
    !email.workspace.incomingAttachments.length;
}

function ensureClientResponse(email) {
  if (email.workspace.incomingAttachments.length || email.workspace.clientResponseMode) return;
  if (email.workspace.statementRevisionsLeft === null || email.workspace.statementRevisionsLeft === undefined) {
    email.workspace.statementRevisionsLeft = randomStatementRevisions();
  }
  if (email.workspace.statementRevisionsLeft > 0) {

    email.workspace.clientResponseMode = "revision";
    return;
  }
  const mode = pick(["pdf", "docx", "docusign"]);
  email.workspace.clientResponseMode = mode;
  if (mode !== "docusign") {
    email.workspace.incomingAttachments = [
      incomingAttachment(signedWsName(email.referral, mode)),
      incomingAttachment(signedLoaName(email.referral, mode))
    ];
  }
}

function completeDocusignResponse(email) {
  email.workspace.clientResponseMode = "pdf";
  email.workspace.incomingAttachments = [
    incomingAttachment(signedWsName(email.referral, "pdf")),
    incomingAttachment(signedLoaName(email.referral, "pdf"))
  ];
  email.workspace.incomingByStage["client-response"] = email.workspace.incomingAttachments;
}

function courtResponseAttachmentsMatchOutcome(email, attachments) {
  if (!Array.isArray(attachments) || !attachments.length) return false;
  const names = attachments.map((item) => String(item.name || "").toLowerCase());
  const shouldHaveOrder = Boolean(email.workspace.courtHasOrder);
  const hasOrderAttachment = orderDocumentNames(email.referral).some((orderName) =>
    names.includes(orderName.toLowerCase()));
  return hasOrderAttachment === shouldHaveOrder;
}

function ensureCourtResponse(email) {
  const cached = email.workspace.incomingByStage["court-response"];
  if (!email.workspace.courtOutcome) {
    email.workspace.courtOutcome = randomCourtOutcome(finalHearingRound(email));
  }
  email.workspace.courtHasOrder = (email.workspace.courtOutcome === "granted-without-notice");
  email.workspace.courtNoaIncluded = false;
  if (Array.isArray(cached) && cached.length && courtResponseAttachmentsMatchOutcome(email, cached)) {
    email.workspace.incomingAttachments = cached;
    return;
  }
  const referral = email.referral;
  const attachments = [];
  if (referral.hasFamily) attachments.push(incomingAttachment(`SEALED-FL401-${referral.surname}.pdf`));
  if (referral.hasChildren) {
    attachments.push(incomingAttachment(`SEALED-C100-${referral.surname}.pdf`));
    attachments.push(incomingAttachment(`SEALED-C1A-${referral.surname}.pdf`));
  }
  attachments.push(incomingAttachment(`SEALED-${signedWsName(referral, "pdf")}`));
  email.workspace.courtNoaIncluded = false;
  attachments.push(incomingAttachment(`Notice of Hearing - ${referral.surname}.pdf`));
  if (email.workspace.courtHasOrder) {
    orderDocumentNames(referral).forEach((name) => attachments.push(incomingAttachment(name)));
  }
  email.workspace.incomingAttachments = attachments;
  email.workspace.incomingByStage["court-response"] = email.workspace.incomingAttachments;
}

function courtResponseBodyText(email) {
  const outcome = courtOutcomeMeta(email.workspace.courtOutcome);
  if (outcome.key === "granted-without-notice") {
    return "Please see attached the sealed application(s), witness statement, order, and notice of hearing for this matter.";
  }
  if (outcome.key === "without-notice-hearing") {
    return "The court has listed a without-notice hearing before deciding whether to make the order. The respondent is not to be served at this stage.";
  }
  return "The court has listed the application with notice. Arrange service of the sealed papers and notice of hearing.";
}

function ensureProcessServerResponse(email) {
  if (email.workspace.incomingAttachments.length) return;
  email.workspace.incomingAttachments = [
    incomingAttachment(statementOfServiceName(email))
  ];
  email.workspace.incomingByStage["process-server-response"] = email.workspace.incomingAttachments;
}

function processServerInvoiceAttachmentsMatchSupplier(email, attachments) {
  if (!Array.isArray(attachments) || !attachments.length) return false;
  return attachmentNameMatchesExpected(attachments, processServerInvoiceName(email));
}

function counselFeeNoteAttachmentsMatchSupplier(email, attachments) {
  if (!Array.isArray(attachments) || !attachments.length) return false;
  return attachmentNameMatchesExpected(attachments, counselFeeNoteName(email));
}

function attachmentNameMatchesExpected(attachments, expectedName) {
  const expected = String(expectedName || "").toLowerCase();
  if (!expected) return false;
  return attachments.some((item) => String(item.name || "").toLowerCase() === expected);
}

function ensureProcessServerInvoice(email) {
  const cached = email.workspace.incomingByStage["process-server-invoice"];
  if (processServerInvoiceAttachmentsMatchSupplier(email, cached)) {
    email.workspace.incomingAttachments = cached;
    return;
  }
  if (processServerInvoiceAttachmentsMatchSupplier(email, email.workspace.incomingAttachments)) {
    email.workspace.incomingByStage["process-server-invoice"] = email.workspace.incomingAttachments;
    return;
  }
  email.workspace.incomingAttachments = [
    incomingAttachment(processServerInvoiceName(email))
  ];
  email.workspace.incomingByStage["process-server-invoice"] = email.workspace.incomingAttachments;
}

function ensureCounselHearingResponse(email) {
  if (email.workspace.incomingAttachments.length) return;
  email.workspace.incomingAttachments = [
    incomingAttachment(draftOrderFromCounselName(email)),
    incomingAttachment(attendanceNoteFromCounselName(email))
  ];
  email.workspace.incomingByStage["counsel-hearing-response"] = email.workspace.incomingAttachments;
}

function ensurePostHearingSealedOrder(email) {
  if (email.workspace.incomingAttachments.length) return;
  email.workspace.incomingAttachments = [
    incomingAttachment(postHearingSealedOrderName(email))
  ];
  if (!isFinalHearingRound(email)) {
    email.workspace.incomingAttachments.push(incomingAttachment(`Notice of Hearing - ${hearingDateSlug(email.referral, currentHearingRound(email) + 1)} - ${email.referral.surname}.pdf`));
  }
  email.workspace.incomingByStage["post-hearing-sealed-order"] = email.workspace.incomingAttachments;
}

function ensureCounselFeeNote(email) {
  const cached = email.workspace.incomingByStage["counsel-fee-note"];
  if (counselFeeNoteAttachmentsMatchSupplier(email, cached)) {
    email.workspace.incomingAttachments = cached;
    return;
  }
  if (counselFeeNoteAttachmentsMatchSupplier(email, email.workspace.incomingAttachments)) {
    email.workspace.incomingByStage["counsel-fee-note"] = email.workspace.incomingAttachments;
    return;
  }
  email.workspace.incomingAttachments = [
    incomingAttachment(counselFeeNoteName(email))
  ];
  email.workspace.incomingByStage["counsel-fee-note"] = email.workspace.incomingAttachments;
}

function saveIncomingStage(email) {
  const stage = email && email.workspace ? email.workspace.inboxStage || REFERRAL_STAGE : "";
  if (!email || stage === REFERRAL_STAGE) return;
  email.workspace.incomingByStage[stage] = email.workspace.incomingAttachments;
}

function resetIncomingStage(email, stage) {
  if (!email || !email.workspace) return;
  delete email.workspace.incomingByStage[stage];
  if (email.workspace.inboxStage === stage) {
    email.workspace.incomingAttachments = [];
  }
}

function stageAttachments(email, stage) {
  if (!email) return [];
  if ((email.workspace.inboxStage || REFERRAL_STAGE) === stage) {
    return email.workspace.incomingAttachments || [];
  }
  return email.workspace.incomingByStage[stage] || [];
}

function switchIncomingStage(email, stage) {
  if (!email) return;
  saveIncomingStage(email);
  email.workspace.inboxStage = stage;
  Object.values(email.workspace.drafts || {}).forEach((draft) => {
    draft.open = false;
  });
  email.workspace.clientDraft = null;
  if (stage === REFERRAL_STAGE) {
    email.workspace.incomingAttachments = [];
    return;
  }
  email.workspace.incomingAttachments = email.workspace.incomingByStage[stage] || [];
  if (stage === "client-response") {
    ensureClientResponse(email);
  } else if (stage === "court-response") {
    ensureCourtResponse(email);
  } else if (stage === "counsel-response") {
    email.workspace.incomingByStage["counsel-response"] = email.workspace.incomingAttachments;
  } else if (stage === "process-server-response") {
    ensureProcessServerResponse(email);
  } else if (stage === "process-server-invoice") {
    ensureProcessServerInvoice(email);
  } else if (stage === "counsel-hearing-response") {
    ensureCounselHearingResponse(email);
  } else if (stage === "post-hearing-sealed-order") {
    ensurePostHearingSealedOrder(email);
  } else if (stage === "counsel-fee-note") {
    ensureCounselFeeNote(email);
  }
}

function incomingPresentation(email) {
  const stage = email.workspace.inboxStage || REFERRAL_STAGE;
  const firm = lawFirmDetails(email.referral);
  const processServer = processServerDetails(email.referral);
  const court = courtDetails(email.referral);
  if (stage === "client-response") {
    return {
      from: email.referral.applicantEmail,
      to: firm.solicitorEmail,
      subject: "Re: Letter of Authority & Statement for Signature & Approval",
      title: canShowRevision(email) ? "Client wants changes" : "Client reply",
      new: true
    };
  }

  if (stage === "court-response") {
    return {
      from: court.email,
      to: firm.solicitorEmail,
      subject: `Court Orders and Notice of Hearing | ${caseName(email.referral)}`,
      title: "Court email",
      new: !email.workspace.courtResponsePrinted
    };
  }
  if (stage === "counsel-response") {
    return {
      from: email.referral.counsel.clerkEmail,
      to: firm.solicitorEmail,
      subject: `Counsel available | ${caseName(email.referral)}`,
      title: "Counsel offer",
      new: !email.workspace.counselOfferPrinted
    };
  }
  if (stage === "process-server-response") {
    return {
      from: processServer.serviceEmail,
      to: firm.solicitorEmail,
      subject: `Statement of Service | ${caseName(email.referral)}`,
      title: "Statement of Service",
      new: !email.workspace.processServerResponsePrinted
    };
  }
  if (stage === "process-server-invoice") {
    return {
      from: processServer.accountsEmail,
      to: firm.solicitorEmail,
      subject: `Invoice | ${processServer.name} | ${caseName(email.referral)}`,
      title: "Process-server invoice",
      new: !email.workspace.processServerInvoiceEmailPrinted
    };
  }
  if (stage === "counsel-hearing-response") {
    return {
      from: email.referral.counsel.clerkEmail,
      to: firm.solicitorEmail,
      subject: `Draft order and Attendance Note | Hearing ${currentHearingDateDisplay(email)} | ${caseName(email.referral)}`,
      title: "Counsel hearing email",
      new: !email.workspace.hearingCounselDocsSaved
    };
  }
  if (stage === "post-hearing-sealed-order") {
    return {
      from: court.email,
      to: firm.solicitorEmail,
      subject: `${isFinalHearingRound(email) ? "Final Order" : "Sealed Order"} | ${caseName(email.referral)}`,
      title: isFinalHearingRound(email) ? "Final order" : "Sealed order",
      new: !email.workspace.postHearingOrderSaved
    };
  }
  if (stage === "counsel-fee-note") {
    return {
      from: email.referral.counsel.clerkEmail,
      to: firm.solicitorEmail,
      subject: `Fee note and CCMS allocation request | ${caseName(email.referral)}`,
      title: "Counsel fee note",
      new: !email.workspace.counselFeeNoteEmailPrinted
    };
  }
  return {
    from: email.referral.source ? email.referral.source.email : "referrals@example.test",
    to: firm.solicitorEmail,
    subject: email.referral.subject,
    title: "Referral",
    new: false
  };
}

function activeEmail() {
  return emails.find((email) => email.referral.id === activeEmailId) || null;
}

function selectedFolder(email = activeEmail()) {
  if (!email || !email.workspace.root || !email.workspace.selectedId) return null;
  const node = findNode(email.workspace.root, email.workspace.selectedId);
  return node && node.type === "folder" ? node : null;
}

function folderMatches(email, folder, expectedName) {
  if (!email || !folder) return false;
  return folder.name === expectedName;
}

function expectedFolderLabel(email, expectedName) {
  return expectedName;
}

function effectiveFolderName(email, expectedName) {
  return expectedName;
}

function findNode(node, id) {
  if (!node) return null;
  if (node.id === id) return node;
  for (const child of node.children || []) {
    const found = findNode(child, id);
    if (found) return found;
  }
  return null;
}

function findParent(node, childId, parent = null) {
  if (!node) return null;
  if (node.id === childId) return parent;
  for (const child of node.children || []) {
    const found = findParent(child, childId, node);
    if (found) return found;
  }
  return null;
}

function findNodeByType(node, type) {
  if (!node) return null;
  if (node.type === type) return node;
  for (const child of node.children || []) {
    const found = findNodeByType(child, type);
    if (found) return found;
  }
  return null;
}

function treeContainsName(node, name) {
  if (!node) return false;
  if (node.name === name) return true;
  return (node.children || []).some((child) => treeContainsName(child, name));
}

function folderPath(email, nodeId) {
  if (!email || !email.workspace.root || !nodeId) return "No folder selected.";
  const path = [];
  function visit(node) {
    path.push(node.name);
    if (node.id === nodeId) return true;
    for (const child of node.children || []) {
      if (child.type === "folder" && visit(child)) return true;
    }
    path.pop();
    return false;
  }
  return visit(email.workspace.root) ? path.join(" / ") : "No folder selected.";
}

function childByName(folder, name, type = null) {
  return (folder.children || []).find((child) => child.name === name && (!type || child.type === type)) || null;
}

function isProcessServerFolder(email, folder) {
  if (!email || !folder || folder.name !== processServerName(email.referral)) return false;
  const parent = findParent(email.workspace.root, folder.id);
  return Boolean(parent && parent.id === email.workspace.root.id);
}

function ensureFolder(folder, name) {
  const existing = childByName(folder, name, "folder");
  if (existing) return existing;
  const node = newNode("folder", name);
  folder.children.push(node);
  return node;
}

function ensureFile(folder, name, type = "file") {
  const existing = childByName(folder, name, type);
  if (existing) return existing;
  const node = newNode(type, name);
  folder.children.push(node);
  return node;
}

function showModal(title, html) {
  modalTitle.textContent = title;
  modalBody.innerHTML = html;
  modalBackdrop.classList.add("visible");
  modalCloseBtn.focus();
}

function closeModal() {
  modalBackdrop.classList.remove("visible");
}

function previewDocumentByName(name) {
  const email = activeEmail();
  const referral = email ? email.referral : null;
  const title = name || "Document preview";
  showModal(title, `<div class="doc-preview">${escapeHtml(fakeDocumentText(title, referral, email))}</div>`);
}

function fakeDocumentText(name, referral, email = null) {
  const lower = nameKey(name);
  const today = trainingToday().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  const surname = referral ? referral.surname : "TRAINING";
  const court = referral ? courtDetails(referral) : null;
  const courtName = court ? court.name : "the Family Court";
  const caseRef = `Case No: ${court ? court.caseReference : "ZZ26F00000"}`;
  const caseBlock = referral
    ? `In ${courtName}\n${caseRef}\n\nApplicant:  ${referral.applicant}\nRespondent: ${referral.respondent}`
    : `In ${courtName}\n${caseRef}`;
  const firm = referral ? lawFirmDetails(referral) : null;
  const firmName = firm ? firm.name : "the training firm";
  const solicitorName = firm ? firm.solicitorName : "the assigned solicitor";
  const counsel = referral && referral.counsel ? referral.counsel : null;
  const hearingLine = email
    ? `Hearing: ${currentHearingDateDisplay(email)} at ${court ? court.hearingTime : "10:30"} before the training bench`
    : "Hearing: to be listed";
  const amountBase = 180 + (surname.charCodeAt(0) % 8) * 15;
  const money = (value) => `£${value.toFixed(2)}`;
  if (isLetterOfAuthorityKey(lower) || /(?:^| )loa(?: |$)/.test(lower)) {
    return `LETTER OF AUTHORITY\n\n${firmName}\nRe: ${referral ? caseName(referral) : "the training matter"}\n\nI, ${referral ? referral.applicant : "the client"}, authorise ${firmName} to act on my behalf in these proceedings and to correspond with the court, counsel, and third parties in connection with my matter.\n\nSigned: ______________________    Dated: ${today}\n\nTraining use: attach it to the first client email; the signed copy the client returns belongs in Client's-Docs.`;
  }
  if (isWitnessStatementKey(lower)) {
    return `WITNESS STATEMENT OF ${referral ? referral.applicant.toUpperCase() : "THE APPLICANT"}\n\n${caseBlock}\n\n1. I make this statement in support of my application and from my own knowledge.\n2. [The numbered paragraphs set out the applicant's evidence.]\n\nStatement of truth: I believe that the facts stated in this witness statement are true.\n\nSigned: ______________________    Dated: ${today}\n\nTraining use: send to the client for approval and signature; the sealed court copy goes in bundle section D only.`;
  }
  if (lower.includes("fl401")) {
    return `FORM FL401\nApplication for a non-molestation order / occupation order\nFamily Law Act 1996\n\n${caseBlock}\n\nSection 1 - The order(s) applied for: ${referral ? orderLabels(referral, referral.orderTypes.filter((order) => ["nmo", "oo"].includes(order.key)).map((order) => order.key)) : "as set out in the application"}.\nSection 5 - The applicant relies on the attached witness statement.\n\nTraining use: once sealed by the court it belongs in bundle section C.`;
  }
  if (lower.includes("c100")) {
    return `FORM C100\nApplication under the Children Act 1989\n\n${caseBlock}\n\nOrders applied for: ${referral ? orderLabels(referral, referral.orderTypes.filter((order) => ["cao", "pso", "sio"].includes(order.key)).map((order) => order.key)) : "child arrangements as set out in the application"}.\nMIAM: exemption claimed - urgency and risk of harm.\n\nTraining use: once sealed by the court it belongs in bundle section C.`;
  }
  if (lower.includes("c1a")) {
    return `FORM C1A\nAllegations of harm and domestic abuse\n\n${caseBlock}\n\nThis form supplements the C100 and sets out the allegations of harm relied on, the dates involved, and any protective orders sought.\n\nTraining use: once sealed by the court it belongs in bundle section C.`;
  }
  if (/c8/i.test(name)) {
    return `FORM C8\nConfidential contact details\n\n${caseRef}\nApplicant: ${referral ? referral.applicant : "the applicant"}\n\nThe applicant asks the court to withhold the contact details listed in this form from the other party.\n\nTraining use: send it to court when the referral carries a C8 marker, and keep protected details out of respondent-facing material.`;
  }
  if (isDraftOrderKey(lower)) {
    return `DRAFT ORDER\n\n${caseBlock}\n\nUPON the application of the Applicant\nIT IS PROPOSED THAT the Respondent be subject to the restrictions and directions set out in the numbered paragraphs below.\n\n[Draft - not yet approved by the court.]\n\nTraining use: attach it to the court application where the order type needs a draft; the sealed order supersedes it if granted.`;
  }
  if (isNoticeOfActingKey(lower) || /(?:^| )noa(?: |$)/.test(lower)) {
    return `NOTICE OF ACTING\n\n${caseBlock}\n\nTAKE NOTICE that ${firmName} (${solicitorName}) now acts for the Applicant in these proceedings. All future correspondence should be addressed to ${firmName}.\n\nDated: ${today}\n\nTraining use: attach it to the court application and, where service is required, to the process-server email.`;
  }
  if (lower.includes("notice of hearing")) {
    return `NOTICE OF HEARING\n\n${caseBlock}\n\n${hearingLine}\nTime estimate: 1 hour. The parties must attend.\n\nTraining use: save it with the court documents, send it to the client, and place it in bundle section C.`;
  }
  if (lower.includes("statement of service")) {
    return `STATEMENT OF SERVICE\n\n${caseRef}\nRespondent served: ${referral ? referral.respondent : "the respondent"}\nDate of service: ${today}\nMethod: personal service by ${referral ? processServerDetails(referral).name : "the process server"}\nDocuments served: the sealed order and notice of hearing.\n\nI believe that the facts stated in this statement are true.\n\nTraining use: save it in the process-server folder and place it in bundle section E only.`;
  }
  if (lower.includes("invoice") || lower.includes("fee note")) {
    const supplier = lower.includes("fee note")
      ? counsel ? `${counsel.counselName}, ${counsel.chambersName}` : "instructed counsel's chambers"
      : referral ? processServerDetails(referral).name : "the supplier";
    const net = lower.includes("fee note") ? amountBase + 320 : amountBase;
    return `${lower.includes("fee note") ? "FEE NOTE" : "INVOICE"}\n\nFrom: ${supplier}\nTo: ${firmName}\nRe: ${referral ? caseName(referral) : "the training matter"}\nDate: ${today}\n\n${lower.includes("fee note") ? "Hearing fee" : "Personal service of documents"}: ${money(net)}\nVAT (20%): ${money(net * 0.2)}\nTotal: ${money(net * 1.2)}\n\nTraining use: save it in Invoices and Fee Notes. It is not a bundle document.`;
  }
  if (lower.includes("brief to counsel")) {
    return `BRIEF TO COUNSEL\n\n${counsel ? `To: ${counsel.counselName}, ${counsel.chambersName}` : "To: instructed counsel"}\nRe: ${referral ? caseName(referral) : "the training matter"}\n${hearingLine}\n\nCounsel is instructed to appear for the Applicant. Enclosed: case summary, chronology, and the court papers to date.\n\nTraining use: attach it when briefing counsel. It is not one of the A-E bundle documents.`;
  }
  if (lower.includes("cover page")) {
    return `HEARING BUNDLE\n\n${caseBlock}\n\n${hearingLine}\nPrepared by: ${firmName}\n\nTraining use: bundle section A only.`;
  }
  if (lower.includes("case summary")) {
    return `CASE SUMMARY\n\n${caseBlock}\n\nBackground, procedural history, issues for the court, and the orders sought, set out neutrally in under two pages.\n\nTraining use: bundle section B only, with the chronology.`;
  }
  if (lower.includes("chronology")) {
    return `CHRONOLOGY\n\n${referral ? `Re: ${caseName(referral)}` : caseRef}\n\n${today} - Referral received and matter opened by ${firmName}.\n[Dated entries continue through issue, service, and each hearing.]\n\nTraining use: bundle section B only, with the case summary.`;
  }
  if (lower.includes("order")) {
    return `ORDER\n\n${caseBlock}\n\nBEFORE the training bench, UPON hearing the parties,\nIT IS ORDERED that the terms set out in the numbered paragraphs below have effect until further order.\n\n[Court seal applied${court ? ` - ${courtName}` : ""}]\n\nTraining use: save it in Court Orders, send it where required, and place it in bundle section C.`;
  }
  if (lower.includes("mortgage")) {
    return `MORTGAGE STATEMENT\n\nBorrower: ${referral ? referral.applicant : "the client"}\nPeriod: the last three months\n\n[Fictional balance and payments supporting the legal-aid means assessment.]\n\nTraining use: it belongs in LAA-Evidence.`;
  }
  if (lower.includes("income support")) {
    return `INCOME SUPPORT LETTER\n\nName: ${referral ? referral.applicant : "the client"}\n\n[Fictional award letter supporting the legal-aid means assessment.]\n\nTraining use: it belongs in LAA-Evidence.`;
  }
  if (lower.includes("payslip")) {
    return `PAYSLIP\n\nEmployee: ${referral ? referral.applicant : "the client"}\nPeriod: as named in the file\n\n[Fictional earnings and deductions supporting the legal-aid means assessment.]\n\nTraining use: payslips belong in LAA-Evidence.`;
  }
  if (lower.includes("statement") && referral) {
    return `BANK STATEMENT\n\nAccount holder: ${referral.applicant}\nPeriod: as named in the file\n\n[Fictional transactions supporting the legal-aid means assessment.]\n\nTraining use: statements belong in LAA-Evidence.`;
  }
  if (lower.includes("universal credit") || lower.includes("balance")) {
    return `${lower.includes("balance") ? "ACCOUNT BALANCE SCREENSHOT" : "UNIVERSAL CREDIT AWARD SCREENSHOT"}\n\nName: ${referral ? referral.applicant : "the client"}\nCaptured: ${today}\n\nTraining use: means evidence - it belongs in LAA-Evidence.`;
  }
  if (lower.includes("client id")) {
    return `PHOTO ID\n\nName: ${referral ? referral.applicant : "the client"}\nDocument: passport-style identification (fictional).\n\nTraining use: identity evidence for the client file.`;
  }
  if (lower.includes("photo")) {
    return `RESPONDENT PHOTOGRAPH\n\nSubject: ${referral ? referral.respondent : "the respondent"}\n\nTraining use: passed to the process server so the respondent can be identified for personal service.`;
  }
  if (/^\d+(?:\.|\[(?:in|out)\])/.test(String(name || ""))) {
    return `PRINTED EMAIL RECORD\n\n${referral ? `Re: ${caseName(referral)}` : "Re: the training matter"}\nFiled by: ${firmName}\n\nA PDF print of a sent or received email, numbered in filing order for the correspondence folder it lives in.\n\nTraining use: the number prefix shows the print order - keep the sequence unbroken.`;
  }
  return `${name || "DOCUMENT"}\n\n${referral ? `Re: ${caseName(referral)}` : "Fictional training papers."}\n\nTraining use: check the file name and the current step before filing or attaching it.`;
}

const statusLog = [];
const actionLog = [];

function setStatus(messageText) {
  statusText.textContent = messageText;
  statusLog.push({ at: new Date().toISOString(), message: String(messageText || "") });
  if (statusLog.length > 20) statusLog.shift();
}

document.addEventListener("click", (event) => {
  const button = event.target && event.target.closest ? event.target.closest("button, select, [role=\"button\"]") : null;
  if (!button) return;
  const label = (button.id || button.getAttribute("aria-label") || button.textContent || "").trim().slice(0, 60);
  if (!label) return;
  actionLog.push({ at: new Date().toISOString(), action: label });
  if (actionLog.length > 40) actionLog.shift();
}, true);

function addMatterBatch() {
  if (emails.length >= MAX_EMAILS) {
    showModal("Inbox full", `The training inbox already has ${MAX_EMAILS} fake emails. Delete one email or press Reset before generating another referral.`);
    return;
  }
  const timestamp = Date.now();
  const reservedNames = usedApplicantNames();
  const newEmail = generateReferral(randomMatterKind(), reservedNames);
  emails = [newEmail, ...emails];
  activeEmailId = newEmail.referral.id;
  setStatus(`${newEmail.referral.subject} arrived.`);
  render();
}

function deleteEmail(emailId) {
  const timestamp = Date.now();
  const deletedActive = activeEmailId === emailId;
  emails = emails.filter((email) => email.referral.id !== emailId);
  if (deletedActive) {
    activeEmailId = null;
  }
  setStatus(deletedActive ? "The selected fake email and its training state were removed." : "Fake email removed from the training inbox.");
  render();
}

function freshWorkspace(finalRound = randomFinalHearingRound()) {
  return {
    score: newProgressState(),
    root: null,
    selectedId: null,
    clientDraft: null,
    drafts: {},
    activeDraftType: "client",
    inboxStage: REFERRAL_STAGE,
    incomingAttachments: [],
    incomingByStage: {},
    closedAs: null,
    clientResponseMode: null,
    statementRevisionsLeft: null,
    statementRevision: 0,
    courtOutcome: null,
    courtHasOrder: null,
    courtNoaIncluded: null,
    hearingRound: 1,
    finalHearingRound: finalRound,
    clientResponsePrinted: false,
    courtApplicationPrinted: false,
    courtResponsePrinted: false,
    counselRequestPrinted: false,
    counselOfferPrinted: false,
    counselBriefPrinted: false,
    hearingCounselDocsSaved: false,
    postHearingOrderSaved: false,
    postHearingOrderClientPrinted: false,
    postHearingProcessServerPrinted: false,
    counselFeeNoteSaved: false,
    counselFeeNoteEmailPrinted: false,
    processServerRequestPrinted: false,
    processServerResponsePrinted: false,
    processServerInvoiceEmailPrinted: false,
    courtBundlePrinted: false,
    bundleCreated: false,
    bundleSections: null,
    finalComplete: false
  };
}

function clearTrainingStorage() {
  try {
    localStorage.removeItem(STATE_STORAGE_KEY);
  } catch (_error) {

  }
}

function resetAllCases({ clearSavedState = true } = {}) {
  if (clearSavedState) {
    clearTrainingStorage();
    suppressNextStateSave = true;
  }
  emails = [];
  activeEmailId = null;
  idCounter = 1;
  nodeCounter = 1;
  c8ReferralCount = 0;
  c8NextInterval = randomInt(2, 4);
  setStatus("Training state cleared.");
  render();
}

function render() {
  repairReadyCounselHearingStages();
  renderInbox();
  renderMessage();
  renderExplorer();
  renderMatterButtons();
  renderStageJump();
  renderFolderSort();
  saveTrainingState();
}

function renderMatterButtons() {
  document.querySelectorAll(".matter-btn").forEach((button) => {
    button.classList.remove("active");
  });
}

function renderStageJump() {
  const email = activeEmail();
  stageJumpSelect.disabled = !email;
  stageJumpSelect.value = "";
}

function renderFolderSort() {
  sortFoldersBtn.classList.toggle("active", folderSortAscending);
  sortFoldersBtn.setAttribute("aria-pressed", folderSortAscending ? "true" : "false");
  sortFoldersBtn.setAttribute("title", folderSortAscending ? "Reverse folder order" : "Sort folders A-Z");
  sortFoldersLabel.textContent = folderSortAscending ? "A-Z" : "Z-A";
}

function renderInbox() {
  inboxCount.textContent = `${emails.length} / ${MAX_EMAILS}`;
  emptyInbox.style.display = emails.length ? "none" : "block";
  emailRows.innerHTML = emails.map((email) => {
    const referral = email.referral;
    const presentation = incomingPresentation(email);
    const isActive = referral.id === activeEmailId;
    const isFinished = Boolean(progressFor(email).finishedAt);
    const subject = isFinished ? `Completed - ${referral.applicant}` : presentation.subject;
    const c8 = referral.c8 ? '<span class="pill c8">C8</span>' : "";
    const isNew = !isFinished && presentation.new ? '<span class="pill new">NEW</span>' : "";
    const orderText = referral.orderTypes.map((order) => order.label).join(", ");
    return `
      <div class="email-row${isActive ? " active" : ""}${isFinished ? " completed" : ""}" data-email-id="${escapeHtml(referral.id)}">
        <div class="email-main" role="button" tabindex="0" aria-label="Open ${escapeHtml(subject)}">
          <div class="email-from">
            <span>${escapeHtml(presentation.from)}</span>
          </div>
          <div class="email-subject">${escapeHtml(subject)}</div>
          <div class="email-snippet">${escapeHtml(orderText)} ${c8} ${isNew}</div>
        </div>
        <button class="delete-email" type="button" data-delete-email="${escapeHtml(referral.id)}" aria-label="Delete ${escapeHtml(subject)}" title="Delete email"><svg class="icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>
      </div>
    `;
  }).join("");
}

function renderMessage() {
  const email = activeEmail();
  if (!email) {
    viewerTitle.textContent = "Email";
    emptyViewer.style.display = "block";
    message.classList.remove("visible");
    clientDraftPane.classList.remove("visible");
    return;
  }
  const referral = email.referral;
  const presentation = incomingPresentation(email);
  const draftOpen = Boolean(email.workspace.clientDraft && email.workspace.clientDraft.open);
  const showWin = Boolean(progressFor(email).finishedAt) && !draftOpen;
  message.classList.toggle("win-mode", showWin);
  viewerTitle.textContent = draftOpen
    ? `Draft: ${draftConfig(email.workspace.clientDraft.type || "client", email).subject}`
    : showWin
      ? `${referral.applicant} - complete`
      : presentation.title;
  emptyViewer.style.display = "none";
  message.classList.toggle("visible", !draftOpen);
  clientDraftPane.classList.toggle("visible", draftOpen);
  if (showWin) {
    renderWinScreenPane(email);
  } else {
    messageSubject.textContent = presentation.subject;
    messageSubjectMeta.textContent = presentation.subject;
    messageFrom.textContent = presentation.from;
    messageTo.textContent = presentation.to;
    messageReceived.textContent = referral.time || "";
    const kindClass = referral.kind === "family" ? "family" : referral.kind === "children" ? "children" : "combined";
    casePills.innerHTML = `<span class="pill ${kindClass}">${escapeHtml(referral.matterLabel)}</span>${referral.c8 ? ' <span class="pill c8">C8</span>' : ""}${presentation.new ? ' <span class="pill new">NEW</span>' : ""}`;

    fakeWarning.innerHTML = `<strong>Training-only fictional example.</strong> ${escapeHtml(referral.applicant)}, ${escapeHtml(referral.respondent)}, every address, number, account, document, and case fact here is invented.`;
    if ((email.workspace.inboxStage || REFERRAL_STAGE) === REFERRAL_STAGE) {
      referralBody.style.display = "";
      incomingBody.style.display = "none";
      referralSignoff.textContent = referral.source ? referral.source.signoff : "Referral Desk";
      referralGreeting.textContent = `Dear ${lawFirmDetails(referral).name},`;
      introText.innerHTML = introBodyHtml(referral);
      attachmentName.textContent = zipName(referral);
      zipAttachment.setAttribute("aria-label", `Click ${zipName(referral)}, then click the matter folder to place it there, or drag it`);
      zipAttachment.setAttribute("title", "Click to select, then click a destination to place it there (or drag it)");
    } else {
      referralBody.style.display = "none";
      incomingBody.style.display = "";
      renderIncomingBody(email);
    }
  }
  guideTrainingStep(email);
  if (draftOpen) {
    renderClientDraft();
  }
}

function toggleFolderSort() {
  folderSortAscending = !folderSortAscending;
  render();
}

function attachmentRowHtml(attachment) {
  const ext = attachmentExt(attachment.name).toUpperCase() || "FILE";
  const saved = attachment.saved ? " saved" : "";
  const note = attachment.saved ? "Saved into the matter folder." : "Caseflow saves this into the matter folder.";
  return `
    <div class="attachment-row${saved}" data-incoming-attachment-id="${escapeHtml(attachment.id)}">
      <div class="file-icon">${escapeHtml(ext)}</div>
      <div>
        <div class="file-name">${escapeHtml(attachment.name)}</div>
        <div class="file-note">${escapeHtml(note)}</div>
      </div>
      <button class="preview-btn" type="button" data-preview-name="${escapeHtml(attachment.name)}" title="Preview ${escapeHtml(attachment.name)}" aria-label="Preview ${escapeHtml(attachment.name)}"><svg class="icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg></button>
    </div>
  `;
}

function renderIncomingBody(email) {
  const stage = email.workspace.inboxStage;
  const firm = lawFirmDetails(email.referral);
  const processServer = processServerDetails(email.referral);
  const court = courtDetails(email.referral);
  if (stage === "client-response") {
    ensureClientResponse(email);
    const cannotSign = email.workspace.clientResponseMode === "docusign" && !email.workspace.incomingAttachments.length;
    const wantsChanges = canShowRevision(email);
    const change = STATEMENT_CHANGE_REQUESTS[email.workspace.statementRevision % STATEMENT_CHANGE_REQUESTS.length];
    incomingBody.innerHTML = `
      <p>Dear ${escapeHtml(firm.name)},</p>
      ${wantsChanges
        ? `<p>Thank you for the statement. I have read it and I am not happy to sign it yet. ${escapeHtml(change)} Can you send it again once it is changed?</p>`
        : cannotSign
        ? "<p>I am sorry, I cannot sign the documents on my device. Can you please send them through DocuSign?</p>"
        : "<p>Please find attached the signed Letter of Authority and witness statement.</p>"}
      <p>Kind regards,<br>${escapeHtml(email.referral.applicant)}</p>
      ${email.workspace.incomingAttachments.length ? '<div class="section-label">Attachments</div>' : ""}
      ${email.workspace.incomingAttachments.map(attachmentRowHtml).join("")}
    `;
    return;
  }
  if (stage === "court-response") {
    ensureCourtResponse(email);
    incomingBody.innerHTML = `
      <p>Dear Sirs,</p>
      <p>${escapeHtml(courtResponseBodyText(email))}</p>
      <p>Kind regards,<br>${escapeHtml(court.signoff)}</p>
      <div class="section-label">Attachments</div>
      ${email.workspace.incomingAttachments.map(attachmentRowHtml).join("")}
    `;
    return;
  }
  if (stage === "counsel-response") {
    const counsel = email.referral.counsel;
    incomingBody.innerHTML = `
      <p>Dear ${escapeHtml(firm.name)},</p>
      <p>Thank you for your request. ${escapeHtml(counsel.counselName)} of ${escapeHtml(counsel.chambersName)} is available for the hearing on ${escapeHtml(currentHearingDateDisplay(email))} at ${escapeHtml(court.hearingTime)} (${escapeHtml(currentHearingMethod(email))}).</p>
      <p>Please send the papers once the sealed documents and hearing notice are ready.</p>
      <p>Kind regards,<br>${escapeHtml(counsel.chambersName)}</p>
    `;
    return;
  }
  if (stage === "process-server-response") {
    ensureProcessServerResponse(email);
    incomingBody.innerHTML = `
      <p>Dear ${escapeHtml(firm.name)},</p>
      <p>Please find attached the Statement of Service confirming personal service of the sealed order and hearing papers.</p>
      <p>Kind regards,<br>${escapeHtml(processServer.signoff)}</p>
      <div class="section-label">Attachments</div>
      ${email.workspace.incomingAttachments.map(attachmentRowHtml).join("")}
    `;
    return;
  }
  if (stage === "process-server-invoice") {
    ensureProcessServerInvoice(email);
    incomingBody.innerHTML = `
      <p>Dear ${escapeHtml(firm.name)},</p>
      <p>Please find attached our invoice for process-server attendance and service of documents.</p>
      <p>Kind regards,<br>${escapeHtml(processServer.name)}</p>
      <div class="section-label">Attachments</div>
      ${email.workspace.incomingAttachments.map(attachmentRowHtml).join("")}
    `;
    return;
  }
  if (stage === "counsel-hearing-response") {
    ensureCounselHearingResponse(email);
    incomingBody.innerHTML = `
      <p>Dear ${escapeHtml(firm.name)},</p>
      <p>Please find attached Counsel's draft order and Attendance Note following the hearing on ${escapeHtml(currentHearingDateDisplay(email))}.</p>
      <p>Kind regards,<br>${escapeHtml(email.referral.counsel.chambersName)}</p>
      <div class="section-label">Attachments</div>
      ${email.workspace.incomingAttachments.map(attachmentRowHtml).join("")}
    `;
    return;
  }
  if (stage === "post-hearing-sealed-order") {
    ensurePostHearingSealedOrder(email);
    incomingBody.innerHTML = `
      <p>Dear Sirs,</p>
      <p>Please see attached the ${isFinalHearingRound(email) ? "sealed final order" : "sealed order and Notice of Hearing"} following the hearing on ${escapeHtml(currentHearingDateDisplay(email))}.</p>
      <p>Kind regards,<br>${escapeHtml(court.signoff)}</p>
      <div class="section-label">Attachments</div>
      ${email.workspace.incomingAttachments.map(attachmentRowHtml).join("")}
    `;
    return;
  }
  if (stage === "counsel-fee-note") {
    ensureCounselFeeNote(email);
    incomingBody.innerHTML = `
      <p>Dear ${escapeHtml(firm.name)},</p>
      <p>Please find attached Counsel's fee note and invoice. Please arrange CCMS allocation for the hearing attendance.</p>
      <p>Kind regards,<br>${escapeHtml(email.referral.counsel.chambersName)}</p>
      <div class="section-label">Attachments</div>
      ${email.workspace.incomingAttachments.map(attachmentRowHtml).join("")}
    `;
  }
}

function renderExplorer() {
  const email = activeEmail();
  const attention = email && email.workspace.root ? new Set(attentionNodeIds(email)) : new Set();

  const groups = emails.map((item) => {
    const active = Boolean(email) && item.referral.id === email.referral.id;
    const closed = item.workspace.closedAs ? " (closed)" : "";
    const head = `<div class="client-line${active ? " active" : ""}" data-case-email="${escapeHtml(item.referral.id)}" role="button" tabindex="0">${escapeHtml(item.referral.applicant)}${closed}</div>`;
    const body = active && item.workspace.root
      ? sortedChildren(item.workspace.root).map((child) => renderNode(item, child, attention)).join("")
      : "";
    return `<div class="client-group">${head}${body}</div>`;
  }).join("");
  let note = "";
  if (!email) {
    note = '<div class="tree-empty">Select a referral to see where its folder goes.<div class="empty-watermark" aria-hidden="true">Fictional training data only</div></div>';
  } else if (!email.workspace.root) {
    note = '<div class="tree-empty">Caseflow makes the client folder next.<div class="empty-watermark" aria-hidden="true">Fictional training data only</div></div>';
  }
  explorerTree.innerHTML = groups + note;
  if (!email) {
    checklist.innerHTML = "";
    return;
  }
  renderChecklist(email);
}

function collectUnfiled(node, skipId, predicate, out = []) {
  if (!node || node.id === skipId) return out;
  if (predicate(node)) out.push(node);
  (node.children || []).forEach((child) => collectUnfiled(child, skipId, predicate, out));
  return out;
}

function attentionNodeIds(email) {
  if (!email || !email.workspace || !email.workspace.root) return [];
  const root = email.workspace.root;
  const step = nextTrainingStep(email);
  if (step === "print-intro") {
    const prelim = childByName(root, preliminaryName(email.referral), "folder");
    return prelim ? [prelim.id] : [];
  }
  return [];
}

function renderNode(email, node, attentionIds) {
  const isSelected = email.workspace.selectedId === node.id;
  const needsAttention = attentionIds.has(node.id);
  const hasChildren = Boolean((node.children || []).length);
  const childrenHtml = node.collapsed ? "" : sortedChildren(node).map((child) => renderNode(email, child, attentionIds)).join("");
  if (node.type === "folder") {
    const chevron = node.collapsed
      ? '<svg class="icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 6 15 12 9 18"/></svg>'
      : '<svg class="icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';
    const toggleIcon = hasChildren
      ? `<button class="folder-toggle" type="button" data-toggle-folder="${escapeHtml(node.id)}" aria-label="${node.collapsed ? "Expand" : "Collapse"} ${escapeHtml(node.name)}">${chevron}</button>`
      : "<span></span>";
    return `
      <div>
        <div class="node-line folder${isSelected ? " selected" : ""}${node.collapsed ? " collapsed" : ""}${needsAttention ? " attention-action" : ""}" data-node-id="${escapeHtml(node.id)}" data-drop-folder="${escapeHtml(node.id)}" tabindex="0">
          <span class="tag">DIR</span>
          <span class="folder-label">${escapeHtml(node.name)}</span>
          ${toggleIcon}
        </div>
        ${childrenHtml ? `<div class="node-children" data-drop-folder="${escapeHtml(node.id)}">${childrenHtml}</div>` : ""}
      </div>
    `;
  }
  const fileClass = nodeFileClass(node);
  const tag = nodeTag(node);
  const action = nodeAction(node);
  return `
    <div class="node-line ${escapeHtml(fileClass)}${needsAttention ? " attention-action" : ""}" data-node-id="${escapeHtml(node.id)}">
      <span class="tag">${tag}</span>
      <span class="file-label">${escapeHtml(node.name)}</span>
      ${action}
    </div>
  `;
}

function sortedChildren(node) {
  const direction = folderSortAscending ? 1 : -1;
  return [...(node.children || [])].sort((left, right) => (
    direction * String(left.name || "").localeCompare(String(right.name || ""), "en-GB", { sensitivity: "base", numeric: true })
  ));
}

function nodeExtension(node) {
  const match = String(node.name || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : "";
}

function nodeFileClass(node) {
  const ext = nodeExtension(node);
  if (node.type === "zip") return "zip";
  if (node.type === "image" || ["png", "jpg", "jpeg"].includes(ext)) return "image";
  if (ext === "pdf") return "pdf";
  if (["doc", "docx"].includes(ext)) return "doc";
  return "file";
}

function nodeTag(node) {
  const fileClass = nodeFileClass(node);
  if (fileClass === "zip") return "ZIP";
  if (fileClass === "image") return "IMG";
  if (fileClass === "pdf") return "PDF";
  if (fileClass === "doc") return "DOC";
  return "FILE";
}

function nodeAction(node) {
  const fileClass = nodeFileClass(node);
  if (fileClass === "zip") {
    if (node.extracted) return "<span></span>";
    return `<button class="extract-btn" type="button" data-extract-zip="${escapeHtml(node.id)}">Extract</button>`;
  }
  return `<button class="preview-btn" type="button" data-preview-node="${escapeHtml(node.id)}" title="Preview ${escapeHtml(node.name)}" aria-label="Preview ${escapeHtml(node.name)}"><svg class="icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg></button>`;
}

function laaEvidenceNames(referral) {
  const names = [];
  const benefits = String((referral && referral.benefits) || "");
  if (/universal credit/i.test(benefits)) names.push("Universal Credit proof.png");
  else if (/income support/i.test(benefits)) names.push("Income Support letter.pdf");
  const wages = String((referral && referral.wages) || "None").trim();
  if (wages && !/^none$/i.test(wages)) names.push("Payslips (3 months).pdf");
  names.push("Bank statements (3 months).pdf");
  if (referral && referral.property === "Own") names.push("Mortgage statements (1 year).pdf");
  return names;
}

function isLaaEvidenceCandidate(node) {
  const name = String(node.name || "");
  if (node.type === "folder") return /^(?:payslips|statements)$/i.test(name);
  return /^(?:universal credit proof|universal credit|income support letter|payslips \(3 months\)|bank statements \(3 months\)|mortgage statements \(1 year\))(?:\.|$)/i.test(name);
}

function isDraftAttachmentCandidate(node) {
  const ext = nodeExtension(node);
  const name = nameKey(node.name);
  return ["doc", "docx", "pdf"].includes(ext) && (
    name.includes("hearing bundle") ||
    name.includes("brief to counsel") ||
    name.includes("chronology") ||
    name.includes("case summary") ||
    isLetterOfAuthorityKey(name) ||
    isWitnessStatementKey(name) ||
    name.includes("loa signed") ||
    name.includes("fl401") ||
    name.includes("c100") ||
    name.includes("c1a") ||
    /^c8\b/.test(name) ||
    isNoticeOfActingKey(name) ||
    name.includes("draft ") ||
    name.startsWith("sealed ") ||
    name.includes("statement of service") ||
    name.includes("notice of hearing") ||
    name.includes("order")
  );
}

function isBundleCandidate(node) {
  if (!node) return false;
  if (node.type === "zip") return false;
  if (node.type === "folder") return isLaaEvidenceCandidate(node);
  return ["file", "image"].includes(node.type) || Boolean(nodeExtension(node));
}

function progressMilestones(email) {
  const state = validationState(email);
  const initialServiceRequired = Boolean(email.workspace.courtHasOrder);
  const complete = state.finalComplete;
  return [
    ["Matter opened", complete || state.rootExists],
    ["Initial pack filed", complete || (state.introSaved && state.docsExtracted)],
    ["Funding evidence sorted", complete || state.laaEvidenceFiled],
    ["Client documents returned", complete || (state.signedDocsFiled && state.clientResponsePrinted)],
    ["Court application sent", complete || state.courtApplicationPrinted],
    ["Court documents saved", complete || (state.courtAttachmentsFiled && state.courtResponsePrinted)],
    [initialServiceRequired ? "Service step handled" : "Initial service held", complete || !initialServiceRequired || (state.processServerRequestPrinted && state.processServerResponsePrinted && email.workspace.processServerInvoiceEmailPrinted && state.processServerInvoiceSaved)],
    ["Court bundle request sent", complete || state.courtBundlePrinted],
    ["Final order cycle complete", complete]
  ];
}

function progressPercent(email) {
  const milestones = progressMilestones(email);
  const done = milestones.filter((item) => item[1]).length;
  return {
    done,
    total: milestones.length,
    percent: Math.round((done / milestones.length) * 100)
  };
}

function saveTrainingState() {
  if (suppressNextStateSave) {
    suppressNextStateSave = false;
    return;
  }
  try {
    localStorage.setItem(STATE_STORAGE_KEY, JSON.stringify({
      emails,
      activeEmailId,
      idCounter,
      nodeCounter,
      folderSortAscending,
      c8ReferralCount,
      c8NextInterval
    }));
  } catch (_error) {

  }
}

function loadTrainingState() {
  initSessionReferrers();
  try {
    const saved = JSON.parse(localStorage.getItem(STATE_STORAGE_KEY) || "{}");
    if (!saved || !Array.isArray(saved.emails)) return;
    emails = saved.emails.map(normaliseSavedEmail).filter(Boolean);
    activeEmailId = emails.some((email) => email.referral.id === saved.activeEmailId)
      ? saved.activeEmailId
      : (emails[0] ? emails[0].referral.id : null);
    idCounter = Math.max(1, Number(saved.idCounter) || idCounter);
    nodeCounter = Math.max(1, Number(saved.nodeCounter) || nodeCounter);
    folderSortAscending = typeof saved.folderSortAscending === "boolean" ? saved.folderSortAscending : folderSortAscending;
    c8ReferralCount = Math.max(0, Number(saved.c8ReferralCount) || 0);
    c8NextInterval = Math.max(2, Math.min(4, Number(saved.c8NextInterval) || 3));
  } catch (_error) {
    emails = [];
    activeEmailId = null;
  }
}

function normaliseSavedEmail(email) {
  if (!email || !email.referral || !email.workspace) return null;
  if (!referralSourceIsCurrent(email.referral.source)) {
    email.referral.source = makeReferralSource();
  }
  email.referral.subject = `New client - ${email.referral.applicant}`;
  if (!email.referral.source.signoff) {
    email.referral.source.signoff = `${email.referral.source.name} Referral Desk`;
  }
  lawFirmDetails(email.referral);
  processServerDetails(email.referral);
  courtDetails(email.referral);
  hearingDatesFor(email.referral);
  const finalRound = typeof email.workspace.finalHearingRound !== "undefined" ? email.workspace.finalHearingRound : randomFinalHearingRound(email.referral.orderTypes);
  const defaults = freshWorkspace(finalRound);
  email.workspace = {
    ...defaults,
    ...email.workspace,
    score: { ...defaults.score, ...(email.workspace.score || {}) },
    drafts: { ...defaults.drafts, ...(email.workspace.drafts || {}) },
    incomingByStage: { ...defaults.incomingByStage, ...(email.workspace.incomingByStage || {}) },
    incomingAttachments: Array.isArray(email.workspace.incomingAttachments) ? email.workspace.incomingAttachments : defaults.incomingAttachments
  };
  if (!STAGE_ORDER.includes(email.workspace.inboxStage)) {
    email.workspace.inboxStage = REFERRAL_STAGE;
  }

  if (email.referral.c8 && email.workspace.root) {
    const zip = findNodeByType(email.workspace.root, "zip");
    if (zip && zip.extracted && !treeContainsName(email.workspace.root, c8DocumentName(email.referral))) {
      const zipParent = findParent(email.workspace.root, zip.id) || email.workspace.root;
      ensureFile(zipParent, c8DocumentName(email.referral), "file");
    }
  }

  repairReadyCounselHearingStage(email);

  if (email.workspace.inboxStage === "process-server-invoice" &&
      email.workspace.processServerInvoiceEmailPrinted &&
      processServerInvoiceSaved(email) &&
      !initialServicePending(email)) {
    email.workspace.inboxStage = "court-response";
    email.workspace.incomingAttachments = email.workspace.incomingByStage["court-response"] || [];
    email.workspace.lastGuidedStep = null;
  }
  ensureBundleSections(email);
  return email;
}

function renderChecklist(email) {
  const progress = progressPercent(email);
  checklist.innerHTML = `
    <div class="progress-card">
      <div class="progress-head">
        <span>Progress</span>
        <span>${progress.percent}%</span>
      </div>
      <div class="progress-track" aria-label="Matter progress">
        <div class="progress-fill" style="width:${progress.percent}%"></div>
      </div>
      <div>${progress.done} of ${progress.total} stages complete</div>
    </div>
  `;
}

function ensureBundleSections(email) {
  if (!email.workspace.bundleSections) {
    email.workspace.bundleSections = {
      cover: [],
      summary: [],
      applications: [],
      statements: [],
      service: []
    };
  }
  const defaults = { cover: [], summary: [], applications: [], statements: [], service: [] };
  ["cover", "summary", "applications", "statements", "service"].forEach((key) => {
    if (!Array.isArray(email.workspace.bundleSections[key])) {
      email.workspace.bundleSections[key] = defaults[key];
    }
  });
  return email.workspace.bundleSections;
}

function bundleSectionReady(email, key) {
  const sections = ensureBundleSections(email);
  const items = sections[key] || [];
  if (key === "cover") {
    return items.some((item) => /^Cover Page\b/i.test(item.name || ""));
  }
  if (key === "summary") {
    return items.some((item) => /^Case Summary\b/i.test(item.name || "")) &&
      items.some((item) => /^Chronology\b/i.test(item.name || ""));
  }
  if (key === "applications") {
    return bundleApplicationsReady(email, items);
  }
  if (key === "statements") {
    return items.some((item) => /^sealed-ws\.signed\b|^sealed witness statement\b/i.test(item.name || ""));
  }
  if (key === "service") {
    if (!serviceRequired(email)) return true;
    return items.some((item) => /statement of service/i.test(item.name || ""));
  }
  return Boolean(items.length);
}

function bundleReady(email) {
  if (!email || !email.workspace.root) return false;
  return BUNDLE_SECTIONS.every((section) => bundleSectionReady(email, section.key));
}

function isBundleApplicationName(name) {
  return /^SEALED-(?:FL401|C100|C1A)\b/i.test(String(name || ""));
}

function isBundleOrderName(name) {
  return /^SEALED .* Order\b/i.test(String(name || ""));
}

function isBundleNoticeName(name) {
  return /^Notice of Hearing\b/i.test(String(name || ""));
}

function bundleApplicationsReady(email, items) {
  const names = items.map((item) => String(item.name || "").toLowerCase());
  const has = (pattern) => names.some((name) => pattern.test(name));
  const familyOk = !email.referral.hasFamily || has(/^sealed-fl401\b/);
  const childrenOk = !email.referral.hasChildren || (has(/^sealed-c100\b/) && has(/^sealed-c1a\b/));
  const noticeOk = has(/^notice of hearing\b/);
  const orderOk = !email.workspace.courtHasOrder || orderDocumentNames(email.referral).every((orderName) => (
    names.includes(orderName.toLowerCase())
  ));
  return familyOk && childrenOk && noticeOk && orderOk;
}

function bundleItemSortWeight(sectionKey, item) {
  if (sectionKey !== "applications") return 0;
  if (isBundleApplicationName(item.name)) return 0;
  if (isBundleNoticeName(item.name)) return 1;
  if (isBundleOrderName(item.name)) return 2;
  return 3;
}

function normaliseBundleSection(sectionKey, items) {
  return [...(items || [])].sort((left, right) => {
    const weight = bundleItemSortWeight(sectionKey, left) - bundleItemSortWeight(sectionKey, right);
    if (weight) return weight;
    return String(left.name || "").localeCompare(String(right.name || ""), "en-GB", { sensitivity: "base", numeric: true });
  });
}

function hearingPreparationDocsReady(email) {
  return bundleReady(email);
}

function arriveCounselHearingIfReady(email) {

  if (!email.workspace.courtBundlePrinted || !email.workspace.bundleCreated) return false;
  if (email.workspace.hearingCounselDocsSaved || email.workspace.postHearingOrderSaved) return false;
  if (email.workspace.inboxStage === "counsel-hearing-response") return false;
  resetIncomingStage(email, "counsel-hearing-response");
  switchIncomingStage(email, "counsel-hearing-response");
  return true;
}

function repairReadyCounselHearingStage(email) {
  if (!email || !email.workspace) return false;
  const repaired = arriveCounselHearingIfReady(email);
  if (repaired) {
    email.workspace.lastGuidedStep = null;
  }
  return repaired;
}

function repairReadyCounselHearingStages() {
  emails.forEach((email) => repairReadyCounselHearingStage(email));
}

function saveHearingBundleToFolder(email, targetFolder = null) {
  if (!email || !email.workspace.root) return false;
  if (!bundleReady(email)) {
    showModal("Bundle incomplete", "Complete each bundle section before creating the bundle.");
    return false;
  }
  const destination = ensureFolder(email.workspace.root, currentHearingFolderName(email));
  ensureFile(destination, hearingBundleName(email.referral), "file");
  email.workspace.bundleCreated = true;
  email.workspace.selectedId = destination.id;
  if (arriveCounselHearingIfReady(email)) {
    setStatus(`${hearingBundleName(email.referral)} saved into ${destination.name}. Counsel's hearing email has arrived.`);
  } else {
    setStatus(`${hearingBundleName(email.referral)} saved into ${destination.name}.`);
  }
  return true;
}

function clientDraftFor(email, type = null) {
  const draftType = type || email.workspace.activeDraftType || (email.workspace.clientDraft && email.workspace.clientDraft.type) || "client";
  if (!email.workspace.drafts) {
    email.workspace.drafts = {};
  }
  const validDraftType = String(draftType || "").trim() || "client";
  if (!email.workspace.drafts[validDraftType]) {
    email.workspace.drafts[validDraftType] = {
      type: validDraftType,
      attachments: [],
      sent: false,
      printed: false,
      open: false
    };
  }
  email.workspace.clientDraft = email.workspace.drafts[validDraftType];
  return email.workspace.clientDraft;
}

function openSavedDraft(email, type) {
  email.workspace.activeDraftType = type;
  Object.values(email.workspace.drafts || {}).forEach((draft) => {
    draft.open = false;
  });
  const draft = clientDraftFor(email, type);
  draft.open = true;
  return draft;
}

function draftHas(draft, pattern) {
  return draft.attachments.some((item) => pattern.test(item.name));
}

function draftKind(type) {
  return String(type || "client").replace(/-\d+$/u, "");
}

function hearingDraftType(email, base) {
  return `${base}-${currentHearingRound(email)}`;
}

function clientDraftReady(draft) {
  const type = draftKind(draft.type || "client");
  if (type === "client") {
    return draftHas(draft, /letter[\s._-]of[\s._-]authority/i) && draftHas(draft, /witness[\s._-]statement|^ws[\s._-]/i);
  }
  if (type === "docusign" || type === "revision") return true;
  if (type === "court") {
    const email = activeEmail();
    if (!email) return false;
    const referral = email.referral;
    const needsDraftOrder = referral.orderTypes.some((order) => ["nmo", "oo", "pso"].includes(order.key));
    const hasDraftOrder = !needsDraftOrder || draftHas(draft, /^draft[\s._-](?:.*order|nmo|oo|pso)\b/i);
    const hasNoa = draftHas(draft, /notice[\s._-]of[\s._-]acting/i);
    const hasSignedWs = draftHas(draft, /^ws[\s._-]|witness[\s._-]statement/i);
    const hasFamilyApplication = !referral.hasFamily || draftHas(draft, /fl401/i);
    const hasChildrenApplications = !referral.hasChildren || (draftHas(draft, /c100/i) && draftHas(draft, /c1a/i));
    const hasC8 = !referral.c8 || draftHas(draft, /^c8\b/i);
    return hasDraftOrder && hasNoa && hasSignedWs && hasFamilyApplication && hasChildrenApplications && hasC8;
  }
  if (type === "order-client") {
    const email = activeEmail();
    if (!email) return false;
    const needsOrder = Boolean(email.workspace.courtHasOrder);
    return draftHas(draft, /notice of hearing/i) && (!needsOrder || draftHas(draft, /order/i));
  }
  if (type === "process-server") {
    const email = activeEmail();
    if (!email) return false;
    return courtAttachmentsSaved(email) && processServerRequiredNames(email, type).every((name) => (
      draft.attachments.some((item) => item.name.toLowerCase() === name.toLowerCase() || (
        isNoticeOfActingKey(nameKey(name)) && isNoticeOfActingKey(nameKey(item.name))
      ))
    ));
  }
  if (type === "post-process-server") {
    const email = activeEmail();
    if (!email) return false;
    return postHearingCourtAttachmentNames(email).every((name) => (
      draft.attachments.some((item) => item.name.toLowerCase() === name.toLowerCase())
    ));
  }
  if (type === "counsel") return true;
  if (type === "brief-counsel") {
    const email = activeEmail();
    if (!email) return false;
    return draftHas(draft, new RegExp(`^${escapeRegExp(briefToCounselName(email.referral))}$`, "i")) &&
      draftHas(draft, /chronology/i) &&
      draftHas(draft, /case summary/i);
  }
  if (type === "court-bundle") {
    return true;
  }
  if (type === "post-order-client") {
    const email = activeEmail();
    return Boolean(email && postHearingCourtAttachmentNames(email).every((name) => (
      draft.attachments.some((item) => item.name.toLowerCase() === name.toLowerCase())
    )));
  }
  return false;
}

function draftAttachmentKind(node) {
  const name = nameKey(node.name);
  if (name.includes("hearing bundle")) return "bundle";
  if (name.includes("brief to counsel")) return "brief";
  if (name.includes("chronology")) return "chronology";
  if (name.includes("case summary")) return "case-summary";
  if (isLetterOfAuthorityKey(name)) return "letter";
  if (name.includes("ws signed")) return "signed-witness";
  if (isWitnessStatementKey(name)) return "witness";
  if (name.includes("loa signed")) return "signed-loa";
  if (name.includes("notice of hearing")) return "hearing";
  if (isNoticeOfActingKey(name)) return "noa";
  if (name.startsWith("sealed ")) return "sealed";
  if (isDraftOrderKey(name) || name.includes("order")) return "order";
  if (name.includes("fl401") || name.includes("c100") || name.includes("c1a") || /^c8\b/.test(name)) return "application";
  return "";
}

function draftConfig(type, email) {
  type = draftKind(type || "client");
  const referral = email.referral;
  const firm = lawFirmDetails(referral);
  const processServer = processServerDetails(referral);
  const court = courtDetails(referral);
  if (type === "revision") {
    const round = email.workspace.statementRevision + 1;
    return {
      subject: `Revised statement for approval (changes ${round})`,
      to: referral.applicantEmail,
      dropText: "No attachments needed in this training step.",
      body: `<p>Dear ${escapeHtml(referral.applicant)},</p><p>Thank you for your comments. We have changed your witness statement as you asked and attach the new version. Please read it again and, if you are happy, sign and return it with the Letter of Authority.</p><p>Kind regards,<br>${escapeHtml(firm.name)}</p>`,
      printFolder: clientCorrespondenceName(referral),
      printName: `3[out]revised-statement-${round}-${referral.surname}.pdf`
    };
  }
  if (type === "docusign") {
    return {
      subject: "DocuSign - Letter of Authority and Statement",
      to: referral.applicantEmail,
      dropText: "No attachments needed in this training step.",
      body: `<p>Dear ${escapeHtml(referral.applicant)},</p><p>We will send the Letter of Authority and your witness statement to you by DocuSign for electronic signature.</p><p>Kind regards,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>`,
      printFolder: clientCorrespondenceName(referral),
      printName: `3[out]docusign-${referral.surname}.pdf`
    };
  }
  if (type === "court") {
    const needsDraftOrder = referral.orderTypes.some((order) => ["nmo", "oo", "pso"].includes(order.key));
    return {
      subject: courtApplicationSubject(referral),
      to: court.email,
      dropText: `${needsDraftOrder ? "Attach the draft order, " : "Attach "}Notice of Acting, applications, signed witness statement, and C8 if present.`,
      body: courtDraftBody(referral),
      printFolder: courtCorrespondenceName(referral),
      printName: courtApplicationPdfName(referral)
    };
  }
  if (type === "order-client") {
    return {
      subject: `${email.workspace.courtHasOrder ? "Court Order and Notice of Hearing" : "Notice of Hearing"} | ${caseName(referral)}`,
      to: referral.applicantEmail,
      dropText: email.workspace.courtHasOrder ? "Attach only the order documents and Notice of Hearing." : "Attach the Notice of Hearing and sealed court papers.",
      body: orderToClientBody(referral, email),
      printFolder: clientCorrespondenceName(referral),
      printName: `3[out]order-to-client-${referral.surname}.pdf`
    };
  }
  if (type === "process-server") {
    return {
      subject: `Court papers for Personal Service | ${caseName(referral)}`,
      to: processServer.serviceEmail,
      dropText: "Attach every court attachment, plus Notice of Acting from templates or saved papers.",
      body: processServerBody(referral),
      printFolder: processServerName(referral),
      printName: `1[out]process-server-${referral.surname}.pdf`
    };
  }
  if (type === "post-process-server") {
    const isFinal = isFinalHearingRound(email);
      return {
      subject: `${isFinal ? "Final Order" : "Sealed Order"} for Personal Service | ${caseName(referral)}`,
      to: processServer.serviceEmail,
      dropText: isFinal ? `Attach ${postHearingSealedOrderName(email)} from Court Orders.` : "Attach the sealed order and next Notice of Hearing.",
      body: processServerBody(referral, email),
      printFolder: processServerName(referral),
      printName: `${isFinal ? "1" : "2"}[out]${isFinal ? "final" : "sealed"}-order-process-server-${hearingDateSlug(referral, currentHearingRound(email))}-${referral.surname}.pdf`
    };
  }
  if (type === "counsel") {
    return {
      subject: `Request for Counsel | Hearing on ${currentHearingDateDisplay(email)} at ${court.hearingTime} | ${caseName(referral)}`,
      to: referral.counsel.clerkEmail,
      dropText: "No attachments needed for the availability request.",
      body: counselRequestBody(referral, email),
      printFolder: counselCorrespondenceName(referral),
      printName: `1[out]request-counsel-${referral.surname}.pdf`
    };
  }
  if (type === "brief-counsel") {
    return {
      subject: `Brief to Counsel | Hearing on ${currentHearingDateDisplay(email)} at ${court.hearingTime} | ${caseName(referral)}`,
      to: referral.counsel.clerkEmail,
      dropText: "Attach the Brief to Counsel, chronology, and case summary.",
      body: briefToCounselBody(referral, email),
      printFolder: counselCorrespondenceName(referral),
      printName: `3[out]brief-to-counsel-${referral.surname}.pdf`
    };
  }
  if (type === "court-bundle") {
    return {
      subject: `Bundle Request for Hearing on ${currentHearingDateDisplay(email)} | ${caseName(referral)}`,
      to: court.email,
      bcc: referral.counsel.clerkEmail,
      dropText: "No attachments needed for this bundle request.",
      body: courtBundleBody(referral, email),
      printFolder: courtCorrespondenceName(referral),
      printName: `3[out]bundle-request-to-court-${hearingDateSlug(referral, currentHearingRound(email))}-${referral.surname}.pdf`
    };
  }
  if (type === "post-order-client") {
    const isFinal = isFinalHearingRound(email);
    return {
      subject: `${isFinal ? "Final Order" : "Sealed Order"} | ${caseName(referral)}`,
      to: referral.applicantEmail,
      dropText: isFinal ? `Attach ${postHearingSealedOrderName(email)} from Court Orders.` : "Attach the sealed order and next Notice of Hearing.",
      body: isFinal ? finalOrderEmailBody(referral, email) : orderToClientBody(referral, email),
      printFolder: clientCorrespondenceName(referral),
      printName: `${isFinal ? "1" : "4"}[out]${isFinal ? "final-order" : "sealed-order"}-to-client-${hearingDateSlug(referral, currentHearingRound(email))}-${referral.surname}.pdf`
    };
  }
  return {
    subject: "Letter of Authority & Statement for Signature & Approval",
    to: referral.applicantEmail,
    dropText: "Attach the Letter of Authority and client witness statement here.",
    body: loaEmailBody(referral),
    printFolder: clientCorrespondenceName(referral),
    printName: onboardingPdfName(referral)
  };
}

function renderClientDraft() {
  const email = activeEmail();
  if (!email) return;
  const draft = clientDraftFor(email);
  const config = draftConfig(draft.type || "client", email);
  const kindClass = email.referral.kind === "family" ? "family" : email.referral.kind === "children" ? "children" : "combined";
  clientDraftSubject.textContent = config.subject;
  clientDraftSubjectMeta.textContent = config.subject;
  clientDraftPills.innerHTML = `<span class="pill ${kindClass}">${escapeHtml(email.referral.matterLabel)}</span>${email.referral.c8 ? ' <span class="pill c8">C8</span>' : ""}`;
  clientDraftFrom.textContent = lawFirmDetails(email.referral).solicitorEmail;
  clientDraftTo.textContent = config.to;
  const cc = config.bcc || config.cc || "";
  clientDraftCcLabel.textContent = config.bcc ? "Bcc" : "Cc";
  clientDraftCcLabel.style.display = cc ? "" : "none";
  clientDraftCc.style.display = cc ? "" : "none";
  clientDraftCc.textContent = cc;
  clientDraftBody.innerHTML = config.body;
  clientDraftAttachments.innerHTML = draft.attachments.length
    ? draft.attachments.map((item) => `<div class="draft-attachment"><span>${escapeHtml(item.name)}</span><span>${escapeHtml(String(item.ext || "file").toUpperCase())}</span></div>`).join("")
    : "";
  const ready = clientDraftReady(draft);
  clientDraftDropText.textContent = config.dropText;
  clientDraftStatus.textContent = ready
    ? `Ready to send. After sending, select ${expectedFolderLabel(email, config.printFolder)} and print the email as PDF.`
    : config.dropText;
  clientDraftSendBtn.textContent = ready || (draft.type || "client") !== "client" ? "Send" : "Email client";
  clientDraftSendBtn.disabled = !ready || draft.sent;
  if (draft.sent) {
    clientDraftSendBtn.textContent = "Sent";
  }
}

function openDraft(type) {
  const email = activeEmail();
  if (!email) return;
  openSavedDraft(email, type);
  render();
}

function stageFromJump(stage) {
  if (stage === "client-draft") return REFERRAL_STAGE;
  if (stage === "court-draft") return "client-response";
  return stage || REFERRAL_STAGE;
}

function resetStageForJump(email, jumpStage) {
  const target = stageFromJump(jumpStage);
  const targetIndex = STAGE_ORDER.indexOf(target);
  const stagesToClear = targetIndex >= 0 ? STAGE_ORDER.slice(targetIndex) : [];
  stagesToClear.forEach((stage) => resetIncomingStage(email, stage));
  email.workspace.incomingAttachments = [];
  email.workspace.inboxStage = target === REFERRAL_STAGE ? REFERRAL_STAGE : target;
  Object.values(email.workspace.drafts || {}).forEach((draft) => {
    draft.open = false;
  });
  if (targetIndex <= STAGE_ORDER.indexOf("client-response")) {
    email.workspace.clientResponseMode = null;
    email.workspace.clientResponsePrinted = false;
  }
  if (targetIndex < STAGE_ORDER.indexOf("court-response")) {
    email.workspace.courtApplicationPrinted = false;
  }
  if (targetIndex <= STAGE_ORDER.indexOf("court-response")) {
    email.workspace.courtOutcome = null;
    email.workspace.courtHasOrder = null;
    email.workspace.courtNoaIncluded = null;
    email.workspace.courtResponsePrinted = false;
  }
  if (targetIndex <= STAGE_ORDER.indexOf("counsel-response")) {
    email.workspace.counselOfferPrinted = false;
  }
  if (targetIndex < STAGE_ORDER.indexOf("counsel-response")) {
    email.workspace.counselRequestPrinted = false;
    email.workspace.bundleCreated = false;
    email.workspace.bundleSections = null;
    email.workspace.counselBriefPrinted = false;
    email.workspace.courtBundlePrinted = false;
  }
  if (targetIndex <= STAGE_ORDER.indexOf("process-server-response")) {
    email.workspace.processServerResponsePrinted = false;
    email.workspace.processServerInvoiceEmailPrinted = false;
  }
  if (targetIndex < STAGE_ORDER.indexOf("process-server-response")) {
    email.workspace.processServerRequestPrinted = false;
  }
  if (targetIndex <= STAGE_ORDER.indexOf("counsel-hearing-response")) {
    email.workspace.hearingRound = 1;
    email.workspace.hearingCounselDocsSaved = false;
    email.workspace.postHearingOrderSaved = false;
    email.workspace.postHearingOrderClientPrinted = false;
    email.workspace.postHearingProcessServerPrinted = false;
    email.workspace.counselFeeNoteSaved = false;
    email.workspace.counselFeeNoteEmailPrinted = false;
  }
  email.workspace.finalComplete = false;
  clearHearingDraftsForJump(email, targetIndex);
  removeGeneratedFilesForJump(email, target);
  rebuildJumpSnapshot(email, jumpStage);
}

function clearHearingDraftsForJump(email, targetIndex) {
  const hearingDraftIndex = STAGE_ORDER.indexOf("counsel-hearing-response");
  if (targetIndex >= hearingDraftIndex) return;
  Object.keys(email.workspace.drafts || {}).forEach((key) => {
    if (/^(brief-counsel|court-bundle|post-order-client|post-process-server)(?:-\d+)?$/.test(key)) {
      delete email.workspace.drafts[key];
    }
  });
  if (targetIndex < STAGE_ORDER.indexOf("court-response")) {
    ["order-client", "process-server"].forEach((key) => {
      delete email.workspace.drafts[key];
    });
  }
}

function removeGeneratedFilesForJump(email, target) {
  if (!email.workspace.root) return;
  const surname = escapeRegExp(email.referral.surname);
  const patterns = [];
  if (["client-response", "court-response", "counsel-response", "process-server-response", "process-server-invoice", "counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"].includes(target)) {
    patterns.push(new RegExp(`^(?:WS\\.SIGNED|LOA\\.SIGNED)-${surname}\\.(?:pdf|docx)$`, "i"));
    patterns.push(new RegExp(`^\\d+(?:\\.|\\[(?:in|out)\\])client-response-${surname}\\.pdf$`, "i"));
  }
  if (["court-response", "counsel-response", "process-server-response", "process-server-invoice", "counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"].includes(target)) {
    patterns.push(/^SEALED-/i, /^Notice of Hearing/i, /\bOrder - /i);
    patterns.push(new RegExp(`^\\d+(?:\\.|\\[(?:in|out)\\])court-orders-${surname}\\.pdf$`, "i"));
  }
  if (["process-server-response", "process-server-invoice", "counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"].includes(target)) {
    patterns.push(/^Statement of Service/i, /^[A-Za-z0-9 -]+ Invoice - \d{4}-\d{2}-\d{2} - /i, /^\d+(?:\.|\[(?:in|out)\])statement-of-service-email/i, /^\d+(?:\.|\[(?:in|out)\])[a-z0-9-]+-invoice-email/i);
  }
  if (["counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"].includes(target)) {
    patterns.push(/^Draft Order - /i, /^Attendance Note - /i, /^Sealed /i, /^Counsel Fee Note/i, /^\d+(?:\.|\[(?:in|out)\])counsel-hearing-email/i, /^\d+(?:\.|\[(?:in|out)\])sealed-order-email/i, /^\d+(?:\.|\[(?:in|out)\])counsel-fee-note/i);
  }
  patterns.forEach((pattern) => removeNodesMatching(email.workspace.root, pattern));
}

function jumpStageIsAtOrAfter(target, stage) {
  const targetIndex = STAGE_ORDER.indexOf(stageFromJump(target));
  const stageIndex = STAGE_ORDER.indexOf(stage);
  return targetIndex >= 0 && stageIndex >= 0 && targetIndex >= stageIndex;
}

function jumpNeedsClientReady(target) {
  return target === "client-draft" || jumpStageIsAtOrAfter(target, "client-response") || target === "court-draft";
}

function jumpNeedsClientResponseFiled(target) {
  return target === "court-draft" || jumpStageIsAtOrAfter(target, "court-response");
}

function jumpNeedsCourtResponseFiled(target) {
  return ["counsel-response", "process-server-response", "process-server-invoice", "counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"].includes(stageFromJump(target));
}

function jumpNeedsProcessServerRequest(target) {
  return ["process-server-response", "process-server-invoice"].includes(stageFromJump(target));
}

function jumpNeedsProcessServerInvoiceComplete(target) {
  return ["counsel-response", "counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"].includes(stageFromJump(target));
}

function jumpNeedsCounselRequest(target) {
  return ["counsel-response", "counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note"].includes(stageFromJump(target));
}

function snapshotFolder(email, expectedName) {
  if (!email || !email.workspace.root) return null;
  return ensureFolder(email.workspace.root, expectedName);
}

function snapshotFile(email, expectedFolder, name, type = "file") {
  const folder = snapshotFolder(email, expectedFolder);
  if (!folder) return null;
  return ensureFile(folder, name, type);
}

function rebuildSnapshotFolders(email) {
  email.workspace.root = newNode("folder", rootFolderName(email.referral));
  email.workspace.selectedId = email.workspace.root.id;
  requiredFolders(email).forEach((name) => ensureFolder(email.workspace.root, name));
}

function addSnapshotIntakeFiles(email) {
  const referral = email.referral;
  const prelim = snapshotFolder(email, preliminaryName(referral));
  if (!prelim) return;
  ensureFile(prelim, introPdfName(referral), "file");
  const zip = ensureFile(prelim, zipName(referral), "zip");
  zip.extracted = true;
  laaEvidenceNames(referral).forEach((name) => snapshotFile(email, laaEvidenceName(referral, email), name, /\.png$/i.test(name) ? "image" : "file"));

  if (referral.orderTypes.some((order) => ["nmo", "oo"].includes(order.key))) {
    ensureFile(prelim, `${ZIP_BUNDLED_DOCUMENT_NAMES.fl401}.${referral.surname}.pdf`, "file");
  }
  if (referral.orderTypes.some((order) => ["cao", "pso", "sio"].includes(order.key))) {
    ensureFile(prelim, `${ZIP_BUNDLED_DOCUMENT_NAMES.c100}.${referral.surname}.pdf`, "file");
    ensureFile(prelim, `${ZIP_BUNDLED_DOCUMENT_NAMES.c1a}.${referral.surname}.pdf`, "file");
  }
  if (referral.c8) {
    ensureFile(prelim, c8DocumentName(referral), "file");
  }
}

function addSnapshotClientResponseFiles(email) {
  const referral = email.referral;
  switchIncomingStage(email, "client-response");
  stageAttachments(email, "client-response").forEach((attachment) => {
    attachment.saved = true;
    snapshotFile(email, clientResponseHome(referral, attachment.name), attachment.name, createIncomingNode(attachment).type);
  });
  email.workspace.incomingByStage["client-response"] = stageAttachments(email, "client-response");
  snapshotFile(email, clientCorrespondenceName(referral), clientResponsePdfName(referral, email));
  email.workspace.clientResponsePrinted = true;
}

function addSnapshotIncomingFiles(email, stage, expectedFolder) {
  switchIncomingStage(email, stage);
  const attachments = stageAttachments(email, stage);
  attachments.forEach((attachment) => {
    attachment.saved = true;
    const folderName = typeof expectedFolder === "function" ? expectedFolder(attachment) : expectedFolder;
    snapshotFile(email, folderName, attachment.name, createIncomingNode(attachment).type);
  });
  email.workspace.incomingByStage[stage] = attachments;
}

function addSnapshotCourtResponseFiles(email) {
  addSnapshotIncomingFiles(email, "court-response", (attachment) => courtOrdersName(email.referral, attachment.name));
  snapshotFile(email, courtCorrespondenceName(email.referral), courtOrdersEmailPdfName(email.referral, email));
  email.workspace.courtResponsePrinted = true;
  snapshotFile(email, clientCorrespondenceName(email.referral), draftConfig("order-client", email).printName);

  markDraftCompleteForTraining(email, "order-client");
}

function addSnapshotProcessServerResponseFiles(email) {
  addSnapshotIncomingFiles(email, "process-server-response", processServerName(email.referral));
  snapshotFile(email, processServerName(email.referral), processServerResponsePdfName(email));
  email.workspace.processServerResponsePrinted = true;
}

function addSnapshotProcessServerInvoiceFiles(email) {
  addSnapshotIncomingFiles(email, "process-server-invoice", invoicesName(email.referral));
  snapshotFile(email, invoicesName(email.referral), processServerInvoiceEmailPdfName(email));
  email.workspace.processServerInvoiceEmailPrinted = true;
}

function forceServiceOutcomeForJump(email, jumpStage) {
  const target = stageFromJump(jumpStage);
  if (!["process-server-response", "process-server-invoice"].includes(target)) return;
  email.workspace.courtOutcome = "granted-without-notice";
  email.workspace.courtHasOrder = true;
  resetIncomingStage(email, "court-response");
}

function rebuildJumpSnapshot(email, jumpStage) {
  if (!email || !email.workspace) return;
  rebuildSnapshotFolders(email);
  forceServiceOutcomeForJump(email, jumpStage);
  if (!jumpNeedsClientReady(jumpStage)) return;

  addSnapshotIntakeFiles(email);

  if (jumpStageIsAtOrAfter(jumpStage, "client-response")) {
    snapshotFile(email, clientCorrespondenceName(email.referral), onboardingPdfName(email.referral));
  }

  if (jumpNeedsClientResponseFiled(jumpStage)) {
    addSnapshotClientResponseFiles(email);
  }

  if (jumpStageIsAtOrAfter(jumpStage, "court-response")) {
    snapshotFile(email, courtCorrespondenceName(email.referral), courtApplicationPdfName(email.referral));
    email.workspace.courtApplicationPrinted = true;
  }

  if (jumpNeedsCourtResponseFiled(jumpStage)) {
    addSnapshotCourtResponseFiles(email);
  }

  if (jumpNeedsProcessServerRequest(jumpStage) || (jumpNeedsProcessServerInvoiceComplete(jumpStage) && serviceRequired(email))) {
    snapshotFile(email, processServerName(email.referral), draftConfig("process-server", email).printName);
    email.workspace.processServerRequestPrinted = true;
  }

  if (stageFromJump(jumpStage) === "process-server-invoice" || (jumpNeedsProcessServerInvoiceComplete(jumpStage) && serviceRequired(email))) {
    addSnapshotProcessServerResponseFiles(email);
  }

  if (jumpNeedsProcessServerInvoiceComplete(jumpStage) && serviceRequired(email)) {
    addSnapshotProcessServerInvoiceFiles(email);
  }

  if (jumpNeedsCounselRequest(jumpStage)) {
    snapshotFile(email, counselCorrespondenceName(email.referral), draftConfig("counsel", email).printName);
    email.workspace.counselRequestPrinted = true;
  }

  if (jumpStageIsAtOrAfter(jumpStage, "counsel-hearing-response")) {

    email.workspace.counselOfferPrinted = true;
    email.workspace.counselBriefPrinted = true;
    email.workspace.courtBundlePrinted = true;
    email.workspace.bundleCreated = true;

    const hearingFolder = ensureFolder(email.workspace.root, currentHearingFolderName(email));
    ensureFile(hearingFolder, hearingBundleName(email.referral), "file");
  }
}

function advanceSelectedMatter(stage) {
  const email = activeEmail();
  if (!email || !stage) return;

  email.workspace.statementRevisionsLeft = 0;
  resetStageForJump(email, stage);
  if (stage === "client-draft") {
    openDraft("client");
    setStatus("Client email draft opened for the selected matter.");
    return;
  }
  if (stage === "client-response") {
    switchIncomingStage(email, "client-response");
    setStatus("Client reply is now showing for the selected matter.");
    render();
    return;
  }
  if (stage === "court-draft") {
    email.workspace.clientResponsePrinted = true;
    openDraft("court");
    setStatus("Court application draft opened for the selected matter.");
    return;
  }
  if (stage === "court-response") {
    email.workspace.courtApplicationPrinted = true;
    switchIncomingStage(email, "court-response");
    setStatus("Court reply is now showing for the selected matter.");
    render();
    return;
  }
  if (stage === "counsel-response") {
    email.workspace.courtApplicationPrinted = true;
    switchIncomingStage(email, "court-response");
    email.workspace.courtResponsePrinted = true;
    markCurrentStageAttachmentsSaved(email, "court-response");
    if (serviceRequired(email)) {
      email.workspace.processServerRequestPrinted = true;
      email.workspace.processServerResponsePrinted = true;
      email.workspace.processServerInvoiceEmailPrinted = true;
      switchIncomingStage(email, "process-server-invoice");
      markCurrentStageAttachmentsSaved(email, "process-server-invoice");
    }
    email.workspace.counselRequestPrinted = true;
    switchIncomingStage(email, "counsel-response");
    setStatus("Counsel offer is now showing for the selected matter.");
    render();
    return;
  }
  if (stage === "process-server-response") {
    email.workspace.processServerRequestPrinted = true;
    switchIncomingStage(email, "process-server-response");
    setStatus("Statement of Service is now showing for the selected matter.");
    render();
    return;
  }
  if (stage === "process-server-invoice") {
    prepareProcessServerInvoiceJump(email);
    switchIncomingStage(email, "process-server-invoice");
    setStatus(`${processServerDetails(email.referral).name} invoice is showing. Save the attachment into ${expectedFolderLabel(email, invoicesName(email.referral))}.`);
    render();
    return;
  }
  if (stage === "counsel-hearing-response") {
    email.workspace.courtBundlePrinted = true;
    switchIncomingStage(email, "counsel-hearing-response");
    setStatus("Counsel hearing email is now showing for the selected matter.");
    render();
    return;
  }
  if (stage === "post-hearing-sealed-order") {
    email.workspace.hearingCounselDocsSaved = true;
    switchIncomingStage(email, "post-hearing-sealed-order");
    setStatus("Sealed order email is now showing for the selected matter.");
    render();
    return;
  }
  if (stage === "counsel-fee-note") {
    prepareCounselFeeNoteJump(email);
    switchIncomingStage(email, "counsel-fee-note");
    setStatus("Counsel's fee note is showing. Save the attachment into Invoices and Fee Notes.");
    render();
    return;
  }
}

function loaEmailBody(referral) {
  const firm = lawFirmDetails(referral);
  return `
    <p>Dear ${escapeHtml(firstName(referral.applicant))},</p>
    <p>We confirm that we will be representing you in your application for ${escapeHtml(orderLabels(referral))} against ${escapeHtml(firstName(referral.respondent))}.</p>
    <p>Please find attached the following documents for your review and signature.</p>
    <ol>
      <li><strong>Your Statement</strong> - Kindly review the statement carefully. If you are satisfied with the contents, please sign and return it to us. If you have any concerns, queries, or would like to request amendments, please do not hesitate to contact us so that we can discuss these with you.</li>
      <li><strong>Letter of Authority</strong> - Please complete and sign this document as required.</li>
    </ol>
    <p>Once we have received the signed documents from you, we will proceed with completing your Legal Aid application. We will then forward the completed Legal Aid forms to you for your signature.</p>
    <p>Please note that we will submit your application to the Court as soon as we have received the signed documents and Legal Aid approval. If you have any questions or require further clarification, please do not hesitate to contact us.</p>
    <p>Yours sincerely,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function courtDraftBody(referral) {
  const firm = lawFirmDetails(referral);
  const lines = [];
  const applicationNoun = referral.orderTypes.length > 1 ? "applications" : "application";
  if (referral.hasFamily) {
    lines.push(`${ZIP_BUNDLED_DOCUMENT_NAMES.fl401} - Application for ${orderLabels(referral, ["nmo", "oo"])}.`);
  }
  if (referral.hasChildren) {
    lines.push(`${ZIP_BUNDLED_DOCUMENT_NAMES.c100} - Application for ${orderLabels(referral, ["cao", "pso", "sio"])}.`);
    lines.push(`${ZIP_BUNDLED_DOCUMENT_NAMES.c1a} - Allegations of Domestic Abuse.`);
  }
  lines.push(`${ZIP_BUNDLED_DOCUMENT_NAMES.witnessStatement} of the Applicant.`);
  referral.orderTypes
    .filter((order) => ["nmo", "oo", "pso"].includes(order.key))
    .forEach((order) => lines.push(`Draft ${order.label}.`));
  lines.push("Our Notice of Acting.");
  if (referral.c8) lines.push("C8 - Confidential contact details.");
  return `
    <p>Dear Sir/Madam,</p>
    <p>${escapeHtml(courtApplicationTitle(referral))}</p>
    ${referral.hasChildren ? `<p>PBA DETAILS<br>${escapeHtml(firm.pbaNumber)}<br>${escapeHtml(firm.name)}<br>We confirm our consent for payment to be deducted from our PBA account.</p>` : ""}
    <p>Please kindly place the attached applications before the Honourable Judge.</p>
    <p>${lines.map(escapeHtml).join("<br>")}</p>
    <p>The Applicant urges the Honourable Judge to grant the ${escapeHtml(orderLabels(referral))} ${applicationNoun} on paper without notice to the Respondent.</p>
    <p>The Applicant will opt for a remote hearing where possible.</p>
    <p>Please do not hesitate to contact us, should you require further information.</p>
    <p>Yours faithfully,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function orderToClientBody(referral, email = null) {
  const firm = lawFirmDetails(referral);
  const court = courtDetails(referral);
  const hearingDate = email ? currentHearingDateDisplay(email) : hearingDateDisplay(referral, 1);
  const hearingMethod = email ? currentHearingMethod(email) : hearingMethodForRound(referral, 1);
  const hasOrder = !email || email.workspace.courtHasOrder;
  return `
    <p>Dear ${escapeHtml(firstName(referral.applicant))},</p>
    <p><strong>${escapeHtml(court.caseReference)}</strong><br><strong>${escapeHtml(caseName(referral))}</strong><br><strong>Hearing: ${escapeHtml(hearingDate)}</strong><br><strong>At ${escapeHtml(court.hearingTime)}</strong><br><strong>${escapeHtml(hearingMethod)}</strong></p>
    <p>Please find attached ${hasOrder ? "a copy of the Order and Notice of Hearing" : "the Notice of Hearing and sealed papers received from the court"} for your records.</p>
    <p>The matter has been listed for a hearing at ${escapeHtml(court.name)}, ${escapeHtml(court.address)} on ${escapeHtml(hearingDate)} at ${escapeHtml(court.hearingTime)}. Time estimate: 30 minutes.</p>
    <p>We are arranging service of the court papers on the Respondent. A barrister will contact you before the hearing to discuss your preparation.</p>
    <p>If you have any queries, please contact us on ${escapeHtml(firm.phone)}.</p>
    <p>Kind regards,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function finalOrderEmailBody(referral, email) {
  const firm = lawFirmDetails(referral);
  return `
    <p>Dear ${escapeHtml(firstName(referral.applicant))},</p>
    <p><strong>${escapeHtml(caseName(referral))}</strong></p>
    <p>Please find attached the sealed Final Order made at the hearing on ${escapeHtml(currentHearingDateDisplay(email))}.</p>
    <p>Please keep this order safe and contact us if you have any questions about the next practical steps.</p>
    <p>Kind regards,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function processServerBody(referral, email = null) {
  const firm = lawFirmDetails(referral);
  const court = courtDetails(referral);
  const hearingDate = email ? currentHearingDateDisplay(email) : hearingDateDisplay(referral, 1);
  return `
    <p>Dear Sirs,</p>
    <p><strong>${escapeHtml(court.caseReference)}</strong><br><strong>${escapeHtml(caseName(referral))}</strong><br><strong>Hearing On: ${escapeHtml(hearingDate)}</strong><br><strong>At: ${escapeHtml(court.hearingTime)}</strong></p>
    <p><strong>Please find attached separately</strong> the court papers for Personal Service upon the Respondent.</p>
    <p>The documents are attached individually so each item to be served is clear.</p>
    <p>Please also lodge with the police.</p>
    <p><strong>Respondent Info</strong><br>${escapeHtml(referral.respondent)}<br>${escapeHtml(referral.respondentAddress)}<br>${escapeHtml(referral.respondentPhone)}</p>
    <p>We await the Statement of Service.</p>
    <p>Kind regards,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function counselRequestBody(referral, email = null) {
  const counsel = referral.counsel;
  const firm = lawFirmDetails(referral);
  const court = courtDetails(referral);
  const hearingDate = email ? currentHearingDateDisplay(email) : hearingDateDisplay(referral, 1);
  const hearingMethod = email ? currentHearingMethod(email) : hearingMethodForRound(referral, 1);
  return `
    <p>Dear Sirs,</p>
    <p><strong>${escapeHtml(court.caseReference)}</strong><br><strong>${escapeHtml(caseName(referral))}</strong><br><strong>Hearing Date: ${escapeHtml(hearingDate)}</strong><br><strong>Time: ${escapeHtml(court.hearingTime)}</strong><br><strong>Method: ${escapeHtml(hearingMethod)}</strong></p>
    <p><strong>Our client/Applicant: ${escapeHtml(referral.applicant)}</strong><br><strong>Instructing Solicitor: ${escapeHtml(firm.solicitorName)}</strong></p>
    <p><strong>Without Notice Hearing</strong></p>
    <p>We write to request Counsel's representation through ${escapeHtml(counsel.chambersName)} in the above matter listed for a <strong>return hearing</strong>, namely a <strong>without notice family injunction hearing</strong>, at <strong>${escapeHtml(court.name)}, ${escapeHtml(court.address)}</strong> with a time estimate of <strong>30</strong> minutes.</p>
    <p>Counsel is instructed by ${escapeHtml(firm.name)}.</p>
    <p>We look forward to Counsel's availability and details. Papers will follow once Counsel is confirmed; this availability request is not dependent on a completed bundle or sealed orders.</p>
    <p>Please note that this case is Legal Aided.</p>
    <p>Should Counsel wish to discuss any aspect of this matter further, please contact us on ${escapeHtml(firm.phone)}.</p>
    <p>Kind regards,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function briefToCounselBody(referral, email = null) {
  const counsel = referral.counsel;
  const firm = lawFirmDetails(referral);
  const court = courtDetails(referral);
  const hearingDate = email ? currentHearingDateDisplay(email) : hearingDateDisplay(referral, 1);
  return `
    <p>Dear Sirs,</p>
    <p>Thank you for offering ${escapeHtml(counsel.counselName)} of ${escapeHtml(counsel.chambersName)} to represent the Applicant at the hearing on ${escapeHtml(hearingDate)} at ${escapeHtml(court.hearingTime)}.</p>
    <p>Please find attached the Brief to Counsel, chronology, and case summary.</p>
    <p><strong>${escapeHtml(caseName(referral))}</strong><br><strong>Instructing Solicitor: ${escapeHtml(firm.solicitorName)}</strong></p>
    <p>Please confirm safe receipt.</p>
    <p>Kind regards,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function courtBundleBody(referral, email = null) {
  const firm = lawFirmDetails(referral);
  const court = courtDetails(referral);
  const hearingDate = email ? currentHearingDateDisplay(email) : hearingDateDisplay(referral, 1);
  return `
    <p>Dear Sir/Madam,</p>
    <p><strong>${escapeHtml(caseName(referral))}</strong><br><strong>Hearing: ${escapeHtml(hearingDate)} at ${escapeHtml(court.hearingTime)}</strong></p>
    <p>Please confirm the bundle requirements and filing arrangements for the next hearing.</p>
    <p>Counsel is blind copied for reference.</p>
    <p>Kind regards,<br>${escapeHtml(firm.solicitorName)}<br>${escapeHtml(firm.name)}</p>
  `.trim();
}

function templateByName(name) {
  return TEMPLATES.find((template) => template.name === name) || null;
}

const TEMPLATE_FILE_STEMS = {
  "Letter of Authority": (surname) => `Letter-of-Authority-${surname}`,
  "Witness Statement": (surname) => `WS.${surname}`,
  "Notice of Acting": (surname) => `Notice-of-Acting-${surname}`,
  "Draft Non-Molestation Order": (surname) => `Draft-NMO-${surname}`,
  "Draft Occupation Order": (surname) => `Draft-OO-${surname}`,
  "Draft Prohibited Steps Order": (surname) => `Draft-PSO-${surname}`
};

function templateFileName(templateName, surname) {
  const template = templateByName(templateName);
  const ext = template ? template.ext : "docx";
  const stem = TEMPLATE_FILE_STEMS[templateName];
  return stem ? `${stem(surname)}.${ext}` : `${templateName} - ${surname}.${ext}`;
}

function templateAllowedForMatter(referral, templateName) {
  const orderKeys = new Set(referral.orderTypes.map((order) => order.key));
  if (templateName === "Draft Non-Molestation Order") {
    return orderKeys.has("nmo");
  }
  if (templateName === "Draft Occupation Order") {
    return orderKeys.has("oo");
  }
  if (templateName === "Draft Prohibited Steps Order") {
    return orderKeys.has("pso");
  }
  return true;
}

function blockedTemplateMessage(referral, templateName) {
  if (templateName === "Draft Non-Molestation Order") {
    return `${templateName} belongs with a non-molestation matter, not this referral.`;
  }
  if (templateName === "Draft Occupation Order") {
    return `${templateName} belongs with an occupation order matter, not this referral.`;
  }
  if (templateName === "Draft Prohibited Steps Order") {
    return `${templateName} belongs with a prohibited steps matter, not this referral.`;
  }
  return `${templateName} does not match this ${referral.matterLabel}.`;
}

function ensureStandardFolders(email) {
  requiredFolders(email).forEach((name) => ensureFolder(email.workspace.root, name));
  return childByName(email.workspace.root, preliminaryName(email.referral), "folder");
}

function createRootFolder() {
  const email = activeEmail();
  if (!email) return;
  if (email.workspace.root) {
    showModal("Root already exists", "This fake matter already has a root folder. Select it or create subfolders inside it.");
    return;
  }
  email.workspace.root = newNode("folder", rootFolderName(email.referral));
  ensureStandardFolders(email);
  email.workspace.selectedId = email.workspace.root.id;
  setStatus(`${rootFolderName(email.referral)} and standard folders were created.`);
  render();
}

function countFolders(node) {
  if (!node || node.type !== "folder") return 0;
  return 1 + (node.children || []).reduce((sum, child) => sum + countFolders(child), 0);
}

function saveIntroPdf() {
  const email = activeEmail();
  if (!email) return;
  const folder = selectedFolder(email);
  if (!folder) {
    showModal("Select folder", "Select the correct destination folder in Explorer before printing the email as PDF.");
    return;
  }
  if (email.workspace.inboxStage === "client-response") {
    if (email.workspace.clientResponsePrinted) {
      setStatus(`${clientResponsePdfName(email.referral, email)} has already been printed.`);
      return;
    }
    if (!folderMatches(email, folder, clientCorrespondenceName(email.referral))) {
      showModal("Wrong folder", `The client response must be printed as <code>${escapeHtml(clientResponsePdfName(email.referral, email))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, clientCorrespondenceName(email.referral)))}</code>.`);
      return;
    }
    ensureFile(folder, clientResponsePdfName(email.referral, email), "file");
    email.workspace.clientResponsePrinted = true;
    setStatus(`${clientResponsePdfName(email.referral, email)} printed into Correspondence with Client.`);
    render();
    return;
  }
  if (email.workspace.inboxStage === "court-response") {
    if (email.workspace.courtResponsePrinted) {
      setStatus(`${courtOrdersEmailPdfName(email.referral, email)} has already been printed.`);
      return;
    }
    if (!folderMatches(email, folder, courtCorrespondenceName(email.referral))) {
      showModal("Wrong folder", `The court email must be printed as <code>${escapeHtml(courtOrdersEmailPdfName(email.referral, email))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, courtCorrespondenceName(email.referral)))}</code>.`);
      return;
    }
    ensureFile(folder, courtOrdersEmailPdfName(email.referral, email), "file");
    email.workspace.courtResponsePrinted = true;
    setStatus(`${courtOrdersEmailPdfName(email.referral, email)} printed into Correspondence with Court.`);
    render();
    return;
  }
  if (email.workspace.inboxStage === "counsel-response") {
    if (!folderMatches(email, folder, counselCorrespondenceName(email.referral))) {
      showModal("Wrong folder", `The counsel offer must be printed as <code>${escapeHtml(counselOfferPdfName(email.referral, email))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, counselCorrespondenceName(email.referral)))}</code>.`);
      return;
    }
    ensureFile(folder, counselOfferPdfName(email.referral, email), "file");
    email.workspace.counselOfferPrinted = true;
    email.workspace.lastGuidedStep = null;
    guideTrainingStep(email, { openDrafts: true, forceStatus: true });
    render();
    return;
  }
  if (email.workspace.inboxStage === "process-server-response") {
    if (email.workspace.processServerResponsePrinted) {
      setStatus(`${processServerResponsePdfName(email)} has already been printed.`);
      return;
    }
    if (!stageIncomingSaved(email, "process-server-response")) {
      showModal("Save Statement of Service", `Save the Statement of Service attachment inside <code>${escapeHtml(expectedFolderLabel(email, processServerName(email.referral)))}</code> before printing this email as PDF.`);
      return;
    }
    if (!folderMatches(email, folder, processServerName(email.referral))) {
      showModal("Wrong folder", `The Statement of Service email must be printed inside <code>${escapeHtml(expectedFolderLabel(email, processServerName(email.referral)))}</code>.`);
      return;
    }
    ensureFile(folder, processServerResponsePdfName(email), "file");
    email.workspace.processServerResponsePrinted = true;
    switchIncomingStage(email, "process-server-invoice");
    setStatus(`${processServerResponsePdfName(email)} printed. Save the ${processServerDetails(email.referral).name} invoice attachment into ${expectedFolderLabel(email, invoicesName(email.referral))}.`);
    render();
    return;
  }
  if (email.workspace.inboxStage === "process-server-invoice") {
    if (email.workspace.processServerInvoiceEmailPrinted) {
      setStatus(`${processServerInvoiceEmailPdfName(email)} has already been printed.`);
      return;
    }
    const invoicePrintFolder = effectiveFolderName(email, invoicesName(email.referral));
    if (!folderMatches(email, folder, invoicePrintFolder)) {
      showModal("Wrong folder", `The invoice email must be printed as <code>${escapeHtml(processServerInvoiceEmailPdfName(email))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, invoicePrintFolder))}</code>.`);
      return;
    }
    ensureFile(folder, processServerInvoiceEmailPdfName(email), "file");
    email.workspace.processServerInvoiceEmailPrinted = true;
    if (!handleProcessServerInvoiceProgress(email)) {
      if (!processServerInvoiceSaved(email)) {
        setStatus(`${processServerInvoiceEmailPdfName(email)} printed. Now click the ${processServerDetails(email.referral).name} invoice attachment, then click ${expectedFolderLabel(email, invoicesName(email.referral))} to place it (or drag it there).`);
      } else {
        setStatus(`${processServerInvoiceEmailPdfName(email)} printed.`);
      }
    }
    render();
    return;
  }
  if (email.workspace.inboxStage === "counsel-hearing-response") {
    if (!folderMatches(email, folder, counselCorrespondenceName(email.referral))) {
      showModal("Wrong folder", `The Counsel hearing email must be printed as <code>${escapeHtml(counselHearingEmailPdfName(email))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, counselCorrespondenceName(email.referral)))}</code>.`);
      return;
    }
    ensureFile(folder, counselHearingEmailPdfName(email), "file");
    setStatus(`${counselHearingEmailPdfName(email)} printed into Correspondence with Counsel.`);
    render();
    return;
  }
  if (email.workspace.inboxStage === "post-hearing-sealed-order") {
    if (!folderMatches(email, folder, courtCorrespondenceName(email.referral))) {
      showModal("Wrong folder", `The sealed-order email must be printed as <code>${escapeHtml(postHearingCourtEmailPdfName(email))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, courtCorrespondenceName(email.referral)))}</code>.`);
      return;
    }
    ensureFile(folder, postHearingCourtEmailPdfName(email), "file");
    setStatus(`${postHearingCourtEmailPdfName(email)} printed into Correspondence with Court.`);
    render();
    return;
  }
  if (email.workspace.inboxStage === "counsel-fee-note") {
    if (email.workspace.counselFeeNoteEmailPrinted) {
      setStatus(`${counselFeeNoteEmailPdfName(email)} has already been printed.`);
      return;
    }
    if (!folderMatches(email, folder, counselCorrespondenceName(email.referral))) {
      showModal("Wrong folder", `Counsel's fee-note email must be printed as <code>${escapeHtml(counselFeeNoteEmailPdfName(email))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, counselCorrespondenceName(email.referral)))}</code>.`);
      return;
    }
    ensureFile(folder, counselFeeNoteEmailPdfName(email), "file");
    email.workspace.counselFeeNoteEmailPrinted = true;
    if (!handleCounselFeeNoteProgress(email)) {
      setStatus(`${counselFeeNoteEmailPdfName(email)} printed into Correspondence with Counsel.`);
    }
    render();
    return;
  }
  if (!folderMatches(email, folder, preliminaryName(email.referral))) {
    showModal("Wrong folder", `The email must be printed as <code>${escapeHtml(introPdfName(email.referral))}</code> inside <code>${escapeHtml(expectedFolderLabel(email, preliminaryName(email.referral)))}</code>.`);
    return;
  }
  ensureFile(folder, introPdfName(email.referral), "file");
  setStatus(`${introPdfName(email.referral)} printed.`);
  render();
}

function saveClientEmailPdf() {
  const email = activeEmail();
  if (!email) return;
  const draft = clientDraftFor(email);
  const config = draftConfig(draft.type || "client", email);
  if (!clientDraftReady(draft)) {
    showModal("Attach documents", "Attach the required documents before sending or printing this email.");
    return;
  }
  if (!draft.sent) {
    showModal("Send first", "Press Send on the email before printing it as PDF.");
    return;
  }
  if (draft.printed) {
    setStatus(`${config.printName} has already been printed.`);
    return;
  }
  const folder = selectedFolder(email);
  if (!folder) {
    showModal("Select folder", `Select <code>${escapeHtml(config.printFolder)}</code> in Explorer before printing this email as PDF.`);
    return;
  }
  const kind = draftKind(draft.type || "client");
  if ((kind === "process-server" || kind === "post-process-server") && !folderMatches(email, folder, processServerName(email.referral))) {
    showModal("Wrong folder", `Process-server emails must be printed inside <code>${escapeHtml(expectedFolderLabel(email, processServerName(email.referral)))}</code>.`);
    return;
  }
  if (kind !== "process-server" && kind !== "post-process-server" && !folderMatches(email, folder, config.printFolder)) {
    showModal("Wrong folder", `Select <code>${escapeHtml(expectedFolderLabel(email, config.printFolder))}</code> before printing this email as PDF.`);
    return;
  }
  ensureFile(folder, config.printName, "file");
  draft.printed = true;
  if (kind === "client") {
    email.workspace.clientResponseMode = null;
    switchIncomingStage(email, "client-response");
    setStatus(`${config.printName} printed. A new client reply has arrived.`);
  } else if (kind === "revision") {
    email.workspace.statementRevision += 1;
    email.workspace.statementRevisionsLeft = Math.max(0, email.workspace.statementRevisionsLeft - 1);
    email.workspace.clientResponseMode = null;
    email.workspace.incomingAttachments = [];
    email.workspace.incomingByStage["client-response"] = [];
    ensureClientResponse(email);
    email.workspace.incomingByStage["client-response"] = email.workspace.incomingAttachments;
    setStatus(`${config.printName} printed. ${email.workspace.statementRevisionsLeft > 0 || email.workspace.clientResponseMode === "revision" ? "The client has asked for more changes." : "The client has replied and is happy to sign."}`);
  } else if (kind === "docusign") {
    completeDocusignResponse(email);
    setStatus(`${config.printName} printed. Signed DocuSign documents are now ready to save.`);
  } else if (kind === "court") {
    email.workspace.courtApplicationPrinted = true;
    switchIncomingStage(email, "court-response");
    setStatus(`${config.printName} printed. A new court reply has arrived.`);
  } else if (kind === "counsel") {
    email.workspace.counselRequestPrinted = true;
    switchIncomingStage(email, "counsel-response");
    setStatus(`${config.printName} printed. ${email.referral.counsel.counselName} has been offered by ${email.referral.counsel.chambersName}.`);
  } else if (kind === "process-server") {
    email.workspace.processServerRequestPrinted = true;
    resetIncomingStage(email, "process-server-response");
    resetIncomingStage(email, "process-server-invoice");
    switchIncomingStage(email, "process-server-response");
    setStatus(`${config.printName} printed. A Statement of Service response has arrived.`);
  } else if (kind === "post-process-server") {
    email.workspace.postHearingProcessServerPrinted = true;

    email.workspace.processServerResponsePrinted = false;
    email.workspace.processServerInvoiceEmailPrinted = false;
    resetIncomingStage(email, "process-server-response");
    resetIncomingStage(email, "process-server-invoice");
    switchIncomingStage(email, "process-server-response");
    setStatus(`${config.printName} printed. A Statement of Service response has arrived.`);
  } else if (kind === "brief-counsel") {
    email.workspace.counselBriefPrinted = true;
    email.workspace.lastGuidedStep = null;
    guideTrainingStep(email, { openDrafts: true, forceStatus: true });
  } else if (kind === "court-bundle") {
    email.workspace.courtBundlePrinted = true;
    email.workspace.lastGuidedStep = null;
    if (arriveCounselHearingIfReady(email)) {
      setStatus(`${config.printName} printed. Counsel's hearing email has arrived.`);
    } else {
      guideTrainingStep(email, { openDrafts: true, forceStatus: true });
    }
  } else if (kind === "post-order-client") {
    email.workspace.postHearingOrderClientPrinted = true;
    setStatus(`${config.printName} printed into Correspondence with Client.`);
    advanceHearingLoopIfReady(email);
  } else {
    setStatus(`${config.printName} printed into ${folder.name}.`);
  }
  draft.open = false;
  render();
}

function dropZip(email, folder) {
  if (!folderMatches(email, folder, preliminaryName(email.referral))) {
    showModal("Wrong folder", `Place <code>${escapeHtml(zipName(email.referral))}</code> into <code>${escapeHtml(expectedFolderLabel(email, preliminaryName(email.referral)))}</code> instead (click it, then click the folder, or drag).`);
    return { name: zipName(email.referral), reason: `belongs in ${expectedFolderLabel(email, preliminaryName(email.referral))}` };
  }
  ensureFile(folder, zipName(email.referral), "zip");
  email.workspace.selectedId = folder.id;
  setStatus(`${zipName(email.referral)} saved. Use Extract on the ZIP row.`);
  render();
}

function destinationForTemplate(email, templateName) {
  if (CLIENT_DOC_TEMPLATE_NAMES.has(templateName)) return clientDocsName(email.referral);
  if (HEARING_TEMPLATE_NAMES.has(templateName)) return currentHearingFolderName(email);
  return preliminaryName(email.referral);
}

function bundleItemFromNode(node) {
  return {
    name: node.name,
    ext: node.type === "folder" ? "folder" : (nodeExtension(node) || nodeTag(node).toLowerCase())
  };
}

function bundleItemFromTemplate(email, templateName) {
  const template = templateByName(templateName);
  if (!template || !templateAllowedForMatter(email.referral, templateName)) return null;
  return {
    name: templateFileName(templateName, email.referral.surname),
    ext: template.ext
  };
}

function addNodeToBundleSection(email, sectionKey, nodeId) {
  if (!email || !email.workspace.root) return;
  const node = findNode(email.workspace.root, nodeId);
  if (!node || !isBundleCandidate(node)) {
    setStatus("Click a file, image, or evidence folder, then click a bundle section to place it there (or drag it).");
    return;
  }
  if (!bundleSectionAccepts(sectionKey, node.name)) {
    setStatus(`${node.name} does not belong in that bundle section.`);
    return;
  }
  const sections = ensureBundleSections(email);
  const section = sections[sectionKey] || [];
  if (!section.some((item) => item.name === node.name)) {
    section.push(bundleItemFromNode(node));
  }
  sections[sectionKey] = normaliseBundleSection(sectionKey, section);
  email.workspace.bundleCreated = false;
  setStatus(`${node.name} added to Bundle Maker.`);
  render();
}

function addTemplateToBundleSection(email, sectionKey, templateName) {
  if (!email || !email.workspace.root) return;
  const item = bundleItemFromTemplate(email, templateName);
  if (!item) {
    setStatus("That template does not belong in this matter.");
    return;
  }
  if (!bundleSectionAccepts(sectionKey, item.name)) {
    setStatus(`${item.name} does not belong in that bundle section.`);
    return;
  }
  const sections = ensureBundleSections(email);
  const section = sections[sectionKey] || [];
  if (!section.some((existing) => existing.name === item.name)) {
    section.push(item);
  }
  sections[sectionKey] = normaliseBundleSection(sectionKey, section);
  email.workspace.bundleCreated = false;
  setStatus(`${item.name} added to Bundle Maker.`);
  render();
}

function bundleSectionAccepts(sectionKey, name) {
  const lower = String(name || "").toLowerCase();
  if (sectionKey === "cover") return /^cover page\b/i.test(name);
  if (sectionKey === "summary") {
    return /^case summary\b/i.test(name) || /^chronology\b/i.test(name);
  }
  if (sectionKey === "applications") {
    return isBundleApplicationName(name) || isBundleNoticeName(name) || isBundleOrderName(name);
  }
  if (sectionKey === "statements") {
    return (/^sealed-ws\.signed\b/i.test(name) || /^sealed witness statement\b/i.test(name)) && !lower.includes("statement of service");
  }
  if (sectionKey === "service") {
    return /^statement of service\b/i.test(name);
  }
  return true;
}

function createBundle() {
  const email = activeEmail();
  if (!email || !email.workspace.root) return;
  saveHearingBundleToFolder(email, bundleDestinationFolder(email, true));
  render();
}

function saveIncomingAttachment(email, folder, attachmentId) {
  const attachment = email.workspace.incomingAttachments.find((item) => item.id === attachmentId);
  if (!attachment || attachment.saved) return;
  const stage = email.workspace.inboxStage;
  const expectedFolder = {
    "client-response": clientResponseHome(email.referral, attachment.name),
    "court-response": courtOrdersName(email.referral, attachment.name),
    "process-server-response": processServerName(email.referral),
    "process-server-invoice": invoicesName(email.referral),
    "counsel-hearing-response": currentHearingFolderName(email),
    "post-hearing-sealed-order": courtOrdersName(email.referral, attachment.name),
    "counsel-fee-note": invoicesName(email.referral)
  }[stage] || preliminaryName(email.referral);
  if (!folderMatches(email, folder, expectedFolder)) {
    showModal("Wrong folder", `Save <code>${escapeHtml(attachment.name)}</code> inside <code>${escapeHtml(expectedFolderLabel(email, expectedFolder))}</code>.`);
    return { name: attachment.name, reason: `belongs in ${expectedFolderLabel(email, expectedFolder)}` };
  }
  const node = createIncomingNode(attachment);
  if (childByName(folder, node.name, node.type)) {
    attachment.saved = true;
    email.workspace.incomingByStage[stage] = email.workspace.incomingAttachments;
    setStatus(`${attachment.name} is already filed in ${folder.name}.`);
    render();
    return;
  }
  ensureFile(folder, node.name, node.type);
  attachment.saved = true;
  email.workspace.incomingByStage[stage] = email.workspace.incomingAttachments;
  email.workspace.selectedId = folder.id;
  setStatus(`${attachment.name} saved into ${folder.name}.`);
  if (stage === "counsel-hearing-response" && email.workspace.incomingAttachments.every((item) => item.saved)) {
    email.workspace.hearingCounselDocsSaved = true;
    switchIncomingStage(email, "post-hearing-sealed-order");
    setStatus(`${attachment.name} saved. The sealed order has arrived from court.`);
  } else if (stage === "post-hearing-sealed-order" && email.workspace.incomingAttachments.every((item) => item.saved)) {
    email.workspace.postHearingOrderSaved = true;
    switchIncomingStage(email, "counsel-fee-note");
    email.workspace.lastGuidedStep = null;
    setStatus(`${attachment.name} saved. Counsel's fee note has arrived. Save it into Invoices and Fee Notes.`);
  } else if (stage === "counsel-fee-note" && email.workspace.incomingAttachments.every((item) => item.saved)) {
    email.workspace.counselFeeNoteSaved = true;
    email.workspace.lastGuidedStep = null;
    if (!handleCounselFeeNoteProgress(email)) {
      guideTrainingStep(email, { forceStatus: true });
    }
  } else if (stage === "process-server-invoice" && email.workspace.incomingAttachments.every((item) => item.saved)) {
    email.workspace.lastGuidedStep = null;
    if (!handleProcessServerInvoiceProgress(email)) {
      guideTrainingStep(email, { forceStatus: true });
    }
  } else if (stage === "court-response" && email.workspace.incomingAttachments.every((item) => item.saved)) {
    setStatus(email.workspace.courtHasOrder
      ? `${attachment.name} saved. Send the order to the client and process server.`
      : `${attachment.name} saved. Send the hearing notice to the client and arrange the next steps.`);
  }
  render();
}

function removeNodesMatching(folder, pattern) {
  if (!folder || !Array.isArray(folder.children)) return;
  folder.children = folder.children.filter((child) => !pattern.test(child.name || ""));
  folder.children.forEach((child) => {
    if (child.type === "folder") removeNodesMatching(child, pattern);
  });
}

function extractZip(zipNodeId) {
  const email = activeEmail();
  if (!email || !email.workspace.root) return;
  const zipNode = findNode(email.workspace.root, zipNodeId);
  const parent = findParent(email.workspace.root, zipNodeId);
  if (!zipNode || zipNode.type !== "zip" || !parent) return;
  if (!folderMatches(email, parent, preliminaryName(email.referral))) {
    showModal("Wrong folder", `Extract <code>${escapeHtml(zipName(email.referral))}</code> only inside <code>${escapeHtml(expectedFolderLabel(email, preliminaryName(email.referral)))}</code>.`);
    return;
  }
  packContents(email.referral).forEach((node) => {
    if (!childByName(parent, node.name, node.type)) {
      parent.children.push(node);
    }
  });
  zipNode.extracted = true;
  email.workspace.selectedId = parent.id;
  setStatus(`${zipName(email.referral)} extracted.`);
  render();
}

function validationState(email) {
  const state = {
    rootExists: Boolean(email && email.workspace.root),
    standardFoldersExist: false,
    introSaved: false,
    docsExtracted: false,
    laaEvidenceFiled: false,
    signedDocsFiled: false,
    clientResponsePrinted: false,
    courtApplicationPrinted: false,
    courtAttachmentsFiled: false,
    courtResponsePrinted: false,
    counselRequestPrinted: false,
    counselOfferPrinted: false,
    counselBriefPrinted: false,
    processServerRequestPrinted: false,
    processServerResponsePrinted: false,
    processServerInvoiceSaved: false,
    courtBundlePrinted: false,
    bundleCreated: false,
    finalComplete: false
  };
  if (!state.rootExists) return state;
  const root = email.workspace.root;
  state.standardFoldersExist = requiredFolders(email).every((name) => Boolean(childByName(root, name, "folder")));
  const prelim = childByName(root, preliminaryName(email.referral), "folder");
  state.introSaved = Boolean(prelim && childByName(prelim, introPdfName(email.referral), "file"));
  const zip = prelim ? childByName(prelim, zipName(email.referral), "zip") : null;
  state.docsExtracted = Boolean(zip && zip.extracted);
  state.laaEvidenceFiled = laaEvidenceComplete(email);
  state.signedDocsFiled = signedDocsReady(email);
  state.clientResponsePrinted = Boolean(email.workspace.clientResponsePrinted);
  state.courtApplicationPrinted = Boolean(email.workspace.courtApplicationPrinted);
  state.courtAttachmentsFiled = courtAttachmentsSaved(email);
  state.courtResponsePrinted = Boolean(email.workspace.courtResponsePrinted);
  state.counselRequestPrinted = Boolean(email.workspace.counselRequestPrinted);
  state.counselOfferPrinted = Boolean(email.workspace.counselOfferPrinted);
  state.counselBriefPrinted = Boolean(email.workspace.counselBriefPrinted);
  state.processServerRequestPrinted = Boolean(email.workspace.processServerRequestPrinted);
  state.processServerResponsePrinted = Boolean(email.workspace.processServerResponsePrinted);
  state.processServerInvoiceSaved = processServerInvoiceSaved(email);
  state.courtBundlePrinted = Boolean(email.workspace.courtBundlePrinted);
  state.bundleCreated = Boolean(email.workspace.bundleCreated);
  state.finalComplete = Boolean(email.workspace.finalComplete);
  return state;
}

function laaEvidenceComplete(email) {
  if (!email || !email.workspace.root) return false;
  const laa = childByName(email.workspace.root, laaEvidenceName(email.referral, email), "folder");
  if (!laa) return false;
  const children = laa.children || [];
  const has = (name) => children.some((node) => String(node.name || "").toLowerCase() === name.toLowerCase());
  return laaEvidenceNames(email.referral).every(has);
}

function canShowDocusign(email) {
  return email.workspace.inboxStage === "client-response" &&
    email.workspace.clientResponseMode === "docusign" &&
    !email.workspace.incomingAttachments.length;
}

function signedDocsReady(email) {
  if (!email || !email.workspace.root) return false;
  const prelim = childByName(email.workspace.root, clientDocsName(email.referral), "folder");
  const preliminary = childByName(email.workspace.root, preliminaryName(email.referral), "folder");
  if (!prelim || !preliminary) return false;
  const hasSignedFile = (folder, nameFor) => ["pdf", "docx", "doc"].some((ext) => childByName(folder, nameFor(email.referral, ext), "file"));
  return Boolean(
    hasSignedFile(prelim, signedWsName) &&
    hasSignedFile(preliminary, signedLoaName)
  );
}

function courtAttachmentsSaved(email) {
  const attachments = stageAttachments(email, "court-response");
  return attachments.length > 0 && attachments.every((attachment) => attachment.saved);
}

function markStageAttachmentsSaved(email, stage) {
  if (!email || !stage) return;
  if (stage === "court-response") ensureCourtResponse(email);
  const attachments = (email.workspace.inboxStage || REFERRAL_STAGE) === stage
    ? (email.workspace.incomingAttachments || [])
    : (email.workspace.incomingByStage[stage] || []);
  attachments.forEach((attachment) => {
    attachment.saved = true;
  });
  email.workspace.incomingByStage[stage] = attachments;
}

function markCurrentStageAttachmentsSaved(email, stage) {
  if (!email || (email.workspace.inboxStage || REFERRAL_STAGE) !== stage) return;
  markStageAttachmentsSaved(email, stage);
}

function processServerRequiredNames(email, type = "process-server") {
  if (draftKind(type) === "post-process-server") {
    return postHearingCourtAttachmentNames(email);
  }
  const names = stageAttachments(email, "court-response").map((attachment) => attachment.name);
  names.push(templateFileName("Notice of Acting", email.referral.surname));
  return names;
}

function postHearingCourtAttachmentNames(email) {
  return stageAttachments(email, "post-hearing-sealed-order").map((attachment) => attachment.name);
}

function stageIncomingSaved(email, stage) {
  const attachments = stageAttachments(email, stage);
  return attachments.length > 0 && attachments.every((attachment) => attachment.saved);
}

function counselFeeNoteSaved(email) {
  const expected = String(counselFeeNoteName(email) || "").toLowerCase();
  return stageAttachments(email, "counsel-fee-note").some((attachment) =>
    Boolean(attachment.saved) && String(attachment.name || "").toLowerCase() === expected);
}

function isPostHearingInvoiceStep(email) {
  return Boolean(email && email.workspace.postHearingOrderSaved && email.workspace.postHearingProcessServerPrinted);
}

function initialServicePending(email) {

  return Boolean(email && email.workspace.courtHasOrder &&
    !email.workspace.postHearingOrderSaved && currentHearingRound(email) === 1);
}

function trainingStepLabel(step) {
  if (CF_HUMAN_LABEL[step]) return CF_HUMAN_LABEL[step];
  if (CF_EXPLAIN[step]) return CF_EXPLAIN[step];
  return "Caseflow is working on this case.";
}

function nextTrainingStep(email) {
  if (!email || email.workspace.finalComplete) return null;
  const ws = email.workspace;
  const state = validationState(email);
  const stage = ws.inboxStage || REFERRAL_STAGE;

  if (!state.rootExists) return "create-folder";
  if (stage === REFERRAL_STAGE) {
    if (!state.introSaved) return "print-intro";
    if (!state.docsExtracted) return "extract-zip";
    if (!state.laaEvidenceFiled) return "file-laa";
    return "client-email";
  }
  if (stage === "client-response") {
    if (!state.signedDocsFiled) return "save-client-docs";
    if (!ws.clientResponsePrinted) return "print-client-response";
  }
  if (!ws.courtApplicationPrinted) return "court-email";
  if (stage === "court-response") {
    if (!state.courtAttachmentsFiled) return "save-court-docs";
    if (!ws.courtResponsePrinted) return "print-court-response";
  }
  if (!draftPrinted(email, "order-client")) return "order-client";
  if (initialServicePending(email)) {
    if (!ws.processServerRequestPrinted) return "process-server-request";
    if (!ws.processServerResponsePrinted) {
      if (stage !== "process-server-response") return "process-server-response";
      if (!stageIncomingSaved(email, "process-server-response")) return "process-server-response";
      return "process-server-response";
    }
    if (!processServerInvoiceSaved(email) || !ws.processServerInvoiceEmailPrinted) {
      if (stage !== "process-server-invoice") return "process-server-invoice";
      if (!processServerInvoiceSaved(email)) return "save-process-server-invoice";
      return "print-process-server-invoice";
    }
  }
  if (!ws.counselRequestPrinted) return "counsel-request";
  if (stage === "counsel-response" && !ws.counselOfferPrinted) return "print-counsel-offer";
  if (!ws.counselBriefPrinted) return "brief-counsel";
  if (!ws.courtBundlePrinted) return "court-bundle";
  if (!ws.bundleCreated) return "build-bundle";
  if (stage === "counsel-hearing-response" && !ws.hearingCounselDocsSaved) return "save-counsel-hearing-docs";
  if (stage === "post-hearing-sealed-order" && !ws.postHearingOrderSaved) return "save-post-hearing-order";
  if (ws.postHearingOrderSaved) {
    if (!counselFeeNoteSaved(email) || !ws.counselFeeNoteEmailPrinted) {
      if (stage !== "counsel-fee-note") return "counsel-fee-note";
      if (!counselFeeNoteSaved(email)) return "save-counsel-fee-note";
      return "print-counsel-fee-note";
    }
    if (!ws.postHearingOrderClientPrinted) return "post-order-client";
    if (serviceRequired(email) && !ws.postHearingProcessServerPrinted) return "post-process-server";
    if (serviceRequired(email)) {
      if (!ws.processServerResponsePrinted) {
        if (stage !== "process-server-response") return "post-process-server-response";
        if (!stageIncomingSaved(email, "process-server-response")) return "post-process-server-response";
        return "post-process-server-response";
      }
      if (!processServerInvoiceSaved(email) || !ws.processServerInvoiceEmailPrinted) {
        if (stage !== "process-server-invoice") return "post-process-server-invoice";
        if (!processServerInvoiceSaved(email)) return "save-post-process-server-invoice";
        return "print-post-process-server-invoice";
      }
    }
    if (currentPostHearingCycleComplete(email)) return "advance-hearing";
  }
  return null;
}

function ensureTrainingInboxStage(email, stage) {
  if (!email || !stage || stage === REFERRAL_STAGE) return;
  if ((email.workspace.inboxStage || REFERRAL_STAGE) !== stage) {
    switchIncomingStage(email, stage);
  }
}

function guideTrainingStep(email, { openDrafts = false, forceStatus = false } = {}) {
  if (!email) return;
  repairReadyCounselHearingStage(email);
  const step = nextTrainingStep(email);
  if (!step) return;
  if (step === "advance-hearing" && advanceHearingLoopIfReady(email)) {
    return;
  }
  if (step === "process-server-response" || step === "post-process-server-response") {
    ensureTrainingInboxStage(email, "process-server-response");
  }
  if (step === "process-server-invoice" || step === "post-process-server-invoice" ||
      step === "save-process-server-invoice" || step === "print-process-server-invoice" ||
      step === "save-post-process-server-invoice" || step === "print-post-process-server-invoice") {
    ensureTrainingInboxStage(email, "process-server-invoice");
  }
  if (step === "counsel-fee-note" || step === "save-counsel-fee-note" || step === "print-counsel-fee-note") {
    ensureTrainingInboxStage(email, "counsel-fee-note");
  }
  if (openDrafts) {
    if (step === "counsel-request") openSavedDraft(email, "counsel");
    if (step === "brief-counsel") openSavedDraft(email, hearingDraftType(email, "brief-counsel"));
    if (step === "court-bundle") openSavedDraft(email, hearingDraftType(email, "court-bundle"));
    if (step === "post-order-client") openSavedDraft(email, hearingDraftType(email, "post-order-client"));
    if (step === "post-process-server") openSavedDraft(email, hearingDraftType(email, "post-process-server"));
  }
  if (forceStatus || email.workspace.lastGuidedStep !== step) {
    email.workspace.lastGuidedStep = step;
    setStatus(trainingStepLabel(step));
  }
}

function canShowCourtFollowUps(email) {
  return email.workspace.courtResponsePrinted &&
    courtAttachmentsSaved(email);
}

function initialServiceComplete(email) {
  if (!serviceRequired(email)) return true;

  if (currentHearingRound(email) > 1 || email.workspace.postHearingOrderSaved) return true;
  return Boolean(
    email.workspace.processServerRequestPrinted &&
    email.workspace.processServerResponsePrinted &&
    email.workspace.processServerInvoiceEmailPrinted &&
    processServerInvoiceSaved(email)
  );
}

function readyForHearingBundle(email) {
  return Boolean(email && canShowCourtFollowUps(email) && initialServiceComplete(email));
}

function draftPrinted(email, type) {
  const drafts = email.workspace.drafts || {};
  const kind = draftKind(type);
  return Object.entries(drafts).some(([key, draft]) => draftKind(key) === kind && Boolean(draft && draft.printed));
}

function processServerInvoiceSaved(email) {

  const expected = String(processServerInvoiceName(email) || "").toLowerCase();
  return stageAttachments(email, "process-server-invoice").some((attachment) =>
    Boolean(attachment.saved) && String(attachment.name || "").toLowerCase() === expected);
}

function markDraftCompleteForTraining(email, type) {
  const draft = clientDraftFor(email, type);
  draft.sent = true;
  draft.printed = true;
  draft.open = false;
}

function prepareProcessServerInvoiceJump(email) {
  if (!email) return;
  email.workspace.courtApplicationPrinted = true;
  email.workspace.courtResponsePrinted = true;
  ensureCourtResponse(email);
  if (!courtAttachmentsSaved(email)) {
    markStageAttachmentsSaved(email, "court-response");
  }
  markDraftCompleteForTraining(email, "order-client");
  if (serviceRequired(email)) {
    email.workspace.processServerRequestPrinted = true;
    email.workspace.processServerResponsePrinted = true;
  }
  email.workspace.processServerInvoiceEmailPrinted = false;
  email.workspace.lastGuidedStep = null;
  email.workspace.counselRequestPrinted = false;
  email.workspace.counselOfferPrinted = false;
  email.workspace.bundleCreated = false;
  email.workspace.counselBriefPrinted = false;
  email.workspace.courtBundlePrinted = false;
}

function prepareCounselFeeNoteJump(email) {
  if (!email) return;
  email.workspace.hearingCounselDocsSaved = true;
  email.workspace.postHearingOrderSaved = true;
  email.workspace.courtBundlePrinted = true;
  email.workspace.counselFeeNoteSaved = false;
  email.workspace.counselFeeNoteEmailPrinted = false;
  email.workspace.postHearingOrderClientPrinted = false;
  email.workspace.postHearingProcessServerPrinted = false;
  email.workspace.processServerResponsePrinted = false;
  email.workspace.processServerInvoiceEmailPrinted = false;
  email.workspace.lastGuidedStep = null;
  resetIncomingStage(email, "post-hearing-sealed-order");
  switchIncomingStage(email, "post-hearing-sealed-order");

  stageAttachments(email, "post-hearing-sealed-order").forEach((attachment) => {
    snapshotFile(email, courtOrdersName(email.referral, attachment.name), attachment.name);
  });
  markStageAttachmentsSaved(email, "post-hearing-sealed-order");
}

function handleCounselFeeNoteProgress(email) {
  if (!email || !counselFeeNoteSaved(email) || !email.workspace.counselFeeNoteEmailPrinted) {
    return false;
  }

  if ((email.workspace.inboxStage || REFERRAL_STAGE) === "counsel-fee-note") {
    switchIncomingStage(email, "post-hearing-sealed-order");
  }
  guideTrainingStep(email, { openDrafts: true, forceStatus: true });
  return true;
}

function handleProcessServerInvoiceProgress(email) {
  if (!email || !email.workspace.processServerInvoiceEmailPrinted || !processServerInvoiceSaved(email)) {
    return false;
  }
  if (isPostHearingInvoiceStep(email) && advanceHearingLoopIfReady(email)) {
    return true;
  }
  if (!initialServicePending(email) && !isPostHearingInvoiceStep(email)) {
    switchIncomingStage(email, "court-response");
    email.workspace.lastGuidedStep = null;
  }
  guideTrainingStep(email, { openDrafts: true, forceStatus: true });
  return true;
}

function currentPostHearingCycleComplete(email) {
  if (!email || currentHearingRound(email) < 1) return false;
  return Boolean(
    email.workspace.postHearingOrderSaved &&
    email.workspace.postHearingOrderClientPrinted &&
    email.workspace.postHearingProcessServerPrinted &&
    processServerInvoiceSaved(email) &&
    email.workspace.processServerInvoiceEmailPrinted &&
    email.workspace.counselFeeNoteSaved &&
    email.workspace.counselFeeNoteEmailPrinted
  );
}

function resetForNextHearing(email) {
  email.workspace.hearingRound = currentHearingRound(email) + 1;
  email.workspace.lastGuidedStep = null;
  email.workspace.bundleCreated = false;
  email.workspace.bundleSections = null;
  email.workspace.courtBundlePrinted = false;
  email.workspace.counselBriefPrinted = false;
  email.workspace.hearingCounselDocsSaved = false;
  email.workspace.postHearingOrderSaved = false;
  email.workspace.postHearingOrderClientPrinted = false;
  email.workspace.postHearingProcessServerPrinted = false;
  email.workspace.counselFeeNoteSaved = false;
  email.workspace.counselFeeNoteEmailPrinted = false;
  email.workspace.processServerResponsePrinted = false;
  email.workspace.processServerInvoiceEmailPrinted = false;
  ["counsel-hearing-response", "post-hearing-sealed-order", "counsel-fee-note", "process-server-response", "process-server-invoice"].forEach((stage) => resetIncomingStage(email, stage));
  Object.keys(email.workspace.drafts || {}).forEach((key) => {
    if (/^(brief-counsel|court-bundle|post-order-client|post-process-server)(?:-\d+)?$/.test(key)) {
      delete email.workspace.drafts[key];
    }
  });

  switchIncomingStage(email, "court-response");
}

function advanceHearingLoopIfReady(email) {
  if (!currentPostHearingCycleComplete(email)) return false;
  if (isFinalHearingRound(email)) {
    finishMatter(email);
    email.workspace.finalComplete = true;
    setStatus("Final order workflow complete. The training matter has reached the final order stage.");
    showWinScreen(email);
    return true;
  }
  resetForNextHearing(email);
  guideTrainingStep(email, { openDrafts: true, forceStatus: true });
  return true;
}

function finishMatter(email) {
  const progress = progressFor(email);
  if (!progress.finishedAt) progress.finishedAt = Date.now();
}

function isClosed(email) {
  return Boolean(email && email.workspace.closedAs);
}

function closeCase(kind) {
  const email = activeEmail();
  if (!email) return;
  if (kind === "open") {
    email.workspace.closedAs = null;
    setStatus("The case is open again.");
    render();
    return;
  }
  if (!CLOSED_LABELS[kind]) return;
  email.workspace.closedAs = kind;
  setStatus(`The case is closed as ${CLOSED_LABELS[kind].toLowerCase()}. Caseflow no longer works on it.`);
  render();
}

function renderWinScreenHtml(email) {
  return `
    <div class="win-screen-title">${escapeHtml(email.referral.applicant)} complete</div>
    <div>The matter has reached the final order stage.</div>
  `;
}

function showWinScreen(email) {
  showModal("Matter complete", `<div class="win-summary">${renderWinScreenHtml(email)}</div>`);
}

function renderWinScreenPane(email) {
  winScreen.innerHTML = renderWinScreenHtml(email);
}

function cloneNodeForMove(node) {
  return {
    ...node,
    id: `node-${nodeCounter++}`,
    sourceParentId: null,
    children: (node.children || []).map((child) => cloneNodeForMove(child))
  };
}

function fileLaaEvidence(email) {
  const laa = childByName(email.workspace.root, laaEvidenceName(email.referral, email), "folder");
  if (!laa) return [];
  const moved = [];
  collectUnfiled(email.workspace.root, laa.id, isLaaEvidenceCandidate).forEach((node) => {
    const parent = findParent(email.workspace.root, node.id);
    if (!parent) return;
    const copy = cloneNodeForMove(node);
    parent.children = parent.children.filter((child) => child.id !== node.id);
    if (!childByName(laa, copy.name, copy.type)) laa.children.push(copy);
    moved.push({ file: copy.name, toId: laa.id });
  });
  if (moved.length) email.workspace.selectedId = laa.id;
  return moved;
}

function selectFolder(folderId) {
  const email = activeEmail();
  if (!email) return;
  const folder = findNode(email.workspace.root, folderId);
  if (!folder || folder.type !== "folder") return;
  email.workspace.selectedId = folderId;
  render();
}

function toggleFolder(folderId) {
  const email = activeEmail();
  if (!email) return;
  const folder = findNode(email.workspace.root, folderId);
  if (!folder || folder.type !== "folder") return;
  if ((folder.children || []).length) {
    folder.collapsed = !folder.collapsed;
  }
  email.workspace.selectedId = folderId;
  render();
}

function attachmentAllowedForDraft(draft, node) {
  const name = nameKey(node.name);
  const type = draftKind(draft.type || "client");
  if (type === "client") {
    return isLetterOfAuthorityKey(name) || isWitnessStatementKey(name);
  }
  if (type === "court") {
    if (isDraftOrderKey(name)) return true;
    if (isNoticeOfActingKey(name)) return true;
    if (isWitnessStatementKey(name)) return true;
    if (name.includes("fl401") || name.includes("c100") || name.includes("c1a")) return true;
    if (/^c8\b/.test(name)) return true;
    return false;
  }
  if (type === "order-client") {
    return name.includes("notice of hearing") || name.includes("order") || name.startsWith("sealed ") || name.includes("fl401") || name.includes("c100") || name.includes("c1a");
  }
  if (type === "process-server") {
    return processServerRequiredNames(activeEmail(), type).some((required) => nameKey(required) === name) ||
      isNoticeOfActingKey(name);
  }
  if (type === "post-process-server" || type === "post-order-client") {
    return postHearingCourtAttachmentNames(activeEmail()).some((attachmentName) => nameKey(attachmentName) === name);
  }
  if (type === "brief-counsel") {
    return name.includes("brief to counsel") ||
      name.includes("chronology") ||
      name.includes("case summary");
  }
  if (type === "court-bundle") {
    return name.includes("hearing bundle") && attachmentExt(node.name) === "pdf";
  }
  return true;
}

function attachNodeToClientDraft(nodeId) {
  const email = activeEmail();
  if (!email || !email.workspace.root) return;
  const node = findNode(email.workspace.root, nodeId);
  const draft = clientDraftFor(email);
  if (!node || !isDraftAttachmentCandidate(node) || !attachmentAllowedForDraft(draft, node)) {
    clientDraftStatus.textContent = draftConfig(draft.type || "client", email).dropText;
    return;
  }
  const kind = draftAttachmentKind(node);
  const ext = nodeExtension(node);
  if (!kind || !["doc", "docx", "pdf"].includes(ext)) {
    clientDraftStatus.textContent = draftConfig(draft.type || "client", email).dropText;
    return;
  }
  if (!draft.attachments.some((item) => item.name === node.name)) {
    draft.attachments.push({ name: node.name, kind, ext });
  }
  draft.sent = false;
  render();
}

function attachGeneratedBundleToClientDraft() {
  const email = activeEmail();
  if (!email) return;
  const draft = clientDraftFor(email);
  const node = hearingBundleObject(email);
  if (!node || !bundleReady(email) || !attachmentAllowedForDraft(draft, node)) {
    clientDraftStatus.textContent = draftConfig(draft.type || "client", email).dropText;
    return;
  }
  const kind = draftAttachmentKind(node);
  const ext = nodeExtension(node);
  if (!draft.attachments.some((item) => item.name === node.name)) {
    draft.attachments.push({ name: node.name, kind, ext });
  }
  draft.sent = false;
  render();
}

function attachTemplateToClientDraft(templateName) {
  const email = activeEmail();
  if (!email) return;
  const template = templateByName(templateName);
  const draft = clientDraftFor(email);
  if (!template || !templateAllowedForMatter(email.referral, templateName)) {
    clientDraftStatus.textContent = draftConfig(draft.type || "client", email).dropText;
    return;
  }
  const node = {
    name: templateFileName(templateName, email.referral.surname),
    type: "file"
  };
  if (!attachmentAllowedForDraft(draft, node)) {
    clientDraftStatus.textContent = draftConfig(draft.type || "client", email).dropText;
    return;
  }
  const kind = draftAttachmentKind(node);
  const ext = nodeExtension(node) || template.ext;
  if (!draft.attachments.some((item) => item.name === node.name)) {
    draft.attachments.push({ name: node.name, kind, ext });
  }
  draft.sent = false;
  render();
}

function sendClientDraft() {
  const email = activeEmail();
  if (!email) return;
  const draft = clientDraftFor(email);
  if (!clientDraftReady(draft)) return;
  draft.sent = true;
  render();
  setStatus("Sent. Caseflow carries on and files the email as a PDF.");
}

function handleInboxClick(target) {
  const deleteButton = target.closest("[data-delete-email]");
  if (deleteButton) {
    deleteEmail(deleteButton.dataset.deleteEmail);
    return;
  }
  const row = target.closest("[data-email-id]");
  if (!row) return;
  activeEmailId = row.dataset.emailId;
  setStatus(`${incomingPresentation(activeEmail()).subject} selected.`);
  render();
}

function handleInboxKeydown(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  const main = event.target.closest(".email-main");
  if (!main) return;
  const row = event.target.closest("[data-email-id]");
  if (!row) return;
  event.preventDefault();
  activeEmailId = row.dataset.emailId;
  setStatus(`${incomingPresentation(activeEmail()).subject} selected.`);
  render();
}

function handleMessageClick(target) {
  const previewButton = target.closest("[data-preview-name]");
  if (previewButton) previewDocumentByName(previewButton.dataset.previewName);
}

function handleExplorerClick(target) {
  const extractButton = target.closest("[data-extract-zip]");
  if (extractButton) {
    extractZip(extractButton.dataset.extractZip);
    return;
  }
  const previewButton = target.closest("[data-preview-node]");
  if (previewButton) {
    const email = activeEmail();
    const node = email && email.workspace.root ? findNode(email.workspace.root, previewButton.dataset.previewNode) : null;
    if (node) previewDocumentByName(node.name);
    return;
  }
  const toggleButton = target.closest("[data-toggle-folder]");
  if (toggleButton) {
    toggleFolder(toggleButton.dataset.toggleFolder);
    return;
  }
  const folderLine = target.closest("[data-drop-folder]");
  if (folderLine) {
    selectFolder(folderLine.dataset.dropFolder);
    return;
  }
  const caseLine = target.closest("[data-case-email]");
  if (caseLine) {
    activeEmailId = caseLine.dataset.caseEmail;
    render();
  }
}

function handleExplorerKeydown(event) {
  const folderLine = event.target.closest("[data-drop-folder]");
  if (!folderLine) return;
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    selectFolder(folderLine.dataset.dropFolder);
  } else if (event.key === "ArrowRight") {
    const email = activeEmail();
    const folder = email ? findNode(email.workspace.root, folderLine.dataset.dropFolder) : null;
    if (folder && folder.type === "folder" && folder.collapsed) {
      event.preventDefault();
      toggleFolder(folderLine.dataset.dropFolder);
    }
  } else if (event.key === "ArrowLeft") {
    const email = activeEmail();
    const folder = email ? findNode(email.workspace.root, folderLine.dataset.dropFolder) : null;
    if (folder && folder.type === "folder" && !folder.collapsed) {
      event.preventDefault();
      toggleFolder(folderLine.dataset.dropFolder);
    }
  }
}

function attachEvents() {
  newMatterBtn.addEventListener("click", addMatterBatch);
  stageJumpSelect.addEventListener("change", (event) => {
    advanceSelectedMatter(event.target.value);
    event.target.value = "";
  });
  sortFoldersBtn.addEventListener("click", toggleFolderSort);
  resetAllBtn.addEventListener("click", () => {
    if (window.confirm("Reset all training data? This clears every matter and profile on this device and cannot be undone.")) {
      resetAllCases();
    }
  });
  clientDraftSendBtn.addEventListener("click", sendClientDraft);
  emailRows.addEventListener("click", (event) => handleInboxClick(event.target));
  emailRows.addEventListener("keydown", handleInboxKeydown);
  message.addEventListener("click", (event) => handleMessageClick(event.target));
  explorerTree.addEventListener("click", (event) => handleExplorerClick(event.target));
  explorerTree.addEventListener("keydown", handleExplorerKeydown);
  explorerTree.addEventListener("keydown", handleExplorerKeydown);
  modalCloseBtn.addEventListener("click", closeModal);
  modalBackdrop.addEventListener("click", (event) => {
    if (event.target === modalBackdrop) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modalBackdrop.classList.contains("visible")) {
      closeModal();
    }
  });
}

const DATA = {
  applicantFirst: ["Amina", "Bianca", "Clara", "Dalia", "Elena", "Farah", "Grace", "Hana", "Imani", "Jaya", "Kira", "Leila", "Maya", "Nadia", "Rosa", "Sofia", "Talia", "Zara"],
  surnames: ["Ashford", "Briar", "Calder", "Dacre", "Elwood", "Fenwick", "Greaves", "Harrow", "Ives", "Jenson", "Keane", "Lark", "Marlow", "Noble", "Orton", "Pryce", "Quill", "Rowan", "Sayer", "Vale"],
  respondentFirst: ["Aaron", "Ben", "Callum", "Darren", "Elliot", "Felix", "Grant", "Harvey", "Isaac", "Jonas", "Kieran", "Luca", "Miles", "Nathan", "Owen", "Ravi", "Simon", "Tomas"],
  childFirst: ["Amelie", "Bryn", "Cassia", "Dylan", "Elsie", "Finn", "Iris", "Jonah", "Lena", "Mira", "Noah", "Orla", "Theo"],
  streets: ["Training Lane", "Example Crescent", "Sample Street", "Practice Road", "Mockingbird Way", "Fiction Close", "Demo Court", "Placeholder Avenue"],
  towns: ["Example Fields", "Sampleford", "North Practice", "West Demo", "Fiction Green", "Training Cross"],
  banks: ["Northbridge Bank", "Harbour Bank", "Queens Trust", "Crown Bank", "Metro Central", "South City Bank", "Bridgewell Building Society"],
  benefits: ["Universal Credit", "Universal Credit and Child Benefit", "Income Support", "No benefits"],
  jobs: ["None", "Part-time wages GBP 620 pcm", "Zero-hours wages around GBP 440 pcm", "Statutory Sick Pay GBP 360 pcm"],
  maintenance: ["None", "GBP 80 pcm child maintenance", "Irregular cash maintenance", "Not paid"],
  childcare: ["None", "GBP 120 pcm nursery fees", "GBP 70 pcm breakfast club", "Informal family childcare"],
  cars: ["No car", "2011 Ford Fiesta", "2014 Nissan Note", "Shared car not available to applicant"],
  workPlaces: ["Example Depot, ZZ1", "Unknown", "Sample Retail Park, ZZ2", "Training Works, ZZ3", "Not stated"],
  counselTitles: ["Ms", "Mr", "Dr"],
  courtStreets: ["Practice Square", "Example Walk", "Training Street", "Sample Yard", "Fiction Court"],
  hearingTimes: ["10:00", "10:30", "11:00", "14:00"],

  orgPrefixes: ["North", "South", "East", "West", "Crown", "Queens", "Bridge", "Harbour", "New", "Green", "Stone", "Red", "Silver"],
  orgMidwords: ["gate", "well", "ford", "field", "worth", "stone", "dale", "wood", "bridge", "water", "moor", "hill", "cross"],
  lawFirmSuffixes: ["Family Solicitors", "Legal Practice", "Law Centre", "Family Law", "Solicitors"],
  chambersSuffixes: ["Family Chambers", "Court Chambers", "Legal Chambers", "Law Chambers", "Advocacy Chambers"],
  processServerSuffixes: ["Process Services", "Legal Support", "Service Bureau", "Document Service", "Process Agency"],
  referrerPrefixes: ["Primary", "Key", "Central", "Main", "First", "Direct", "Family"],
  referrerMidwords: ["Intake", "Referral", "Support", "Help", "Care", "Hub", "Gateway", "Service", "Court", "Legal"],
  referrerSuffixes: ["Team", "Unit", "Centre", "Hub", "Service", "Office", "Desk"]
};

const CF_COLUMNS = [
  { key: "folders", label: "Folders" },
  { key: "referral", label: "Referral papers" },
  { key: "laa", label: "LAA evidence" },
  { key: "client", label: "Client email" },
  { key: "court", label: "Court" },
  { key: "order", label: "Order to client" },
  { key: "service", label: "Service" },
  { key: "counsel", label: "Counsel" },
  { key: "bundle", label: "Bundle" },
  { key: "after", label: "After hearing" },
  { key: "concluded", label: "Concluded" },
  { key: "transferred", label: "Transferred" },
  { key: "dropped-out", label: "Dropped out" }
];

const CF_STEP_COLUMN = {
  "create-folder": "folders",
  "print-intro": "referral",
  "extract-zip": "referral",
  "file-laa": "laa",
  "client-email": "client",
  "save-client-docs": "client",
  "print-client-response": "client",
  "court-email": "court",
  "save-court-docs": "court",
  "print-court-response": "court",
  "order-client": "order",
  "process-server-request": "service",
  "process-server-response": "service",
  "process-server-invoice": "service",
  "save-process-server-invoice": "service",
  "print-process-server-invoice": "service",
  "counsel-request": "counsel",
  "print-counsel-offer": "counsel",
  "brief-counsel": "counsel",
  "court-bundle": "bundle",
  "build-bundle": "bundle",
  "save-counsel-hearing-docs": "after",
  "save-post-hearing-order": "after",
  "counsel-fee-note": "after",
  "save-counsel-fee-note": "after",
  "print-counsel-fee-note": "after",
  "post-order-client": "after",
  "post-process-server": "after",
  "post-process-server-response": "after",
  "post-process-server-invoice": "after",
  "save-post-process-server-invoice": "after",
  "print-post-process-server-invoice": "after",
  "advance-hearing": "after"
};

const CF_EXPLAIN = {
  "create-folder": "The system creates the client's folder with the standard subfolders, and one Attendance Notes and one Court Orders folder for each order type. It files the referral email as a PDF and the documents zip in Preliminary-Docs.",
  "print-intro": "The system files the referral email as a PDF in Preliminary-Docs.",
  "extract-zip": "The system saves the zip in Preliminary-Docs and unpacks it, keeping its folders.",
  "file-laa": "The system files the Legal Aid Agency evidence the referral email describes (benefit proof, payslips, bank statements, and mortgage statements where the client owns their home) in LAA-Evidence.",
  "client-email": "The system makes the Letter of Authority and the witness statement in their folders and drafts the email to the client with both attached. It is on the send gate's safelist, so it is sent automatically, in Auto or Manual. Every other email waits for a person to read the draft and press Send.",
  "save-client-docs": "The system saves the client's signed documents: the signed Letter of Authority in Preliminary-Docs and the signed witness statement in Client's-Docs.",
  "print-client-response": "The system files the client's reply as a PDF in Correspondences-with-Client.",
  "court-email": "The system makes the Notice of Acting and the draft order for each order type, and drafts the application email to the court with everything attached. A person reads it and presses Send.",
  "save-court-docs": "The system saves the court's sealed documents, each in the Court Orders folder for its own order type.",
  "print-court-response": "The system files the court's email as a PDF in Correspondences-with-Court.",
  "order-client": "The system drafts the email sending the order and the notice of hearing to the client. A person reads it and presses Send.",
  "process-server-request": "The system drafts the request to the process server with the court papers and the Notice of Acting. A person reads it and presses Send.",
  "process-server-response": "The system saves the process server's Statement of Service and files their email as a PDF.",
  "process-server-invoice": "The system saves the process server's invoice.",
  "save-process-server-invoice": "The system saves the process server's invoice.",
  "print-process-server-invoice": "The system files the process server's invoice email as a PDF.",
  "counsel-request": "The system drafts the request to counsel for availability. A person reads it and presses Send.",
  "print-counsel-offer": "The system files counsel's offer as a PDF in Correspondences-with-Counsel.",
  "brief-counsel": "The system makes the Brief to Counsel, the chronology and the case summary and drafts the email to counsel with them attached. A person reads it and presses Send.",
  "court-bundle": "The system drafts the email asking the court about the bundle for the next hearing. A person reads it and presses Send.",
  "build-bundle": "The system builds the hearing bundle from the sealed papers.",
  "save-counsel-hearing-docs": "The system saves counsel's papers from the hearing into the hearing folder.",
  "save-post-hearing-order": "The system saves the sealed order, each in the Court Orders folder for its type.",
  "counsel-fee-note": "The system saves counsel's fee note.",
  "save-counsel-fee-note": "The system saves counsel's fee note in Invoices-and-Fee-Notes.",
  "print-counsel-fee-note": "The system files counsel's fee-note email as a PDF.",
  "post-order-client": "The system drafts the email sending the sealed order to the client. A person reads it and presses Send.",
  "post-process-server": "The system drafts the email sending the sealed order to the process server. A person reads it and presses Send.",
  "post-process-server-response": "The system saves the process server's Statement of Service and files their email as a PDF.",
  "post-process-server-invoice": "The system saves the process server's invoice.",
  "save-post-process-server-invoice": "The system saves the process server's invoice.",
  "print-post-process-server-invoice": "The system files the process server's invoice email as a PDF.",
  "advance-hearing": "The system moves on to the next hearing, or finishes when the final order is made."
};

const CF_REAL = {
  "create-folder": "Real Caseflow: the record step logs the client, then the folder step makes the folder set and checks it against the standard layout.",
  "print-intro": "Real Caseflow: the folder step saves the referral email and the documents in the client's folder.",
  "extract-zip": "Real Caseflow: the folder step unpacks the zip and sorts the files. It also reads the C8 form's box for contact details the client wants kept back, and says whether it is filled, blank or unreadable.",
  "file-laa": "Real Caseflow: a person files the Legal Aid evidence, as here.",
  "client-email": "Real Caseflow: the statement step puts the witness statement into the firm's template and proofreads it, then the email step drafts the email with a Documenso signing link. If the client replies asking for changes, the amend step makes a new round. Nothing is sent without a person.",
  "save-client-docs": "Real Caseflow: signing in Documenso is the client's approval, and the signed Letter of Authority and statement are filed for you.",
  "print-client-response": "Real Caseflow: the client's reply is filed, and the amend step reads it: an approval moves on, a request for changes starts another round.",
  "court-email": "Real Caseflow: the court pack step makes the Notice of Acting, draft orders and forms, then the court email step drafts the application once. A court on the call-first list still gets its draft, with a line telling the person to phone the court before sending.",
  "save-court-docs": "Real Caseflow: the court reply step files the court's reply and each attachment it keeps in the right Court Orders folder.",
  "print-court-response": "Real Caseflow: the court reply step files the email as a PDF. A rejection is filed as an email only, and the step waits for the next reply.",
  "order-client": "Real Caseflow: the client papers step drafts the email with the court's papers and the hearing date, once the client's address has been checked against their name.",
  "process-server-request": "Real Caseflow: the serve step drafts the papers for personal service. It applies to family-law orders, and to a children order only when a person marks it.",
  "process-server-response": "Real Caseflow: the sos received step files the statement of service, and the sos to court step drafts the email sending it to the court.",
  "process-server-invoice": "Real Caseflow: the invoice is filed with the matter's other papers; it is not a separate step.",
  "save-process-server-invoice": "Real Caseflow: the invoice is filed with the matter's other papers; it is not a separate step.",
  "print-process-server-invoice": "Real Caseflow: the invoice is filed with the matter's other papers; it is not a separate step.",
  "counsel-request": "Real Caseflow: the book counsel step drafts a request to the chambers for each hearing. If chambers cannot be chosen from one match, a person chooses.",
  "print-counsel-offer": "Real Caseflow: counsel's acceptance is read from their reply and recorded on the hearing, which marks it as booked. A rejection makes the next nearest chambers due.",
  "brief-counsel": "Real Caseflow: the brief step drafts the Brief to Counsel for each hearing with counsel booked. Details the papers do not give stay marked TBC.",
  "court-bundle": "Real Caseflow: there is no separate step; the court is asked about the bundle by email outside the chain.",
  "build-bundle": "Real Caseflow: the bundle step builds the bundle once counsel is booked, or the working day before the hearing. A person's review of it is what bills its page count.",
  "save-counsel-hearing-docs": "Real Caseflow: counsel's papers are filed in the hearing folder.",
  "save-post-hearing-order": "Real Caseflow: the court reply step files the sealed order.",
  "counsel-fee-note": "Real Caseflow: counsel's fee note is filed in Invoices-and-Fee-Notes.",
  "save-counsel-fee-note": "Real Caseflow: counsel's fee note is filed in Invoices-and-Fee-Notes.",
  "print-counsel-fee-note": "Real Caseflow: counsel's fee-note email is filed as a PDF.",
  "post-order-client": "Real Caseflow: the mid letter step drafts the court outcome letter for each hearing, with an email to the client. It waits for a person to fix the letter if the check finds a fault.",
  "post-process-server": "Real Caseflow: the serve step drafts the sealed order for service in the same way as the first time.",
  "post-process-server-response": "Real Caseflow: the sos received and sos to court steps file and send each statement of service.",
  "post-process-server-invoice": "Real Caseflow: the invoice is filed with the matter's other papers.",
  "save-post-process-server-invoice": "Real Caseflow: the invoice is filed with the matter's other papers.",
  "print-post-process-server-invoice": "Real Caseflow: the invoice is filed with the matter's other papers.",
  "advance-hearing": "Real Caseflow: at the end the closing letter step drafts the closing client care letter, once the matter's folder is under Concluded. The client care letter step covers the opening letter."
};

const CF_HUMAN_LABEL = {
};
const CF_SEND_LABEL = "Your turn: read the draft, then press Send. Caseflow sends only the safelist emails by itself.";

function cfWalk(node, out = []) {
  if (!node) return out;
  out.push(node);
  (node.children || []).forEach((child) => cfWalk(child, out));
  return out;
}

function cfNodes(email, pattern) {
  return cfWalk(email.workspace.root).filter((node) => pattern.test(node.name || ""));
}

function cfFolder(email, expectedName) {
  return cfWalk(email.workspace.root).find((node) => node.type === "folder" && folderMatches(email, node, expectedName)) || null;
}

function cfSelect(email, expectedName) {
  const folder = cfFolder(email, expectedName);
  if (folder) email.workspace.selectedId = folder.id;
  return folder;
}

function cfModalOpen() {
  return modalBackdrop.classList.contains("visible");
}

function cfBlocked(email) {
  return cfModalOpen() && !email.workspace.finalComplete;
}

function cfIncomingFolderName(email, attachment) {
  const stage = email.workspace.inboxStage;
  return {
    "client-response": clientResponseHome(email.referral, attachment && attachment.name),
    "court-response": courtOrdersName(email.referral, attachment && attachment.name),
    "process-server-response": processServerName(email.referral),
    "process-server-invoice": invoicesName(email.referral),
    "counsel-hearing-response": currentHearingFolderName(email),
    "post-hearing-sealed-order": courtOrdersName(email.referral, attachment && attachment.name),
    "counsel-fee-note": invoicesName(email.referral)
  }[stage] || preliminaryName(email.referral);
}

function cfDraftTypeFor(email, step) {
  const round = currentHearingRound(email);
  switch (step) {
    case "client-email": return canShowRevision(email) ? `revision-${email.workspace.statementRevision + 1}` : canShowDocusign(email) ? "docusign" : "client";
    case "save-client-docs": return canShowRevision(email) ? `revision-${email.workspace.statementRevision + 1}` : canShowDocusign(email) ? "docusign" : null;
    case "court-email": return "court";
    case "order-client": return "order-client";
    case "process-server-request": return "process-server";
    case "counsel-request": return "counsel";
    case "brief-counsel": return `brief-counsel-${round}`;
    case "court-bundle": return `court-bundle-${round}`;
    case "post-order-client": return `post-order-client-${round}`;
    case "post-process-server": return `post-process-server-${round}`;
    default: return null;
  }
}

function caseflowColumnFor(email) {
  if (email.workspace.closedAs) return email.workspace.closedAs;
  if (email.workspace.finalComplete || progressFor(email).finishedAt) return "concluded";
  const step = nextTrainingStep(email);
  return CF_STEP_COLUMN[step] || "after";
}

function caseflowWaiting(email) {
  if (!email || email.workspace.finalComplete || email.workspace.closedAs) return false;
  const step = nextTrainingStep(email);
  const type = cfDraftTypeFor(email, step);
  if (!type) return false;
  const draft = (email.workspace.drafts || {})[type];
  return Boolean(draft && !draft.sent && clientDraftReady(draft));
}

function caseflowStepInfo(email) {
  if (!email) return null;
  if (email.workspace.closedAs) {
    return { step: null, human: false, closed: email.workspace.closedAs, explain: "This case is closed. Caseflow leaves closed cases alone; reopening one puts it back at the step it was at." };
  }
  const step = nextTrainingStep(email);
  if (!step) return { step: null, human: false, done: true, explain: "The final order is made, so the case is concluded." };
  const human = caseflowWaiting(email);
  return { step, human, label: human ? (CF_HUMAN_LABEL[step] || CF_SEND_LABEL) : "Caseflow will do this next.", explain: CF_EXPLAIN[step] || "", real: CF_REAL[step] || "" };
}

function cfName(full) {
  const at = String(full).lastIndexOf(" ");
  return { name: full, first: full.slice(0, at), last: full.slice(at + 1) };
}

function cfAddress(text) {
  const [line1 = "", line2 = "", postcode = ""] = String(text || "").split(", ");
  return { line1, line2, postcode };
}

function cfClientDetails(referral) {
  const respondent = cfName(referral.respondent);
  return {
    ...cfName(referral.applicant),
    dob: referral.applicantDob,
    nino: referral.applicantNino,
    phone: referral.applicantPhone,
    address: cfAddress(referral.applicantAddress),
    respondent: {
      ...respondent,
      dob: referral.respondentDob,
      phone: referral.respondentPhone,
      address: cfAddress(referral.respondentAddress)
    },
    children: (referral.children || []).map((child) => ({
      name: child.name, dob: child.dob, pr: child.pr, sex: child.sex
    })),
    order: referral.orderRequired,
    court: referral.court && referral.court.name,
    caseReference: referral.court && referral.court.caseReference,
    c8: !!referral.c8
  };
}

function cfWaitingDraft(email) {
  const step = nextTrainingStep(email);
  const type = step ? cfDraftTypeFor(email, step) : null;
  if (!type) return null;
  const draft = (email.workspace.drafts || {})[type];
  if (!(draft && !draft.sent && clientDraftReady(draft))) return null;
  const config = draftConfig(type, email);
  return { type, subject: config.subject, to: config.to };
}

function caseflowBoard() {
  return {
    columns: CF_COLUMNS,
    cards: emails.map((email) => ({
      id: email.referral.id,
      name: email.referral.applicant,
      email: email.referral.applicantEmail,
      details: cfClientDetails(email.referral),
      column: caseflowColumnFor(email),
      waiting: caseflowWaiting(email),
      step: nextTrainingStep(email),
      draft: cfWaitingDraft(email),
      round: currentHearingRound(email),
      rounds: finalHearingRound(email),
      revision: email.workspace.statementRevision || 0,
      closedAs: email.workspace.closedAs || null,
      active: email.referral.id === activeEmailId
    }))
  };
}

function cfSetFirstHearing(referral) {
  if (!referral || referral.firstHearingSet) return;
  const at = new Date(Date.now() + 5 * 60_000);
  const pad = (n) => String(n).padStart(2, "0");
  referral.court.hearingTime = `${pad(at.getHours())}:${pad(at.getMinutes())}`;
  const dates = hearingDatesFor(referral);
  dates[0] = { ...dates[0], date: isoDate(at) };
  referral.firstHearingSet = true;
}

function cfEvent(step, label, extra = {}) {
  return { kind: "auto", step, label, explain: CF_EXPLAIN[step] || "", real: CF_REAL[step] || "", ...extra };
}

function cfMakeAndAttach(email, templateName, made) {
  if (!templateAllowedForMatter(email.referral, templateName)) return;
  const folder = ensureFolder(email.workspace.root, destinationForTemplate(email, templateName));
  const fileName = templateFileName(templateName, email.referral.surname);
  let node = childByName(folder, fileName, "file");
  if (!node) {
    node = ensureFile(folder, fileName, "file");
    made.push({ file: fileName, toId: folder.id, folder: folder.name });
  }
  attachNodeToClientDraft(node.id);
}

function cfPrepareDraft(email, type, made = []) {
  openSavedDraft(email, type);
  const kind = draftKind(type);
  const attachByPattern = (pattern) => {
    const node = cfNodes(email, pattern).find((n) => n.type !== "folder");
    if (node) { attachNodeToClientDraft(node.id); return true; }
    return false;
  };
  if (kind === "client") {
    cfMakeAndAttach(email, "Letter of Authority", made);
    cfMakeAndAttach(email, "Witness Statement", made);
  } else if (kind === "court") {
    const referral = email.referral;
    if (referral.hasFamily) attachByPattern(/^FL401\b/i);
    if (referral.hasChildren) { attachByPattern(/^C100\b/i); attachByPattern(/^C1A\b/i); }
    if (referral.c8) attachByPattern(/^C8\b/i);
    cfMakeAndAttach(email, "Notice of Acting", made);
    referral.orderTypes.forEach((order) => {
      if (order.key === "nmo") cfMakeAndAttach(email, "Draft Non-Molestation Order", made);
      if (order.key === "oo") cfMakeAndAttach(email, "Draft Occupation Order", made);
      if (order.key === "pso") cfMakeAndAttach(email, "Draft Prohibited Steps Order", made);
    });
    if (!attachByPattern(/^(WS\.SIGNED|Witness Statement)\b.*signed|^WS\.SIGNED/i)) {
      attachByPattern(/witness[\s._-]statement|^WS\./i);
    }
  } else if (kind === "order-client") {
    attachByPattern(/^Notice of Hearing\b/i);
    if (email.workspace.courtHasOrder) {
      orderDocumentNames(email.referral).forEach((name) => {
        attachByPattern(new RegExp("^" + escapeRegExp(name) + "$", "i"));
      });
    }
  } else if (kind === "process-server") {
    processServerRequiredNames(email, kind).forEach((name) => {
      if (!attachByPattern(new RegExp("^" + escapeRegExp(name) + "$", "i")) && isNoticeOfActingKey(nameKey(name))) {
        cfMakeAndAttach(email, "Notice of Acting", made);
      }
    });
  } else if (kind === "post-process-server" || kind === "post-order-client") {
    postHearingCourtAttachmentNames(email).forEach((name) => {
      attachByPattern(new RegExp("^" + escapeRegExp(name) + "$", "i"));
    });
  } else if (kind === "brief-counsel") {
    cfMakeAndAttach(email, "Brief to Counsel", made);
    cfMakeAndAttach(email, "Chronology", made);
    cfMakeAndAttach(email, "Case Summary", made);
  }
  return clientDraftFor(email, type);
}

function cfBuildBundle(email) {
  addTemplateToBundleSection(email, "cover", "Cover Page");
  addTemplateToBundleSection(email, "summary", "Case Summary");
  addTemplateToBundleSection(email, "summary", "Chronology");
  const wants = [
    ["applications", /^SEALED-FL401\b/i],
    ["applications", /^SEALED-C100\b/i],
    ["applications", /^SEALED-C1A\b/i],
    ["applications", /^Notice of Hearing\b/i],
    ["applications", /^SEALED .* Order\b/i],
    ["statements", /^SEALED-WS\.SIGNED\b|^sealed witness statement\b/i],
    ["service", /^Statement of Service\b/i]
  ];
  for (const [section, pattern] of wants) {
    const seen = new Set();
    for (const node of cfNodes(email, pattern)) {
      if (node.type === "folder" || seen.has(node.name)) continue;
      seen.add(node.name);
      addNodeToBundleSection(email, section, node.id);
    }
  }
  if (!bundleReady(email)) return false;
  createBundle();
  return !cfBlocked(email);
}

function cfSaveIncoming(email, step) {
  const moves = [];
  for (const attachment of [...(email.workspace.incomingAttachments || [])]) {
    if (attachment.saved) continue;
    const folder = cfSelect(email, cfIncomingFolderName(email, attachment));
    if (!folder) return null;
    saveIncomingAttachment(email, folder, attachment.id);
    if (cfBlocked(email)) return null;
    moves.push({ file: attachment.name, toId: folder.id, folder: folder.name });
  }
  if (!moves.length) return null;
  const folders = [...new Set(moves.map((m) => m.folder))];
  const where = folders.length === 1 ? folders[0] : `${folders.length} folders (${folders.join(", ")})`;
  return cfEvent(step, `Saved ${moves.length === 1 ? "the attachment" : `${moves.length} attachments`} from the email into ${where}.`, {
    toId: moves[moves.length - 1].toId,
    files: moves.map((m) => m.file),
    moves
  });
}

function cfPrintIncoming(email, step, folderName) {
  const folder = cfSelect(email, folderName);
  if (!folder) return null;
  const subject = incomingPresentation(email).subject;
  saveIntroPdf();
  if (cfBlocked(email)) return null;
  return cfEvent(step, `Filed the email "${subject}" as a PDF in ${folder.name}.`, { toId: folder.id });
}

function caseflowNext(email) {
  if (!email) return { kind: "none", label: "Open a matter first." };
  const finish = (event) => {
    if (cfModalOpen()) closeModal();
    render();
    return event;
  };
  if (isClosed(email)) {
    return finish({
      kind: "closed",
      label: `This case is closed as ${CLOSED_LABELS[email.workspace.closedAs].toLowerCase()}. Caseflow does not work on closed cases.`,
      explain: "A case can end without reaching its final order: it is transferred, the client drops out, or it is concluded. Caseflow leaves closed cases alone; reopening one puts it back at the step it was at."
    });
  }
  guideTrainingStep(email);
  const step = nextTrainingStep(email);
  if (!step) {
    return finish({ kind: "done", label: "The matter has reached the final order stage.", explain: "The final order is made, so the case is concluded." });
  }
  const stuck = (why) => finish({ kind: "stuck", step, label: `Caseflow could not do this step on its own: ${why}` });

  if (step === "file-laa") {
    const moves = fileLaaEvidence(email);
    if (!moves.length) return stuck("the evidence is not in Preliminary-Docs");
    return finish(cfEvent(step, `Filed ${moves.length === 1 ? "the evidence" : `${moves.length} pieces of evidence`} in LAA-Evidence: ${moves.map((m) => m.file).join(", ")}.`, { toId: moves[0].toId, files: moves.map((m) => m.file), moves }));
  }

  const draftType = cfDraftTypeFor(email, step);
  if (step === "court-email") cfSetFirstHearing(email.referral);
  if (draftType) {
    const draft = clientDraftFor(email, draftType);
    if (!draft.sent) {
      if (!clientDraftReady(draft)) {
        const made = [];
        cfPrepareDraft(email, draftType, made);
        const ready = clientDraftFor(email, draftType);
        if (!clientDraftReady(ready)) return stuck("the draft could not be completed");
        const config = draftConfig(draftType, email);
        const madeNote = made.length ? `Made ${made.length === 1 ? "a document" : `${made.length} documents`} in ${[...new Set(made.map((m) => m.folder))].join(", ")}. ` : "";
        return finish(cfEvent(step, `${madeNote}Drafted "${config.subject}" with ${ready.attachments.length} document${ready.attachments.length === 1 ? "" : "s"} attached. Nothing has been sent.`, { files: ready.attachments.map((a) => a.name), moves: made }));
      }
      openSavedDraft(email, draftType);
      return finish({
        kind: "human",
        step,
        explain: CF_EXPLAIN[step] || "",
        label: CF_SEND_LABEL
      });
    }
    if (!draft.printed) {
      const config = draftConfig(draftType, email);
      openSavedDraft(email, draftType);
      const folder = cfSelect(email, config.printFolder);
      if (!folder) return stuck(`the folder ${config.printFolder} is missing`);
      saveClientEmailPdf();
      if (cfBlocked(email)) return stuck("the sent email could not be filed");
      return finish(cfEvent(step, `Filed the sent email as a PDF in ${folder.name}.`, { toId: folder.id, files: [config.printName] }));
    }
  }

  let event = null;
  switch (step) {
    case "create-folder": {
      createRootFolder();
      const prelim = cfSelect(email, preliminaryName(email.referral));
      if (!prelim) return stuck("Preliminary-Docs is missing");
      saveIntroPdf();
      if (cfBlocked(email)) return stuck("the referral email could not be filed");
      dropZip(email, prelim);
      const zipNode = cfWalk(email.workspace.root).find((n) => n.type === "zip");
      if (!zipNode) return stuck("the referral zip could not be saved");
      const moves = [introPdfName(email.referral), zipNode.name].map((file) => ({ file, toId: prelim.id }));
      event = cfEvent(step, `Set up the client folder with its standard subfolders, then filed the referral email and the documents zip in ${prelim.name}.`, { toId: prelim.id, files: moves.map((m) => m.file), moves });
      break;
    }
    case "print-intro": {
      const folder = cfSelect(email, preliminaryName(email.referral));
      if (!folder) return stuck("Preliminary-Docs is missing");
      saveIntroPdf();
      if (cfBlocked(email)) return stuck("the referral email could not be filed");
      event = cfEvent(step, `Filed the referral email as a PDF in ${folder.name}.`, { toId: folder.id });
      break;
    }
    case "extract-zip": {
      const folder = cfSelect(email, preliminaryName(email.referral));
      if (!folder) return stuck("Preliminary-Docs is missing");
      let zipNode = cfWalk(email.workspace.root).find((n) => n.type === "zip");
      if (!zipNode) {
        dropZip(email, folder);
        zipNode = cfWalk(email.workspace.root).find((n) => n.type === "zip");
        if (!zipNode) return stuck("the referral zip could not be saved");
        event = cfEvent(step, `Saved the referral zip into ${folder.name}.`, { toId: folder.id, files: [zipNode.name] });
      } else {
        extractZip(zipNode.id);
        if (!zipNode.extracted) return stuck("the zip could not be unpacked");
        event = cfEvent(step, `Unpacked the referral zip inside ${folder.name}.`, { toId: folder.id });
      }
      break;
    }
    case "save-client-docs":
    case "save-court-docs":
    case "process-server-invoice":
    case "save-process-server-invoice":
    case "save-post-process-server-invoice":
    case "save-counsel-hearing-docs":
    case "save-post-hearing-order":
    case "counsel-fee-note":
    case "save-counsel-fee-note":
      event = cfSaveIncoming(email, step);
      break;
    case "process-server-response":
    case "post-process-server-response":
      event = stageIncomingSaved(email, "process-server-response")
        ? cfPrintIncoming(email, step, processServerName(email.referral))
        : cfSaveIncoming(email, step);
      break;
    case "print-client-response":
      event = cfPrintIncoming(email, step, clientCorrespondenceName(email.referral));
      break;
    case "print-court-response":
      event = cfPrintIncoming(email, step, courtCorrespondenceName(email.referral));
      break;
    case "print-process-server-invoice":
    case "print-post-process-server-invoice":
      event = cfPrintIncoming(email, step, effectiveFolderName(email, invoicesName(email.referral)));
      break;
    case "print-counsel-offer":
    case "print-counsel-fee-note":
      event = cfPrintIncoming(email, step, counselCorrespondenceName(email.referral));
      break;
    case "build-bundle":
      if (!cfBuildBundle(email)) return stuck("the bundle could not be built");
      event = cfEvent(step, "Built the hearing bundle from the sealed papers.");
      break;
    case "advance-hearing":
      if (!advanceHearingLoopIfReady(email)) return stuck("the next hearing is not ready");
      event = cfEvent(step, "Moved on to the next hearing.");
      break;
    default:
      return stuck(`there is no automatic action for "${step}"`);
  }
  if (!event) return stuck("the step did not complete");
  return finish(event);
}

loadTrainingState();
attachEvents();
render();

const EngineAPI = {
  env: __env,

  consts: { APP_BUILD, BUNDLE_SECTIONS },

  state: {
    get emails() { return emails; },
    set emails(v) { emails = v; },
    get activeEmailId() { return activeEmailId; },
    set activeEmailId(v) { activeEmailId = v; },
  },

  fns: {

    render, addMatterBatch, deleteEmail, activeEmail, renderChecklist, loadTrainingState, saveTrainingState,

    nextTrainingStep, guideTrainingStep, advanceHearingLoopIfReady, advanceSelectedMatter, currentHearingRound, serviceRequired, canShowDocusign, canShowRevision, finalHearingRound, stageIncomingSaved,

    progressFor, finishMatter,
    caseflowNext, caseflowBoard, caseflowWaiting, caseflowStepInfo,
    closeCase, isClosed,

    createRootFolder, toggleFolder, selectFolder, toggleFolderSort,
    findNode, folderMatches, effectiveFolderName, expectedFolderLabel, isLaaEvidenceCandidate,

    preliminaryName, clientDocsName, clientResponseHome, courtOrdersName, processServerName, invoicesName,
    currentHearingFolderName, clientCorrespondenceName, courtCorrespondenceName,
    counselCorrespondenceName, laaEvidenceName, zipName, templateFileName,
    orderDocumentNames, processServerRequiredNames, postHearingCourtAttachmentNames,
    escapeRegExp, incomingPresentation,

    saveIntroPdf, extractZip, dropZip, fileLaaEvidence, laaEvidenceComplete,
    saveIncomingAttachment,

    openDraft, attachTemplateToClientDraft, attachNodeToClientDraft, sendClientDraft, saveClientEmailPdf,
    clientDraftFor, clientDraftReady, draftConfig, draftKind,

    addNodeToBundleSection, addTemplateToBundleSection, createBundle,
    bundleReady, ensureBundleSections, bundleSectionReady,

    showModal, closeModal, previewDocumentByName, showWinScreen,
    resetAllCases,
    setStatus,
  },

  ui: {
    status() { return statusText.textContent; },
    modalVisible() { return modalBackdrop.classList.contains("visible"); },
    modalTitle() { return modalTitle.textContent || modalTitle.innerHTML; },
    modalText() { return String(modalBody.innerHTML || modalBody.textContent).replace(/<[^>]+>/g, ""); },
    draftOpen() { return clientDraftPane.classList.contains("visible"); },
  },

  helpers: {
    selectEmail(id) {

      activeEmailId = id;
      const email = activeEmail();
      if (!email) return;
      setStatus(`${incomingPresentation(email).subject} selected.`);
      render();
    },
    logAction(label) {
      actionLog.push({ at: new Date().toISOString(), action: String(label).slice(0, 60) });
      if (actionLog.length > 40) actionLog.shift();
    },
  },
};

  return EngineAPI;
}
