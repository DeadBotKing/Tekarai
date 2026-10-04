import { chromium } from "@playwright/test";

const BASE = "http://localhost:4173";
const out = "/tmp/assets";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE ERROR:", m.text()); });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.fill('input[autocomplete="organization"]', "platform");
await page.fill('input[autocomplete="username"]', "platform-admin");
await page.fill('input[autocomplete="current-password"]', "Tekarai-Demo-2026!");
await page.click('button[type="submit"]');
await page.waitForTimeout(3500);

await page.goto(`${BASE}/app/maintenance/asset-tree`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${out}/tree-default.png`, fullPage: true });

const rows = await page.$$eval(".asset-tree__row", (els) =>
  els.map((el) => ({
    indent: el.style.marginInlineStart,
    code: el.querySelector(".asset-tree__code")?.textContent ?? "",
    name: el.querySelector(".asset-tree__name")?.textContent ?? "",
    badges: Array.from(el.querySelectorAll(".badge")).map((b) => b.textContent),
  })),
);
console.log("VISIBLE ROWS:", JSON.stringify(rows, null, 1));

const metrics = await page.$$eval(".metric-card", (els) =>
  els.map((el) => `${el.querySelector(".metric-card__label")?.textContent}=${el.querySelector(".metric-card__value")?.textContent}`),
);
console.log("METRICS:", JSON.stringify(metrics));

const dir = await page.evaluate(() => ({
  dir: document.documentElement.dir,
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
}));
console.log("FRAME:", JSON.stringify(dir));

await browser.close();
