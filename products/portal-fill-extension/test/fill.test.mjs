
import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { ALLOWED_ORIGINS, ARRANGEMENTS, FORMAT, pageFor, specialArrangementsFields } from "../extension/answers.js";
import { fillPage } from "../extension/fill.js";
import { PORT, start } from "../mock/serve.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const BASE = `http://127.0.0.1:${PORT}/#/cases/case-details/0000/trigger/allegationsOfHarmRevised`;
const OPTIONS = { pageMustShow: "Testperson", appearMs: 1500 };
const NMO = "newOrdersNonMolestation";
const yes = (id, extra = {}) => ({ id, type: "yesno", value: "Yes", ...extra });
const no = (id) => ({ id, type: "yesno", value: "No" });

const PAGE_ONE = [yes("newAllegationsOfHarmYesNo")];
const PAGE_TWO = [
  yes("newAllegationsOfHarmDomesticAbuseYesNo"),
  no("newAllegationsOfHarmChildAbuseYesNo"),
  no("newAllegationsOfHarmChildAbductionYesNo"),
  yes("newAllegationsOfHarmSubstanceAbuseYesNo"),
  { id: "newAllegationsOfHarmSubstanceAbuseDetails", type: "textarea", value: "Synthetic detail.\nSecond line (paragraph 12).", conditional: true },
  no("newAllegationsOfHarmOtherConcerns"),
  yes(NMO),
  { id: `${NMO}DateIssued`, type: "date", value: "2025-03-04", conditional: true },
  { id: `${NMO}EndDate`, type: "date", value: "2026-03-03", conditional: true },
  yes(`${NMO}Current`, { conditional: true }),
  { id: `${NMO}CourtName`, type: "text", value: "Testtown Family Court", conditional: true },
  { id: `${NMO}CaseNumber`, type: "text", value: "TT25F00000", conditional: true },
  no("newOrdersOccupation"),
  ...["ForcedMarriageProtection", "Restraining", "OtherInjunctive", "UndertakingInPlace"].map((name) => ({ ...no(`newOrders${name}`), conditional: true })),
];
const EXPECTED = Object.fromEntries(PAGE_TWO.map((field) => [field.id, field.value]));

let server, browser, page;
const model = async (target = page) => JSON.parse(await target.locator("#model").innerText());
const run = (fields, options = OPTIONS, target = page) =>
  target.evaluate(`(${fillPage.toString()})(${JSON.stringify(fields)}, ${JSON.stringify(options)})`);
const answered = (values) => Object.fromEntries(Object.entries(values).filter(([, value]) => value !== null));

async function open(name, target = page) {
  await target.goto("about:blank");
  await target.goto(`${BASE}/${name}`);
  await target.locator("#model").waitFor();
}

async function openPageTwo(target = page) {
  await open("allegationsOfHarmRevised1", target);
  await target.evaluate(() => sessionStorage.clear());
  await open("allegationsOfHarmRevised1", target);
  await run(PAGE_ONE, OPTIONS, target);
  await open("allegationsOfHarmRevised2", target);
}

before(async () => {
  server = await start();
  browser = await chromium.launch();
  page = await browser.newPage();
});
after(async () => {
  await browser?.close();
  server?.close();
});

test("every answer on the page reaches the form, dates and dependent questions included", async () => {
  await openPageTwo();
  const report = await run(PAGE_TWO);
  assert.equal(report.refused, "");
  assert.deepEqual(report.failed, []);
  assert.deepEqual(report.absent, []);
  assert.equal(report.filled.length, PAGE_TWO.length);
  assert.deepEqual(answered(await model()), EXPECTED);
});

test("the check is real: a value written into a box without the events never reaches the form", async () => {
  await openPageTwo();
  await page.evaluate(() => {
    document.getElementById("newAllegationsOfHarmSubstanceAbuseYesNo_Yes").click();
  });
  await page.locator("#newAllegationsOfHarmSubstanceAbuseDetails").waitFor();
  await page.evaluate(() => {
    document.getElementById("newAllegationsOfHarmSubstanceAbuseDetails").value = "looks filled";
  });
  assert.equal(await page.locator("#newAllegationsOfHarmSubstanceAbuseDetails").inputValue(), "looks filled");
  assert.equal((await model()).newAllegationsOfHarmSubstanceAbuseDetails, null);
});

