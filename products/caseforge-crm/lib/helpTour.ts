
export interface HelpStep {
  title: string;
  text: string;

  selector?: string;

  withText?: string;

  openMenu?: boolean;
}

const item = (id: string) => `[data-header-item="${id}"] [data-header-measure]`;

const menuStep = (title: string, text: string, selector: string, withText?: string): HelpStep => ({
  title: `Menu: ${title}`,
  text,
  selector,
  withText,
  openMenu: true,
});
const entry = ".app-drawer-quick-list-item";

const APPLICANT_STEP: HelpStep = {
  title: "Referral Info",
  text: "On a client page, the Referral Info line under the name opens the client's referral document, their intro or new client form, when one is on record.",
  selector: ".detail-subtitle",
};

const MENU_STEPS: HelpStep[] = [
  menuStep("Case Flow Board", "Every client as a card, in the column for the step they are at.", entry, "Case Flow Board"),
  menuStep("Scans", "What is waiting in Scanned Docs, for the whole firm. Read only.", entry, "Scans"),
  menuStep(
    "Notification Board",
    "Where older notifications go: Active, Dismissed (yours, or cleared after 7 days) and Hidden. The switch at the top flips to Automation: the automatic jobs' notices.",
    entry,
    "Notification Board",
  ),
  menuStep("Improve Classifier", "The labelling sheet for the mail classifier: say which kind each email is.", 'a[href$="/review-mail"]'),
  menuStep("Help", "Help runs this tour again.", entry, "Help"),
  menuStep("Client Lists", "Every client list, one tab each: To Check, Concluded, Frequent callers, Transferred, Dropped out, Removed, Merged, Waiting.", entry, "Client Lists"),
  menuStep("Demo", "The demo: a practice copy of the CRM with made-up clients, in a tab of its own. On the demo itself this tile is Home.", entry, "Demo"),
  menuStep("Home", "Back to the live CRM, in a tab of its own. Only the demo has this tile.", entry, "Home"),
  menuStep("Vergil", "The assistant: ask it about clients and matters. Opens in a tab of its own.", entry, "Vergil"),
  menuStep("E-Signatures", "E-signing of documents.", entry, "E-Signatures"),
  menuStep("Chambers Finder", "Finds barristers' chambers.", entry, "Chambers Finder"),
  menuStep("BundleTool", "Builds court bundles.", entry, "BundleTool"),
  menuStep("Envelope Guide", "Which envelope and stamp a letter needs.", entry, "Envelope Guide"),
  menuStep("Settings", "Your personal settings; a developer also has System health here. The theme picker (light, system or dark) sits just below it.", entry, "Settings"),
];

const win = (name: string) => `.demo-window[aria-label="${name}"]`;

export const HELP_STEPS: HelpStep[] = [
  {
    title: "Welcome to the demo",
    text: "This is the practice screen. Nothing here touches a real client, real email or real files, and anything you make disappears when the demo restarts.",
  },
  {
    title: "DEMO",
    text: "Press DEMO to open the training windows: Demo, Inbox, Email, Explorer and Case flow. Each case you start in them appears here as a client.",
    selector: ".header-demo",
  },
  {
    title: "Search",
    text: "Type a client's name, email, reference or matter number. Two letters are enough. Results appear underneath, and choosing one opens that client.",
    selector: ".search-input",
  },
  {
    title: "New client",
    text: "Makes a client and their matter folder.",
    selector: '[aria-label="New client"]',
  },
  {
    title: "Results",
    text: "Every client that matches your search. The three fixed practice clients are always here.",
    selector: ".results-pane",
  },
  {
    title: "Tabs",
    text: "One tab for each part of a client's file: details, hearings, billing, to-dos and more. Pick a client to see them.",
    selector: ".detail-tabs",
  },
  {
    title: "Case Flow",
    text: "The new-client steps in order. Each step says who acts next: Case flow does it, or you do. Run runs a step, Mark done records one you did yourself, and Reset forgets a step's mark and deletes nothing.",
    selector: ".detail-tab-button",
    withText: "Case Flow",
  },
  APPLICANT_STEP,
  {
    title: "Apps menu",
    text: "The nine squares. Quick lists, the Case flow board, Scans, Settings, Help, the demo windows and the other firm apps are all in here: the next steps open it and go through each line.",
    selector: ".app-drawer-trigger",
  },
  ...MENU_STEPS,
  {
    title: "Window: Demo",
    text: "Go to stage jumps a case ahead. Beside it, Hint lights the next thing to press and the bin resets everything. The plus in the Inbox bar makes a fake referral email.",
    selector: win("Demo"),
  },
  {
    title: "Window: Inbox",
    text: "Referral emails arrive here. Select one and open it in the New clients tray. Caseflow then does each job the system can do by itself and stops where you must act, which is reading and sending each drafted email.",
    selector: win("Inbox"),
  },
  {
    title: "Window: Email",
    text: "The selected email. Print it as a PDF and save its attachments, as in the real Case Flow's first steps.",
    selector: win("Email"),
  },
  {
    title: "Window: Explorer",
    text: "The matter's folders. Click a folder, then click a document to put it there. Every document has one home: a wrong place is refused and counts as a mistake.",
    selector: win("Explorer"),
  },
  {
    title: "Window: Case flow",
    text: "Each chip is a client, in the column of the step they are at. It moves along as Caseflow does its work.",
    selector: win("Case flow"),
  },
  {
    title: "Moving the windows",
    text: "Drag a title bar to move a window and any edge or corner to resize it. At the right of the bar, the dash shrinks it to a tab on the screen edge (press the tab to bring it back), the pin locks it on top and in place (it cannot be moved or resized until you unpin it), and the cross closes it. Double-click a title bar to put the window back where it started.",
    selector: ".fw-actions",
  },
  {
    title: "The floating tutorial card",
    text: "While a case runs, a card says what is happening and what you do next. Drag it by its top edge to wherever it is out of the way; the cross hides it until the next step.",
    selector: "#stepCard:not([hidden])",
  },
];

