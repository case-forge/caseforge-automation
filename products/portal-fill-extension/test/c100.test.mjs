
import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { pageFor } from "../extension/answers.js";
import { fillPage } from "../extension/fill.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const BASE = "http://127.0.0.1:3000";
const signed = JSON.parse(await readFile(join(root, "lab/c100-sample-export.json"), "utf8"));
const sample = signed.body;
const OPTIONS = { pageMustShow: "", appearMs: 1500 };

const labUp = await fetch(`${BASE}/ping.json`, { signal: AbortSignal.timeout(2000) }).then(
  (response) => response.status < 500,
  () => false,
);
const lab = { skip: labUp ? false : "the digital C100 lab is not running on 127.0.0.1:3000" };

let copy, profile, context, worker, tab, applicantId;

async function startApplication(target) {
  await target.goto(`${BASE}/steps/opening/start_or_continue`);

  await Promise.all([
    target.waitForNavigation(),
    target.evaluate(() => document.querySelector('form[action="/session/bypass_postcode"]').requestSubmit()),
  ]);
}

const fillWithExtension = (url) =>
  worker.evaluate(
    async ({ data, url }) => {
      await chrome.storage.session.set({ held: { data, confirmed: true, trust: "lab", touched: Date.now() } });
      const [found] = await chrome.tabs.query({ url, active: true });
      return globalThis.caseforgeFillTab(found);
    },
    { data: sample, url: `${url}*` },
  );

async function makeApplicant(target) {
  await target.goto(`${BASE}/steps/applicant/names`);
  await target.locator("input[name*=first_name]").fill("Testa");
  await target.locator("input[name*=last_name]").fill("Testperson");
  await Promise.all([target.waitForNavigation(), target.locator('form[action*="/steps/"] button[type=submit]').first().click()]);
  await Promise.all([target.waitForNavigation(), target.getByRole("button", { name: "Continue" }).click()]);
  const id = target.url().match(/privacy_known\/([^/?#]+)/)[1];

  await target.goto(`${BASE}/steps/children/names`);
  await target.locator("input[name*=first_name]").fill("Testchild");
  await target.locator("input[name*=last_name]").fill("Testperson");
  await Promise.all([target.waitForNavigation(), target.locator('form[action*="/steps/"] button[type=submit]').first().click()]);
  return id;
}

before(async () => {
  if (lab.skip) return;

  copy = await mkdtemp(join(tmpdir(), "c100-fill-"));
  profile = await mkdtemp(join(tmpdir(), "c100-fill-profile-"));
  await cp(join(root, "extension"), copy, { recursive: true });
  const manifest = JSON.parse(await readFile(join(copy, "manifest.json"), "utf8"));
  await writeFile(join(copy, "manifest.json"), JSON.stringify({ ...manifest, host_permissions: [`${BASE}/*`] }));
  context = await chromium.launchPersistentContext(profile, {
    channel: "chromium",
    args: [`--disable-extensions-except=${copy}`, `--load-extension=${copy}`],
  });
  worker = context.serviceWorkers()[0] || (await context.waitForEvent("serviceworker"));
  tab = await context.newPage();
  await startApplication(tab);
  applicantId = await makeApplicant(tab);
});

after(async () => {
  await context?.close();
  if (copy) await rm(copy, { recursive: true, force: true });
  if (profile) await rm(profile, { recursive: true, force: true });
});

test("a page path in the export is matched whole, so children and applicant pages stay apart", () => {
  const data = { pages: { "/steps/abuse_concerns/details/children/sexual": [{ name: "x", type: "text", value: "a" }] } };
  assert.equal(pageFor(data, `${BASE}/steps/abuse_concerns/details/children/sexual?x=1`).name, "/steps/abuse_concerns/details/children/sexual");
  assert.match(pageFor(data, `${BASE}/steps/abuse_concerns/details/applicant/sexual`).error, /no answers/);
});

for (const [key, fields] of Object.entries(sample.pages)) {
  test(`${key}: every answer is filled, kept by the server, and still there on reload`, lab, async () => {
    const path = key.replace(":id", applicantId);
    await tab.goto(`${BASE}${path}`);
    assert.equal(new URL(tab.url()).pathname, path, "the page opened");

    const report = await fillWithExtension(`${BASE}${path}`);
    assert.equal(report.refused, "", report.refused);
    assert.deepEqual(report.failed, []);
    assert.deepEqual(report.absent, []);
    assert.equal(report.filled.length, fields.length);

    await Promise.all([tab.waitForNavigation(), tab.locator('form[action*="/steps/"] button[type=submit]').first().click()]);
    assert.doesNotMatch(tab.url(), /errors|invalid/);
    assert.equal(await tab.locator(".govuk-error-summary").count(), 0, "the server found nothing wrong with the answers");

    await tab.goto(`${BASE}${path}`);
    const kept = await tab.evaluate(() => {
      const form = [...document.forms].find((candidate) => /\/steps\//.test(candidate.action));
      const data = new FormData(form);
      return Object.fromEntries([...new Set([...data.keys()])].map((key) => [key, data.getAll(key)]));
    });
    for (const field of fields) {
      const want = field.type === "date" ? (([y, m, d]) => [String(Number(d)), String(Number(m)), y])(field.value.split("-")) : null;
      if (field.type === "date") {
        const base = field.name.slice(0, -1);
        assert.deepEqual(["3i", "2i", "1i"].map((mark) => kept[`${base}(${mark})]`]?.[0]), want, field.name);
      } else if (field.type === "checkbox") {
        assert.deepEqual([...(kept[`${field.name}[]`] ?? [])].filter(Boolean).sort(), [...field.value].sort(), field.name);
      } else {
        assert.equal(kept[field.name]?.at(-1), field.value, field.name);
      }
    }
  });
}

test("a person's own answer is left alone", lab, async () => {
  const path = "/steps/safety_questions/substance_abuse";
  await tab.goto(`${BASE}${path}`);
  await tab.locator('input[type=radio][value="no"]').check();
  const report = await fillWithExtension(`${BASE}${path}`);
  assert.deepEqual(report.left, ["steps_safety_questions_substance_abuse_form[substance_abuse]"]);
  assert.equal(await tab.locator('input[type=radio][value="no"]').isChecked(), true);
});

test("an unknown page of the export is refused", lab, async () => {
  await tab.goto(`${BASE}/steps/opening/consent_order`);
  const report = await fillWithExtension(`${BASE}/steps/opening/consent_order`);
  assert.match(report.refused, /no answers for this page/);
});
