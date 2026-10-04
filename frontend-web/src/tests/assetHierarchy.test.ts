import { describe, expect, it } from "vitest";
import { collectIds, countDevices, filterTree } from "../features/maintenance/assetTree";
import {
  toAssetAncestry,
  toAssetMovement,
  toAssetTree,
} from "../features/maintenance/registryService";
import type { AssetTreeNode } from "../shared/types/domain";

const node = (
  id: string,
  nodeType: "location" | "device",
  code: string,
  children: AssetTreeNode[] = [],
  extra: Partial<AssetTreeNode> = {},
): AssetTreeNode => ({
  id,
  nodeType,
  code,
  name: code,
  kind: "",
  assetLevel: "",
  status: "",
  criticality: "",
  path: "",
  costCenterCode: "",
  costCenterName: "",
  installedOn: "",
  retiredOn: "",
  deviceCount: 0,
  children,
  ...extra,
});

// سایت ← خط تولید ← پرس ← الکتروموتور ← یاتاقان
const bearing = node("bearing", "device", "BRG-01");
const motor = node("motor", "device", "MTR-01", [bearing]);
const press = node("press", "device", "PRESS-01", [motor]);
const line = node("line", "location", "LINE-01", [press]);
const site = node("site", "location", "SITE-01", [line]);

describe("filterTree", () => {
  it("keeps a branch whose descendant matches", () => {
    // Searching for the bearing must not drop the line and press above it —
    // otherwise the hit becomes unreachable in the rendered tree.
    const result = filterTree([site], "BRG");
    expect(result).toHaveLength(1);
    expect(collectIds(result)).toEqual(["site", "line", "press", "motor", "bearing"]);
  });

  it("prunes branches with no match anywhere", () => {
    const spare = node("spare", "location", "YARD-01", [node("x", "device", "NOPE-01")]);
    const result = filterTree([site, spare], "BRG");
    expect(result.map((item) => item.id)).toEqual(["site"]);
  });

  it("keeps only the matching subtree, not its siblings", () => {
    const other = node("other", "device", "PUMP-09");
    const widened = node("line2", "location", "LINE-02", [other, press]);
    const result = filterTree([widened], "PRESS");
    expect(collectIds(result)).toEqual(["line2", "press", "motor", "bearing"]);
  });

  it("matches on the cost centre as well as code and name", () => {
    const costed = node("c", "device", "GEN-01", [], { costCenterCode: "CC-500" });
    expect(filterTree([costed], "cc-500")).toHaveLength(1);
  });

  it("returns the original forest for an empty or blank term", () => {
    expect(filterTree([site], "")).toHaveLength(1);
    expect(filterTree([site], "   ")).toHaveLength(1);
  });

  it("is case-insensitive", () => {
    expect(filterTree([site], "brg-01")).toHaveLength(1);
  });

  it("does not mutate the input", () => {
    filterTree([site], "BRG");
    expect(site.children[0].children).toHaveLength(1);
  });
});

describe("countDevices", () => {
  it("counts devices at any depth and ignores locations", () => {
    expect(countDevices(site)).toBe(3);
    expect(countDevices(line)).toBe(3);
    expect(countDevices(bearing)).toBe(0);
  });
});

describe("asset hierarchy mappers", () => {
  it("defaults every missing field instead of leaking undefined into the UI", () => {
    const tree = toAssetTree({});
    expect(tree.roots).toEqual([]);
    expect(tree.unplacedDevices).toEqual([]);
    expect(tree.counts).toEqual({ locations: 0, devices: 0, unplacedDevices: 0 });
  });

  it("maps a nested tree recursively", () => {
    const tree = toAssetTree({
      roots: [
        {
          id: "l1",
          nodeType: "location",
          code: "SITE-01",
          name: "سایت",
          kind: "site",
          deviceCount: 2,
          children: [{ id: "d1", nodeType: "device", code: "P-1", assetLevel: "mainEquipment" }],
        },
      ],
      counts: { locations: 1, devices: 1, unplacedDevices: 0 },
    });
    expect(tree.roots[0].deviceCount).toBe(2);
    expect(tree.roots[0].children[0].nodeType).toBe("device");
    expect(tree.roots[0].children[0].assetLevel).toBe("mainEquipment");
    expect(tree.roots[0].children[0].children).toEqual([]);
  });

  it("treats any unknown nodeType as a location", () => {
    const tree = toAssetTree({ roots: [{ id: "x", nodeType: "weird", code: "?" }] });
    expect(tree.roots[0].nodeType).toBe("location");
  });

  it("maps an ancestry payload including the previous location", () => {
    const ancestry = toAssetAncestry({
      device: { id: "d1", code: "PUMP-01", costCenterCode: "CC-100" },
      deviceChain: [{ id: "p1", code: "LINE-01", nodeType: "device" }],
      locationChain: [{ id: "l1", code: "SITE-01", nodeType: "location", kind: "site" }],
      children: [{ id: "c1", code: "BRG-01", assetLevel: "component" }],
      descendantCount: 4,
      previousLocation: { locationPath: "سایت / خط ۱", movedOn: "2026-03-05" },
    });
    expect(ancestry.device.costCenterCode).toBe("CC-100");
    expect(ancestry.deviceChain[0].code).toBe("LINE-01");
    expect(ancestry.locationChain[0].kind).toBe("site");
    expect(ancestry.children[0].assetLevel).toBe("component");
    expect(ancestry.descendantCount).toBe(4);
    expect(ancestry.previousLocation.locationPath).toBe("سایت / خط ۱");
  });

  it("survives an ancestry payload with nothing in it", () => {
    const ancestry = toAssetAncestry({});
    expect(ancestry.deviceChain).toEqual([]);
    expect(ancestry.locationChain).toEqual([]);
    expect(ancestry.previousLocation.locationPath).toBe("");
  });

  it("maps a movement row", () => {
    const movement = toAssetMovement({
      id: "m1",
      deviceId: "d1",
      fromLocationPath: "خط ۱",
      toLocationPath: "خط ۲",
      movedOn: "2026-04-05",
      reason: "بازچینش",
    });
    expect(movement.fromLocationPath).toBe("خط ۱");
    expect(movement.toLocationPath).toBe("خط ۲");
    expect(movement.movedOn).toBe("2026-04-05");
    expect(movement.performedBy).toBe("");
  });
});