export const HEADER_HELP_STEPS: HelpStep[] = [
  {
    title: "CaseForge logo",
    text: "Returns to the Today folder: no search, no list and no client open.",
    selector: ".app-header-brand",
  },
  {
    title: "Calendar and Clients",
    text: "Calendar shows hearings by day. Inside the Calendar the same button reads Clients and takes you back to client search.",
    selector: item("view"),
  },
  {
    title: "Hearings Panel",
    text: "On the home page, this button opens the next fortnight's hearings in a window. Move, resize, pin (locks it) or shrink it to an edge tab. Double-click its title bar to reset it.",
    selector: ".teaser-launcher",
  },
  {
    title: "Flagged",
    text: "The clients flagged for attention, as a list.",
    selector: item("flagged"),
  },
  {
    title: "Starred",
    text: "The clients you have starred, as a list.",
    selector: item("starred"),
  },
  {
    title: "Notifications bell",
    text: "The one bell for every notification: complaints, updates, New client notices, statement, counsel and court replies. It shows the last 3 days; older ones are on the Notification board.",
    selector: item("bell"),
  },
  {
    title: "Tasks",
    text: "The firm's to-do list: yours, everyone's and one list per person. The number is what is overdue or due today.",
    selector: item("todo"),
  },
  {
    title: "Automation notices",
    text: "What the automatic jobs could not finish. These, and the system health alerts, are also on the Notification board under Automation.",
    selector: item("robot"),
  },
  {
    title: "New client",
    text: "Makes a client and their matter folder.",
    selector: item("newclient"),
  },
  APPLICANT_STEP,
  {
    title: "Apps menu",
    text: "The nine squares. The next steps open it and go through each line.",
    selector: ".app-drawer-trigger",
  },
  ...MENU_STEPS,
];

export function helpTargetExists(step: HelpStep, root: ParentNode = document): boolean {
  if (!step.selector) return false;
  return Array.from(root.querySelectorAll<HTMLElement>(step.selector)).some(
    (el) => !step.withText || (el.textContent ?? "").trim().toLowerCase().startsWith(step.withText.toLowerCase()),
  );
}

export function findHelpTarget(step: HelpStep, root: ParentNode = document): HTMLElement | null {
  if (!step.selector) return null;
  const candidates = Array.from(root.querySelectorAll<HTMLElement>(step.selector));
  const found = step.withText
    ? candidates.find((el) => (el.textContent ?? "").trim().toLowerCase().startsWith(step.withText!.toLowerCase()))
    : candidates[0];
  if (!found) return null;

  if (getComputedStyle(found).visibility === "hidden") return null;
  const box = found.getBoundingClientRect();
  return box.width > 0 && box.height > 0 ? found : null;
}

export function availableHelpSteps(root: ParentNode = document, menuIsOpenable = true, steps: HelpStep[] = HELP_STEPS): number[] {
  return steps.flatMap((step, index) => {
    if (!step.selector) return [index];
    if (step.openMenu) return menuIsOpenable && helpTargetExists(step, root) ? [index] : [];
    return findHelpTarget(step, root) ? [index] : [];
  });
}
