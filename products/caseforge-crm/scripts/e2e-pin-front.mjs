#!/usr/bin/env node

const base = process.env.BASE_URL || "http://127.0.0.1:3170";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
let failures = 0;
const check = (ok, what) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
  if (!ok) failures += 1;
};

await page.goto(base + "/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
for (const name of [/^Hearings Panel/, /^What's New/, /^Improve Classifier/]) await page.getByRole("button", { name }).first().click();

await page.locator("[data-window-id='hearings-rail'] button").filter({ hasText: "Stub" }).first().click();
await page.waitForTimeout(800);
await page.getByRole("button", { name: "Show or hide the demo windows" }).click();
await page.waitForTimeout(1200);

const ids = await page.evaluate(() => [...document.querySelectorAll("[data-window-id]")].map((e) => e.dataset.windowId));
check(ids.length >= 8, `${ids.length} windows open: ${ids.join(", ")}`);

const topmostAtCentre = (id) =>
  page.evaluate((wid) => {
    const el = document.querySelector(`[data-window-id="${wid}"]`);
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && el.contains(hit);
  }, id);

const pin = (id) => page.locator(`[data-window-id="${id}"] .fw-action-pin`).first().evaluate((el) => el.click());

for (const id of ids) {
  await pin(id);
  await page.waitForTimeout(150);
  check(await topmostAtCentre(id), `${id}: topmost at its centre after Pin`);
}

for (const id of [...ids].reverse()) {
  await pin(id);
  await pin(id);
  await page.waitForTimeout(150);
  check(await topmostAtCentre(id), `${id}: topmost at its centre after pinning it again over other pinned windows`);
}
await browser.close();
if (failures) {
  console.log(`${failures} failed`);
  process.exit(1);
}
console.log("all windows come to the front when pinned");
