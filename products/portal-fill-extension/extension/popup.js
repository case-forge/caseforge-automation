import { clear, keep, load, parseExport } from "./answers.js";

const $ = (id) => document.getElementById(id);

function say(message, lines = []) {
  $("message").textContent = message;
  $("report").replaceChildren(...lines.map((line) => Object.assign(document.createElement("li"), { textContent: line })));
}

async function show() {
  const held = await load();
  $("empty").hidden = Boolean(held);
  $("loaded").hidden = !held;
  if (!held) return;
  $("c8").hidden = held.data.contains_c8 !== true;
  $("who").textContent = `Filling for: ${held.data.client.surname}, ${held.data.client.reference}`;
  $("confirm").checked = held.confirmed;
  $("fill").disabled = !held.confirmed;
}

$("load").addEventListener("click", async () => {
  const { data, trust, error } = await parseExport($("paste").value);
  $("paste").value = "";

  await navigator.clipboard.writeText("").catch(() => {});
  if (error) return say(error);
  await keep(data, false, trust);
  say("Loaded. Check the name, then tick.");
  await show();
});

$("confirm").addEventListener("change", async () => {
  const held = await load();
  if (held) await keep(held.data, $("confirm").checked, held.trust);
  await show();
});

$("clear").addEventListener("click", async () => {
  await clear();
  say("Cleared.");
  await show();
});

$("fill").addEventListener("click", async () => {
  const result = await chrome.runtime.sendMessage({ type: "fill" });
  if (result.refused) return say(result.refused);
  say(`${result.filled.length} answers filled on this page. Check every one before you continue.`, [
    ...result.failed.map((id) => `Did not take, type it yourself: ${id}`),
    ...result.left.map((id) => `Already answered, left alone: ${id}`),
    ...result.absent.map((id) => `Not on the page: ${id}`),
  ]);
});

show();
