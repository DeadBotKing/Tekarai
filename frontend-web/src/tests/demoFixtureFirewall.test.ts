/**
 * The build-time half of the boundary.
 *
 * Runtime checks cannot keep fixtures out of a bundle, because static imports
 * have already linked them in by the time any flag is read. The firewall
 * replaces those modules during the build; these specs pin the rule that
 * decides when it fires and the stub it produces.
 */

import { describe, expect, it } from "vitest";
import {
  FIXTURE_MODULES,
  buildStubModule,
  fixturesAllowedFor,
  isFixtureModule,
  parseFixtureExports,
} from "../../vite/demoFixtureFirewall";

describe("which modules are fixtures", () => {
  it("recognises every registered fixture module by absolute path", () => {
    for (const relative of FIXTURE_MODULES) {
      expect(isFixtureModule(`/repo/frontend-web/${relative}`)).toBe(true);
    }
  });

  it("tolerates a vite query suffix and windows separators", () => {
    expect(isFixtureModule("/a/src/features/demo/demoData.ts?v=123")).toBe(true);
    expect(isFixtureModule("C:\\a\\src\\features\\demo\\demoData.ts")).toBe(true);
  });

  it("leaves real source alone", () => {
    expect(isFixtureModule("/a/src/pages/SparePartsPage.tsx")).toBe(false);
    expect(isFixtureModule("/a/src/features/demo/demoGateway.ts")).toBe(false);
  });
});

describe("when fixtures are allowed into a build", () => {
  it("allows them in development by default", () => {
    expect(fixturesAllowedFor("development", {})).toBe(true);
  });

  it("refuses them in production even when demo mode is requested", () => {
    expect(
      fixturesAllowedFor("production", { VITE_DEMO_MODE: "true" }),
    ).toBe(false);
  });

  it("allows them in production only with the explicit second flag", () => {
    expect(
      fixturesAllowedFor("production", {
        VITE_DEMO_MODE: "true",
        VITE_ALLOW_DEMO_IN_PRODUCTION: "true",
      }),
    ).toBe(true);
  });

  it("refuses them in production when nothing is set at all", () => {
    expect(fixturesAllowedFor("production", {})).toBe(false);
  });

  it("honours an explicit opt-out in development", () => {
    expect(
      fixturesAllowedFor("development", { VITE_DEMO_MODE: "false" }),
    ).toBe(false);
  });
});

describe("the generated stub", () => {
  const source = [
    "export const demoDevices = [{ id: 1, name: 'گراندفوس' }];",
    "export const demoConfig = { tenant: 'demo' };",
    "export const createDemoService = () => ({ list: async () => [] });",
    "export const resetDemo = async () => undefined;",
    "export function registerDemoDevice(x) { return x; }",
    "export const DEMO_SELF_ID = 'u-1';",
    "const notExported = [1, 2, 3];",
  ].join("\n");

  it("classifies each export by the shape of its initialiser", () => {
    expect(parseFixtureExports(source)).toEqual([
      { name: "demoDevices", kind: "array" },
      { name: "demoConfig", kind: "object" },
      { name: "createDemoService", kind: "callable" },
      { name: "resetDemo", kind: "callable" },
      { name: "DEMO_SELF_ID", kind: "scalar" },
      { name: "registerDemoDevice", kind: "callable" },
    ]);
  });

  it("keeps every export name so importers still resolve", () => {
    const stub = buildStubModule(source, "demoData.ts");
    for (const name of [
      "demoDevices",
      "demoConfig",
      "createDemoService",
      "resetDemo",
      "registerDemoDevice",
      "DEMO_SELF_ID",
    ]) {
      expect(stub).toContain(`export const ${name} =`);
    }
  });

  it("carries none of the fabricated content", () => {
    expect(buildStubModule(source, "demoData.ts")).not.toContain("گراندفوس");
  });

  it("preserves the shape so a leaked consumer renders empty, not broken", () => {
    const stub = buildStubModule(source, "demoData.ts");
    expect(stub).toContain("export const demoDevices = [];");
    expect(stub).toContain("export const demoConfig = {};");
  });

  it("makes a demo service factory throw rather than return an empty husk", () => {
    // Reaching a demo factory in a non-demo build is a routing bug. Failing
    // loudly in staging beats an inexplicably blank page for a customer.
    expect(buildStubModule(source, "demoData.ts")).toContain(
      'export const createDemoService = refuse("createDemoService");',
    );
  });
});

describe("the real fixture modules survive the parser", () => {
  it("every registered module yields at least one export", async () => {
    const { readFileSync } = await import("node:fs");
    for (const relative of FIXTURE_MODULES) {
      const source = readFileSync(relative, "utf-8");
      expect(
        parseFixtureExports(source).length,
        `${relative} parsed to no exports — the stub would drop its importers`,
      ).toBeGreaterThan(0);
    }
  });
});
