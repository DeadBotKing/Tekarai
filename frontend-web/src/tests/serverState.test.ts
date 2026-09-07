import { describe, expect, it } from "vitest";
import { TenantAwareCache } from "../core/api/serverState";

describe("tenant-aware server state cache", () => {
  it("expires entries and keeps tenant keys isolated", () => {
    let now = 1000;
    const cache = new TenantAwareCache(() => now);
    const tenantA = cache.key("tenant-a", "projects", "page=1");
    const tenantB = cache.key("tenant-b", "projects", "page=1");
    cache.set(tenantA, ["a"], 100);
    cache.set(tenantB, ["b"], 100);
    expect(cache.get(tenantA)).toEqual(["a"]);
    expect(cache.get(tenantB)).toEqual(["b"]);
    now += 101;
    expect(cache.get(tenantA)).toBeNull();
    expect(cache.get(tenantB)).toBeNull();
  });

  it("invalidates one resource family without clearing other families", () => {
    const cache = new TenantAwareCache();
    cache.set("tenant-a:projects:1", [1], 1000);
    cache.set("tenant-a:projects:2", [2], 1000);
    cache.set("tenant-a:tasks:1", [3], 1000);
    cache.invalidate("tenant-a:projects:");
    expect(cache.get("tenant-a:projects:1")).toBeNull();
    expect(cache.get("tenant-a:projects:2")).toBeNull();
    expect(cache.get("tenant-a:tasks:1")).toEqual([3]);
  });
});