test("a date box told only of `input` stays empty in the form: it is read on `change`", async () => {
  await openPageTwo();
  await page.evaluate((id) => document.getElementById(`${id}_Yes`).click(), NMO);
  await page.locator(`#${NMO}DateIssued-day`).waitFor();
  await page.evaluate((id) => {
    for (const [part, value] of [["day", "4"], ["month", "3"], ["year", "2025"]]) {
      const box = document.getElementById(`${id}-${part}`);
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(box, value);
      box.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }, `${NMO}DateIssued`);
  assert.equal((await model())[`${NMO}DateIssued`], null);
});

test("a question that is always on the page and is missing stops the whole page", async () => {
  await openPageTwo();
  const report = await run([...PAGE_TWO, no("newQuestionThatIsNotThere")]);
  assert.match(report.refused, /This page has changed: newQuestionThatIsNotThere not found/);
  assert.deepEqual(answered(await model()), {});
});

test("a page that does not show the client's name is not filled", async () => {
  await openPageTwo();
  const report = await run(PAGE_TWO, { ...OPTIONS, pageMustShow: "Someoneelse" });
  assert.match(report.refused, /does not show "Someoneelse"/);
  assert.deepEqual(answered(await model()), {});
});

test("an answer a person has already given differently is left alone and reported", async () => {
  await openPageTwo();
  await page.locator("#newAllegationsOfHarmChildAbuseYesNo_Yes").click();
  const report = await run(PAGE_TWO);
  assert.deepEqual(report.left, ["newAllegationsOfHarmChildAbuseYesNo"]);
  assert.equal((await model()).newAllegationsOfHarmChildAbuseYesNo, "Yes");
});

test("a kind of field the tool does not fill stops the page: it never uploads", async () => {
  await openPageTwo();
  const report = await run([...PAGE_TWO, { id: `${NMO}Document`, type: "document", value: "x.pdf", conditional: true }]);
  assert.match(report.refused, /does not fill \(document\)/);
  assert.deepEqual(answered(await model()), {});
});

test("filling never leaves the page", async () => {
  await openPageTwo();
  const before = page.url();
  await run(PAGE_TWO);
  assert.equal(page.url(), before);
});

const sample = (expires) => ({
  format: FORMAT,
  client: { surname: "TESTPERSON", reference: "261012/99FL" },
  contains_c8: false,
  issued: new Date().toISOString(),
  expires,
  page_must_show: "Testperson",
  pages: { allegationsOfHarmRevised1: PAGE_ONE, allegationsOfHarmRevised2: PAGE_TWO },
});
const SOON = () => new Date(Date.now() + 30 * 60 * 1000).toISOString();

test("this build fills the local mock and no other address, the real portal included", () => {
  const data = sample(SOON());
  assert.deepEqual(ALLOWED_ORIGINS, [`http://127.0.0.1:${PORT}`, "http://127.0.0.1:3000"]);
  assert.equal(pageFor(data, `${BASE}/allegationsOfHarmRevised2`).name, "allegationsOfHarmRevised2");
  const tail = "/cases/case-details/0000/trigger/allegationsOfHarmRevised/allegationsOfHarmRevised2";
  for (const origin of ["https://manage-case.platform.hmcts.net", "https://apply-to-court-about-child-arrangements.service.justice.gov.uk", "http://localhost:8377", "http://127.0.0.1:9999"]) {
    assert.match(pageFor(data, `${origin}${tail}`).error, /not a page this tool fills/);
  }
  assert.match(pageFor(data, `${BASE}/somethingElse`).error, /no answers for this page/);
});

test("the shipped extension asks for no site access, no network and no clipboard read", async () => {
  const manifest = JSON.parse(await readFile(join(root, "extension/manifest.json"), "utf8"));
  assert.deepEqual(manifest.permissions.sort(), ["activeTab", "scripting", "storage"]);
  for (const key of ["host_permissions", "optional_host_permissions", "content_scripts", "externally_connectable", "update_url", "web_accessible_resources"]) {
    assert.equal(manifest[key], undefined, key);
  }
  assert.match(manifest.content_security_policy.extension_pages, /connect-src 'none'/);
  for (const name of ["background.js", "popup.js", "answers.js", "fill.js"]) {
    const source = await readFile(join(root, "extension", name), "utf8");
    assert.doesNotMatch(source, /\bfetch\(|XMLHttpRequest|WebSocket|sendBeacon|EventSource|importScripts|\beval\(/, name);
  }
});

test("loaded as a real extension, it fills the page from its own isolated script", async () => {

  const copy = await mkdtemp(join(tmpdir(), "portal-fill-"));
  const profile = await mkdtemp(join(tmpdir(), "portal-fill-profile-"));
  await cp(join(root, "extension"), copy, { recursive: true });
  const manifest = JSON.parse(await readFile(join(copy, "manifest.json"), "utf8"));
  await writeFile(join(copy, "manifest.json"), JSON.stringify({ ...manifest, host_permissions: [`http://127.0.0.1:${PORT}/*`] }));
  const context = await chromium.launchPersistentContext(profile, {
    channel: "chromium",
    args: [`--disable-extensions-except=${copy}`, `--load-extension=${copy}`],
  });
  try {
    const worker = context.serviceWorkers()[0] || (await context.waitForEvent("serviceworker"));
    const tab = await context.newPage();
    await openPageTwo(tab);
    const report = await worker.evaluate(async (data) => {
      await chrome.storage.session.set({ held: { data, confirmed: true, touched: Date.now() } });
      const [found] = await chrome.tabs.query({ url: "http://127.0.0.1/*", active: true });
      return globalThis.caseforgeFillTab(found);
    }, sample(SOON()));
    assert.equal(report.refused, "");
    assert.equal(report.page, "allegationsOfHarmRevised2");
    assert.deepEqual(report.failed, []);
    assert.deepEqual(answered(await model(tab)), EXPECTED);

    const unconfirmed = await worker.evaluate(async (data) => {
      await chrome.storage.session.set({ held: { data, confirmed: false, touched: Date.now() } });
      const [found] = await chrome.tabs.query({ url: "http://127.0.0.1/*", active: true });
      return globalThis.caseforgeFillTab(found);
    }, sample(SOON()));
    assert.match(unconfirmed.refused, /Tick to confirm the client/);
  } finally {
    await context.close();
    await rm(copy, { recursive: true, force: true });
    await rm(profile, { recursive: true, force: true });
  }
});

test("special arrangements: yes, then the four standard requests reach the text box, one per line", async () => {
  await open("attendingTheHearing1");
  await page.evaluate(() => sessionStorage.clear());
  await open("attendingTheHearing1");
  const fields = specialArrangementsFields(["video", "waitingRoom", "entrance", "screen"]);
  const report = await run(fields);
  assert.equal(report.refused, "");
  assert.deepEqual(report.failed, []);
  assert.deepEqual(report.filled, ["isSpecialArrangementsRequired", "specialArrangementsRequired"]);
  assert.deepEqual(answered(await model()), {
    isSpecialArrangementsRequired: "Yes",
    specialArrangementsRequired: Object.values(ARRANGEMENTS).join("\n"),
  });
});

test("special arrangements: none chosen answers No and leaves the text box off the page", async () => {
  await open("attendingTheHearing1");
  await page.evaluate(() => sessionStorage.clear());
  await open("attendingTheHearing1");
  const report = await run(specialArrangementsFields([]));
  assert.deepEqual(report.filled, ["isSpecialArrangementsRequired"]);
  assert.deepEqual(answered(await model()), { isSpecialArrangementsRequired: "No" });
  assert.equal(await page.locator("#specialArrangementsRequired").count(), 0);
});

test("special arrangements: an unknown request is refused rather than typed", () => {
  assert.throws(() => specialArrangementsFields(["helicopter"]), /Unknown arrangement/);
});
