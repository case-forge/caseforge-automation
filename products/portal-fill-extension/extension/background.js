
import { keep, load, pageFor } from "./answers.js";
import { fillPage } from "./fill.js";

const APPEAR_MS = 1500;

export async function fillTab(tab) {
  const held = await load();
  if (!held) return { refused: "No answers are loaded. Paste the export first." };
  if (!held.confirmed) return { refused: "Tick to confirm the client before filling." };
  const page = pageFor(held.data, tab.url || "", held.trust);
  if (page.error) return { refused: page.error };
  await keep(held.data, true, held.trust);
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: fillPage,
    args: [page.fields, { pageMustShow: held.data.page_must_show || "", appearMs: APPEAR_MS }],
  });
  return { page: page.name, ...result };
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {

  if (sender.id !== chrome.runtime.id || sender.tab || message?.type !== "fill") return false;
  chrome.tabs
    .query({ active: true, lastFocusedWindow: true })
    .then(([tab]) => (tab ? fillTab(tab) : { refused: "No page is open." }))
    .catch((error) => ({ refused: `Could not fill this page: ${error.message}` }))
    .then(respond);
  return true;
});

chrome.commands.onCommand.addListener((command, tab) => {
  if (command === "fill-page" && tab) fillTab(tab).catch(() => {});
});

globalThis.caseforgeFillTab = fillTab;
