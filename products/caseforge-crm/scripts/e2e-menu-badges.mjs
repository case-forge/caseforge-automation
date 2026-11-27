#!/usr/bin/env node

const base = process.env.BASE_URL || "http://127.0.0.1:3170";
const shots = process.env.SHOTS || "";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch();
let failures = 0;
for (const width of [390, 520, 700]) {
  for (const scheme of ["light", "dark"]) {
    const page = await browser.newPage({ viewport: { width, height: 800 }, colorScheme: scheme });
    await page.goto(base + "/", { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: /^Hide|^Close|^Dismiss/ }).first().click({ timeout: 300 }).catch(() => {});
    await page.locator("summary.app-drawer-trigger").click();
    await page.waitForTimeout(400);
    const entries = await page.evaluate(() =>
      [...document.querySelectorAll(".app-drawer-overflow button")].map((b) => ({ name: b.getAttribute("aria-label") || b.textContent.trim(), badge: b.querySelector(".header-view-badge, .attention-count")?.textContent ?? null })),
    );
    const inHeader = await page.evaluate(() => [...document.querySelectorAll(".header-view-button")].filter((b) => b.getBoundingClientRect().width > 0 && !b.closest("[data-collapsed='true']")).map((b) => b.getAttribute("aria-label")));
    const clients = entries.find((e) => /^Clients/.test(e.name));
    const calendar = entries.find((e) => /^Calendar/.test(e.name));
    const clientsInHeader = inHeader.some((n) => /^Clients/.test(n ?? ""));
    const ok = clientsInHeader || (clients?.badge === "2" && calendar?.badge === "4");
    console.log(`${ok ? "ok  " : "FAIL"} ${width}px ${scheme}: header has Clients=${clientsInHeader}; menu entries ${JSON.stringify(entries)}`);
    if (!ok) failures += 1;
    if (shots) await page.screenshot({ path: `${shots}/menu-${width}-${scheme}.png` });
    await page.close();
  }
}
await browser.close();
process.exit(failures ? 1 : 0);
