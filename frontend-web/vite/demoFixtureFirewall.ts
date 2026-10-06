/**
 * Keeps demo fixtures out of builds that are not demo builds.
 *
 * Demo mode used to be a runtime flag only. Because every page imports its
 * fixtures statically, the fabricated records were linked into the bundle
 * whatever the flag said — roughly 45 KB of invented Persian equipment,
 * people and suppliers sitting in a production deployment, one `demoMode`
 * check away from being rendered as if it were the customer's data.
 *
 * A runtime check cannot fix that, because the data is already there. So this
 * plugin replaces each fixture module at build time with a stub that has the
 * same export names and no content. When demo mode is off, the fabricated
 * records do not exist in the output at all, and any code path that still
 * reaches for them gets emptiness or a thrown error instead of fiction.
 */

import { readFileSync } from "node:fs";
import type { Plugin } from "vite";

/** Modules that exist only to supply fake data. */
export const FIXTURE_MODULES = [
  "src/features/demo/demoData.ts",
  "src/features/demo/pageDemoFixtures.ts",
  "src/features/communication/chatDemoData.ts",
  "src/features/maintenance/maintenanceDemoData.ts",
  "src/features/maintenance/registryDemoData.ts",
  "src/features/maintenance/workCalendarDemoData.ts",
  "src/features/maintenance/performanceReviewDemoData.ts",
] as const;

export const isFixtureModule = (id: string): boolean => {
  const normalised = id.split("?")[0].replace(/\\/g, "/");
  return FIXTURE_MODULES.some((suffix) => normalised.endsWith(suffix));
};

type ExportKind = "array" | "object" | "callable" | "scalar";

export interface FixtureExport {
  name: string;
  kind: ExportKind;
}

/**
 * Reads the export names out of a fixture module and classifies each one by
 * the shape of its initialiser, so the stub can keep the module's contract.
 *
 * Shape matters: a consumer that was handed `demoDevices` will call `.map` on
 * it, and a stub that got the shape wrong would turn "no demo data" into a
 * white screen. An empty array renders an empty table, which is the honest
 * outcome.
 */
export const parseFixtureExports = (source: string): FixtureExport[] => {
  const exports: FixtureExport[] = [];
  const pattern =
    /^export\s+(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*(?::[^=]+)?=\s*(.)/gm;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    const [, name, firstChar] = match;
    const rest = source.slice(match.index + match[0].length - 1);
    let kind: ExportKind = "scalar";
    if (firstChar === "[") kind = "array";
    else if (firstChar === "{") kind = "object";
    else if (/^(\(|async\s|function\b)/.test(rest)) kind = "callable";
    exports.push({ name, kind });
  }
  for (const fnMatch of source.matchAll(
    /^export\s+(?:async\s+)?function\s+([A-Za-z0-9_$]+)/gm,
  )) {
    exports.push({ name: fnMatch[1], kind: "callable" });
  }
  return exports;
};

/**
 * A callable stub throws rather than returning an inert object. Reaching a
 * demo service factory in a non-demo build is a routing bug, and a loud
 * failure in testing beats a silent one in front of a customer.
 */
export const buildStubModule = (
  source: string,
  moduleLabel: string,
): string => {
  const parsed = parseFixtureExports(source);
  const header = [
    "// Replaced at build time by vite/demoFixtureFirewall.ts.",
    `// Original: ${moduleLabel}`,
    "// Demo mode is off for this build, so the fixtures are not linked in.",
    "",
    "const refuse = (name) => () => {",
    "  throw new Error(",
    `    \`\${name}() is demo-only and this build was made with demo mode off. \` +`,
    '    "Route this through the live service instead.",',
    "  );",
    "};",
    "",
  ].join("\n");

  const body = parsed.map(({ name, kind }) => {
    if (kind === "callable") return `export const ${name} = refuse("${name}");`;
    if (kind === "array") return `export const ${name} = [];`;
    if (kind === "object") return `export const ${name} = {};`;
    return `export const ${name} = undefined;`;
  });

  return `${header}${body.join("\n")}\n`;
};

export interface FirewallOptions {
  /** When true the real fixtures are left alone (development, demo builds). */
  allowFixtures: boolean;
}

export const demoFixtureFirewall = ({
  allowFixtures,
}: FirewallOptions): Plugin => ({
  name: "tekarai:demo-fixture-firewall",
  enforce: "pre",
  apply: "build",
  load(id) {
    if (allowFixtures || !isFixtureModule(id)) return null;
    const file = id.split("?")[0];
    const source = readFileSync(file, "utf-8");
    return buildStubModule(
      source,
      file.replace(/\\/g, "/").split("/src/")[1] ?? file,
    );
  },
});

/**
 * Mirrors the runtime rule in `src/app/configuration/runtimeConfig.ts`:
 * fixtures are allowed in a development build, and in a production build only
 * when demo mode is requested *and* explicitly permitted for production.
 */
export const fixturesAllowedFor = (
  mode: string,
  env: Record<string, string | undefined>,
): boolean => {
  const demoRequested = env.VITE_DEMO_MODE !== "false";
  if (mode !== "production") return demoRequested;
  return (
    env.VITE_DEMO_MODE === "true" &&
    env.VITE_ALLOW_DEMO_IN_PRODUCTION === "true"
  );
};
