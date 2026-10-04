import { chromium } from "@playwright/test";
const BASE = "http://localhost:4173";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
await page.goto(BASE, { waitUntil: "networkidle" });
await page.fill('input[autocomplete="organization"]', "platform");
await page.fill('input[autocomplete="username"]', "platform-admin");
await page.fill('input[autocomplete="current-password"]', "Tekarai-Demo-2026!");
await page.click('button[type="submit"]');
await page.waitForTimeout(3500);
await page.goto(`${BASE}/app/maintenance/asset-tree`, { waitUntil: "networkidle" });
await page.waitForTimeout(2000);
for (const b of await page.$$("button")) {
  if (((await b.textContent()) ?? "").includes("باز کردن همه")) { await b.click(); break; }
}
await page.waitForTimeout(1200);
await page.screenshot({ path: "/tmp/assets/tree-expanded.png", fullPage: true });
const rows = await page.$$eval(".asset-tree__row", (els) =>
  els.map((el) => `${el.style.marginInlineStart.padEnd(7)}${el.querySelector(".asset-tree__code")?.textContent}`));
console.log(rows.join("\n"));
await browser.close();
