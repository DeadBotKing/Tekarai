import { chromium } from "@playwright/test";
const BASE = "http://localhost:4173";
const PUMP = "13e7280f-f6ca-4860-b506-2719bbf85dc2";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.fill('input[autocomplete="organization"]', "platform");
await page.fill('input[autocomplete="username"]', "platform-admin");
await page.fill('input[autocomplete="current-password"]', "Tekarai-Demo-2026!");
await page.click('button[type="submit"]');
await page.waitForTimeout(3500);

async function openLocationTab() {
  await page.goto(`${BASE}/app/maintenance/devices/${PUMP}/profile`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  for (const tab of await page.$$(".registry-tabs button")) {
    if (((await tab.textContent()) ?? "").includes("محل")) { await tab.click(); break; }
  }
  await page.waitForTimeout(1500);
}
async function clickByText(text, scope = "button") {
  for (const b of await page.$$(scope)) {
    if (((await b.textContent()) ?? "").includes(text)) { await b.click(); return true; }
  }
  return false;
}

await openLocationTab();
console.log("buttons:", JSON.stringify(await page.$$eval(".card button", (bs) => bs.map((b) => b.textContent?.trim()))));

if (!(await clickByText("بازگشت به چرخهٔ کار"))) {} else { await page.waitForTimeout(2500); await openLocationTab(); }
await clickByText("خروج از رده");
await page.waitForTimeout(1200);
await page.screenshot({ path: "/tmp/assets/retire-modal.png" });
const modalInputs = await page.$$('.modal textarea, .modal input[type="text"], .modal input:not([type])');
if (modalInputs.length) await modalInputs[modalInputs.length - 1].fill("فرسودگی کامل بدنه");
for (const b of await page.$$(".modal button")) {
  if (((await b.textContent()) ?? "").includes("ثبت خروج")) { await b.click(); break; }
}
await page.waitForTimeout(3000);
await page.screenshot({ path: "/tmp/assets/after-retire.png", fullPage: true });
console.log("AFTER RETIRE badges:", JSON.stringify(await page.$$eval(".badge", (bs) => bs.map((b) => b.textContent?.trim()))));
console.log("AFTER RETIRE buttons:", JSON.stringify(await page.$$eval(".card button", (bs) => bs.map((b) => b.textContent?.trim()))));

// reinstate
console.log("clicked:", await clickByText("بازگشت به چرخهٔ کار"));
await page.waitForTimeout(3000);
console.log("AFTER REINSTATE buttons:", JSON.stringify(await page.$$eval(".card button", (bs) => bs.map((b) => b.textContent?.trim()))));
await page.screenshot({ path: "/tmp/assets/after-reinstate.png", fullPage: true });
await browser.close();
