import { chromium } from "@playwright/test";
const BASE = "http://localhost:4173";
const out = "/tmp/assets";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.fill('input[autocomplete="organization"]', "platform");
await page.fill('input[autocomplete="username"]', "platform-admin");
await page.fill('input[autocomplete="current-password"]', "Tekarai-Demo-2026!");
await page.click('button[type="submit"]');
await page.waitForTimeout(3500);

// find PRS-101 (the machine that owns a motor which owns a bearing)
const list = await page.evaluate(async () => {
  const token = JSON.parse(localStorage.getItem("tekarai.gui.session.v1") || "{}");
  const r = await fetch("/api/v1/maintenance/devices?pageSize=100", {
    headers: { Authorization: `Bearer ${token.accessToken}` },
  });
  const j = await r.json();
  return (j.data?.items ?? j.data ?? []).map((d) => ({ id: d.id, code: d.code }));
});
const press = { id: "9c534180-bba8-4f51-b456-9c2b6ffcc5a9", code: "PRS-101" };
console.log("target:", JSON.stringify(press));

await page.goto(`${BASE}/app/maintenance/devices/${press.id}/profile`, { waitUntil: "networkidle" });
await page.waitForTimeout(2000);
// open the «محل استقرار» tab
const tabs = await page.$$('.registry-tabs button');
for (const tab of tabs) {
  const label = (await tab.textContent()) ?? "";
  if (label.includes("محل")) { await tab.click(); break; }
}
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/profile-hierarchy.png`, fullPage: true });

const chain = await page.$$eval(".asset-chain__link", (els) => els.map((e) => e.textContent?.trim()));
console.log("UPSTREAM CHAIN:", JSON.stringify(chain));
const summary = await page.$$eval(".registry-summary-grid div", (els) =>
  els.map((e) => `${e.querySelector(".muted-cell")?.textContent}=${e.querySelector("strong")?.textContent}`));
console.log("SUMMARY:", JSON.stringify(summary, null, 1));

// record a transfer
const moveBtn = await page.$$('button');
for (const b of moveBtn) {
  if (((await b.textContent()) ?? "").includes("ثبت جابه‌جایی")) { await b.click(); break; }
}
await page.waitForTimeout(1200);
await page.screenshot({ path: `${out}/move-modal.png` });
const selects = await page.$$('.modal select');
if (selects.length) {
  const options = await selects[0].$$eval("option", (os) => os.map((o) => ({ v: o.value, l: o.textContent })));
  const target = options.find((o) => (o.l ?? "").includes("خط تولید ۲"));
  console.log("picking:", JSON.stringify(target));
  await selects[0].selectOption(target.v);
}
const inputs = await page.$$('.modal input[type="text"], .modal input:not([type])');
if (inputs.length >= 2) await inputs[inputs.length - 2].fill("بازچینش خط");
const submit = await page.$$('.modal button');
for (const b of submit) {
  if (((await b.textContent()) ?? "").includes("ثبت جابه‌جایی")) { await b.click(); break; }
}
await page.waitForTimeout(3000);
await page.screenshot({ path: `${out}/after-move.png`, fullPage: true });

const rows = await page.$$eval("table.data-table tr", (trs) =>
  trs.map((tr) => Array.from(tr.querySelectorAll("td")).map((td) => td.textContent?.trim())).filter((r) => r.length));
console.log("TABLE ROWS:", JSON.stringify(rows, null, 1));
const prev = await page.$$eval(".registry-summary-grid div", (els) =>
  els.map((e) => `${e.querySelector(".muted-cell")?.textContent}=${e.querySelector("strong")?.textContent}`));
console.log("SUMMARY AFTER:", JSON.stringify(prev, null, 1));
await browser.close();
