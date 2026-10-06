#!/usr/bin/env node
/**
 * Builds the app the way production builds it, then searches the output for
 * fabricated records.
 *
 * The unit tests check the firewall's rules; this checks the artefact that
 * actually ships. They are different claims, and only this one would have
 * caught the original defect: 45 KB of invented Persian equipment sitting in
 * a bundle that every `demoMode` check said was clean.
 *
 *   node scripts/verifyDemoBoundary.mjs
 *
 * Exits non-zero if any fixture string survives into dist/.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";

/** Strings that exist only inside the fixtures. */
const FABRICATED = [
  "گراندفوس",
  "رضا احمدی",
  "پمپ خنک‌کننده اصلی",
  "تأمین‌کننده نمونه",
  "راهبر نمایشی",
  "قطعه نمونه",
  "تسمه V118",
  "سیل مکانیکی 45mm",
  "مدیر سکو",
  "demo@tekarai.local",
];

/**
 * The CSV import template ships a sample row on purpose — it is a template,
 * not data presented as the tenant's own. Listed here so the exception is
 * deliberate and reviewable rather than an unexplained gap in the list above.
 */
const ALLOWED_SAMPLE_STRINGS = ["بلبرینگ 6204"];

const walk = (dir) =>
  readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });

const main = () => {
  console.log("→ building with VITE_DEMO_MODE=false");
  rmSync("dist", { recursive: true, force: true });
  execFileSync("npm", ["run", "build"], {
    stdio: "inherit",
    env: { ...process.env, VITE_DEMO_MODE: "false" },
  });

  const files = walk("dist").filter(
    (file) => file.endsWith(".js") || file.endsWith(".css") || file.endsWith(".html"),
  );

  const leaks = [];
  for (const file of files) {
    const content = readFileSync(file, "utf-8");
    for (const needle of FABRICATED) {
      if (content.includes(needle)) leaks.push(`${file}: ${needle}`);
    }
  }

  if (leaks.length > 0) {
    console.error("\n✗ fabricated records found in the production bundle:");
    for (const leak of leaks) console.error(`   ${leak}`);
    console.error(
      "\nMove the data into a module listed in vite/demoFixtureFirewall.ts,",
    );
    console.error("or delete the fallback and show an error state instead.");
    process.exit(1);
  }

  console.log(
    `\n✓ ${files.length} build artefacts contain no fabricated records`,
  );
  console.log(
    `  (deliberate exceptions: ${ALLOWED_SAMPLE_STRINGS.join(", ")} — CSV import template)`,
  );
};

main();
